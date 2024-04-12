"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""
import abc
from typing import Callable, List, Optional

import carb
import omni.client
import six
from pydantic import BaseModel, root_validator

from .core_detail_popup import AssetDetailCore


class ContentData(BaseModel):
    """
    Schema of options
    """

    title: str
    path: str
    image_path_fn: Optional[Callable[[], str]] = None  # function that return an image path
    # function that return an image path for the detail window
    image_primary_detail_fn: Optional[Callable[[], str]] = None
    checkpoint_version: Optional[int] = None
    original_path: Optional[str] = None  # dont set it

    @root_validator(allow_reuse=True)
    def inject_checkpoint_version(cls, values):  # noqa: N805
        if values["original_path"] is None:
            values["original_path"] = values["path"]
        if values["checkpoint_version"] is not None:
            values["path"] = f"{values['original_path']}?&{values['checkpoint_version']}"
        return values

    def is_checkpointed(self) -> bool:
        result, entry = omni.client.stat(self.original_path)
        if result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.IS_CHECKPOINTED:
            return True
        return False

    class Config:
        underscore_attrs_are_private = True
        validate_assignment = True


class ContentDataAdd(BaseModel):
    """
    Schema of options
    """

    title: Optional[str]
    path: Optional[str]


@six.add_metaclass(abc.ABCMeta)
class ContentViewerCore:
    class _Event(set):
        """
        A list of callable objects. Calling an instance of this will cause a
        call to each item in the list in ascending order by index.
        """

        def __call__(self, *args, **kwargs):
            """Called when the instance is “called” as a function"""
            # Call all the saved functions
            for f in self:
                f(*args, **kwargs)

        def __repr__(self):
            """
            Called by the repr() built-in function to compute the “official”
            string representation of an object.
            """
            return f"Event({set.__repr__(self)})"

    class _EventSubscription:
        """
        Event subscription.

        _Event has callback while this object exists.
        """

        def __init__(self, event, fn):
            """
            Save the function, the event, and add the function to the event.
            """
            self._fn = fn
            self._event = event
            event.add(self._fn)

        def __del__(self):
            """Called by GC."""
            self._event.remove(self._fn)

    def __init__(self):
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self.__ignore_thumbnails = False  # noqa PLW0238
        self.__selection_blocked = False

        self.__asset_detail_core = AssetDetailCore()  # noqa PLW0238

        self.__on_content_changed = self._Event()
        self.__on_error_get_data = self._Event()
        self.__on_selection_changed = self._Event()
        self.__on_primary_thumbnail_loaded = self._Event()

    @property
    def default_attr(self):
        return {"_content": [], "_selection": [], "_item_was_clicked": False}

    @abc.abstractmethod
    def _get_content_data(self) -> Optional[List[ContentData]]:
        """If None is returned, an error message is showed"""
        return []

    def _content_changed(self, maps: List[ContentData] = None):
        """Call the event object that has the list of functions"""
        self.__on_content_changed(maps)

    def subscribe_content_changed(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_content_changed, fn)

    def _error_get_data(self, message):
        """Call the event object that has the list of functions"""
        self.__on_error_get_data(message)

    def subscribe_error_get_data(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_error_get_data, fn)

    def _selection_changed(self):
        """Call the event object that has the list of functions"""
        self.__on_selection_changed(self._selection)

    def subscribe_selection_changed(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_selection_changed, fn)

    def primary_thumbnail_loaded(self, path, thumbnail_path):
        """Call the event object that has the list of functions"""
        self.__on_primary_thumbnail_loaded(path, thumbnail_path)

    def subscribe_primary_thumbnail_loaded(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_primary_thumbnail_loaded, fn)

    def set_selection(self, content_data: Optional[ContentData], append: bool = False, append_in_between: bool = False):
        """Set the selected content"""
        if content_data is None:
            self._selection = []
        else:
            if append:
                if self._selection and isinstance(self._selection[0], ContentDataAdd):
                    # we cant have a multi selection with a ContentDataAdd
                    return
                if content_data in self._selection:
                    self._selection.remove(content_data)
                else:
                    self._selection.append(content_data)
            elif append_in_between:
                if not self._selection:
                    self._selection = [content_data]
                else:
                    if self._selection and isinstance(self._selection[0], ContentDataAdd):
                        # we cant have a multi selection with a ContentDataAdd
                        return
                    idx_clicked = self._content.index(content_data)
                    ix_last_selected = self._content.index(self._selection[-1])
                    start_idx = ix_last_selected + 1 if idx_clicked - ix_last_selected > 0 else idx_clicked
                    end_idx = idx_clicked + 1 if idx_clicked - ix_last_selected > 0 else ix_last_selected
                    for content in self._content[start_idx:end_idx]:
                        if content not in self._selection:
                            self._selection.append(content)
            else:
                self._selection = [content_data]
        self._selection_changed()

    def get_selection(self) -> List[ContentData]:
        """Get the current selection"""
        return self._selection

    def set_item_was_clicked(self, value):
        self._item_was_clicked = value

    def was_item_clicked(self):
        return self._item_was_clicked

    def set_block_selection(self, value):
        self.__selection_blocked = value

    def is_selection_blocked(self):
        return self.__selection_blocked

    def refresh_content(self):
        """Refresh the list of content"""
        data = self._get_content_data()
        if data is None:
            message = "Error: can't get any data.\nDo you have access to your data (vpn? wrong server?)?"
            carb.log_error(message)
            self._error_get_data(message)
            return
        self._content = data
        self._content_changed(self._content)

    def get_current_content(self):
        return self._content

    def get_content_size(self):
        self.__ignore_thumbnails = True  # noqa PLW0238
        result = len(self._get_content_data())
        self.__ignore_thumbnails = False  # noqa PLW0238
        return result  # noqa R504

    def destroy(self):
        self.__ignore_thumbnails = False  # noqa PLW0238
        self.__selection_blocked = False
        for attr, value in self.default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()  # noqa PLE1102
                del m_attr  # noqa PLW4701
                setattr(self, attr, value)
        instance = super(ContentViewerCore, self)  # noqa PLR1725
        if instance:
            del instance

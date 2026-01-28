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
import functools
from typing import Callable, List, Optional, Type

import carb
import omni.client
import omni.usd
import six
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import async_wrap as _async_wrap
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.resources import get_icons as _get_icons
from pydantic import BaseModel, ConfigDict, model_validator

from .thumbnail_core import ThumbnailCore as _ThumbnailCore


class BaseContentData(BaseModel):
    title: str
    path: Optional[str]


class ContentData(BaseContentData):
    """
    Schema of options
    """

    path: str
    image_path_fn: Optional[Callable[[], str]] = None  # function that return an image path
    checkpoint_version: Optional[int] = None
    original_path: Optional[str] = None  # dont set it

    model_config = ConfigDict(validate_assignment=True)

    @model_validator(mode="after")
    @classmethod
    def inject_checkpoint_version(cls, instance_model):  # noqa: N805
        if instance_model.original_path is None:
            instance_model.original_path = instance_model.path
        if instance_model.checkpoint_version is not None:
            instance_model.path = f"{instance_model.original_path}?&{instance_model.checkpoint_version}"
        return instance_model

    def is_checkpointed(self) -> bool:
        result, entry = omni.client.stat(self.original_path)
        if result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.IS_CHECKPOINTED:
            return True
        return False

    def __hash__(self):
        return hash((self.title, self.path))


class ContentDataAdd(BaseContentData):
    """
    Schema of options
    """

    image_path_fn: Optional[Callable[[], str]] = functools.partial(_get_icons, "add")


@six.add_metaclass(abc.ABCMeta)
class ContentViewerCore:
    def __init__(self):
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._name = None
        self.__ignore_thumbnails = False
        self.__selection_blocked = False

        self.__thumbnail_core = _ThumbnailCore()

        self.__on_content_changed = _Event()
        self.__on_error_get_data = _Event()
        self.__on_selection_changed = _Event()
        self.__on_primary_thumbnail_loaded = _Event()

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of the core"""
        return ""

    @property
    def default_attr(self):
        """Attribute that will be set an destroyed"""
        return {"_content": [], "_selection": [], "_item_was_clicked": False}

    def _get_primary_thumbnail(self, path: str) -> str:
        """Get the primary thumbnail of the asset"""
        if self.__ignore_thumbnails:
            return ""
        return self.__thumbnail_core.get_primary_thumbnails(path)

    @abc.abstractmethod
    def _get_content_data(self) -> List[Type[BaseContentData]]:
        """If None is returned, an error message is showed"""
        return []

    @omni.usd.handle_exception
    async def __deferred_get_content_data(self, callback):  # noqa PLW0238
        wrapped_fn = _async_wrap(self._get_content_data)
        result = await wrapped_fn()
        callback(result)

    def __get_content_data(self, callback):
        """If None is returned, an error message is showed"""
        # asyncio.ensure_future(self.__deferred_get_content_data(callback))
        # TODO: bug with the omni.client and threading: CC-424
        result = self._get_content_data()
        result = sorted(result, key=lambda x: x.title)
        callback(result)

    def _content_changed(self, maps: List[Type[BaseContentData]] = None):
        """Call the event object that has the list of functions"""
        self.__on_content_changed(maps)

    def subscribe_content_changed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_content_changed, function)

    def _error_get_data(self, message):
        """Call the event object that has the list of functions"""
        self.__on_error_get_data(message)

    def subscribe_error_get_data(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_error_get_data, function)

    def _selection_changed(self):
        """Call the event object that has the list of functions"""
        self.__on_selection_changed(self._selection)

    def subscribe_selection_changed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_selection_changed, function)

    def primary_thumbnail_loaded(self, path, thumbnail_path):
        """Call the event object that has the list of functions"""
        self.__on_primary_thumbnail_loaded(path, thumbnail_path)

    def subscribe_primary_thumbnail_loaded(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_primary_thumbnail_loaded, function)

    def set_selection(
        self, content_data: Optional[BaseContentData], append: bool = False, append_in_between: bool = False
    ):
        """Set the selected content"""
        if content_data is None:
            self._selection = []
        elif append:
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

    def get_selection(self) -> List[Type[BaseContentData]]:
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

        def do_it(data):
            if data is None:
                message = "Error: can't get any data.\nDo you have access to your data (vpn? wrong server?)?"
                carb.log_error(message)
                self._error_get_data(message)
                return
            self._content = data
            self._content_changed(self._content)

        self.__get_content_data(do_it)

    def get_current_content(self):
        return self._content

    def destroy(self):
        self.__ignore_thumbnails = False
        self.__selection_blocked = False
        _reset_default_attrs(self)

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

import asyncio
from collections.abc import Callable

import omni.ext
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.search_core import AbstractSearchItem, AbstractSearchModel, SearchEngineRegistry
from omni.kit.widget.filebrowser.model import FileBrowserItem


class _SearchWidget:
    def __init__(self, callback: Callable[[str], None]):
        """
        Create a widget with an input field to be able to do search

        Args:
            callback: the function that will be called when the used input a character in the field
        """
        self._default_attr = {
            "_root_frame": None,
            "_search_image": None,
            "_search_clear_image": None,
            "_tags_frame": None,
            "_field": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._callback = callback

        self._create_ui()

    def _do_search(self, model):
        value = model.get_value_as_string()
        self._search_clear_image.visible = bool(value)
        self._search_image.selected = bool(value)

        if value == "":
            value = None
        self._callback(value)

    def get_current_text(self) -> str | None:
        """Get the current text in the input field"""
        value = self._field.model.get_value_as_string()
        if not value:
            return None
        return value

    def _do_clear(self):
        self._field.model.set_value("")
        self._field.focus_keyboard()

    def _create_ui(self):
        """Create the UI"""
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.ZStack(height=ui.Pixel(24)):
                with ui.Frame(separate_window=True):
                    with ui.ZStack():
                        ui.Rectangle(name="SearchBackground")
                        with ui.HStack(content_clipping=True):
                            ui.Spacer(width=ui.Pixel(4))
                            with ui.VStack(width=ui.Pixel(24)):
                                ui.Spacer(height=ui.Pixel(4))
                                self._search_image = ui.Image("", name="Search", width=ui.Pixel(24 - 8))
                                ui.Spacer(height=ui.Pixel(4))
                            with ui.ZStack():
                                ui.Spacer()
                                self._field = ui.StringField(name="SearchField")
                                self._tags_frame = ui.Frame()
                            self._search_clear_image = ui.Image(
                                "", name="SearchClear", width=ui.Pixel(24), visible=False
                            )
                            self._search_clear_image.set_mouse_released_fn(lambda x, y, b, m: self._do_clear())

        self._field.model.add_value_changed_fn(self._do_search)

    def destroy(self):
        _reset_default_attrs(self)


def create_search_widget(callback: Callable[[str], None]) -> _SearchWidget:
    """
    Create a widget with an input field to be able to do search

    Args:
        callback: the function that will be called when the used input a character in the field
    """
    return _SearchWidget(callback)


class SearchExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._subscription = SearchEngineRegistry().register_search_model("Search Widget", SearchModel)

    def on_shutdown(self):
        self._subscription = None


class SearchItem(AbstractSearchItem):
    def __init__(self, dir_path: str, file_entry: omni.client.ListEntry):
        super().__init__()
        self._dir_path = dir_path
        self._file_entry = file_entry

    @property
    def path(self) -> str:
        return f"{self._dir_path}/{self._file_entry.relative_path}"

    @property
    def name(self) -> str:
        return str(self._file_entry.relative_path)

    @property
    def date(self) -> str:
        # TODO BUG OM-123876: Adjust this to whatever return type is compatible with kit FileBrowserTreeViewDelegate
        return str(self._file_entry.modified_time)

    @property
    def size(self) -> str:
        return FileBrowserItem.size_as_string(self._file_entry.size)

    @property
    def is_folder(self) -> bool:
        return (self._file_entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN) > 0


class SearchModel(AbstractSearchModel):
    def __init__(
        self, search_text: str | None = None, current_dir: str | None = None, search_lifetime: str | None = None
    ):
        super().__init__()
        self._search_text = search_text
        self._current_dir = current_dir
        self._search_lifetime = search_lifetime

        self.__list_task = asyncio.ensure_future(self._list())
        self.__items = []

    def destroy(self):
        if not self.__list_task.done():
            self.__list_task.cancel()
        self._search_lifetime = None

    @property
    def items(self) -> list[SearchItem]:
        return self.__items

    @omni.usd.handle_exception
    async def _list(self):
        result, entries = await omni.client.list_async(self._current_dir)

        if result != omni.client.Result.OK:
            self.__items = []
        else:
            self.__items = [
                SearchItem(dir_path=self._current_dir, file_entry=entry)
                for entry in entries
                if all(word in entry.relative_path.lower() for word in self._search_text.lower().split(" "))
            ]

        self._item_changed()
        self._search_lifetime = None

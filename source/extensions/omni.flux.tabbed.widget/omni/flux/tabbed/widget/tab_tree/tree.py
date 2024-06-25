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

from typing import TYPE_CHECKING, Any, Callable, List, Tuple

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .model import HEADER_DICT as _HEADER_DICT

if TYPE_CHECKING:
    from .delegate import Delegate as _Delegate
    from .model import Item as _Item
    from .model import Model as _Model


class Tree(ui.Widget):
    def __init__(
        self,
        model: "_Model",
        delegate: "_Delegate",
        horizontal: bool = True,
        root_frame_name: str = None,
        selection_changed_fn: Callable[[List["_Item"]], Any] = None,
        size_tab_label: Tuple[ui.Length, ui.Length] = None,
    ):
        super().__init__()

        self._default_attr = {
            "_model": None,
            "_delegate": None,
            "_horizontal": None,
            "_sub_item_changed": None,
            "root_frame_name": None,
            "_selection_changed_fn": None,
            "_sub_item_mouse_released": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._size_tab_label = size_tab_label
        self._selection = []
        self._selection_changed_fn = selection_changed_fn
        self._model = model
        self._delegate = delegate
        self._horizontal = horizontal
        self.__root_frame = ui.Frame(name=root_frame_name or "")
        self.__refresh()

        self._sub_item_changed = self._model.subscribe_item_changed_fn(self._on_item_changed)
        self._sub_item_mouse_released = self._model.subscribe_item_mouse_released(self._on_item_released)

    def set_toggled_value(self, items: List["_Item"], value: bool):
        """
        Set the gradient visible (toggle on/off)

        Args:
            items: the item to toggle
            value: toggle or not
        """
        self._delegate.set_toggled_value(items, value)

    @property
    def selection(self):
        return self._selection

    @selection.setter
    def selection(self, value: List["_Item"]):
        self._selection = value
        for item in value:
            self._delegate.on_item_mouse_released(item)

    def _on_item_released(self, item: "_Item"):
        for _item in self._model.get_item_children(None):
            _item.selected = _item == item
        self._selection = [item]
        # refresh delegate
        self._selection_changed_fn([item])

    def _on_item_changed(self, model, item):
        self.__refresh()

    @property
    def root_frame(self):
        return self.__root_frame

    def __refresh(self):
        self.__root_frame.clear()
        with self.__root_frame:
            if self._horizontal:
                stack = ui.HStack()
            else:
                stack = ui.VStack()
            with stack:
                for item in self._model.get_item_children(None):
                    for column, _title in _HEADER_DICT.items():
                        frame = ui.Frame()
                        if self._size_tab_label:
                            frame.height = self._size_tab_label[1]
                            frame.width = self._size_tab_label[0]
                        with frame:
                            self._delegate.build_widget(self._model, item, column, 0, False)

    def destroy(self):
        _reset_default_attrs(self)
        super().destroy()

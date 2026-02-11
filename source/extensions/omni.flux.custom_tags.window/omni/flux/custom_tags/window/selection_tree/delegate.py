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

from functools import partial
from collections.abc import Callable

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.hover import hover_helper as _hover_helper
from pxr import Sdf

from .items import TagsEditItem as _TagsEditItem
from .items import TagsSelectionItem as _TagsSelectionItem


class TagsSelectionDelegate(ui.AbstractItemDelegate):
    ROW_HEIGHT = 24
    ICON_SIZE = 20

    def __init__(self):
        super().__init__()

        self._default_attr = {
            "_edit_field": None,
            "_value_changed_sub": None,
            "_end_edit_sub": None,
            "_is_edit_valid": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._edit_field = None

        self._value_changed_sub = None
        self._end_edit_sub = None

        self._is_edit_valid = False

        self.__on_item_edited = _Event()
        self.__on_item_double_clicked = _Event()

    def build_widget(self, model, item, column_id, level, expanded):
        """
        Create one widget per item
        """
        if item is None:
            return
        if column_id == 0:
            if isinstance(item, _TagsSelectionItem):
                stack = ui.HStack(
                    height=ui.Pixel(self.ROW_HEIGHT),
                    spacing=ui.Pixel(8),
                    mouse_double_clicked_fn=partial(self._on_item_double_clicked, item),
                )
                with stack:
                    with ui.VStack(width=0):
                        ui.Spacer(width=0)
                        ui.Image("", name="Drag", width=ui.Pixel(self.ICON_SIZE), height=ui.Pixel(self.ICON_SIZE))
                        ui.Spacer(width=0)

                    ui.Label(item.title, identifier="tag")
                _hover_helper(stack)
            elif isinstance(item, _TagsEditItem):
                with ui.HStack(height=ui.Pixel(self.ROW_HEIGHT)):
                    ui.Spacer(width=ui.Pixel(self.ICON_SIZE))
                    with ui.VStack():
                        ui.Spacer()
                        self._edit_field = ui.StringField(height=ui.Pixel(self.ICON_SIZE), identifier="edit_tag")
                        ui.Spacer()

                    self._edit_field.model.set_value(item.value)
                    self._value_changed_sub = self._edit_field.model.subscribe_value_changed_fn(
                        self._on_item_value_changed
                    )
                    self._end_edit_sub = self._edit_field.model.subscribe_end_edit_fn(
                        partial(self._on_item_edited, item)
                    )

                    self._edit_field.focus_keyboard()

    def _on_item_value_changed(self, model: ui.AbstractValueModel):
        """
        Validate the string field value whenever its value changes

        Args:
            model: The value model of the string field
        """
        self._is_edit_valid = bool(Sdf.Path.IsValidPathString(model.get_value_as_string()))

        self._edit_field.style_type_name_override = "Field" if self._is_edit_valid else "FieldError"
        self._edit_field.tooltip = (
            ""
            if self._is_edit_valid
            else "The tag name is not valid. The name can only contain letters, numbers, dashes and underscores."
        )

    def _on_item_edited(self, item: _TagsEditItem, model: ui.AbstractValueModel):
        """
        Trigger the `on_item_edited` event whenever the string field item ends its edits

        Args:
            item: The tree item that was edited
            model: The value model of the string field
        """
        self.__on_item_edited(item, model.get_value_as_string() if self._is_edit_valid else item.value)

    def _on_item_double_clicked(self, item: _TagsSelectionItem, x: float, y: float, b: int, m: int):
        """
        Trigger the `item_double_clicked` event whenever a tree item is double-clicked

        Args:
            item: The item that was double-clicked
            x: The clicked location's x component
            y: The clicked location's y component
            b: The button used to double-click
            m: Modified used while clicking
        """
        if b != 0 or not isinstance(item, _TagsSelectionItem):
            return
        self.__on_item_double_clicked(item)

    def subscribe_item_edited(self, callback: Callable[[_TagsEditItem, str], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_edited, callback)

    def subscribe_item_double_clicked(self, callback: Callable[[_TagsSelectionItem], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_double_clicked, callback)

    def destroy(self):
        _reset_default_attrs(self)

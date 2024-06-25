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

__all__ = (
    "Delegate",
    "FieldBuilder",
    "FieldBuilderList",
)

import abc
import asyncio
import dataclasses
from typing import Callable, Iterable, List, Optional

import carb
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.delegates.default import DefaultField
from omni.flux.property_widget_builder.delegates.string_value.default_label import NameField
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from . import clipboard
from .model import HEADER_DICT, Item, Model


@dataclasses.dataclass
class FieldBuilder:
    """
    A FieldBuilder simply connects a method used to "claim" the widget building of an item and a callable responsible
    for creating the widgets.
    """

    claim_func: Callable[[Item], bool]
    build_func: Callable[[Item], ui.Widget | list[ui.Widget] | None]


class FieldBuilderList(list[FieldBuilder]):
    """
    A simple list of FieldBuilder with some helper methods to assist in constructing FieldBuilder instances.
    """

    def register_build(self, claim_func: Callable[[Item], bool]):
        """
        Decorator for simplifying the construction of a FieldBuilder wrapping a build method with a claim callable.
        """

        def _deco(
            build_func: Callable[[Item], ui.Widget | list[ui.Widget] | None]
        ) -> Callable[[Item], ui.Widget | list[ui.Widget] | None]:
            self.append(FieldBuilder(claim_func=claim_func, build_func=build_func))
            return build_func

        return _deco


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the tree"""

    DEFAULT_IMAGE_ICON_SIZE = 24

    def __init__(self, field_builders: list[FieldBuilder] | None = None):
        super().__init__()

        self.field_builders = field_builders or []
        for field_builder in reversed(self._get_default_field_builders()):
            self.field_builders.insert(0, field_builder)

        self._name_widgets = {}
        self._subscriptions: list[carb.Subscription] = []

        # Keeps track of the selected items.
        self._selected_items: list[Item] = []

        # This is populated during a right click event within `_show_menu`. We store this Menu instance to avoid it
        # being garbage collected while it's displayed.
        self._context_menu: ui.Menu | None = None

        self.__on_item_expanded = _Event()
        self.__on_item_clicked = _Event()

    @property
    def default_attrs(self):
        return {
            "field_builders": None,
            "_name_widgets": None,
            "_subscriptions": None,
            "_selected_items": None,
            "_context_menu": None,
        }

    def reset(self):
        """
        Resets any state stored on the delegate.

        This method is called when the parent widget is hidden.
        """
        self._name_widgets.clear()
        self._subscriptions.clear()
        self._selected_items.clear()
        self._context_menu = None

    def selected_items_changed(self, items: Iterable[Item]):
        """
        Callback intended to be connected to the view's selection changed event.

        This needs to be connected manually when configuring the delegate and the view.
        """
        self._selected_items = list(items)

    def get_selected_items(self) -> list[Item]:
        return self._selected_items

    def _show_context_menu(self, model: Model, item: Item):
        """
        Display a context menu if the item was right-clicked for extra actions.
        """
        selected_items = [x for x in self.get_selected_items() if not x.read_only]
        all_items = model.get_all_items()

        # Early out optimization. No need to show a menu that can't actually do anything.
        if not selected_items and not all_items:
            return

        # NOTE: The context menu is stored on the object like this to avoid it being garbage collected and
        # prematurely destroyed.
        if self._context_menu is not None:
            self._context_menu.destroy()
        self._context_menu = ui.Menu("Context Menu")

        with self._context_menu:
            ui.MenuItem(
                "Copy All",
                identifier="copy_all",
                enabled=bool(all_items),
                triggered_fn=lambda: clipboard.copy(all_items),
            )
            ui.MenuItem(
                "Copy Selected",
                identifier="copy_selected",
                enabled=bool(selected_items),
                triggered_fn=lambda: clipboard.copy(selected_items),
            )
            ui.Separator(
                delegate=ui.MenuDelegate(
                    on_build_item=lambda _: ui.Line(
                        height=0, alignment=ui.Alignment.V_CENTER, style_type_name_override="Menu.Separator"
                    )
                )
            )
            ui.MenuItem(
                "Paste All",
                identifier="paste_all",
                enabled=any(clipboard.iter_clipboard_changes(all_items)),
                triggered_fn=lambda: clipboard.paste(all_items),
            )
            ui.MenuItem(
                "Paste Selected",
                identifier="paste_selected",
                enabled=any(clipboard.iter_clipboard_changes(selected_items)),
                triggered_fn=lambda: clipboard.paste(selected_items),
            )

        self._context_menu.show()

    def _item_clicked(self, button: int, model: Model, item: Item):
        """
        Callback ran whenever an item is clicked on.
        """
        # First emit the event which allows the parent tree to potentially modify the selection.
        self.__on_item_clicked(button, model, item)
        if button == 1:
            self._show_context_menu(model, item)

    def _build_regular_branch(self, _model, item, _column_id, _level, expanded):
        # Draw the +/- icon
        style_type_name_override = "TreeView.Item.Minus" if expanded else "TreeView.Item.Plus"
        with ui.VStack(
            width=ui.Pixel(16),
            mouse_released_fn=lambda x, y, b, m: self._item_expanded(b, item, not expanded),
        ):
            ui.Spacer(width=0)
            ui.Image(
                "", width=10, height=10, style_type_name_override=style_type_name_override, identifier="property_branch"
            )
            ui.Spacer(width=0)

    def build_branch(self, model: Model, item: Item, column_id: int, level: int, expanded: bool):
        """Create a branch widget that opens or closes subtree"""
        if column_id == 0:
            with ui.HStack(width=16 * (level + 2), height=self.DEFAULT_IMAGE_ICON_SIZE):
                if model.can_item_have_children(item):
                    self._build_regular_branch(model, item, column_id, level, expanded)
                else:
                    ui.Spacer(width=ui.Pixel(16))

    def _get_default_field_builders(self) -> list[FieldBuilder]:
        """
        Get default FieldBuilder used to build item widget(s).

        This can be subclassed to add specific builders based on the delegate.
        """
        return [
            FieldBuilder(
                claim_func=lambda _: True,
                build_func=DefaultField(ui.StringField),
            ),
        ]

    def get_widget_builder(
        self, item, default: Callable[[Item], ui.Widget | list[ui.Widget] | None] = None
    ) -> Callable[[Item], ui.Widget | list[ui.Widget] | None]:
        """
        Get a callable that will build widget(s) for the provided `item`.
        """
        for field_builder in reversed(self.field_builders):
            if field_builder.claim_func(item):
                return field_builder.build_func
        if default is None:
            raise ValueError(f"No custom field builder found for {item}")
        return default

    @abc.abstractmethod
    def _build_widget(
        self, model: Model, item: Item, column_id: int = 0, level: int = 0, expanded: bool = False
    ) -> Optional[List[ui.Widget]]:
        if column_id == 0:
            builder = NameField()
            return builder(item)
        if column_id == 1:
            builder = self.get_widget_builder(item, default=DefaultField(ui.StringField))
            return builder(item)
        return None

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return

        if column_id == 0:
            with ui.Frame(mouse_pressed_fn=lambda x, y, b, m: self._item_clicked(b, model, item)):
                widgets = self._build_widget(model, item, column_id, level, expanded)
        else:
            widgets = self._build_widget(model, item, column_id, level, expanded)

        if not widgets:
            return

        if not isinstance(widgets, list):
            widgets = [widgets]

        if column_id == 0:
            self._name_widgets[id(item)] = widgets
            return
        if id(item) in self._name_widgets:
            # if the value has a bigger height we need to resize the height of the name stack to have the same size
            asyncio.ensure_future(self.__resize_name_height(widgets, item))

        self.set_model_edit_fn(widgets, item)

    @omni.usd.handle_exception
    async def __resize_name_height(self, widgets, item):
        # wait 1 frame to have the widget to appear
        await omni.kit.app.get_app().next_update_async()
        stacks = self._name_widgets.get(id(item), [])
        max_height = 0
        for widget in widgets:
            value = widget.computed_height
            if value > max_height:
                max_height = value
        for stack in stacks:
            stack.height = ui.Pixel(max_height)
        # cleanup
        if stacks:
            del self._name_widgets[id(item)]

    def set_model_edit_fn(self, widgets: ui.Widget, item):
        """
        Set the callback when the value of the item is edited

        Args:
            widgets: the widget that show the item
            item: the item
        """
        for value_model in item.value_models:
            self._subscriptions.append(value_model.subscribe_end_edit_fn(lambda m: self.value_model_updated(item)))
            for widget in widgets:
                value_model.add_begin_edit_fn(lambda m, w=widget: self._set_selected_style(w, True))
                value_model.add_end_edit_fn(lambda m, w=widget: self._set_selected_style(w, False))

    def _set_selected_style(self, widget: ui.Widget, value: bool):
        """
        Set the style name override of the widget when the widget is edited

        Args:
            widget: the widget that is edited (or not)
            value: edited or not
        """
        suffix = "Selected"
        if value:
            widget.style_type_name_override = f"{widget.style_type_name_override}{suffix}"
        elif widget.style_type_name_override.endswith(suffix):
            widget.style_type_name_override = widget.style_type_name_override[: -len(suffix)]

    def value_model_updated(self, item):
        """
        Callback ran whenever an item's value model updates.
        """
        pass

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def _item_expanded(self, button, item, expanded):
        """Call the event object that has the list of functions"""
        if button != 0:
            return
        self.__on_item_expanded(item, expanded)

    def subscribe_item_expanded(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_expanded, function)

    def subscribe_item_clicked(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_clicked, function)

    def destroy(self):
        _reset_default_attrs(self)

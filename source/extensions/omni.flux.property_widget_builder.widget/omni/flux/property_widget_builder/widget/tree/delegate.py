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
from typing import TYPE_CHECKING, Callable

import carb
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.delegates import NameField
from omni.flux.property_widget_builder.delegates.default import DefaultField
from omni.flux.utils.widget.tree_widget import TreeDelegateBase as _TreeDelegateBase

from . import clipboard
from .model import HEADER_DICT, Item, Model

if TYPE_CHECKING:
    from .item_model import ItemModelBase


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


class Delegate(_TreeDelegateBase):
    """Delegate of the tree"""

    def __init__(self, field_builders: list[FieldBuilder] | None = None):
        super().__init__()

        self.field_builders = field_builders or []
        for field_builder in reversed(self._get_default_field_builders()):
            self.field_builders.insert(0, field_builder)

        self._name_widgets = {}
        self._subscriptions: list[carb.Subscription] = []

        # This is populated during a right click event within `_show_menu`. We store this Menu instance to avoid it
        # being garbage collected while it's displayed.
        self._context_menu: ui.Menu | None = None

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "field_builders": None,
                "_name_widgets": None,
                "_subscriptions": None,
                "_context_menu": None,
            }
        )
        return default_attr

    def reset(self):
        """
        Resets any state stored on the delegate.

        This method is called when the parent widget is hidden.
        """
        self._name_widgets.clear()
        self._subscriptions.clear()
        self._selection.clear()
        self._context_menu = None

    def value_model_updated(self, item):
        """
        Callback ran whenever an item's value model updates.
        """
        pass

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
    def _build_item_widgets(
        self, model: Model, item: Item, column_id: int, level: int, expanded: bool
    ) -> list[ui.Widget] | None:
        if column_id == 0:
            builder = NameField()
        elif column_id == 1:
            builder = self.get_widget_builder(item, default=DefaultField(ui.StringField))
        else:
            return None
        widgets = builder(item)
        return widgets

    def _build_widget(self, model: Model, item: Item, column_id, level, expanded):
        widgets = self._build_item_widgets(model, item, column_id, level, expanded)

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
        self.set_model_value_changed_fn(widgets, item)

    def _build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def set_model_edit_fn(self, widgets: list[ui.Widget], item):
        """
        Set the callbacks when the item is being edited.

        Args:
            widgets: the list of widgets that show the item
            item: the item
        """
        for value_model in item.value_models:
            for widget in widgets:
                value_model.add_begin_edit_fn(lambda m, w=widget: self._set_selected_style(w, True))
                value_model.add_end_edit_fn(lambda m, w=widget: self._set_selected_style(w, False))

    def set_model_value_changed_fn(self, widgets: list[ui.Widget], item):
        """
        Set the callbacks when the value of the item changes.

        Args:
            widgets: the list of widgets that show the item
            item: the item
        """
        for value_model in item.value_models:
            # subscribe the delegate to each items value change
            self._subscriptions.append(value_model.subscribe_value_changed_fn(lambda m: self.value_model_updated(item)))

            for widget in widgets:
                self._subscriptions.append(
                    value_model.subscribe_value_changed_fn(
                        lambda m, item_value_model=value_model, w=widget: self._set_mixed_style(item_value_model, w)
                    )
                )
                self._set_mixed_style(value_model, widget)

    @staticmethod
    def _set_style_state(widget: ui.Widget, selected: bool | None = None, mixed: bool | None = None):
        """
        Set the correct style override name for the current state.

        Args:
            widget: the value widget
            selected: whether to change the styling to "selected" state. None value will stay same.
            mixed: whether to change the styling to "mixed" state. None value will stay same.
        """
        style_override = widget.style_type_name_override

        def check_and_strip_existing(style_override_, suffix_, arg_):
            if style_override_.endswith(suffix_):
                if arg_ is None:
                    arg_ = True
                style_override_ = style_override_[: -len(suffix_)]
            return style_override_, arg_

        selected_suffix = "Selected"
        mixed_suffix = "Mixed"
        # "Mixed" will always be second, i.e. DelegateSelectedMixed
        style_override, mixed = check_and_strip_existing(style_override, mixed_suffix, mixed)
        style_override, selected = check_and_strip_existing(style_override, selected_suffix, selected)
        if selected:
            style_override = f"{style_override}{selected_suffix}"
        if mixed:
            style_override = f"{style_override}{mixed_suffix}"
        if widget.style_type_name_override != style_override:
            widget.style_type_name_override = style_override

    def _set_selected_style(self, widget: ui.Widget, value: bool):
        """
        Set the style name override of the widget when the widget is edited

        Args:
            widget: the widget that is edited (or not)
            value: edited or not
        """
        self._set_style_state(widget, selected=value)

    def _set_mixed_style(self, item_value_model: "ItemModelBase", widget: ui.Widget):
        """
        Set the style name override of the widget when the widget represents

        Args:
            widget: the widget that is edited (or not)
            value: edited or not
        """
        self._set_style_state(widget, mixed=item_value_model.is_mixed)

    def _show_context_menu(self, model: Model, item: Item):
        """
        Display a context menu if the item was right-clicked for extra actions.
        """
        selected_items = [x for x in self.selection if not x.read_only]
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
        super()._show_context_menu(model, item)

    @omni.usd.handle_exception
    async def __resize_name_height(self, widgets, item):
        # wait 1 frame to have the widget to appear
        await omni.kit.app.get_app().next_update_async()

        if not self._name_widgets:
            return

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

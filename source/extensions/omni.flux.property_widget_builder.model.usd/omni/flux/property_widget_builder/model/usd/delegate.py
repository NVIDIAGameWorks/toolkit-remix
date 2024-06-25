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

__all__ = ("USDDelegate",)

import dataclasses
import functools
from typing import TYPE_CHECKING, Any, Iterable, Optional

import omni.kit.undo
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.delegates.default import CreatorField
from omni.flux.property_widget_builder.delegates.string_value.default_label import NameField
from omni.flux.property_widget_builder.widget import Delegate as _Delegate
from omni.flux.property_widget_builder.widget import FieldBuilder
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.usd.layers import LayerUtils as _LayerUtils
from pxr import Usd

from .field_builders import ALL_FIELD_BUILDERS
from .items import USDAttributeItemStub as _USDAttributeItemStub

if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item as _Item

    from .model import USDModel as _USDModel


@dataclasses.dataclass
class Row:
    """
    Holds state and widgets for an item.
    """

    name: str
    selected: bool = False

    background_widgets: list[ui.Rectangle] = dataclasses.field(default_factory=list)
    default_indicator_widget: Optional[ui.Circle] = None
    more_widget: Optional[ui.HStack] = None
    attribute_widgets: list[ui.Widget] = dataclasses.field(default_factory=list)


class USDDelegate(_Delegate):
    """Delegate of the tree"""

    def __init__(self, field_builders: list[FieldBuilder] | None = None):
        super().__init__(field_builders=field_builders)
        self._context_menu_widgets: dict[int, ui.Menu] = {}
        self._rows: dict[int, Row] = {}

    def reset(self):
        """
        Reset any stored state.
        """
        super().reset()
        self._context_menu_widgets.clear()
        self._rows.clear()

    @property
    def default_attrs(self) -> dict[str, Any]:
        default_attrs = super().default_attrs
        default_attrs.update(
            {
                "_context_menu_widgets": None,
                "_rows": None,
            }
        )
        return default_attrs

    def build_branch(self, model: "_USDModel", item: "_Item", column_id: int, level: int, expanded: bool) -> None:
        """Create a branch widget that opens or closes subtree"""
        if column_id != 0:
            return

        row = self._rows.get(id(item))
        if row is None:
            row = Row("".join(x.get_value_as_string() for x in item.name_models))
        self._rows[id(item)] = row

        has_override = any(v.is_overriden for v in item.value_models)
        is_default = all(v.is_default for v in item.value_models)

        with ui.ZStack(mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, id(item))):
            with ui.VStack():
                ui.Spacer()
                row.background_widgets.append(
                    ui.Rectangle(
                        name="OverrideBackground",
                        height=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE + 2),
                        visible=has_override,
                    )
                )
                ui.Spacer()
            with ui.HStack(width=16 * (level + 2), height=self.DEFAULT_IMAGE_ICON_SIZE):
                if model.can_item_have_children(item):
                    self._build_regular_branch(model, item, column_id, level, expanded)
                else:
                    # Z Stack is used to reserve the space
                    with ui.ZStack(width=ui.Pixel((self.DEFAULT_IMAGE_ICON_SIZE / 2) + 8)):
                        row.default_indicator_widget = ui.Circle(
                            style_type_name_override="OverrideIndicator",
                            tooltip="Reset the attribute to the default USD value",
                            width=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE / 2),
                            visible=not is_default,
                            mouse_released_fn=lambda x, y, b, m: self._on_reset_item(b, item),
                        )

    def value_model_updated(self, item):
        """
        Callback ran whenever an item's value model updates.
        """
        row = self._rows.get(id(item))
        if row:
            has_override = any(v.is_overriden for v in item.value_models)
            is_default = all(v.is_default for v in item.value_models)
            for bg_widget in row.background_widgets:
                bg_widget.visible = has_override
            if row.default_indicator_widget is not None:
                row.default_indicator_widget.visible = not is_default
            if row.more_widget is not None:
                row.more_widget.visible = has_override

    def _delete_overrides(self, item, layer=None):
        """
        Delete overrides on an item.
        """
        if layer is None:
            item.delete_all_overrides()
        else:
            item.delete_layer_override(layer)
        self.value_model_updated(item)

    def _get_default_field_builders(self) -> list[FieldBuilder]:
        return ALL_FIELD_BUILDERS

    def _build_widget(
        self, model: "_USDModel", item: "_Item", column_id: int, level: int, expanded: bool
    ) -> Optional[list[ui.Widget]]:
        """Create a widget per item"""
        if item is None:
            return None

        widgets = None
        has_override = any(v.is_overriden for v in item.value_models)

        row = self._rows.get(id(item))
        if row is None:
            row = Row("".join(x.get_value_as_string() for x in item.name_models))
            self._rows[id(item)] = row

        if isinstance(item, _USDAttributeItemStub):
            if column_id == 0:
                stack = ui.VStack()
                with stack:
                    with ui.Frame():
                        with ui.HStack():
                            with ui.VStack(height=ui.Pixel(24)):
                                ui.Spacer(height=ui.Pixel(4))
                                with ui.HStack(height=ui.Pixel(16)):
                                    ui.Spacer()
                                    ui.Label(
                                        f"{item.name}",
                                        width=0,
                                        name="PropertiesWidgetLabel",
                                    )
                                    ui.Spacer(width=ui.Pixel(8))
                                ui.Spacer(height=ui.Pixel(4))
                    ui.Spacer(width=0)
                widgets = [stack]
            elif column_id == 1:
                builder = CreatorField(text=f"Create {item.name}", clicked_callback=item.create_attributes)
                widgets = builder(item)
        else:
            with ui.ZStack(
                mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, id(item)),
            ):
                with ui.VStack():
                    ui.Spacer()
                    row.background_widgets.append(
                        ui.Rectangle(
                            name="OverrideBackground",
                            height=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE + 2),
                            visible=has_override,
                        )
                    )
                    ui.Spacer()
                with ui.HStack():
                    if column_id == 0:
                        row.more_widget = ui.HStack(width=ui.Pixel(16), visible=has_override)
                        with row.more_widget:
                            ui.Image(
                                "",
                                name="More",
                                tooltip="View attribute overrides",
                                mouse_released_fn=functools.partial(self._show_override_menu, model, item),
                                width=ui.Pixel(16),
                            )
                            ui.Spacer(width=ui.Pixel(8))
                        widgets = NameField()(item)
                    if column_id == 1 and item.value_models:
                        # NOTE: the _fallback_builder registered below makes it so that this method never fails to
                        # return a builder. No need to provide a default.
                        builder = self.get_widget_builder(item)
                        widgets = builder(item)

        if widgets:
            row.attribute_widgets.extend(widgets)

        return widgets

    def selected_items_changed(self, items: Iterable["_Item"]):
        super().selected_items_changed(items)

        # Reset the selected item look
        for item_id, row in self._rows.items():
            if row.selected:
                row.selected = False
                self._on_item_hovered(False, item_id, True)

        for item in self.get_selected_items():
            item_id = id(item)
            row = self._rows.get(item_id)
            if row is not None:
                row.selected = True
                self._on_item_hovered(True, item_id)

    def _on_item_hovered(self, hovered, item_id, force=False):
        row = self._rows.get(item_id)
        if row is not None:
            for background_widget in row.background_widgets:
                if not force and row.selected:
                    style_name = "OverrideBackgroundSelected"
                else:
                    style_name = "OverrideBackgroundHovered" if hovered else "OverrideBackground"
                background_widget.style_type_name_override = style_name

    def _on_reset_item(self, button, item):
        if button != 0:
            return
        with omni.kit.undo.group():
            for value_model in item.value_models:
                value_model.reset_default_value()

    def _show_override_menu(self, model, item, x, y, button, *_):
        if button != 0:
            return
        self._context_menu_widgets[id(item)] = ui.Menu("Context menu", direction=ui.Direction.LEFT_TO_RIGHT)
        with self._context_menu_widgets[id(item)]:
            # Ensure there are no repeated entries in the menu
            property_stack = set()
            sub_layers = set()
            # Find all the stack items and sub-layers
            for value_model in item.value_models:
                for attribute in value_model.attributes:
                    property_stack = property_stack.union(attribute.GetPropertyStack(Usd.TimeCode.Default()))
                    sub_layers = sub_layers.union(
                        _LayerUtils.get_all_sublayers(
                            value_model.stage, include_session_layers=True, include_anonymous_layers=False
                        )
                    )
            ui.MenuItem(
                "Delete all overrides",
                triggered_fn=functools.partial(self._delete_overrides, item),
            )
            with ui.MenuItemCollection("Delete override from"):
                for stack_item in property_stack:
                    if stack_item.layer.identifier in sub_layers:
                        # If the layer is locked, we should not delete overrides on it
                        is_locked = omni.usd.is_layer_locked(
                            omni.usd.get_context(model.context_name), stack_item.layer.identifier
                        )
                        layer_name = _LayerUtils.get_custom_layer_name(stack_item.layer)
                        if is_locked:
                            layer_name += " [LOCKED]"
                        # Disable locked layers items
                        menu_item = ui.MenuItem(
                            layer_name,
                            triggered_fn=functools.partial(self._delete_overrides, item, layer=stack_item.layer),
                            tooltip=stack_item.layer.identifier,
                        )
                        menu_item.enabled = not is_locked
        self._context_menu_widgets[id(item)].show_at(x, y)

    def destroy(self):
        super().destroy()
        _reset_default_attrs(self)

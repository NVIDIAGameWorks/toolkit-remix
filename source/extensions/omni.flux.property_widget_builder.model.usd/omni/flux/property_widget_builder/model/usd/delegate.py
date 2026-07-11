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

from __future__ import annotations

import abc
import dataclasses
import functools
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.delegates.default import CreatorField
from omni.flux.property_widget_builder.delegates.string_value.default_label import NameField
from omni.flux.property_widget_builder.widget import Delegate as _Delegate
from omni.flux.property_widget_builder.widget import FieldBuilder
from omni.flux.property_widget_builder.widget import Item as _Item
from omni.flux.property_widget_builder.widget import ItemGroup as _ItemGroup
from omni.flux.utils.widget.resources import get_icons as _get_icons
from omni.kit.usd.layers import LayerUtils as _LayerUtils
from pxr import Sdf, Usd

from .field_builders import ALL_FIELD_BUILDERS
from .items import USDAttributeItemStub as _USDAttributeItemStub
from .items import USDLogicalGroupOutletItem as _USDLogicalGroupOutletItem
from .logical_row import LogicalRowState as _LogicalRowState

if TYPE_CHECKING:
    from .model import USDModel as _USDModel

__all__ = ("BuildLayerTransferMenu", "USDDelegate")

BuildLayerTransferMenu = Callable[[Any, Any, list[Sdf.PropertySpec], set[str], bool], None]


@dataclasses.dataclass
class Row:
    """
    Holds state and widgets for an item.
    """

    name: str
    selected: bool = False

    override_background_widgets: list[ui.Rectangle] = dataclasses.field(default_factory=list)
    default_indicator_widget: ui.Circle | None = None
    mixed_indicator_widget: ui.Image | None = None
    more_widget: ui.Image | None = None
    attribute_widgets: list[ui.Widget] = dataclasses.field(default_factory=list)


class USDDelegate(_Delegate):
    """Delegate of the tree"""

    _MORE_ICON_SIZE = ui.Pixel(16)
    _MORE_ICON_SPACING = ui.Pixel(8)

    def __init__(
        self,
        field_builders: list[FieldBuilder] | None = None,
        right_aligned_labels: bool = True,
        layer_transfer_menu_fn: BuildLayerTransferMenu | None = None,
    ):
        """Create the USD property delegate.

        Args:
            field_builders: Optional custom field builders for value widgets.
            right_aligned_labels: Whether property labels should be right aligned.
            layer_transfer_menu_fn: Callback that adds property-layer transfer actions to the override menu.
        """
        super().__init__(field_builders=field_builders)
        self._right_aligned_labels = right_aligned_labels
        self._layer_transfer_menu_fn = layer_transfer_menu_fn
        self._more_icon_source_url = _get_icons("ellipsis") or ""
        self._context_menu_widgets: dict[int, ui.Menu] = {}
        self._rows: dict[int, Row] = {}

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_right_aligned_labels": None,
                "_layer_transfer_menu_fn": None,
                "_more_icon_source_url": None,
                "_context_menu_widgets": None,
                "_rows": None,
            }
        )
        return default_attr

    @property
    def selection(self) -> list[_Item]:
        """Return the currently selected property tree items.

        Returns:
            Copy of selected items.
        """
        return list(self._selection)

    @selection.setter
    def selection(self, value: Iterable[_Item]) -> None:
        """Update selected rows and refresh hover/selection styling.

        Args:
            value: Items to mark as selected.
        """
        self._selection = list(value)

        # Reset the selected item look
        for item_id, row in self._rows.items():
            if row.selected:
                row.selected = False
                self._on_item_hovered(False, item_id, True)

        for item in value:
            item_id = id(item)
            row = self._rows.get(item_id)
            if row is not None:
                row.selected = True
                self._on_item_hovered(True, item_id)

    def reset(self) -> None:
        """Clear cached row widgets and context menus."""
        super().reset()
        self._context_menu_widgets.clear()
        self._rows.clear()

    @staticmethod
    def _get_row_attributes(item: _Item) -> list[Usd.Attribute]:
        """Return attrs owned by this renderable row, excluding visual item groups.

        Args:
            item: Tree item whose row is being rendered.

        Returns:
            USD attributes owned by the item, or an empty list for grouping rows.
        """
        if isinstance(item, _ItemGroup):
            return []
        return item.get_owned_attributes()

    @staticmethod
    def _get_row_properties(item: _Item) -> list[Usd.Property]:
        """Return properties owned by this renderable row, excluding visual item groups.

        Args:
            item: Tree item whose row is being rendered.

        Returns:
            USD properties owned by the item, or an empty list for grouping rows.
        """
        if isinstance(item, _ItemGroup):
            return []
        return item.get_owned_properties()

    @staticmethod
    def _get_row_state(item: _Item) -> _LogicalRowState:
        """Return mixed/default/override state for a renderable row.

        Args:
            item: Tree item whose indicators are being updated.

        Returns:
            Logical row state, or default state for grouping rows.
        """
        if isinstance(item, _ItemGroup):
            return _LogicalRowState()
        return item.get_row_state()

    def value_model_updated(self, item: _Item) -> None:
        """
        Callback ran whenever an item's value model updates.

        Args:
            item: Item whose value model changed.
        """
        row = self._rows.get(id(item))
        if row:
            row_state = self._get_row_state(item)
            has_override = row_state.is_overriden
            is_default = row_state.is_default
            is_mixed = row_state.is_mixed
            for bg_widget in row.override_background_widgets:
                bg_widget.visible = has_override

            if row.default_indicator_widget is not None:
                row.default_indicator_widget.style_type_name_override = (
                    "OverrideIndicator" if not is_default else "OverrideIndicatorForceDisabled"
                )

            if row.more_widget is not None:
                row.more_widget.name = "More" if has_override else "MoreDisabled"

            if row.mixed_indicator_widget is not None:
                row.mixed_indicator_widget.name = "Mixed" if is_mixed else "MixedForceDisabled"

    def _get_default_field_builders(self) -> list[FieldBuilder]:
        return ALL_FIELD_BUILDERS

    def _build_item_widgets(
        self, model: _USDModel, item: _Item, column_id: int, level: int, expanded: bool = False
    ) -> list[ui.Widget] | None:
        """Build the widgets for one property row cell.

        Args:
            model: USD property model backing the tree.
            item: Item being rendered.
            column_id: Column index to build.
            level: Tree depth.
            expanded: Whether the item is expanded.

        Returns:
            Built widgets for the cell, or ``None``.
        """
        widgets = None
        row_state = self._get_row_state(item)
        has_override = row_state.is_overriden
        is_default = row_state.is_default
        is_mixed = row_state.is_mixed

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
                                    if not isinstance(item, _ItemGroup):
                                        with ui.HStack(width=0):
                                            with ui.VStack(
                                                width=self._MORE_ICON_SIZE,
                                                height=self._MORE_ICON_SIZE,
                                            ):
                                                ui.Spacer()
                                                row.more_widget = ui.Image(
                                                    self._more_icon_source_url,
                                                    name="MoreDisabled",
                                                    tooltip="When highlighted, the displayed value has modifications.",
                                                    width=self._MORE_ICON_SIZE,
                                                    height=self._MORE_ICON_SIZE,
                                                )
                                                ui.Spacer()
                                            ui.Spacer(width=self._MORE_ICON_SPACING)
                                        if self._right_aligned_labels:
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
                row.override_background_widgets.append(
                    ui.Rectangle(
                        name="OverrideBackground",
                        visible=has_override,
                        style_type_name_override="OverrideBackground",
                    )
                )
                if column_id == 0:
                    outer = ui.VStack()
                    with outer:
                        with ui.HStack(height=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE)):
                            if not isinstance(item, _ItemGroup):
                                with ui.HStack(width=0):
                                    ui.Spacer(width=ui.Pixel(4))
                                    with ui.VStack():
                                        ui.Spacer()
                                        row.mixed_indicator_widget = ui.Image(
                                            "",
                                            name="Mixed" if is_mixed else "MixedForceDisabled",
                                            height=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE / 2),
                                            width=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE / 2),
                                            tooltip=(
                                                "Multiple values are selected.\n\nHover over value widget to see them."
                                                if is_mixed
                                                else "When highlighted, multiple values are selected."
                                            ),
                                        )
                                        ui.Spacer()
                                    ui.Spacer(width=ui.Pixel(4))
                                    row.default_indicator_widget = ui.Circle(
                                        style_type_name_override=(
                                            "OverrideIndicatorForceDisabled" if is_default else "OverrideIndicator"
                                        ),
                                        tooltip=(
                                            "When highlighted, the displayed value is not the default USD value."
                                            if is_default
                                            else (
                                                "The displayed value is not the default USD value.\n\n"
                                                "Click to reset the attribute to the default USD value."
                                            )
                                        ),
                                        width=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE / 2),
                                        mouse_released_fn=lambda x, y, b, m: self._on_reset_item(b, item),
                                    )
                                    ui.Spacer(width=ui.Pixel(4))
                                    if has_override:
                                        override_tooltip = (
                                            "The displayed value has modifications.\n\n"
                                            "Click to view and manage the modifications."
                                        )
                                    else:
                                        override_tooltip = "When highlighted, the displayed value has modifications."
                                    with ui.VStack(width=self._MORE_ICON_SIZE, content_clipping=True):
                                        ui.Spacer()
                                        row.more_widget = ui.Image(
                                            self._more_icon_source_url,
                                            name="More" if has_override else "MoreDisabled",
                                            tooltip=override_tooltip,
                                            opaque_for_mouse_events=True,
                                            mouse_pressed_fn=lambda x, y, b, m: self._show_override_menu(
                                                model, item, b
                                            ),
                                            width=self._MORE_ICON_SIZE,
                                            height=self._MORE_ICON_SIZE,
                                            identifier="override_more_menu_button",
                                        )
                                        ui.Spacer()
                                    ui.Spacer(width=self._MORE_ICON_SPACING)
                            NameField()(item, right_aligned=self._right_aligned_labels)
                        ui.Spacer()
                    widgets = [outer]
                # Logical group outlets render a value-column button but do not own value models.
                elif column_id == 1 and (item.value_models or isinstance(item, _USDLogicalGroupOutletItem)):
                    builder = self.get_field_builder(item)
                    widgets = self._build_field_widgets(builder, item)

        if widgets:
            row.attribute_widgets.extend(widgets)

        return widgets

    def build_branch(
        self, model: _USDModel, item: _Item, column_id: int = 0, level: int = 0, expanded: bool = False
    ) -> None:
        """
        Create a branch widget that opens or closes the subtree for item that can have children,
        or the default & override widgets for items that can't.

        Args:
            model: USD property model backing the tree.
            item: Item being rendered.
            column_id: Column index to build.
            level: Tree depth.
            expanded: Whether the item is expanded.
        """
        if column_id != 0:
            return

        row = self._rows.get(id(item))
        if row is None:
            row = Row("".join(x.get_value_as_string() for x in item.name_models))
        self._rows[id(item)] = row

        has_override = self._get_row_state(item).is_overriden

        with ui.ZStack(
            mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, id(item)),
        ):
            row.override_background_widgets.append(
                ui.Rectangle(
                    name="OverrideBackground",
                    visible=has_override,
                    style_type_name_override="OverrideBackground",
                )
            )
            if model.can_item_have_children(item):
                with ui.HStack(width=16 * (level + 2), height=self.DEFAULT_IMAGE_ICON_SIZE):
                    ui.Spacer()
                    with ui.Frame(mouse_released_fn=lambda x, y, b, m: self._item_expanded(b, item, not expanded)):
                        super()._build_branch(model, item, column_id, level, expanded)

    def _delete_overrides(self, item: _Item, layer: Sdf.Layer | None = None) -> None:
        """
        Delete overrides on an item.

        Args:
            item: Row item whose overrides should be removed.
            layer: Optional layer to target; ``None`` deletes all row overrides.
        """
        item.delete_row_overrides(layer=layer)
        self.value_model_updated(item)

    def _on_item_hovered(self, hovered: bool, item_id: int, force: bool = False) -> None:
        """Update row background style for hover, selection, and forced refresh.

        Args:
            hovered: Whether the mouse is currently over the row.
            item_id: ``id`` of the hovered item.
            force: Whether to refresh styling even when the row is selected.
        """
        row = self._rows.get(item_id)
        if row is not None:
            for background_widget in row.override_background_widgets:
                if not force and row.selected:
                    style_name = "OverrideBackgroundSelected"
                else:
                    style_name = "OverrideBackgroundHovered" if hovered else "OverrideBackground"
                background_widget.style_type_name_override = style_name

    def _on_reset_item(self, button: int, item: _Item) -> None:
        """Reset a row to its default value on left click.

        Args:
            button: Mouse button id from omni.ui.
            item: Row item to reset.
        """
        if button != 0:
            return

        if self._get_row_state(item).is_default:
            return
        item.reset_row_value()
        self.value_model_updated(item)

    def _is_ogn_item(self, item: _Item) -> bool:
        """Check if the item belongs to an OmniGraph node.

        Args:
            item: Row item whose owned attributes should be inspected.

        Returns:
            ``True`` when any owned attribute belongs to an ``OmniGraphNode`` prim.
        """
        for attribute in self._get_row_attributes(item):
            prim = attribute.GetPrim()
            if prim.IsValid() and prim.GetTypeName() == "OmniGraphNode":
                return True
        return False

    def _show_override_menu(self, model: _USDModel, item: _Item, button: int) -> None:
        """Open the override management menu for a row.

        Args:
            model: USD property model backing the tree.
            item: Row item whose property stack should be shown.
            button: Mouse button id from omni.ui.
        """
        row_state = self._get_row_state(item)
        if button != 0 or not row_state.is_overriden:
            return
        # TODO: This is a temporary fix. We need to find a better way to handle this.
        # OGN node properties don't support layer-based override deletion because it will remove the attr type.
        enabled = not self._is_ogn_item(item)
        self._context_menu_widgets[id(item)] = ui.Menu("Modification menu", direction=ui.Direction.LEFT_TO_RIGHT)
        with self._context_menu_widgets[id(item)]:
            sub_layers = set()
            stage = omni.usd.get_context(model.context_name).get_stage()
            if stage is not None:
                sub_layers = sub_layers.union(
                    _LayerUtils.get_all_sublayers(stage, include_session_layers=True, include_anonymous_layers=False)
                )
            property_stack = item.get_property_stack()
            delete_all_overrides_label = "Revert This Property Modification"
            if not enabled:
                delete_all_overrides_label += " [DISABLED FOR THIS PROPERTY]"
            top_menu_item = ui.MenuItem(
                delete_all_overrides_label,
                triggered_fn=functools.partial(self._delete_overrides, item),
            )
            top_menu_item.enabled = enabled
            with ui.MenuItemCollection("Revert This Property Modification on Layer..."):
                for layer in item.get_layer_override_layers(sub_layers):
                    # If the layer is locked, we should not delete overrides on it
                    is_locked = omni.usd.is_layer_locked(omni.usd.get_context(model.context_name), layer.identifier)
                    layer_name = _LayerUtils.get_custom_layer_name(layer)
                    if is_locked:
                        layer_name += " [LOCKED]"
                    if not enabled:
                        layer_name += " [DISABLED FOR THIS PROPERTY]"
                    # Disable locked layers items
                    menu_item = ui.MenuItem(
                        layer_name,
                        triggered_fn=functools.partial(self._delete_overrides, item, layer=layer),
                        tooltip=layer.identifier,
                    )
                    menu_item.enabled = not is_locked and enabled
            if self._layer_transfer_menu_fn:
                self._layer_transfer_menu_fn(model, item, property_stack, sub_layers, enabled)
        self._context_menu_widgets[id(item)].show()

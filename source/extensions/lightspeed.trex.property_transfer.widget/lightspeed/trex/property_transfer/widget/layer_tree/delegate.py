"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from collections.abc import Callable

from omni import ui
from omni.flux.layer_tree.usd.widget import LayerDelegate as _LayerDelegate
from omni.flux.layer_tree.usd.widget import LayerModel as _LayerModel
from pxr import Sdf

from .model import _PropertyTransferLayerModel
from .state import OpinionState


class _PropertyTransferLayerDelegate(_LayerDelegate):
    _STATE_WIDTH = ui.Pixel(112)
    _ICON_SIZE = ui.Pixel(16)
    _ROW_TRIGGER_HEIGHT = ui.Pixel(2)

    def __init__(
        self,
        state_label: str,
        spacing_sm: ui.Length,
        target_double_clicked_fn: Callable[[object], None] | None = None,
    ):
        """Create the property-transfer layer tree delegate.

        Args:
            state_label: User-facing transfer state column label.
            spacing_sm: Compact spacing used by the transfer window layout.
            target_double_clicked_fn: Callback to run when a valid target layer is double-clicked.
        """
        super().__init__()
        self._state_label = state_label
        self._spacing_sm = spacing_sm
        self._target_double_clicked_fn = target_double_clicked_fn

    @property
    def default_attr(self) -> dict[str, None]:
        """Get attributes reset during delegate destruction.

        Returns:
            Mapping of attribute names to their reset values.
        """
        default_attr = super().default_attr
        default_attr.update({"_state_label": None, "_spacing_sm": None, "_target_double_clicked_fn": None})
        return default_attr

    @property
    def state_width(self) -> ui.Length:
        """Get the transfer state column width.

        Returns:
            Width for the state column.
        """
        return self._STATE_WIDTH

    @property
    def _dynamic_edit_target_icons(self):
        return False

    def _build_header(self, column_id: int):
        text = "Layer" if column_id == 0 else self._state_label
        alignment = ui.Alignment.LEFT_CENTER if column_id == 0 else ui.Alignment.CENTER
        with ui.HStack(height=ui.Pixel(self.row_height)):
            ui.Spacer(width=self._spacing_sm)
            ui.Label(
                text,
                width=ui.Fraction(1),
                height=ui.Pixel(self.row_height),
                alignment=alignment,
                identifier=f"property_transfer_header_{column_id}",
            )
            ui.Spacer(width=self._spacing_sm)

    def _build_widget(self, model: _LayerModel, item, column_id: int, level: int, expanded: bool):
        layer = item.data.get("layer") if item and item.data else None
        if layer is None:
            return

        if column_id == 0:
            super()._build_widget(model, item, column_id, level, expanded)
            return
        self._build_state_column(model, item, layer)

    def _build_branch_end_icons(self, _model: _LayerModel, item) -> None:
        layer = item.data.get("layer") if item and item.data else None
        is_valid_target = item.enabled
        tooltip = (
            layer.identifier
            if is_valid_target and layer
            else (item.data.get("disabled_tooltip", "") if item.data else "")
        )
        with ui.VStack(width=self._ICON_SIZE):
            ui.Spacer(width=0)
            ui.Image(
                "",
                height=self._ICON_SIZE,
                name="LayerStatic" if is_valid_target else "LayerDisabled",
                tooltip=tooltip,
            )
            ui.Spacer(width=0)

    def _build_widget_icons(self, _model: _LayerModel, _item) -> None:
        pass

    @staticmethod
    def _get_item_tooltip(item) -> str:
        if not item.enabled and item.data.get("disabled_tooltip"):
            return item.data["disabled_tooltip"]
        layer = item.data.get("layer") if item.data else None
        return layer.identifier if layer else "Invalid Layer"

    @staticmethod
    def _get_item_label_name(item) -> str:
        return "PropertiesPaneSectionTreeItem" if item.enabled else "PropertiesPaneSectionTreeItemDisabled"

    def _get_item_label_tooltip(self, item) -> str:
        return self._get_item_tooltip(item)

    def _build_state_column(self, model: _PropertyTransferLayerModel, item, layer: Sdf.Layer) -> None:
        state = model.get_layer_opinion_state(layer.identifier)
        with ui.ZStack(height=ui.Pixel(self.row_height)):
            if id(item) not in self._background_items:
                self._background_items[id(item)] = []
            with ui.ZStack():
                with ui.VStack(height=ui.Pixel(self.row_height)):
                    spacer = ui.Line(height=self._ROW_TRIGGER_HEIGHT, visible=False, name="TreeSpacer")
                    rectangle = ui.Rectangle(
                        style_type_name_override="TreeView.Item",
                        mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, model, item),
                    )
                with ui.VStack(height=ui.Pixel(self.row_height)):
                    ui.Spacer(
                        height=self._ROW_TRIGGER_HEIGHT,
                        mouse_hovered_fn=lambda hovered: self._on_trigger_hovered(hovered, model, item),
                    )
            self._background_items[id(item)].append((spacer, rectangle))
            with ui.HStack(height=ui.Pixel(self.row_height)):
                ui.Spacer(width=self._spacing_sm)
                self._build_state_label(state, item)
                ui.Spacer(width=self._spacing_sm)

    def _build_state_label(self, state: OpinionState | None, item) -> None:
        if not item.enabled:
            ui.Spacer(width=ui.Fraction(1))
            return
        if state not in {OpinionState.STRONGEST, OpinionState.WEAKER}:
            ui.Spacer(width=ui.Fraction(1))
            return
        self._build_state_indicator(state)

    def _build_state_indicator(self, state: OpinionState) -> None:
        with ui.HStack(width=ui.Fraction(1)):
            ui.Spacer()
            with ui.VStack(
                width=self._ICON_SIZE,
                height=ui.Pixel(self.row_height),
                tooltip=self._get_transfer_state_tooltip(state),
            ):
                ui.Spacer()
                ui.Image(
                    "",
                    name=(
                        "PropertyTransferStateStrong"
                        if state is OpinionState.STRONGEST
                        else "PropertyTransferStateWeak"
                    ),
                    width=self._ICON_SIZE,
                    height=self._ICON_SIZE,
                )
                ui.Spacer()
            ui.Spacer()

    def _get_transfer_state_tooltip(self, state: OpinionState) -> str:
        if self._state_label == "Definition":
            if state is OpinionState.STRONGEST:
                return "This is the layer where the definition lives."
            return "This layer has the definition, but a stronger layer provides the active definition."
        subject = self._state_label.lower()
        if state is OpinionState.STRONGEST:
            return f"This layer provides the active {subject}."
        return f"This layer has the {subject}, but a stronger layer provides the active {subject}."

    def _show_context_menu(self, _model, _item) -> None:
        pass

    def _on_item_hovered(self, hovered, model, item):
        super()._on_item_hovered(hovered and item.enabled, model, item)

    def _on_item_mouse_double_clicked(self, button, model, item):
        if button == 0 and item.enabled and self._target_double_clicked_fn:
            self._target_double_clicked_fn(item)

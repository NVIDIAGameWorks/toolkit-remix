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

__all__ = ["PropertyTransferWindow"]

import asyncio
from collections import OrderedDict
from collections.abc import Iterator, Sequence

import carb
import omni.kit.app
import omni.kit.commands
import omni.kit.undo
import omni.usd
from carb.input import KeyboardInput
from omni import ui
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget as _ScrollingTreeWidget
from pxr import Sdf

from .enums import TransferKind
from .layer_tree.delegate import _PropertyTransferLayerDelegate
from .layer_tree.model import _PropertyTransferLayerModel


class PropertyTransferWindow:
    """Modal window that transfers authored USD specs to a selected replacement layer."""

    _WINDOW_WIDTH = ui.Pixel(720)
    _WINDOW_HEIGHT = ui.Pixel(440)
    _SPACING_SM = ui.Pixel(4)
    _SPACING_MD = ui.Pixel(8)
    _BUTTON_WIDTH = ui.Pixel(64)
    _BUTTON_HEIGHT = ui.Pixel(24)

    def __init__(
        self,
        context_name: str,
        property_stack: Sequence[Sdf.Spec],
        transfer_kind: str = "property",
        reference_to_transfer: Sdf.Reference | None = None,
        display_name: str = "",
    ):
        """Create a property transfer modal.

        Args:
            context_name: USD context name containing the stage.
            property_stack: Authored property, prim, or reference specs to transfer.
            transfer_kind: Transfer type, either property, prim, reference, or layer.
            reference_to_transfer: Reference list edit to transfer for reference transfers.
            display_name: Optional user-facing name to show in the modal.
        """
        self._context_name = context_name
        self._transfer_kind = TransferKind(transfer_kind)
        if self._transfer_kind is TransferKind.PRIM:
            self._transfer_state_label = "Definition"
        elif self._transfer_kind is TransferKind.LAYER:
            self._transfer_state_label = "Layer Changes"
        else:
            self._transfer_state_label = "Modification"
        self._reference_to_transfer = reference_to_transfer
        self._display_name = display_name
        self._property_specs_by_path = self._collect_specs_by_path(property_stack, self._transfer_kind)
        self._selected_target_layer_identifier = ""
        self._window = None
        self._model = None
        self._delegate = None
        self._tree = None
        self._transfer_button = None
        self._expand_task = None
        self._sub_refresh_completed = None
        self._sub_selection_changed = None
        self._build_ui()

    def destroy(self) -> None:
        """Destroy the modal and release resources with explicit lifetimes."""
        if self._expand_task:
            self._expand_task.cancel()
            self._expand_task = None
        self._sub_refresh_completed = None
        self._sub_selection_changed = None
        if self._delegate:
            self._delegate.destroy()
            self._delegate = None
        self._tree = None
        self._transfer_button = None
        if self._model:
            self._model.destroy()
            self._model = None
        if self._window:
            self._window.destroy()
            self._window = None

    def _build_ui(self) -> None:
        self._model = _PropertyTransferLayerModel(self._context_name, self._property_specs_by_path)
        self._sub_refresh_completed = self._model.subscribe_refresh_completed(self._expand_layers)
        self._delegate = _PropertyTransferLayerDelegate(
            self._transfer_state_label,
            self._SPACING_SM,
            self._transfer_to_item,
        )
        self._window = ui.Window(
            f"Transfer {self._transfer_state_label} to Layer",
            width=self._WINDOW_WIDTH,
            height=self._WINDOW_HEIGHT,
            visible=True,
            flags=(
                ui.WINDOW_FLAGS_MODAL
                | ui.WINDOW_FLAGS_NO_DOCKING
                | ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_RESIZE
            ),
        )
        with self._window.frame:
            with ui.Frame(key_pressed_fn=self._on_key_pressed):
                with ui.HStack(spacing=self._SPACING_MD):
                    ui.Spacer(width=0)
                    with ui.VStack(spacing=self._SPACING_MD):
                        ui.Spacer(height=0)
                        self._build_description()
                        with ui.ZStack():
                            ui.Rectangle(name="TreePanelBackground", identifier="property_transfer_tree_background")
                            self._tree = _ScrollingTreeWidget(
                                self._model,
                                self._delegate,
                                alternating_rows=False,
                                row_height=self._delegate.row_height,
                                select_all_children=False,
                                frame_selection=False,
                                validate_action_selection=True,
                                header_visible=True,
                                drop_between_items=False,
                                columns_resizable=True,
                                column_widths=[ui.Fraction(1), self._delegate.state_width],
                                style_type_name_override="TreeView.Selection",
                            )
                        self._sub_selection_changed = self._tree.subscribe_selection_changed(self._on_selection_changed)
                        self._build_footer()
                        ui.Spacer(height=0)
                    ui.Spacer(width=0)
        self._model.refresh()

    def _build_description(self) -> None:
        property_path_tooltip = self._get_property_path_tooltip()
        property_name = self._get_property_item_display_name()
        subject = {
            TransferKind.PRIM: "definition",
            TransferKind.REFERENCE: "reference",
            TransferKind.LAYER: "layer changes",
        }.get(self._transfer_kind, "property")
        flatten_message = (
            "If these layer changes exist on multiple layers, the composed values will be flattened onto the "
            "selected target layer and the other source layer values will be removed."
            if self._transfer_kind is TransferKind.LAYER
            else (
                f"If this {subject} exists on multiple layers, the composed value will be flattened onto the "
                "selected target layer and the other source layer values will be removed."
            )
        )
        with ui.VStack(height=0, spacing=self._SPACING_SM):
            ui.Label(
                f'Transfer "{property_name}" to another layer.',
                word_wrap=True,
                height=0,
                tooltip=property_path_tooltip,
                identifier="property_transfer_property_message",
            )
            ui.Label(
                flatten_message,
                word_wrap=True,
                height=0,
                identifier="property_transfer_flatten_message",
            )

    def _build_footer(self) -> None:
        subject = self._transfer_state_label.lower()
        with ui.HStack(spacing=self._SPACING_SM, height=0):
            ui.Spacer()
            ui.Button(
                "Cancel",
                width=self._BUTTON_WIDTH,
                height=self._BUTTON_HEIGHT,
                tooltip=f"Close the window without transferring the {subject}",
                clicked_fn=lambda: setattr(self._window, "visible", False),
                identifier="property_transfer_cancel",
            )
            self._transfer_button = ui.Button(
                "Transfer",
                width=self._BUTTON_WIDTH,
                height=self._BUTTON_HEIGHT,
                tooltip=f"Transfer the {subject} to the selected layer",
                clicked_fn=self._transfer,
                enabled=False,
                identifier="property_transfer_confirm",
            )

    def _expand_layers(self) -> None:
        if not self._model or not self._window:
            return
        if self._expand_task:
            self._expand_task.cancel()
        self._expand_task = asyncio.ensure_future(self._expand_layers_async())

    async def _expand_layers_async(self) -> None:
        await omni.kit.app.get_app().next_update_async()
        if not self._tree or not self._model or not self._delegate:
            return
        for item in self._model.get_item_children():
            self._tree.set_expanded(item, True, True)
        self._delegate.on_item_selected([], self._model.get_item_children(recursive=True), self._model)
        self._tree.dirty_widgets()
        self._sync_transfer_button()

    def _on_selection_changed(self, items) -> None:
        if not self._model or not self._delegate:
            return
        item = items[0] if items else None
        layer = item.data.get("layer") if item and item.data and item.enabled else None
        if item and not item.enabled:
            items = []
            if self._tree:
                self._tree.selection = []
        if self._tree:
            self._tree.on_selection_changed(items)
        self._delegate.on_item_selected(items, self._model.get_item_children(recursive=True), self._model)
        self._selected_target_layer_identifier = layer.identifier if layer else ""
        self._sync_transfer_button()

    def _transfer_to_item(self, item) -> None:
        if not item or not item.enabled:
            return
        if self._tree:
            self._tree.selection = [item]
        self._on_selection_changed([item])
        self._transfer()

    def _on_key_pressed(self, key, _, is_down) -> None:
        if not is_down or key != int(KeyboardInput.ENTER):
            return
        self._transfer()

    def _get_property_item_display_name(self) -> str:
        if self._display_name:
            return self._display_name
        property_paths = [path.pathString for path in self._property_specs_by_path]
        return ", ".join(property_paths)

    def _get_property_path_tooltip(self) -> str:
        return "\n".join(path.pathString for path in self._property_specs_by_path)

    @staticmethod
    def _collect_specs_by_path(
        property_stack: Sequence[Sdf.Spec], transfer_kind: TransferKind
    ) -> OrderedDict[Sdf.Path, list[Sdf.Spec]]:
        result: OrderedDict[Sdf.Path, list[Sdf.Spec]] = OrderedDict()
        seen = set()
        for spec in property_stack:
            if spec is None or not PropertyTransferWindow._is_transfer_spec_path(spec.path, transfer_kind):
                continue
            key = (spec.path, spec.layer.identifier)
            if key in seen:
                continue
            seen.add(key)
            result.setdefault(spec.path, []).append(spec)
        return result

    @staticmethod
    def _is_transfer_spec_path(path: Sdf.Path, transfer_kind: TransferKind) -> bool:
        if transfer_kind is TransferKind.PROPERTY:
            return path.IsPropertyPath()
        return path.IsPrimPath()

    def _sync_transfer_button(self) -> None:
        if self._transfer_button:
            self._transfer_button.enabled = self._can_transfer_to_selected_layer()

    def _iter_pending_spec_groups(self, target_layer_identifier: str) -> Iterator[tuple[Sdf.Path, Sequence[Sdf.Spec]]]:
        for spec_path, specs in self._property_specs_by_path.items():
            if any(spec.layer.identifier != target_layer_identifier for spec in specs):
                yield spec_path, specs

    def _can_transfer_to_selected_layer(self) -> bool:
        target_layer_identifier = self._selected_target_layer_identifier
        if not target_layer_identifier or not self._model:
            return False
        return self._model.can_transfer_specs_to_layer(
            target_layer_identifier,
            (specs for _spec_path, specs in self._iter_pending_spec_groups(target_layer_identifier)),
        )

    def _transfer(self) -> None:
        target_layer_identifier = self._selected_target_layer_identifier
        if not self._can_transfer_to_selected_layer() or not self._model:
            return
        if self._transfer_kind is TransferKind.REFERENCE and self._reference_to_transfer is None:
            return

        did_transfer = False
        failed = False
        try:
            with omni.kit.undo.group():
                for spec_path, specs in self._iter_pending_spec_groups(target_layer_identifier):
                    source_layer_identifiers = [spec.layer.identifier for spec in specs]
                    if self._transfer_kind is TransferKind.REFERENCE:
                        success, _result = omni.kit.commands.execute(
                            "TransferReferenceSpecToLayer",
                            prim_path=spec_path.pathString,
                            reference=self._reference_to_transfer,
                            source_layer_identifiers=source_layer_identifiers,
                            target_layer_identifier=target_layer_identifier,
                            usd_context=self._context_name,
                        )
                    elif self._transfer_kind is TransferKind.PROPERTY:
                        success, _result = omni.kit.commands.execute(
                            "TransferPropertySpecToLayer",
                            property_path=spec_path.pathString,
                            source_layer_identifiers=source_layer_identifiers,
                            target_layer_identifier=target_layer_identifier,
                            usd_context=self._context_name,
                        )
                    else:
                        success, _result = omni.kit.commands.execute(
                            "TransferPrimDefinitionSpecToLayer",
                            prim_path=spec_path.pathString,
                            source_layer_identifiers=source_layer_identifiers,
                            target_layer_identifier=target_layer_identifier,
                            usd_context=self._context_name,
                        )
                    if not success:
                        failed = True
                        break
                    did_transfer = True
        except Exception:
            if did_transfer:
                omni.kit.undo.undo()
            self._sync_transfer_button()
            raise
        if failed:
            carb.log_warn("Property transfer failed; reverting partial transfer.")
            if did_transfer:
                omni.kit.undo.undo()
            self._sync_transfer_button()
            return
        if self._window:
            self._window.visible = False

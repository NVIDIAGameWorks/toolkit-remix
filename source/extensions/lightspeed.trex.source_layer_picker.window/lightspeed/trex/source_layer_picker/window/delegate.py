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

__all__ = ["SourceLayerPickerDelegate"]

from collections.abc import Callable

from omni import ui
from omni.flux.layer_tree.usd.widget import LayerDelegate as _LayerDelegate
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

from .constants import _PADDING_MD, _PADDING_SM, _ROW_HEIGHT


class SourceLayerPickerDelegate(_LayerDelegate):
    """LayerDelegate that swaps the per-row layer-management icons for a single checkbox.

    Rows for layers in the replacement subtree (mod.usda + recursive sublayers) get
    an enabled checkbox driving the picker's draft selection. Other layers stay
    visible for context but render no checkbox; the filter only cares about
    mod layers once the draft is applied.
    """

    def __init__(
        self,
        selected_ids: set[str] | None,
        mod_layer_ids: frozenset[str],
    ):
        super().__init__()
        self._selected_ids = self._copy_selected_ids(selected_ids)
        self._mod_layer_ids = mod_layer_ids
        self.__on_selected_ids_changed = _Event()

    def __del__(self):
        self.destroy()

    @property
    def default_attr(self) -> dict:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_selected_ids": None,
                "_mod_layer_ids": frozenset(),
                "_SourceLayerPickerDelegate__on_selected_ids_changed": _Event(),
            }
        )
        return default_attr

    @property
    def selected_ids(self) -> set[str] | None:
        return self._copy_selected_ids(self._selected_ids)

    @selected_ids.setter
    def selected_ids(self, value: set[str] | None) -> None:
        self._selected_ids = self._copy_selected_ids(value)

    @property
    def mod_layer_ids(self) -> frozenset[str]:
        return self._mod_layer_ids

    @mod_layer_ids.setter
    def mod_layer_ids(self, value: frozenset[str]) -> None:
        self._mod_layer_ids = frozenset(value)

    def subscribe_selected_ids_changed(self, callback: Callable[[set[str] | None], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_selected_ids_changed, callback)

    @property
    def _dynamic_edit_target_icons(self):
        # Returning False stops the base from swapping the per-row icon column for the
        # "currently authoring" indicator, which the picker has no concept of.
        return False

    def refresh_gradient_color(self, item, model, deferred: bool = True):
        # Keep on_item_selected's row tint as the only selection signal; the right-edge
        # gradient strip duplicates it and reads as noise in the picker's narrow window.
        return

    async def _add_gradient_or_not(self, item):
        # Base class also paints a default dark gradient on overflowing rows here, before
        # refresh_gradient_color ever runs. Skip provider creation entirely so the strip
        # never appears in the picker.
        return

    def _build_widget(self, model, item, column_id, level, expanded):
        if item is None:
            return
        if column_id != 0:
            return
        with ui.ZStack(identifier="layer_item_root"):
            if id(item) not in self._background_items:
                self._background_items[id(item)] = []
            with ui.ZStack():
                with ui.VStack(height=_ROW_HEIGHT):
                    spacer = ui.Line(height=ui.Pixel(2), visible=False, name="TreeSpacer")
                    rectangle = ui.Rectangle(
                        style_type_name_override="TreeView.Item",
                        mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, model, item),
                    )
                with ui.VStack(height=_ROW_HEIGHT):
                    ui.Spacer(
                        height=ui.Pixel(2),
                        mouse_hovered_fn=lambda hovered: self._on_trigger_hovered(hovered, model, item),
                    )
            self._background_items[id(item)].append((spacer, rectangle))
            with ui.HStack():
                ui.Spacer(width=_PADDING_SM)
                with ui.Frame(
                    separate_window=True,
                    mouse_pressed_fn=lambda _x, _y, button, _modifier: self._on_item_mouse_pressed(button, item),
                    mouse_released_fn=lambda _x, _y, button, _modifier: self._on_item_mouse_released(button, item),
                    key_pressed_fn=lambda key, _scancode, pressed: item.on_key_pressed(key, pressed),
                    tooltip=item.data["layer"].identifier if item.data["layer"] else "Invalid Layer",
                ):
                    self._scroll_frames[id(item)] = ui.ScrollingFrame(
                        name="TreePanelBackground",
                        height=_ROW_HEIGHT,
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        scroll_y_max=0,
                    )
                    with self._scroll_frames[id(item)]:
                        with ui.HStack():
                            ui.Spacer(width=_PADDING_SM)
                            with ui.VStack():
                                ui.Label(item.title, name="PropertiesPaneSectionTreeItem")
                                ui.Spacer(height=_PADDING_SM)
                self._build_widget_icons(model, item)

    def _build_widget_icons(self, model, item):
        # Picker exposes no save/lock/visible/mute actions; suppress the standard icons.
        return

    def _show_context_menu(self, model, item):
        # Keep the picker read-only even though it reuses the full layer-tree delegate.
        return

    def _build_branch_start_icons(self, model, item):
        layer = item.data.get("layer") if item.data else None
        identifier = layer.identifier if layer else None
        is_pickable = bool(identifier) and identifier in self.mod_layer_ids
        with ui.HStack(
            width=_ROW_HEIGHT,
            height=_ROW_HEIGHT,
            identifier="source_layer_checkbox_stack",
            opaque_for_mouse_events=True,
            mouse_released_fn=lambda _x, _y, button, _modifier, _id=identifier, _pickable=is_pickable: (
                self._on_check_released(_id, button) if _pickable else None
            ),
        ):
            # Non-mod rows: keep the column width so layer names stay aligned across the tree,
            # but render no checkbox at all (was previously a disabled checkbox).
            if not is_pickable:
                return
            ui.Spacer(width=_PADDING_MD)
            with ui.VStack():
                ui.Spacer()
                selected = self.selected_ids
                is_checked = selected is None or identifier in selected
                checkbox = ui.CheckBox(
                    width=_ROW_HEIGHT,
                    height=_ROW_HEIGHT,
                    identifier="source_layer_checkbox",
                )
                checkbox.model.set_value(is_checked)
                ui.Spacer()

    def _on_check_released(self, identifier: str | None, button: int) -> None:
        if button != 0 or identifier is None or identifier not in self.mod_layer_ids:
            return
        selected = self.selected_ids
        is_checked = selected is None or identifier in selected
        self._on_check_changed(identifier, not is_checked)

    def _on_check_changed(self, identifier: str | None, checked: bool) -> None:
        if identifier is None:
            return
        current = self.selected_ids
        # None state means "all mod layers selected"; materialize it before mutating.
        if current is None:
            current = set(self.mod_layer_ids)
        else:
            current = set(current)
        if checked:
            current.add(identifier)
        else:
            current.discard(identifier)
        self.selected_ids = current
        self.__on_selected_ids_changed(self.selected_ids)

    @staticmethod
    def _copy_selected_ids(ids: set[str] | None) -> set[str] | None:
        return None if ids is None else set(ids)

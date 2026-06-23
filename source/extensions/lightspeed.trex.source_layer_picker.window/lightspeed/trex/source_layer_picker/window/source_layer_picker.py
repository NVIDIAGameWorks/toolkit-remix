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

__all__ = ["SourceLayerPicker"]

import asyncio
from collections.abc import Callable
from functools import partial

import omni.kit.app
import omni.usd
from omni import ui
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget as _ScrollingTreeWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.kit.usd.layers import LayerUtils as _LayerUtils

from .constants import (
    _PADDING_MD,
    _PADDING_SM,
    _PICKER_DIVIDER_HEIGHT,
    _PICKER_WINDOW_HEIGHT,
    _PICKER_WINDOW_WIDTH,
    _ROW_HEIGHT,
)
from .delegate import SourceLayerPickerDelegate
from .model import SearchableLayerModel


class SourceLayerPicker:
    """Standalone window for choosing which mod sublayers drive the Edit-State filter.

    Reuses the same scrollable tree primitive as the layer-tree widget and overlays
    per-row checkboxes via ``SourceLayerPickerDelegate``. Layer-management
    actions are blocked through model excludes plus a disabled context menu, so the
    picker is structurally read-only.
    """

    def __init__(
        self,
        context_name: str,
        mod_layer_ids: frozenset[str],
        selected_ids: set[str] | None,
    ):
        self._context_name = context_name
        self._mod_layer_ids: frozenset[str] = frozenset(mod_layer_ids)
        self._selected_ids: set[str] | None = None
        self.selected_ids = selected_ids
        self._draft_selected_ids: set[str] | None = self.selected_ids
        self._window: ui.Window | None = None
        self._model: SearchableLayerModel | None = None
        self._delegate: SourceLayerPickerDelegate | None = None
        self._tree_widget: _ScrollingTreeWidget | None = None
        self._search_field: ui.StringField | None = None
        self._select_all_label: ui.Label | None = None
        self._deselect_all_label: ui.Label | None = None
        self._search_sub = None
        self._model_item_changed_sub = None
        self._delegate_item_expanded_sub = None
        self._delegate_selected_ids_sub = None
        self._expand_tree_task = None
        self.__on_selected_ids_applied = _Event()

    def __del__(self):
        self.destroy()

    def show(self) -> None:
        self._reset_draft_selected_ids()
        if self._window is None:
            self._build_window()
        self._window.visible = True
        self._set_model_listeners_enabled(True)
        self.refresh()

    def hide(self) -> None:
        if self._window is not None:
            self._window.visible = False
        self._cancel_expand_tree_task()
        self._set_model_listeners_enabled(False)

    def refresh(self) -> None:
        # LayerModel listens to USD layer events itself; nudge the tree to redraw
        # so checkbox enablement reflects the current replacement-layer set.
        self._prune_draft_selected_ids()
        if self._delegate is not None:
            self._delegate.selected_ids = self.draft_selected_ids
            self._delegate.mod_layer_ids = self._mod_layer_ids
        self._refresh_action_label_states()
        if self._model is not None:
            search_text = self._search_field.model.get_value_as_string() if self._search_field is not None else ""
            self._model.set_search(search_text, force=True)

    @property
    def mod_layer_ids(self) -> frozenset[str]:
        return self._mod_layer_ids

    @mod_layer_ids.setter
    def mod_layer_ids(self, value: frozenset[str]) -> None:
        self._mod_layer_ids = frozenset(value)
        if self._delegate is not None:
            self._delegate.mod_layer_ids = self._mod_layer_ids

    @property
    def selected_ids(self) -> set[str] | None:
        return None if self._selected_ids is None else set(self._selected_ids)

    @selected_ids.setter
    def selected_ids(self, value: set[str] | None) -> None:
        self._selected_ids = None if value is None else set(value)

    @property
    def draft_selected_ids(self) -> set[str] | None:
        return None if self._draft_selected_ids is None else set(self._draft_selected_ids)

    @draft_selected_ids.setter
    def draft_selected_ids(self, value: set[str] | None) -> None:
        self._draft_selected_ids = None if value is None else set(value)

    def subscribe_selected_ids_applied(self, callback: Callable[[set[str] | None], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_selected_ids_applied, callback)

    def destroy(self) -> None:
        self.hide()
        self._cancel_expand_tree_task()
        self._tree_widget = None
        if self._delegate is not None:
            self._delegate.destroy()
        self._delegate = None
        if self._model is not None:
            self._model.destroy()
        self._model = None
        self._search_sub = None
        self._model_item_changed_sub = None
        self._delegate_item_expanded_sub = None
        self._delegate_selected_ids_sub = None
        self._search_field = None
        self._select_all_label = None
        self._deselect_all_label = None
        if self._window is not None:
            self._window.destroy()
            self._window = None

    @property
    def visible(self) -> bool:
        return self._window is not None and self._window.visible

    @property
    def is_ready(self) -> bool:
        return self._model is not None and self._tree_widget is not None

    def set_search(self, text: str) -> None:
        if self._search_field is not None:
            self._search_field.model.set_value(text)
        elif self._model is not None:
            self._model.set_search(text)

    def _build_window(self) -> None:
        self._model = SearchableLayerModel(
            context_name=self._context_name,
            exclude_add_child_fn=self._get_all_layer_identifiers,
            exclude_remove_fn=self._get_all_layer_identifiers,
            exclude_lock_fn=self._get_all_layer_identifiers,
            exclude_move_fn=self._get_all_layer_identifiers,
            exclude_mute_fn=self._get_all_layer_identifiers,
            exclude_edit_target_fn=self._get_all_layer_identifiers,
        )
        self._model_item_changed_sub = self._model.subscribe_item_changed_fn(
            lambda *_args: self._request_expand_tree_items()
        )
        self._delegate = SourceLayerPickerDelegate(
            selected_ids=self.draft_selected_ids,
            mod_layer_ids=self.mod_layer_ids,
        )
        self._delegate_item_expanded_sub = self._delegate.subscribe_on_item_expanded(self._set_selected_items_expanded)
        self._delegate_selected_ids_sub = self._delegate.subscribe_selected_ids_changed(
            self._set_draft_selected_ids_and_refresh
        )
        self._window = ui.Window(
            "Select Source Layers",
            width=_PICKER_WINDOW_WIDTH,
            height=_PICKER_WINDOW_HEIGHT,
            visible=False,
            flags=ui.WINDOW_FLAGS_NO_RESIZE | ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_SCROLLBAR,
        )
        with self._window.frame:
            with ui.ZStack():
                ui.Rectangle(name="WorkspaceBackground")
                with ui.HStack(spacing=_PADDING_MD):
                    ui.Spacer(width=0, height=0)
                    with ui.VStack(spacing=_PADDING_MD):
                        ui.Spacer(height=0)
                        ui.Label(
                            "Choose which replacement source layers to find edits. Non-mod layers remain visible for context.",
                            alignment=ui.Alignment.LEFT,
                            word_wrap=True,
                            height=0,
                        )
                        with ui.VStack():
                            self._build_filter_controls()
                            ui.Spacer(height=_PADDING_MD)
                            ui.Line(name="PropertiesPaneSectionTitle", height=_PICKER_DIVIDER_HEIGHT)
                            ui.Spacer(height=_PADDING_MD)
                            with ui.ZStack(height=ui.Fraction(1)):
                                ui.Rectangle(
                                    name="TreePanelBackground",
                                    identifier="property_transfer_tree_background",
                                )
                                self._tree_widget = _ScrollingTreeWidget(
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
                                    column_widths=[ui.Fraction(1)],
                                    style_type_name_override="TreeView.Selection",
                                )
                            ui.Spacer(height=_PADDING_MD)
                            with ui.VStack(height=_ROW_HEIGHT):
                                ui.Spacer()
                                with ui.HStack(height=_ROW_HEIGHT):
                                    ui.Spacer(width=ui.Fraction(1))
                                    ui.Button(
                                        "Select",
                                        width=ui.Pixel(112),
                                        height=_ROW_HEIGHT,
                                        clicked_fn=self._apply_selection_and_hide,
                                    )
                                    ui.Spacer(width=_PADDING_MD)
                                ui.Spacer()
                            ui.Spacer(height=_PADDING_MD)
                    ui.Spacer(width=0, height=0)

    def _build_filter_controls(self) -> None:
        with ui.HStack(height=_ROW_HEIGHT, spacing=_PADDING_MD):
            ui.Label("Search:", width=ui.Pixel(48), alignment=ui.Alignment.LEFT_CENTER)
            self._search_field = ui.StringField(height=_ROW_HEIGHT, width=ui.Fraction(1))
            # Hold the subscription on the picker so it can't be garbage-collected
            # while the window is alive; some omni.ui versions drop unheld callbacks.
            self._search_sub = self._search_field.model.add_value_changed_fn(self._on_search_changed)
            # None means all mod layers stay selected, including future sublayers.
            self._select_all_label = self._build_action_label(
                "Select All",
                partial(self._set_draft_selected_ids_and_refresh, None),
                self._is_select_all_enabled,
                ui.Pixel(64),
            )
            self._deselect_all_label = self._build_action_label(
                "Deselect All",
                partial(self._set_draft_selected_ids_and_refresh, set()),
                self._is_deselect_all_enabled,
                ui.Pixel(72),
            )
            ui.Spacer(width=_PADDING_SM)

    def _build_action_label(
        self, text: str, clicked_fn: Callable[[], None], enabled_fn: Callable[[], bool], width: ui.Length
    ) -> ui.Label:
        return ui.Label(
            text,
            name="FilterSectionAction",
            width=width,
            enabled=enabled_fn(),
            alignment=ui.Alignment.LEFT_CENTER,
            mouse_released_fn=lambda _x, _y, button, _modifier, fn=clicked_fn, is_enabled=enabled_fn: (
                self._on_action_label_clicked(button, fn, is_enabled)
            ),
        )

    def _on_action_label_clicked(
        self, button: int, clicked_fn: Callable[[], None], enabled_fn: Callable[[], bool]
    ) -> None:
        if button != 0 or not enabled_fn():
            return
        clicked_fn()

    def _refresh_action_label_states(self) -> None:
        if self._select_all_label is not None:
            self._select_all_label.enabled = self._is_select_all_enabled()
        if self._deselect_all_label is not None:
            self._deselect_all_label.enabled = self._is_deselect_all_enabled()

    def _is_select_all_enabled(self) -> bool:
        mod_layer_ids = self.mod_layer_ids
        if not mod_layer_ids:
            return False
        selected_ids = self.draft_selected_ids
        if selected_ids is None:
            return False
        return not mod_layer_ids.issubset(selected_ids)

    def _is_deselect_all_enabled(self) -> bool:
        mod_layer_ids = self.mod_layer_ids
        if not mod_layer_ids:
            return False
        selected_ids = self.draft_selected_ids
        if selected_ids is None:
            return True
        return bool(set(selected_ids) & set(mod_layer_ids))

    def _on_search_changed(self, model) -> None:
        if self._model is not None:
            self._model.set_search(model.get_value_as_string())

    def _set_model_listeners_enabled(self, enabled: bool) -> None:
        if self._model is not None:
            self._model.enable_listeners(enabled)

    def _request_expand_tree_items(self) -> None:
        if self._model is None or self._tree_widget is None:
            return
        self._cancel_expand_tree_task()
        self._expand_tree_task = asyncio.ensure_future(self._expand_tree_items_async())

    @omni.usd.handle_exception
    async def _expand_tree_items_async(self) -> None:
        await omni.kit.app.get_app().next_update_async()
        self._expand_tree_items()

    def _expand_tree_items(self) -> None:
        if self._model is None or self._tree_widget is None:
            return
        for item in self._model.get_item_children(recursive=True):
            self._tree_widget.set_expanded(item, True, False)

    def _set_selected_items_expanded(self, expanded: bool) -> None:
        if self._tree_widget is None:
            return
        for item in self._tree_widget.selection:
            if item.can_have_children:
                self._tree_widget.set_expanded(item, expanded, False)

    def _cancel_expand_tree_task(self) -> None:
        if self._expand_tree_task is not None and not self._expand_tree_task.done():
            self._expand_tree_task.cancel()
        self._expand_tree_task = None

    def _reset_draft_selected_ids(self) -> None:
        self.draft_selected_ids = self.selected_ids

    def _prune_draft_selected_ids(self) -> None:
        draft_ids = self.draft_selected_ids
        if draft_ids is None:
            return
        draft_ids.intersection_update(self.mod_layer_ids)
        self.draft_selected_ids = draft_ids

    def _get_all_layer_identifiers(self) -> list[str]:
        context = omni.usd.get_context(self._context_name)
        if not context:
            return []
        stage = context.get_stage()
        if not stage:
            return []
        identifiers = []
        root_layer = stage.GetRootLayer()
        if root_layer is not None:
            identifiers.append(root_layer.identifier)
        identifiers.extend(
            _LayerUtils.get_all_sublayers(stage, include_session_layers=False, include_anonymous_layers=False)
        )
        return list(dict.fromkeys(identifiers))

    def _set_draft_selected_ids_and_refresh(self, ids: set[str] | None) -> None:
        self.draft_selected_ids = ids
        self.refresh()

    def _apply_selection_and_hide(self) -> None:
        self.selected_ids = self.draft_selected_ids
        self.__on_selected_ids_applied(self.selected_ids)
        self.hide()

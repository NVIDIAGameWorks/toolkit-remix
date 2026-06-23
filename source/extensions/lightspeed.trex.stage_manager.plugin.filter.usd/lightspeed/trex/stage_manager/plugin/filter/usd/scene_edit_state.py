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

__all__ = ["SceneEditFilterPlugin", "SceneEditState"]

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

import carb
from lightspeed.layer_manager.core import LayerManagerCore
from lightspeed.trex.source_layer_picker.window import SourceLayerPicker
from omni import ui, usd
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin
from omni.flux.utils.common import EventSubscription
from omni.kit.usd.layers import LayerEventType, get_layer_event_payload, get_layers
from pydantic import Field, PrivateAttr


class SceneEditState(Enum):
    def __new__(cls, value: str, label: str):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.label = label
        return obj

    ALL = ("all", "Show all prims")
    MODIFIED = ("modified", "Modified prims")
    UNEDITED = ("unedited", "Unedited prims")
    UNUSED_EDITS = ("unused_edits", "Unused edits")


# Identifying "mod" opinions by layer type alone is unreliable: sublayers authored by the UI under
# mod.usda usually carry no `lightspeed_layer_type` metadata. LayerManagerCore.get_replacement_layers()
# walks the replacement layer tree (mod.usda + its sublayers, recursive) and returns the full set,
# which is what we use for edit-state membership. This also keeps referenced capture asset layers
# without layer-type metadata visible as unedited when they are outside the replacement tree.

_EMPTY_LAYER_SET = frozenset()


@dataclass(frozen=True)
class _SceneEditPredicateState:
    """Mode-specific state reused while filter_predicate walks Stage Manager items."""

    mode: SceneEditState
    mod_layers: frozenset = _EMPTY_LAYER_SET
    active_set: frozenset = _EMPTY_LAYER_SET


class SceneEditFilterPlugin(StageManagerUSDFilterPlugin):
    _filter_active_fields: ClassVar[tuple[str, ...]] = ("mode",)

    display_name: str = Field(default="Edit State", exclude=True)
    tooltip: str = Field(
        default=(
            "Filter by whether mods have changed these prims.\n"
            "\n"
            "Options:\n"
            "- Show all prims: Show every prim in the scene.\n"
            "- Modified prims: Show prims with at least one edit from the selected mod layer(s).\n"
            "- Unedited prims: Show prims with no opinions from the replacement layer tree.\n"
            "- Unused edits: Show prims with mod edits that are shadowed by a stronger opinion."
        ),
        exclude=True,
    )

    mode: SceneEditState = Field(
        default=SceneEditState.ALL,
        description="Which subset of prims to show based on mod edit state.",
    )

    _layer_manager: LayerManagerCore | None = PrivateAttr(default=None)
    _combobox: ui.ComboBox | None = PrivateAttr(default=None)
    _picker_label: ui.Label | None = PrivateAttr(default=None)
    _picker: SourceLayerPicker | None = PrivateAttr(default=None)
    _picker_selected_ids_sub: EventSubscription | None = PrivateAttr(default=None)
    _stage_event_sub: carb.events.ISubscription | None = PrivateAttr(default=None)
    _layer_event_sub: carb.events.ISubscription | None = PrivateAttr(default=None)
    _bound_context_name: str | None = PrivateAttr(default=None)
    # None = no explicit subset (treat as "all selected"). set[str] = explicit identifier subset.
    _selected_layer_ids: set[str] | None = PrivateAttr(default=None)
    # Caches read via _get_predicate_state(), _get_mod_layers(), and _get_active_set(). Invalidated
    # when mode, layer selection, or the replacement sublayer hierarchy changes.
    _mod_layers_cache: frozenset | None = PrivateAttr(default=None)
    _mod_layer_ids_cache: frozenset[str] | None = PrivateAttr(default=None)
    _active_set_cache: frozenset | None = PrivateAttr(default=None)
    _predicate_state_cache: _SceneEditPredicateState | None = PrivateAttr(default=None)

    def set_context_name(self, name: str):
        if self._bound_context_name == name and self._layer_manager is not None:
            return

        self._destroy_context_services()
        super().set_context_name(name)
        usd_context = usd.get_context(name)
        self._layer_manager = LayerManagerCore(name)
        self._stage_event_sub = usd_context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="SceneEditFilter-StageEvents"
        )
        self._layer_event_sub = (
            get_layers(usd_context)
            .get_event_stream()
            .create_subscription_to_pop(self._on_layer_event, name="SceneEditFilter-LayerEvents")
        )
        self._bound_context_name = name

    def __del__(self):
        # Best-effort cleanup. Python doesn't guarantee __del__ runs, but the host's plugin
        # lifecycle drops the only ref to this plugin at shutdown; the resources released
        # here (layer-event subscription, picker window, LayerManagerCore) all tolerate being
        # left to GC if shutdown skips this path.
        self.destroy()

    def destroy(self):
        self._destroy_context_services()
        self._picker_label = None
        self._combobox = None

    @property
    def selected_layer_ids(self) -> set[str] | None:
        return None if self._selected_layer_ids is None else set(self._selected_layer_ids)

    @property
    def mod_layer_ids(self) -> frozenset[str]:
        if self._mod_layer_ids_cache is None:
            self._mod_layer_ids_cache = frozenset(layer.identifier for layer in self._get_mod_layers())
        return self._mod_layer_ids_cache

    def _destroy_context_services(self):
        if self._picker is not None:
            self._picker.destroy()
            self._picker = None
        self._picker_selected_ids_sub = None
        if self._layer_manager is not None:
            self._layer_manager.destroy()
            self._layer_manager = None
        self._stage_event_sub = None
        self._layer_event_sub = None
        self._bound_context_name = None
        self._selected_layer_ids = None
        self._mod_layers_cache = None
        self._mod_layer_ids_cache = None
        self._active_set_cache = None
        self._predicate_state_cache = None

    def filter_predicate(self, item: StageManagerItem) -> bool:
        if not self.filter_active:
            return True
        if self.mode is SceneEditState.ALL:
            return True
        if self._layer_manager is None:
            return True

        prim = item.data
        if not prim:
            return False

        stack = prim.GetPrimStack()
        if not stack:
            return False

        predicate_state = self._get_predicate_state()

        # A spec is a "mod opinion" iff its layer is mod.usda or one of its (recursive) sublayers.
        # Each branch reuses the mode-specific layer-set view computed by _get_predicate_state().
        match predicate_state.mode:
            case SceneEditState.UNEDITED:
                # Capture references can contribute specs from untyped asset layers, so metadata-only
                # detection would hide truly unedited lights, materials, and meshes.
                mod_layers = predicate_state.mod_layers
                return not any(spec.layer in mod_layers for spec in stack)
            case SceneEditState.MODIFIED:
                active_set = predicate_state.active_set
                return any(spec.layer in active_set for spec in stack)
            case SceneEditState.UNUSED_EDITS:
                mod_layers = predicate_state.mod_layers
                # Shadowed opinion on a selected mod layer AND strongest is non-mod.
                if stack[0].layer in mod_layers:
                    return False
                active_set = predicate_state.active_set
                return any(spec.layer in active_set for spec in stack[1:])
        return False

    def _refresh_filter_active(self) -> None:
        self._predicate_state_cache = None
        self.filter_active = self.mode is not SceneEditState.ALL

    def _get_predicate_state(self) -> _SceneEditPredicateState:
        if self._predicate_state_cache is None:
            match self.mode:
                case SceneEditState.UNEDITED:
                    self._predicate_state_cache = _SceneEditPredicateState(
                        mode=self.mode,
                        mod_layers=self._get_mod_layers(),
                    )
                case SceneEditState.MODIFIED:
                    self._predicate_state_cache = _SceneEditPredicateState(
                        mode=self.mode,
                        active_set=self._get_active_set(),
                    )
                case SceneEditState.UNUSED_EDITS:
                    mod_layers = self._get_mod_layers()
                    self._predicate_state_cache = _SceneEditPredicateState(
                        mode=self.mode,
                        mod_layers=mod_layers,
                        active_set=self._get_active_set(mod_layers),
                    )
                case _:
                    self._predicate_state_cache = _SceneEditPredicateState(mode=self.mode)
        return self._predicate_state_cache

    def _get_mod_layers(self) -> frozenset:
        if self._mod_layers_cache is None:
            if self._layer_manager is None:
                return frozenset()
            self._mod_layers_cache = frozenset(self._layer_manager.get_replacement_layers())
        return self._mod_layers_cache

    def _get_active_set(self, mod_layers: frozenset | None = None) -> frozenset:
        if self._active_set_cache is None:
            if mod_layers is None:
                mod_layers = self._get_mod_layers()
            if self._selected_layer_ids is None:
                self._active_set_cache = mod_layers
            else:
                self._active_set_cache = frozenset(
                    layer for layer in mod_layers if layer.identifier in self._selected_layer_ids
                )
        return self._active_set_cache

    def build_ui(self):
        states = list(SceneEditState)
        with ui.HStack(spacing=ui.Pixel(8), tooltip=self.tooltip):
            ui.Spacer(width=0)
            ui.Label(self.display_name, width=ui.Pixel(self._LABEL_WIDTH), alignment=ui.Alignment.RIGHT)
            with ui.VStack(spacing=ui.Pixel(2)):
                self._combobox = ui.ComboBox(
                    states.index(self.mode),
                    *(state.label for state in states),
                )
                self._combobox.model.add_item_changed_fn(self._on_mode_changed)
                self._picker_label = ui.Label(
                    "Select Source Layers",
                    name="FilterSectionAction",
                    alignment=ui.Alignment.LEFT,
                    tooltip="Source Layer(s)",
                    mouse_released_fn=self._on_picker_button_clicked,
                    enabled=self._picker_button_enabled(),
                )

    def _picker_button_enabled(self) -> bool:
        return self.mode in (SceneEditState.MODIFIED, SceneEditState.UNUSED_EDITS)

    def _on_mode_changed(self, model: ui.AbstractItemModel, _item: ui.AbstractItem):
        selected_index = model.get_item_value_model().get_value_as_int()
        self.mode = list(SceneEditState)[selected_index]
        if self._picker_label is not None:
            self._picker_label.enabled = self._picker_button_enabled()
        self._filter_items_changed()

    def _on_picker_button_clicked(self, _x, _y, button, _modifier):
        if button != 0 or not self._picker_button_enabled():
            return
        self._open_source_layer_picker()

    def _open_source_layer_picker(self):
        if self._layer_manager is None:
            return
        if self._picker is None:
            self._picker = SourceLayerPicker(
                context_name=self._context_name,
                mod_layer_ids=self.mod_layer_ids,
                selected_ids=self.selected_layer_ids,
            )
            self._picker_selected_ids_sub = self._picker.subscribe_selected_ids_applied(self.set_selected_layer_ids)
        else:
            self._picker.mod_layer_ids = self.mod_layer_ids
            self._picker.selected_ids = self.selected_layer_ids
        self._picker.show()

    def set_selected_layer_ids(self, ids: set[str] | None):
        # None is the "all mod layers selected" sentinel; the picker uses it to flag "Select all"
        # so newly added sublayers are picked up automatically. A concrete set freezes the
        # membership at the time of the call.
        self._selected_layer_ids = set(ids) if ids is not None else None
        self._active_set_cache = None
        self._predicate_state_cache = None
        self._filter_items_changed()

    def _on_stage_event(self, event):
        if event.type == int(usd.StageEventType.OPENED):
            self._sync_to_stage_open()

    def _on_layer_event(self, event):
        payload = get_layer_event_payload(event)
        if payload is None:
            return
        if payload.event_type == LayerEventType.SUBLAYERS_CHANGED:
            self.sync_to_layer_changes()

    def _sync_to_stage_open(self):
        # A new stage can open in the same USD context, so set_context_name() will not always
        # run. Reset explicit source-layer selection here to avoid carrying old project layer
        # identifiers into the new stage.
        self._selected_layer_ids = None
        if self._picker is not None:
            self._picker.destroy()
            self._picker = None
            self._picker_selected_ids_sub = None
        self.sync_to_layer_changes()

    def sync_to_layer_changes(self):
        # New sublayer policy: when an explicit subset is active, new layers come in unchecked.
        # Existing layers that vanished are dropped from the selection. When _selected_layer_ids is
        # None, leave it None; the predicate continues to treat all mod layers as selected.
        self._mod_layers_cache = None
        self._mod_layer_ids_cache = None
        self._active_set_cache = None
        self._predicate_state_cache = None
        if self._selected_layer_ids is not None:
            current_ids = self.mod_layer_ids
            self._selected_layer_ids &= current_ids
        if self._picker is not None:
            self._picker.mod_layer_ids = self.mod_layer_ids
            self._picker.selected_ids = self.selected_layer_ids
            self._picker.refresh()
        if self.mode is not SceneEditState.ALL:
            self._filter_items_changed()

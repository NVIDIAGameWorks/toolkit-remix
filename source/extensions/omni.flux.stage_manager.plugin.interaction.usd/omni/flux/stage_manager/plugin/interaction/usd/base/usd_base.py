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

import abc
from asyncio import Future, ensure_future

import omni.kit.app
import omni.kit.usd.layers as _layers
import omni.usd
from omni.flux.stage_manager.factory import StageManagerDataTypes as _StageManagerDataTypes
from omni.flux.stage_manager.factory import StageManagerTreeItem as _StageManagerTreeItem
from omni.flux.stage_manager.factory.plugins import StageManagerInteractionPlugin as _StageManagerInteractionPlugin
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common.utils import get_omni_prims as _get_omni_prims
from pxr import Sdf, Usd
from pydantic import BaseModel, Field, PrivateAttr


class RefreshRule(BaseModel):
    use_name: bool = Field(True, description="Whether to use the prim name or full prim path to match")
    start: str = Field("", description="String to match the start of the affected prims' names")
    end: str = Field("", description="String to match the end of the affected prims' names")


class USDEventFilteringRules(BaseModel):
    ignore_properties_events: list[str] = Field(["xformOpOrder"], description="List of property names to ignore")
    ignore_paths_events: list[str] = Field(
        ["/RootNode/Camera"],
        description="List of prim paths to ignore (Only exact matches for the Prim Path will be ignored)",
    )
    ignore_xform_events: bool = Field(
        True, description="Whether the XForm events emitted by the USD listener should be ignored or not"
    )
    ignore_omni_prims_events: bool = Field(
        True, description="Whether the events emitted on Omniverse Prims should be ignored or not"
    )
    ignore_custom_layer_data_events: bool = Field(
        True, description="Whether the events emitted for Custom Layer Data should be ignored or not"
    )
    force_refresh_rules: list[RefreshRule] = Field(
        [], description="List of rules to force a refresh of the tree items rather than a delegate refresh"
    )


class StageManagerUSDInteractionPlugin(_StageManagerInteractionPlugin, abc.ABC):
    synchronize_selection: bool = Field(True, description="Synchronize the USD selection between the stage and the UI")
    filtering_rules: USDEventFilteringRules = Field(
        USDEventFilteringRules(), description="Rules used for the USD events in the callback"
    )

    _context_name: str = PrivateAttr("")
    _selection_update_lock: bool = PrivateAttr(False)
    _ignore_selection_update: bool = PrivateAttr(False)
    _listener_event_occurred_subs: list[_EventSubscription] = PrivateAttr([])
    _items_changed_task: Future | None = PrivateAttr(None)

    @classmethod
    @property
    def compatible_data_type(cls):
        return _StageManagerDataTypes.USD

    @omni.usd.handle_exception
    async def _update_context_items(self):
        if not self._is_active:
            return

        self._set_context_name()

        await super()._update_context_items()

    def _setup_listeners(self):
        # Context Will be a USD Context, so we can subscribe to the USD Base Context events
        self._listener_event_occurred_subs.extend(
            self._context.subscribe_listener_event_occurred(_layers.LayerEventType, self._on_layer_event_occurred)
        )
        self._listener_event_occurred_subs.extend(
            self._context.subscribe_listener_event_occurred(omni.usd.StageEventType, self._on_stage_event_occurred)
        )
        self._listener_event_occurred_subs.extend(
            self._context.subscribe_listener_event_occurred(Usd.Notice.ObjectsChanged, self._on_usd_event_occurred)
        )

    def _clear_listeners(self):
        self._listener_event_occurred_subs.clear()

    def _set_context_name(self):
        """
        Set the context name in the interaction and all children USD plugins using the USD context plugin.
        """
        context_attribute_name = "context_name"
        set_context_method_name = "set_context_name"

        if not hasattr(self._context, context_attribute_name):
            return

        value = getattr(self._context, context_attribute_name, "")
        self._context_name = value

        # Propagate the value
        if hasattr(self.tree, set_context_method_name):
            self.tree.set_context_name(value)

        for filter_plugin in self.filters:
            if hasattr(filter_plugin, set_context_method_name):
                filter_plugin.set_context_name(value)

        for column_plugin in self.columns:
            if hasattr(column_plugin, set_context_method_name):
                column_plugin.set_context_name(value)

            for widget_plugin in column_plugin.widgets:
                if hasattr(widget_plugin, set_context_method_name):
                    widget_plugin.set_context_name(value)

    @_ignore_function_decorator(attrs=["_selection_update_lock"])
    def _update_tree_selection(self):
        # Cache the value to be used in `_update_expansion_states_deferred`
        scroll_to_selection = not self._ignore_selection_update
        # Make sure to reset the value so next time we update the tree selection we have the right value
        self._ignore_selection_update = False

        if not self.synchronize_selection or not self._is_active:
            return

        # Get USD selection
        selection = self._get_selection()

        if selection:
            self._item_expansion_states.clear()

        def is_selected_item(selected_prim_paths, item) -> bool:
            should_select = item.data and item.data.GetPath() in selected_prim_paths

            # Expand the selected items and their parents
            if should_select:
                self._item_expansion_states[hash(item)] = should_select
                parent = item.parent
                while parent:
                    self._item_expansion_states[hash(parent)] = should_select
                    parent = parent.parent

            return should_select

        self._tree_widget.selection = self.tree.model.find_items(lambda item: is_selected_item(selection, item))

        if self._update_expansion_task:  # noqa PLE0203
            self._update_expansion_task.cancel()  # noqa PLE0203
        self._update_expansion_task = ensure_future(
            self._update_expansion_states_deferred(scroll_to_selection_override=scroll_to_selection)
        )

    def _get_selection(self):
        return omni.usd.get_context(self._context_name).get_selection().get_selected_prim_paths()

    def _on_selection_changed(self, items: list[_StageManagerTreeItem]):
        if self._selection_update_lock or not self.synchronize_selection:
            return

        # Will trigger _on_stage_event_occurred -> _update_tree_selection -> self._ignore_selection_update = False
        self._ignore_selection_update = True

        selection_prim_paths = [str(item.data.GetPath()) for item in items if item.data]
        selection = self._get_selection()
        if selection != selection_prim_paths:
            omni.usd.get_context(self._context_name).get_selection().set_selected_prim_paths(selection_prim_paths)

    def _on_layer_event_occurred(self, event_type: _layers.LayerEventType):
        """
        Callback for layer events.

        Args:
            event_type: The `LayerEventType` object containing the layer event type.
        """
        if event_type in [_layers.LayerEventType.MUTENESS_STATE_CHANGED, _layers.LayerEventType.SUBLAYERS_CHANGED]:
            self._queue_update()

    def _on_stage_event_occurred(self, event_type: omni.usd.StageEventType):
        """
        Callback for stage events.

        Args:
            event_type: The `omni.usd.StageEventType` object containing the stage event type.
        """
        if event_type == omni.usd.StageEventType.SELECTION_CHANGED:
            self._update_tree_selection()
        elif event_type == omni.usd.StageEventType.ACTIVE_LIGHT_COUNTS_CHANGED:
            self._queue_update()

    def _on_usd_event_occurred(self, notice: Usd.Notice.ObjectsChanged):
        """
        Callback for USD events.

        Args:
            notice: The `Usd.Notice.ObjectsChanged` object containing the changed paths.
        """
        changed_info_only_paths = notice.GetChangedInfoOnlyPaths()
        resynced_paths = notice.GetResyncedPaths()

        def should_refresh(paths: set, exclude_list: set | None = None):
            for path in paths:
                if path.IsPropertyPath():
                    # Don't refresh if the update comes from ignored properties
                    if path.name in self.filtering_rules.ignore_properties_events:
                        continue
                    # # Don't refresh if the update comes from Xform properties
                    if self.filtering_rules.ignore_xform_events and path.name.startswith("xformOp:"):
                        continue
                # Get the prim path for the changed path
                prim_path = path.GetPrimPath()
                # If the path is in the exclude list, don't refresh
                if exclude_list is not None and prim_path in exclude_list:
                    continue
                # Don't refresh if the update comes from ignored paths
                if str(prim_path) in self.filtering_rules.ignore_paths_events:
                    continue
                # Don't refresh the stage manager when Omni Prims are updated
                if self.filtering_rules.ignore_omni_prims_events and any(
                    path.HasPrefix(omni_path) for omni_path in _get_omni_prims()
                ):
                    continue
                # Don't refresh the stage manager when Custom Layer Data is updated
                # This should include camera updates on newer mods
                changed_fields = notice.GetChangedFields(path)
                if (
                    self.filtering_rules.ignore_custom_layer_data_events
                    and bool(changed_fields)
                    and all(field == "customLayerData" for field in changed_fields)
                ):
                    continue
                return True
            return False

        # Check if the context items should be updated first
        # If `resynced_paths` is empty, no need to compute the exclude list
        if resynced_paths and should_refresh(
            resynced_paths, exclude_list={p.GetPrimPath() for p in changed_info_only_paths}
        ):
            self._queue_update(update_context_items=True)
        # If not, check if the delegates should be updated
        # If `changed_info_only_paths` is empty, no need to compute the exclude list
        elif changed_info_only_paths and should_refresh(
            changed_info_only_paths, exclude_list={p.GetPrimPath() for p in resynced_paths}
        ):
            update_context_items = False
            if any(p for p in changed_info_only_paths if self._evaluate_filtering_rules(p)):
                update_context_items = True
            self._queue_update(update_context_items=update_context_items)

    def _evaluate_filtering_rules(self, prim_path: Sdf.Path) -> bool:
        for rule in self.filtering_rules.force_refresh_rules:
            # Choose the string based on rule.use_name
            value = prim_path.name if rule.use_name else str(prim_path)
            if rule.start and rule.end:
                if value.startswith(rule.start) and value.endswith(rule.end):
                    return True
            elif rule.start:
                if value.startswith(rule.start):
                    return True
            elif rule.end:  # noqa SIM102
                if value.endswith(rule.start):
                    return True
        return False

    def _on_item_changed(self, model, item):
        # Convert `_on_item_changed` to an async method since `_update_context_items` is also async
        if self._items_changed_task:
            self._items_changed_task.cancel()
        self._items_changed_task = ensure_future(self._on_item_changed_async(model, item))

    @omni.usd.handle_exception
    async def _on_item_changed_async(self, model, item):
        """
        Async implementation for the `_on_item_changed` function. Waits 1 frame between the super function and selection
        update calls to ensure the items are rendered before updating the selection
        """
        super()._on_item_changed(model, item)

        # Wait for the updated items to be rendered
        await omni.kit.app.get_app().next_update_async()
        self._update_tree_selection()

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
import traceback
from asyncio import Future, ensure_future

import carb
import omni.kit.app
import omni.kit.usd.layers as _layers
import omni.usd
from omni.flux.stage_manager.factory import StageManagerDataTypes as _StageManagerDataTypes
from omni.flux.stage_manager.factory import StageManagerTreeItem as _StageManagerTreeItem
from omni.flux.stage_manager.factory.plugins import StageManagerInteractionPlugin as _StageManagerInteractionPlugin
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.prims import get_omni_prims as _get_omni_prims
from omni.flux.utils.common.prims import get_proto_from_prim as _get_proto_from_prim
from pxr import Sdf, Usd
from pydantic import BaseModel, Field, PrivateAttr


class RefreshRule(BaseModel):
    use_name: bool = Field(default=True, description="Whether to use the prim name or full prim path to match")
    start: str = Field(default="", description="String to match the start of the affected prims' names")
    end: str = Field(default="", description="String to match the end of the affected prims' names")


class USDEventFilteringRules(BaseModel):
    ignore_properties_events: list[str] = Field(
        default=["xformOpOrder"], description="List of property names to ignore"
    )
    ignore_property_prefix_events: list[str] = Field(
        default=["ui:"], description="List of property name prefixes to ignore"
    )
    ignore_paths_events: list[str] = Field(
        default=["/RootNode/Camera"],
        description="List of prim paths to ignore (Only exact matches for the Prim Path will be ignored)",
    )
    ignore_xform_events: bool = Field(
        default=True, description="Whether the XForm events emitted by the USD listener should be ignored or not"
    )
    ignore_omni_prims_events: bool = Field(
        default=True, description="Whether the events emitted on Omniverse Prims should be ignored or not"
    )
    ignore_custom_layer_data_events: bool = Field(
        default=True, description="Whether the events emitted for Custom Layer Data should be ignored or not"
    )
    force_refresh_rules: list[RefreshRule] = Field(
        default=[], description="List of rules to force a refresh of the tree items rather than a delegate refresh"
    )


class StageManagerUSDInteractionPlugin(_StageManagerInteractionPlugin, abc.ABC):
    synchronize_selection: bool = Field(
        default=True, description="Synchronize the USD selection between the stage and the UI"
    )
    filtering_rules: USDEventFilteringRules = Field(
        default=USDEventFilteringRules(), description="Rules used for the USD events in the callback"
    )

    compatible_data_type: _StageManagerDataTypes = Field(default=_StageManagerDataTypes.USD, exclude=True)

    _context_name: str = PrivateAttr(default="")
    _selection_update_lock: bool = PrivateAttr(default=False)
    _ignore_selection_update: bool = PrivateAttr(default=False)
    _programmatic_tree_selection_paths: tuple[str, ...] | None = PrivateAttr(default=None)
    _listener_event_occurred_subs: list[_EventSubscription] = PrivateAttr(default=[])
    _items_changed_task: Future | None = PrivateAttr(default=None)
    _tree_selection_task: Future | None = PrivateAttr(default=None)
    _tree_selection_update_pending: bool = PrivateAttr(default=False)

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

    def on_hidden(self):
        """Cancel pending USD selection work before destroying the interaction UI."""
        self._cancel_selection_tasks()
        super().on_hidden()

    def set_active(self, value: bool):
        if not value:
            self._cancel_selection_tasks()
        super().set_active(value)

    def destroy(self):
        """Cancel pending USD selection work before destroying the interaction."""
        self._cancel_selection_tasks()
        super().destroy()

    def _cancel_selection_tasks(self):
        self._tree_selection_update_pending = False
        if self._tree_selection_task:
            self._tree_selection_task.cancel()
            self._tree_selection_task = None
        if self._items_changed_task:
            self._items_changed_task.cancel()
            self._items_changed_task = None

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

        for filter_plugin in self.additional_filters:
            if hasattr(filter_plugin, set_context_method_name):
                filter_plugin.set_context_name(value)

        for column_plugin in self.columns:
            if hasattr(column_plugin, set_context_method_name):
                column_plugin.set_context_name(value)

            for widget_plugin in column_plugin.widgets:
                if hasattr(widget_plugin, set_context_method_name):
                    widget_plugin.set_context_name(value)

    def _update_tree_selection(self) -> Future | None:
        """
        Queue an async task to update the tree selection without blocking the UI.
        """
        if self._selection_update_lock or (
            self._tree_selection_task is not None and not self._tree_selection_task.done()
        ):
            self._tree_selection_update_pending = True
            return self._tree_selection_task

        self._selection_update_lock = True
        try:
            if self._tree_selection_task:
                self._tree_selection_task.cancel()
            self._tree_selection_task = ensure_future(self._update_tree_selection_async())
            self._tree_selection_task.add_done_callback(self._log_background_task_exception)
            return self._tree_selection_task
        finally:
            self._selection_update_lock = False

    async def _update_tree_selection_async(self):
        """
        Async implementation of tree selection update.
        """

        while True:
            self._tree_selection_update_pending = False

            # Make sure to reset the value so next time we update the tree selection we have the right value
            self._ignore_selection_update = False

            if not self.synchronize_selection or not self._is_active:
                return

            selection = set(self._get_selection())
            matching_items = []
            for path in selection:
                matching_items.extend(self.tree.model.get_items_by_path(path))

            task_cancelled = (
                self._tree_selection_task is None or self._tree_selection_task.cancelled() or not self._is_active
            )
            if task_cancelled:
                return

            await self._set_tree_widget_selection_async(matching_items)
            if not self._tree_selection_update_pending:
                return

    async def _set_tree_widget_selection_async(self, items: list[_StageManagerTreeItem]):
        # Lock to prevent _on_selection_changed from writing programmatic tree selection changes back to USD.
        self._set_programmatic_tree_selection_paths(items)
        self._selection_update_lock = True
        try:
            await self._tree_widget.set_selection_async(items)
            self.tree.model.selection = items
        finally:
            self._selection_update_lock = False

    def _set_programmatic_tree_selection_paths(self, items: list[_StageManagerTreeItem]):
        self._programmatic_tree_selection_paths = self._get_tree_item_paths(items)

    def _clear_programmatic_tree_selection_paths(self):
        self._programmatic_tree_selection_paths = None

    @staticmethod
    def _get_tree_item_paths(items: list[_StageManagerTreeItem]) -> tuple[str, ...]:
        return tuple(str(item.path) for item in items if item.data is not None and item.path)

    def _get_selection(self) -> list[str]:
        return omni.usd.get_context(self._context_name).get_selection().get_selected_prim_paths()

    def _get_refresh_expand_filtered_roots(self) -> bool:
        return self._should_expand_filtered_items()

    def _is_tree_model_refresh_pending(self) -> bool:
        return bool(
            (self._model_refresh_task and not self._model_refresh_task.done())
            or (self._items_changed_task and not self._items_changed_task.done())
        )

    def _should_ignore_empty_selection_from_tree_refresh(
        self,
        selection_prim_paths: tuple[str, ...],
        previous_selection_prim_paths: tuple[str, ...],
    ) -> bool:
        if selection_prim_paths or not previous_selection_prim_paths or not self._is_tree_model_refresh_pending():
            return False
        return set(self._get_selection()) == set(previous_selection_prim_paths)

    def _on_selection_changed(self, items: list[_StageManagerTreeItem]):
        """Synchronize tree selection back to USD without rewriting order-only changes.

        Args:
            items: Selected tree items that may map to USD prim paths.
        """
        previous_selection_prim_paths = self._get_tree_item_paths(self.tree.model.selection)
        selection_prim_paths = self._get_tree_item_paths(items)
        # Tree rebuilds can briefly emit [] before current scene selection is reapplied. If USD still
        # has the previous tree selection, preserve it instead of treating the callback as user clear.
        if self._should_ignore_empty_selection_from_tree_refresh(selection_prim_paths, previous_selection_prim_paths):
            return

        super()._on_selection_changed(items)  # updates model.selection before USD sync

        is_programmatic_tree_selection = (
            self._programmatic_tree_selection_paths is not None
            and selection_prim_paths == self._programmatic_tree_selection_paths
        )
        # Tree widgets can emit selection callbacks after set_selection_async returns.
        # Keep the marker through unrelated callbacks so the delayed programmatic callback
        # cannot later overwrite a real user selection.
        if is_programmatic_tree_selection:
            self._clear_programmatic_tree_selection_paths()

        if self._selection_update_lock or is_programmatic_tree_selection or not self.synchronize_selection:
            return

        # Will trigger _on_stage_event_occurred -> _update_tree_selection -> self._ignore_selection_update = False
        self._ignore_selection_update = True

        selection = self._get_selection()
        # Only synchronize membership changes back to USD.
        # Order-only differences are owned by the upstream selection source and
        # must not be rewritten from the tree, or we can clobber the active
        # selection ordering that downstream property panels rely on.
        if set(selection) != set(selection_prim_paths):
            omni.usd.get_context(self._context_name).get_selection().set_selected_prim_paths(list(selection_prim_paths))

    def _on_layer_event_occurred(self, event_type: _layers.LayerEventType):
        """
        Callback for layer events.

        Args:
            event_type: The `LayerEventType` object containing the layer event type.
        """
        if event_type in {_layers.LayerEventType.MUTENESS_STATE_CHANGED, _layers.LayerEventType.SUBLAYERS_CHANGED}:
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

        def is_nickname_path(path):
            return path.IsPropertyPath() and path.name == "nickname"

        # Check for nickname-only changes and handle with lightweight update
        nickname_prim_paths = set()
        for path in changed_info_only_paths:
            if is_nickname_path(path):
                nickname_prim_paths.add(path.GetPrimPath())

        # Also check resynced paths for nickname attribute creation
        for path in resynced_paths:
            if is_nickname_path(path):
                nickname_prim_paths.add(path.GetPrimPath())

        if nickname_prim_paths:
            # Filter out nickname changes from the paths we'll check below
            non_nickname_info_paths = [p for p in changed_info_only_paths if not is_nickname_path(p)]
            non_nickname_resync_paths = [p for p in resynced_paths if not is_nickname_path(p)]

            # If only nicknames changed, do lightweight update and return
            if not non_nickname_info_paths and not non_nickname_resync_paths:
                self._update_nickname_items(nickname_prim_paths)
                return

            # Otherwise, do lightweight update for nicknames and continue with normal processing
            self._update_nickname_items(nickname_prim_paths)
            # Update the paths for further processing
            changed_info_only_paths = non_nickname_info_paths
            resynced_paths = non_nickname_resync_paths

        def get_refreshable_paths(paths: list):
            result = []
            for path in paths:
                if path.IsPropertyPath():
                    # Don't refresh if the update comes from ignored properties
                    if path.name in self.filtering_rules.ignore_properties_events:
                        continue
                    # Don't refresh if the update comes from ignored property prefixes
                    if any(
                        path.name.startswith(prefix) for prefix in self.filtering_rules.ignore_property_prefix_events
                    ):
                        continue
                    # # Don't refresh if the update comes from Xform properties
                    if self.filtering_rules.ignore_xform_events and path.name.startswith("xformOp:"):
                        continue
                # Get the prim path for the changed path
                prim_path = path.GetPrimPath()
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
                result.append(path)
            return result

        def forces_context_item_refresh(path: Sdf.Path):
            if not path.IsPropertyPath():
                return True
            return self._evaluate_filtering_rules(path)

        refreshable_resynced_paths = get_refreshable_paths(resynced_paths) if resynced_paths else []
        refreshable_changed_info_only_paths = (
            get_refreshable_paths(changed_info_only_paths) if changed_info_only_paths else []
        )
        if not refreshable_resynced_paths and not refreshable_changed_info_only_paths:
            return

        update_context_items = any(forces_context_item_refresh(p) for p in refreshable_resynced_paths) or any(
            forces_context_item_refresh(p) for p in refreshable_changed_info_only_paths
        )
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
            elif rule.end:  # noqa: SIM102
                if value.endswith(rule.end):
                    return True
        return False

    def _update_nickname_items(self, prim_paths: set):
        """
        Lightweight update for items whose nicknames changed.
        Only reloads the nickname and rebuilds the affected item widgets.

        Args:
            prim_paths: Set of Sdf.Path objects for prims whose nicknames changed
        """

        def matches_prim_path(item: _StageManagerTreeItem) -> bool:
            if not item.data:
                return False
            prim = _get_proto_from_prim(item.data)
            return prim and (prim.GetPath() in prim_paths)

        # Find affected items and reload their nicknames
        for item in self.tree.model.find_items(matches_prim_path):
            self.tree.model.notify_item_changed(item)  # Rebuild only this widget

    def _should_expand_filtered_items(self) -> bool:
        return any(filter_plugin.enabled and filter_plugin.filter_active for filter_plugin in self.filters) or any(
            filter_plugin.filter_active for filter_plugin in self.additional_filters
        )

    def _on_item_changed(self, model, item):
        # Convert `_on_item_changed` to an async method since `_update_context_items` is also async
        if self._items_changed_task:
            self._items_changed_task.cancel()
        self._items_changed_task = ensure_future(self._on_item_changed_async(model, item))
        self._items_changed_task.add_done_callback(self._log_background_task_exception)

    @staticmethod
    def _log_background_task_exception(task: Future):
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:  # noqa: BLE001
            carb.log_error(traceback.format_exc())

    async def _on_item_changed_async(self, model, item):
        """
        Async implementation for the `_on_item_changed` function. Waits 1 frame between the super function and selection
        update calls to ensure the items are rendered before updating the selection
        """
        super()._on_item_changed(model, item)

        # Wait for the updated items to be rendered
        await omni.kit.app.get_app().next_update_async()
        selection_task = self._update_tree_selection()
        if selection_task is not None:
            await selection_task

    async def _wait_for_post_refresh_work(self):
        """Wait until rebuilt rows have synchronized and framed the live USD selection."""
        items_changed_task = self._items_changed_task
        if items_changed_task is not None:
            await items_changed_task

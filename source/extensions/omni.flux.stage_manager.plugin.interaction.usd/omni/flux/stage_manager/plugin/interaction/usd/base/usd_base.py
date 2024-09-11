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
from typing import Iterable

import omni.kit.app
import omni.kit.usd.layers as _layers
import omni.usd
from omni.flux.stage_manager.factory import StageManagerDataTypes as _StageManagerDataTypes
from omni.flux.stage_manager.factory.plugins import StageManagerInteractionPlugin as _StageManagerInteractionPlugin
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.decorators import (
    ignore_function_decorator_and_reset_value as _ignore_function_decorator_and_reset_value,
)
from omni.flux.utils.common.utils import get_omni_prims as _get_omni_prims
from pxr import Usd
from pydantic import Field, PrivateAttr


class StageManagerUSDInteractionPlugin(_StageManagerInteractionPlugin, abc.ABC):
    synchronize_selection: bool = Field(True, description="Synchronize the USD selection between the stage and the UI")

    _context_name: str = PrivateAttr("")
    _selection_update_lock: bool = PrivateAttr(False)
    _listener_event_occurred_subs: list[_EventSubscription] = PrivateAttr([])
    _update_context_task: Future | None = PrivateAttr(None)

    @classmethod
    @property
    def compatible_data_type(cls):
        return _StageManagerDataTypes.USD

    @classmethod
    @property
    def recursive_traversal(cls) -> bool:
        """
        Whether the interaction plugin should perform a recursive traversal of the context items.

        Returns:
            bool: True if the interaction plugin should perform a recursive traversal, False otherwise.
        """
        return False

    @classmethod
    @property
    def _select_all_children(cls) -> bool:
        return True

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

    def _on_layer_event_occurred(self, event_type: _layers.LayerEventType):
        if event_type in [_layers.LayerEventType.MUTENESS_STATE_CHANGED, _layers.LayerEventType.SUBLAYERS_CHANGED]:
            self._update_context_items()

    def _on_stage_event_occurred(self, event_type: omni.usd.StageEventType):
        if event_type == omni.usd.StageEventType.SELECTION_CHANGED:
            self._update_tree_selection()
        elif event_type == omni.usd.StageEventType.ACTIVE_LIGHT_COUNTS_CHANGED:
            self._update_context_items()

    def _on_usd_event_occurred(self, notice: Usd.Notice.ObjectsChanged):
        refresh = False
        for path in notice.GetChangedInfoOnlyPaths() + notice.GetResyncedPaths():
            # Don't refresh the stage manager when Omni Prims are updated
            if any(path.HasPrefix(omni_path) for omni_path in _get_omni_prims()):
                continue
            # Don't refresh the stage manager when Custom Layer Data is updated
            if any(field == "customLayerData" for field in notice.GetChangedFields(path)):
                continue
            refresh = True

        if not refresh:
            return

        self._update_context_items()

    def _update_context_items(self):
        # Use a deferred method to combine all the updates caught within 1 frame into a single call
        if self._update_context_task:
            self._update_context_task.cancel()
        self._update_context_task = ensure_future(self._update_context_items_deferred())

    @omni.usd.handle_exception
    async def _update_context_items_deferred(self):
        await omni.kit.app.get_app().next_update_async()

        self._set_context_name()

        context_items = self._context.get_items()
        if self.recursive_traversal:
            context_items = self._traverse_children_recursive(context_items)
        else:
            context_items = self._filter_context_items(context_items)

        self.tree.model.context_items = context_items
        self.tree.model.refresh()

        self._update_tree_selection()

    def _set_context_name(self):
        """
        Set the context name in the interaction and all children USD plugins using the USD context plugin.
        """
        attribute_name = "context_name"

        if not hasattr(self._context, attribute_name):
            return

        value = getattr(self._context, attribute_name, "")
        self._context_name = value

        # Propagate the value
        if hasattr(self.tree, attribute_name):
            self.tree.context_name = value

        for filter_plugin in self.filters:
            if hasattr(filter_plugin, attribute_name):
                filter_plugin.context_name = value

        for column_plugin in self.columns:
            if hasattr(column_plugin, attribute_name):
                column_plugin.context_name = value

            for widget_plugin in column_plugin.widgets:
                if hasattr(widget_plugin, attribute_name):
                    widget_plugin.context_name = value

    def _traverse_children_recursive(self, prims: Iterable[Usd.Prim], filter_prims: bool = True) -> list[Usd.Prim]:
        """
        Get a filtered list of all the prims and their children recursively.

        Args:
            prims: The list of prims to traverse

        Returns:
            A filtered list of all the prims and their children
        """
        filtered_prims = self._filter_context_items(prims) if filter_prims else list(prims)
        children = filtered_prims.copy()
        for prim in filtered_prims:
            children.extend(
                self._traverse_children_recursive(
                    prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate), filter_prims=filter_prims
                )
            )
        return children

    @_ignore_function_decorator_and_reset_value(attrs={"_selection_update_lock": True})
    def _update_tree_selection(self):
        if not self.synchronize_selection:
            return

        selection = omni.usd.get_context(self._context_name).get_selection().get_selected_prim_paths()

        if selection:
            self._item_expansion_states.clear()

        def is_selected_item(selected_prim_paths, item) -> bool:
            prim = item.data.get("prim")
            should_select = prim and prim.GetPath() in selected_prim_paths

            # Expand the selected items and their parents
            if should_select:
                self._item_expansion_states[hash(item)] = should_select
                parent = item.parent
                while parent:
                    self._item_expansion_states[hash(parent)] = should_select
                    parent = parent.parent

            return should_select

        self.tree_widget.selection = self.tree.model.find_items(lambda item: is_selected_item(selection, item))
        self._update_expansion_states()

    def _on_selection_changed(self, items):
        if self._selection_update_lock or not self.synchronize_selection:
            return

        selection_prim_paths = [str(item.data.get("prim").GetPath()) for item in items if item.data.get("prim")]
        selection = omni.usd.get_context(self._context_name).get_selection()
        if selection.get_selected_prim_paths() != selection_prim_paths:
            selection.set_selected_prim_paths(selection_prim_paths)

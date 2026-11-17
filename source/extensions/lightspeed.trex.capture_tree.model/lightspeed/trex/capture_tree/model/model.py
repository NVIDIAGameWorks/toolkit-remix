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

import asyncio

from carb.eventdispatcher import get_eventdispatcher
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCoreSetup
from omni import ui, usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import deferred_destroy_tasks as _deferred_destroy_tasks
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.usd import layers as _layers

from .items import CaptureTreeItem

HEADER_DICT = {
    0: ("Capture Layer", "Capture layer loaded in the stage"),
    1: ("Replaced", "Number of replaced prims in the given capture"),
}


class CaptureTreeModel(ui.AbstractItemModel):
    """List model of actions"""

    def __init__(self, context_name, show_progress: bool = True):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_show_progress": None,
            "_core_capture": None,
            "_core_replacement": None,
            "_stage_event_sub": None,
            "_layer_event_sub": None,
            "_fetch_task": None,
            "_progress_cache": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._show_progress = show_progress

        self._core_capture = _CaptureCoreSetup(context_name)
        self._core_replacement = _ReplacementCoreSetup(context_name)

        self._stage_event_sub = None
        self._layer_event_sub = None
        self._fetch_task = None

        self.__children = []
        # Cache for progress data accessible by path
        self._progress_cache: dict[str, tuple[int, int]] = {}

        # Events
        self.__on_progress_updated = _Event()
        self.__on_stage_opened_or_closed = _Event()
        self.__on_sublayers_changed = _Event()

    def refresh(self, paths: list[tuple[str, str | None]]):
        """Refresh the list"""
        self.__children = [CaptureTreeItem(path, image) for path, image in sorted(paths, key=lambda x: x[0])]
        self._progress_cache.clear()
        self._item_changed(None)

        if self._show_progress:
            self.fetch_progress()

    def get_item_children(self, item):
        """Returns all the children when the model asks it."""
        if item is None:
            return self.__children
        return []

    def get_item_value_model_count(self, _):
        """The number of columns"""
        return 2 if self._show_progress else 1

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if column_id == 0:
            return item.path_model
        return None

    def cancel_tasks(self):
        if self._fetch_task is not None:
            self._fetch_task.cancel()  # Actually cancel the running task
            self._fetch_task = None

    def enable_listeners(self, value: bool):
        """Enable or release the stage and layer event observers."""
        if value:
            context = usd.get_context(self._context_name)
            self._stage_event_sub = [
                get_eventdispatcher().observe_event(
                    event_name=context.stage_event_name(usd.StageEventType.CLOSING),
                    on_event=lambda _: self.cancel_tasks(),
                    observer_name="lightspeed.trex.capture_tree.model:CaptureTreeModel.cancel_tasks",
                ),
                get_eventdispatcher().observe_event(
                    event_name=context.stage_event_name(usd.StageEventType.CLOSED),
                    on_event=self.__on_stage_closed,
                    observer_name="lightspeed.trex.capture_tree.model:CaptureTreeModel.__on_stage_closed",
                ),
                get_eventdispatcher().observe_event(
                    event_name=context.stage_event_name(usd.StageEventType.OPENED),
                    on_event=lambda _: self.__on_stage_opened_or_closed(),
                    observer_name="lightspeed.trex.capture_tree.model:CaptureTreeModel.__on_stage_opened_or_closed",
                ),
            ]
            layers = _layers.get_layers()
            self._layer_event_sub = get_eventdispatcher().observe_event(
                event_name=_layers.layer_event_name(_layers.LayerEventType.SUBLAYERS_CHANGED),
                on_event=lambda _: self.__on_sublayers_changed(),
                filter=layers.get_event_key(),
                observer_name="lightspeed.trex.capture_tree.model:CaptureTreeModel.__on_sublayers_changed",
            )
        else:
            self._stage_event_sub = None
            self._layer_event_sub = None

    def fetch_progress(self, items: list[CaptureTreeItem] | None = None):
        self.cancel_tasks()
        self._fetch_task = asyncio.ensure_future(self.__fetch_progress(items))

    def __on_stage_closed(self, _event):
        self.cancel_tasks()
        self.__on_stage_opened_or_closed()

    def __task_completed(self):
        if self._fetch_task is not None:
            self._fetch_task.cancel()
            self._fetch_task = None

    @usd.handle_exception
    async def async_get_captured_hashes(self, item: CaptureTreeItem, replaced_items: list[str]):
        replaced_result, all_assets_result = await self._core_capture.async_get_replaced_hashes(
            item.path, replaced_items
        )
        item.replaced_items = len(replaced_result)
        item.total_items = len(all_assets_result)

        self._progress_cache[item.path] = (item.replaced_items, item.total_items)
        self._item_changed(None)  # Force full refresh to ensure delegate gets updated data

    @usd.handle_exception
    async def __fetch_progress(self, items: list[CaptureTreeItem] | None = None):
        collection = items or self.__children
        # Reset the UI item state
        for item in collection:
            item.replaced_items = None
            item.total_items = None
            self._progress_cache.pop(item.path, None)

        # Fetch the replaced hashes
        replaced_items = set()
        for layer in self._core_replacement.get_replaced_hashes().items():
            replaced_items = replaced_items.union(_ReplacementCoreSetup.group_replaced_hashes(layer))

        tasks = [asyncio.ensure_future(self.async_get_captured_hashes(item, replaced_items)) for item in collection]
        if not tasks:
            self.__on_progress_updated()
            self.__task_completed()
            return
        await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
        self.__on_progress_updated()
        # Make sure the cancel is reset
        self.__task_completed()

    def get_progress_data(self, item_path: str) -> tuple[int | None, int | None]:
        """Get progress data from cache by path"""
        return self._progress_cache.get(item_path, (None, None))

    def subscribe_progress_updated(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_progress_updated, func)

    def subscribe_stage_opened_or_closed(self, func):
        """
        Subscribe to stage opened/closed events.
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_stage_opened_or_closed, func)

    def subscribe_sublayers_changed(self, func):
        """
        Subscribe to sublayers changed events.
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_sublayers_changed, func)

    def destroy(self):
        asyncio.ensure_future(self._deferred_destroy())

    @usd.handle_exception
    async def _deferred_destroy(self):
        await _deferred_destroy_tasks([self._fetch_task])
        self.cancel_tasks()
        _reset_default_attrs(self)

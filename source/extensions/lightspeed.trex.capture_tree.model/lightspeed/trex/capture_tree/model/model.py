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
from typing import List, Optional, Tuple

from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCoreSetup
from omni import ui, usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import deferred_destroy_tasks as _deferred_destroy_tasks
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

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
            "_fetch_task": None,
            "_cancel_token": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._show_progress = show_progress

        self._core_capture = _CaptureCoreSetup(context_name)
        self._core_replacement = _ReplacementCoreSetup(context_name)

        self._stage_event_sub = None
        self._fetch_task = None
        self._cancel_token = False

        self.__children = []
        self.__on_progress_updated = _Event()

    def refresh(self, paths: List[Tuple[str, str]]):
        """Refresh the list"""
        self.__children = [CaptureTreeItem(path, image) for path, image in sorted(paths, key=lambda x: x[0])]
        self._item_changed(None)

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
            self._cancel_token = True

    def enable_listeners(self, value: bool):
        if value:
            self._stage_event_sub = (
                usd.get_context(self._context_name)
                .get_stage_event_stream()
                .create_subscription_to_pop(self.__on_stage_event, name="STAGE_CHANGED_SUB")
            )
        else:
            self._stage_event_sub = None

    def fetch_progress(self, items: Optional[List[CaptureTreeItem]] = None):
        self.cancel_tasks()
        self._fetch_task = asyncio.ensure_future(self.__fetch_progress(items))

    def __on_stage_event(self, event):
        if event.type not in [int(usd.StageEventType.CLOSING), int(usd.StageEventType.CLOSED)]:
            return
        self.cancel_tasks()

    def __task_completed(self):
        if self._fetch_task is not None:
            self._fetch_task.cancel()
            self._fetch_task = None
        self._cancel_token = False

    @usd.handle_exception
    async def async_get_captured_hashes(self, item: CaptureTreeItem, replaced_items: List[str]):
        replaced_result, all_assets_result = await self._core_capture.async_get_replaced_hashes(
            item.path, replaced_items
        )
        item.replaced_items = len(replaced_result)
        item.total_items = len(all_assets_result)

    @usd.handle_exception
    async def __fetch_progress(self, items: Optional[List[CaptureTreeItem]] = None):
        collection = items if items else self.__children
        # Reset the item state
        for item in collection:
            item.replaced_items = None
            item.total_items = None
        self._progress_updated()
        # Allow cancelling the task after resetting the UI
        if self._cancel_token:
            self.__task_completed()
            return
        # Fetch the replaced hashes
        replaced_items = set()
        for layer in self._core_replacement.get_replaced_hashes().items():
            # Allow cancelling the task for every layer
            if self._cancel_token:
                self.__task_completed()
                return
            replaced_items = replaced_items.union(_ReplacementCoreSetup.group_replaced_hashes(layer))

        tasks = []
        for item in collection:
            # Allow cancelling the task for every capture item
            if self._cancel_token:
                self.__task_completed()
                return
            tasks.append(asyncio.ensure_future(self.async_get_captured_hashes(item, replaced_items)))
        await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
        self._progress_updated()
        # Make sure the cancel is reset
        self.__task_completed()

    def _progress_updated(self):
        """Call the event object that has the list of functions"""
        self.__on_progress_updated()

    def subscribe_progress_updated(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_progress_updated, func)

    def destroy(self):
        asyncio.ensure_future(self._deferred_destroy())

    @usd.handle_exception
    async def _deferred_destroy(self):
        await _deferred_destroy_tasks([self._fetch_task])
        self.cancel_tasks()
        _reset_default_attrs(self)

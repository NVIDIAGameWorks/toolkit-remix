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

import asyncio
import threading
from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.stage_manager.factory.items import StageManagerItem
from omni.flux.stage_manager.factory.utils import StageManagerUtils
from omni.flux.utils.common.task_budget import TaskPartition

__all__ = ["TestStageManagerUtilsFilterItems"]


def _make_tree(spec):
    """Build items from (identifier, parent_index) spec. parent_index None = root."""
    items = []
    for identifier, parent_idx in spec:
        parent = items[parent_idx] if parent_idx is not None else None
        items.append(StageManagerItem(identifier, data=None, parent=parent))
    return items


class TestStageManagerUtilsFilterItems(omni.kit.test.AsyncTestCase):
    async def test_filter_items_include_invalid_parents_true(self):
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])

        def keep_only_b(item):
            return item.identifier == "b"

        # Act
        result = await StageManagerUtils.filter_items(items, [keep_only_b], include_invalid_parents=True)

        # Assert
        self.assertEqual(["root", "a", "b"], [item.identifier for item in result])
        self.assertEqual(items[:3], result)

    async def test_filter_items_include_invalid_parents_false(self):
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])

        def keep_only_b(item):
            return item.identifier == "b"

        # Act
        result = await StageManagerUtils.filter_items(items, [keep_only_b], include_invalid_parents=False)

        # Assert
        self.assertEqual(["b"], [item.identifier for item in result])
        self.assertIs(result[0], items[2])
        self.assertIsNone(result[0].parent)

    async def test_filter_items_reparents_to_nearest_valid_ancestor_when_invalid_parents_are_excluded(self):
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])

        def keep_a_and_c(item):
            return item.identifier in {"a", "c"}

        # Act
        result = await StageManagerUtils.filter_items(items, [keep_a_and_c], include_invalid_parents=False)

        # Assert
        self.assertEqual(["a", "c"], [item.identifier for item in result])
        self.assertIs(result[1].parent, result[0])
        self.assertEqual([items[1], items[3]], result)

    async def test_filter_items_updates_owned_wrappers_in_place(self):
        # Arrange
        items = _make_tree([("root", None), ("child", 0)])

        # Act
        result = await StageManagerUtils.filter_items(
            items,
            [lambda item: item.identifier == "child"],
            include_invalid_parents=True,
        )

        # Assert
        self.assertEqual(["root", "child"], [item.identifier for item in result])
        self.assertEqual(items, result)
        self.assertIs(result[1].parent, items[0])
        self.assertFalse(hasattr(result[1], "prepared_data"))
        self.assertTrue(items[0].is_child_valid)
        self.assertTrue(items[1].is_valid)

    async def test_filter_items_does_not_reset_fresh_wrappers(self):
        # Arrange
        items = _make_tree([("root", None), ("child", 0)])
        for item in items:
            item.reset_filter_state = Mock()

        # Act
        await StageManagerUtils.filter_items(items, [lambda _item: True])

        # Assert
        for item in items:
            item.reset_filter_state.assert_not_called()

    async def test_filter_items_cancel_event_returns_none(self):
        # Arrange
        items = _make_tree([("root", None), ("child", 0)])
        worker_started = threading.Event()
        release_worker = threading.Event()
        cancel_event = threading.Event()

        def blocking_predicate(item):
            worker_started.set()
            release_worker.wait(timeout=2)
            return item.identifier == "child"

        worker = asyncio.create_task(
            StageManagerUtils.filter_items(
                items,
                [blocking_predicate],
                include_invalid_parents=False,
                cancel_event=cancel_event,
            )
        )
        while not worker_started.is_set():
            await asyncio.sleep(0)

        # Act
        cancel_event.set()
        release_worker.set()
        result = await worker

        # Assert
        self.assertIsNone(result)
        self.assertIs(items[1].parent, items[0])

    async def test_filter_items_runs_predicates_off_caller_thread(self):
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])
        caller_thread_id = threading.get_ident()
        predicate_thread_ids = []

        def keep_non_c(item):
            predicate_thread_ids.append(threading.get_ident())
            return item.identifier != "c"

        # Act
        result = await StageManagerUtils.filter_items(items, [keep_non_c], include_invalid_parents=False)

        # Assert
        self.assertTrue(all(thread_id != caller_thread_id for thread_id in predicate_thread_ids))
        self.assertEqual(["root", "a", "b"], [item.identifier for item in result])

    async def test_filter_items_blocked_worker_keeps_event_loop_responsive(self):
        # Arrange
        items = _make_tree([(str(index), None) for index in range(1024)])
        worker_started = threading.Event()
        release_worker = threading.Event()
        blocked = False

        def blocking_predicate(_item):
            nonlocal blocked
            if not blocked:
                blocked = True
                worker_started.set()
                release_worker.wait(timeout=1)
            return True

        async def release_from_event_loop():
            while not worker_started.is_set():
                await asyncio.sleep(0)
            release_worker.set()

        release_task = asyncio.create_task(release_from_event_loop())

        # Act
        try:
            result = await StageManagerUtils.filter_items(items, [blocking_predicate])
            await release_task
        finally:
            release_worker.set()
            release_task.cancel()

        # Assert
        self.assertEqual(len(items), len(result))

    async def test_filter_items_uses_adaptive_task_budget_and_updates_metrics(self):
        # Arrange
        items = _make_tree([(str(index), None) for index in range(1024)])
        task_budget = Mock()
        task_budget.compute_partition.return_value = TaskPartition(task_count=2, chunk_size=512)
        to_thread = asyncio.to_thread
        submitted_chunks = []

        async def record_to_thread(callback, *args):
            if callback.__name__ == "filter_chunk":
                submitted_chunks.append(args)
            return await to_thread(callback, *args)

        # Act
        with (
            patch.object(StageManagerUtils, "_task_budget", task_budget, create=True),
            patch(
                "omni.flux.stage_manager.factory.utils.asyncio.to_thread",
                side_effect=record_to_thread,
            ),
        ):
            result = await StageManagerUtils.filter_items(items, [lambda _: True])

        # Assert
        self.assertEqual(len(items), len(result))
        self.assertEqual([(0, 512), (512, 1024)], submitted_chunks)
        task_budget.compute_partition.assert_called_once_with(len(items), 1)
        task_budget.update_metrics.assert_called_once()

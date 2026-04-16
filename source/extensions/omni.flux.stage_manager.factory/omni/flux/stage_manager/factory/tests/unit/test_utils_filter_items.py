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

import time
from unittest.mock import AsyncMock, Mock, patch

import omni.kit.test
from omni.flux.stage_manager.factory.items import StageManagerItem
from omni.flux.stage_manager.factory.utils import StageManagerUtils

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
        self.assertEqual(result, [items[0], items[1], items[2]])

    async def test_filter_items_include_invalid_parents_false(self):
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])

        def keep_only_b(item):
            return item.identifier == "b"

        # Act
        result = await StageManagerUtils.filter_items(items, [keep_only_b], include_invalid_parents=False)

        # Assert
        self.assertEqual(result, [items[2]])

    async def test_filter_items_accepts_iterables(self):
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1)])

        def keep_non_b(item):
            return item.identifier != "b"

        # Act
        result_list = await StageManagerUtils.filter_items(items, [keep_non_b])
        result_iter = await StageManagerUtils.filter_items(iter(items), iter([keep_non_b]))

        # Assert
        self.assertEqual(result_iter, result_list)

    async def test_filter_items_resets_state_each_run(self):
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1)])

        def keep_only_b(item):
            return item.identifier == "b"

        def keep_only_a(item):
            return item.identifier == "a"

        # Act
        first_run = await StageManagerUtils.filter_items(items, [keep_only_b], include_invalid_parents=False)
        second_run = await StageManagerUtils.filter_items(items, [keep_only_a], include_invalid_parents=False)

        # Assert
        self.assertEqual(first_run, [items[2]])
        self.assertEqual(second_run, [items[1]])
        self.assertFalse(items[2].is_valid)

    async def test_filter_items_uses_partitioned_executor_calls(self):
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])
        execution = {"calls": 0, "executor": "not-set", "callable_name": ""}
        fake_budget = Mock()
        fake_budget.compute_partition.return_value = Mock(task_count=2, chunk_size=2)

        def keep_non_c(item):
            return item.identifier != "c"

        async def _fake_run_in_executor(executor, callback, *args):
            execution["calls"] += 1
            execution["executor"] = executor
            execution["callable_name"] = callback.__name__
            return callback(*args)

        fake_loop = Mock()
        fake_loop.run_in_executor = AsyncMock(side_effect=_fake_run_in_executor)
        fake_loop.time = Mock(side_effect=time.perf_counter)

        # Act
        with (
            patch("omni.flux.stage_manager.factory.utils.asyncio.get_event_loop", return_value=fake_loop),
            patch.object(StageManagerUtils, "_task_budget", fake_budget),
        ):
            result = await StageManagerUtils.filter_items(items, [keep_non_c], include_invalid_parents=False)

        # Assert
        self.assertEqual(execution["calls"], 2)
        self.assertIsNotNone(execution["executor"])
        self.assertEqual(execution["callable_name"], "_run_chunk")
        self.assertEqual(result, [items[0], items[1], items[2]])
        fake_budget.compute_partition.assert_called_once_with(len(items), 1)
        fake_budget.update_metrics.assert_called_once()
        self.assertEqual(fake_budget.update_metrics.call_args.kwargs["task_count"], execution["calls"])

    async def test_filter_items_reports_executed_chunk_count_to_metrics(self):
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2), ("d", 3)])
        execution = {"calls": 0}
        fake_budget = Mock()
        fake_budget.compute_partition.return_value = Mock(task_count=8, chunk_size=2)

        async def _fake_run_in_executor(_executor, callback, *args):
            execution["calls"] += 1
            return callback(*args)

        fake_loop = Mock()
        fake_loop.run_in_executor = AsyncMock(side_effect=_fake_run_in_executor)
        fake_loop.time = Mock(side_effect=time.perf_counter)

        # Act
        with (
            patch("omni.flux.stage_manager.factory.utils.asyncio.get_event_loop", return_value=fake_loop),
            patch.object(StageManagerUtils, "_task_budget", fake_budget),
        ):
            await StageManagerUtils.filter_items(items, [lambda _: True], include_invalid_parents=False)

        # Assert
        self.assertEqual(execution["calls"], 3)
        self.assertEqual(fake_budget.update_metrics.call_args.kwargs["task_count"], execution["calls"])

    async def test_filter_items_with_empty_list_skips_executor_work(self):
        # Arrange
        fake_budget = Mock()
        fake_budget.compute_partition.return_value = Mock(task_count=0, chunk_size=1)
        fake_loop = Mock()
        fake_loop.run_in_executor = AsyncMock()
        fake_loop.time = Mock(side_effect=time.perf_counter)

        # Act
        with (
            patch("omni.flux.stage_manager.factory.utils.asyncio.get_event_loop", return_value=fake_loop),
            patch.object(StageManagerUtils, "_task_budget", fake_budget),
        ):
            result = await StageManagerUtils.filter_items([], [lambda _: True], include_invalid_parents=False)

        # Assert
        self.assertEqual(result, [])
        fake_loop.run_in_executor.assert_not_called()
        fake_budget.update_metrics.assert_called_once()

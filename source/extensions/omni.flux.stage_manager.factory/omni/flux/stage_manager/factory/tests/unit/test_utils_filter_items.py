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

from ... import utils as stage_manager_utils

__all__ = ["TestStageManagerUtilsFilterItems"]


def _make_tree(spec):
    """Build items from (identifier, parent_index) spec. parent_index None = root."""
    items = []
    for identifier, parent_idx in spec:
        parent = items[parent_idx] if parent_idx is not None else None
        items.append(StageManagerItem(identifier, data=None, parent=parent))
    return items


class TestStageManagerUtilsFilterItems(omni.kit.test.AsyncTestCase):
    """Test Stage Manager context-item filtering behavior."""

    async def test_filter_items_include_invalid_parents_true(self):
        """Retain invalid ancestors when configured."""
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])

        def keep_only_b(item):
            """Retain only item b."""
            return item.identifier == "b"

        # Act
        result = await StageManagerUtils.filter_items(items, [keep_only_b], include_invalid_parents=True)

        # Assert
        self.assertEqual(["root", "a", "b"], [item.identifier for item in result])
        self.assertEqual(items[:3], result)

    async def test_filter_items_include_invalid_parents_false(self):
        """Exclude invalid ancestors when configured."""
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])

        def keep_only_b(item):
            """Retain only item b."""
            return item.identifier == "b"

        # Act
        result = await StageManagerUtils.filter_items(items, [keep_only_b], include_invalid_parents=False)

        # Assert
        self.assertEqual(["b"], [item.identifier for item in result])
        self.assertIs(result[0], items[2])
        self.assertIsNone(result[0].parent)
        self.assertIsNone(items[0].is_child_valid)
        self.assertIsNone(items[1].is_child_valid)

    async def test_filter_items_reparents_to_nearest_valid_ancestor_when_invalid_parents_are_excluded(self):
        """Reparent survivors to their nearest retained ancestor."""
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])

        def keep_a_and_c(item):
            """Retain items a and c."""
            return item.identifier in {"a", "c"}

        # Act
        result = await StageManagerUtils.filter_items(items, [keep_a_and_c], include_invalid_parents=False)

        # Assert
        self.assertEqual(["a", "c"], [item.identifier for item in result])
        self.assertIs(result[1].parent, result[0])
        self.assertEqual([items[1], items[3]], result)

    async def test_filter_items_updates_owned_wrappers_in_place(self):
        """Update owned wrappers without replacing their prepared state."""
        # Arrange
        items = _make_tree([("root", None), ("child", 0)])
        items[1].prepare_group_memberships(("value",))

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
        self.assertEqual(("value",), result[1].prepared_group_memberships)
        self.assertTrue(items[0].is_child_valid)
        self.assertTrue(items[1].is_valid)

    async def test_filter_items_does_not_reset_fresh_wrappers(self):
        """Avoid resetting wrappers created for the current refresh."""
        # Arrange
        items = _make_tree([("root", None), ("child", 0)])
        for item in items:
            item.reset_filter_state = Mock()

        # Act
        await StageManagerUtils.filter_items(items, [lambda _item: True])

        # Assert
        for item in items:
            item.reset_filter_state.assert_not_called()

    async def test_filter_items_with_display_name_ancestors_disabled_excludes_parent_from_naming(self):
        """Exclude invalid ancestors from display-name preparation when configured."""
        # Arrange
        parent_prim = Mock()
        parent_path = Mock(name="parent_path")
        parent_path.name = "Thing"
        parent_prim.GetPath.return_value = parent_path
        child_prim = Mock()
        child_path = Mock(name="child_path")
        child_path.name = "Thing"
        child_path.GetParentPath.return_value.name = "Parent"
        child_prim.GetPath.return_value = child_path
        parent = StageManagerItem("parent", data=parent_prim)
        child = StageManagerItem("child", data=child_prim, parent=parent)

        def keep_child_and_mark_display_name(item):
            """Retain the child and request display-name preparation."""
            if item is child:
                item.mark_display_name_candidate()
                return True
            return False

        # Act
        result = await StageManagerUtils.filter_items(
            [parent, child],
            [keep_child_and_mark_display_name],
            include_invalid_parents=False,
            include_display_name_ancestors=False,
        )

        # Assert
        self.assertEqual([child], result)
        self.assertEqual(("Thing", None), child.prepared_display_name)
        with self.assertRaises(RuntimeError):
            _ = parent.prepared_display_name
        parent_prim.GetPath.assert_not_called()

    async def test_filter_items_with_display_name_candidate_parent_outside_source_stops_ancestor_naming(self):
        """Stop display-name ancestor collection at the first parent absent from the source items."""
        # Arrange
        ancestor_path = Mock(name="ancestor_path")
        ancestor_path.name = "Thing"
        ancestor_prim = Mock()
        ancestor_prim.GetPath.return_value = ancestor_path
        ancestor = StageManagerItem("ancestor", data=ancestor_prim)
        missing_parent = StageManagerItem("missing_parent", parent=ancestor)
        candidate_path = Mock(name="candidate_path")
        candidate_path.name = "Thing"
        candidate_path.GetParentPath.return_value.name = "Missing"
        candidate_prim = Mock()
        candidate_prim.GetPath.return_value = candidate_path
        candidate = StageManagerItem("candidate", data=candidate_prim, parent=missing_parent)

        def keep_candidate_and_mark_display_name(item):
            """Retain the candidate and request display-name preparation."""
            if item is candidate:
                item.mark_display_name_candidate()
                return True
            return False

        # Act
        result = await StageManagerUtils.filter_items([ancestor, candidate], [keep_candidate_and_mark_display_name])

        # Assert
        self.assertEqual([ancestor, candidate], result)
        self.assertEqual(("Thing", None), candidate.prepared_display_name)
        with self.assertRaises(RuntimeError):
            _ = ancestor.prepared_display_name
        ancestor_prim.GetPath.assert_not_called()

    async def test_filter_items_with_nested_display_name_candidates_uses_linear_parent_reads(self):
        """Use linear parent reads while preparing nested display names."""
        # Arrange
        original_parent = StageManagerItem.parent
        items = []
        for index in range(8):
            path = Mock(name=f"path_{index}")
            path.name = f"Item{index}"
            prim = Mock(name=f"prim_{index}")
            prim.GetPath.return_value = path
            parent = items[-1] if items else None
            items.append(StageManagerItem(f"item_{index}", data=prim, parent=parent))
        parent_reads = dict.fromkeys(items, 0)

        def read_parent(item):
            """Count parent reads while retaining the production property behavior."""
            parent_reads[item] += 1
            return original_parent.fget(item)

        def mark_display_name_candidate(_item):
            """Request display-name preparation while rejecting every item."""
            _item.mark_display_name_candidate()
            return False

        # Act
        with patch.object(StageManagerItem, "parent", property(read_parent, original_parent.fset)):
            result = await StageManagerUtils.filter_items(
                items,
                [mark_display_name_candidate],
                include_invalid_parents=False,
                include_display_name_ancestors=True,
            )

        # Assert
        self.assertEqual([], result)
        self.assertLessEqual(sum(parent_reads.values()), 2 * len(items))
        self.assertEqual(
            [(f"Item{index}", None) for index in range(len(items))],
            [item.prepared_display_name for item in items],
        )

    async def test_filter_items_cancel_event_returns_none(self):
        """Return no result when cancellation occurs during predicate evaluation."""
        # Arrange
        items = _make_tree([("root", None), ("child", 0)])
        worker_started = threading.Event()
        release_worker = threading.Event()
        cancel_event = threading.Event()

        def blocking_predicate(item):
            """Block filtering until the test releases the worker."""
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

    async def test_filter_items_cancelled_during_invalid_parent_collection_returns_none(self):
        """Return no result when cancellation occurs during retained-item collection."""
        # Arrange
        collection_started = threading.Event()
        release_collection = threading.Event()
        cancel_event = threading.Event()

        class BlockingItems(list):
            """Pause retained-item collection after yielding the first item."""

            def __iter__(self):
                """Yield one item, block, then yield the remaining items."""
                iterator = super().__iter__()
                yield next(iterator)
                collection_started.set()
                release_collection.wait(timeout=2)
                yield from iterator

        items = BlockingItems(_make_tree([("root", None), ("child", 0)]))
        worker = asyncio.create_task(
            StageManagerUtils.filter_items(
                items,
                [lambda _item: True],
                include_invalid_parents=True,
                cancel_event=cancel_event,
            )
        )
        while not collection_started.is_set():
            await asyncio.sleep(0)

        # Act
        try:
            cancel_event.set()
            release_collection.set()
            result = await worker
        finally:
            release_collection.set()

        # Assert
        self.assertIsNone(result)

    async def test_filter_items_cancelled_after_sparse_reparent_collection_returns_none(self):
        """Return no result when cancellation follows sparse reparenting collection."""
        # Arrange
        cancel_event = threading.Event()

        class SparseItems(list):
            """Signal cancellation immediately after yielding the final item."""

            def __iter__(self):
                """Yield all source items before signaling the completed collection."""
                yield from super().__iter__()
                cancel_event.set()

        root, excluded, retained = _make_tree([("root", None), ("excluded", 0), ("retained", 1)])
        items = SparseItems([root, excluded, retained])

        # Act
        result = await StageManagerUtils.filter_items(
            items,
            [lambda item: item.identifier in {"root", "retained"}],
            include_invalid_parents=False,
            cancel_event=cancel_event,
        )

        # Assert
        self.assertIsNone(result)
        self.assertIs(retained.parent, root)

    async def test_filter_items_cancelled_during_display_name_preparation_stops_scanning(self):
        """Stop display-name scanning when cancellation occurs during preparation."""
        # Arrange
        first_path = Mock(name="first_path")
        first_path.name = "First"
        name_scan_started = threading.Event()
        release_name_scan = threading.Event()

        second_path = Mock(name="second_path")
        second_path.name = "Second"
        first_prim = Mock(name="first_prim")
        second_prim = Mock(name="second_prim")

        def _get_path(path):
            """Block whichever name lookup starts first until the test releases it."""
            name_scan_started.set()
            release_name_scan.wait(timeout=2)
            return path

        first_prim.GetPath.side_effect = lambda: _get_path(first_path)
        second_prim.GetPath.side_effect = lambda: _get_path(second_path)
        items = [
            StageManagerItem("first", data=first_prim),
            StageManagerItem("second", data=second_prim),
        ]
        cancel_event = threading.Event()

        def _mark_display_name_candidate(item):
            """Request display-name preparation for one item."""
            item.mark_display_name_candidate()
            return True

        worker = asyncio.create_task(
            StageManagerUtils.filter_items(items, [_mark_display_name_candidate], cancel_event=cancel_event)
        )
        while not name_scan_started.is_set():
            await asyncio.sleep(0)

        # Act
        cancel_event.set()
        release_name_scan.set()
        result = await worker

        # Assert
        self.assertIsNone(result)
        self.assertEqual(1, first_prim.GetPath.call_count + second_prim.GetPath.call_count)

    async def test_filter_items_runs_predicates_off_caller_thread(self):
        """Evaluate context predicates off the caller thread."""
        # Arrange
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])
        caller_thread_id = threading.get_ident()
        predicate_thread_ids = []

        def keep_non_c(item):
            """Record the worker thread and reject item c."""
            predicate_thread_ids.append(threading.get_ident())
            return item.identifier != "c"

        # Act
        result = await StageManagerUtils.filter_items(items, [keep_non_c], include_invalid_parents=False)

        # Assert
        self.assertTrue(all(thread_id != caller_thread_id for thread_id in predicate_thread_ids))
        self.assertEqual(["root", "a", "b"], [item.identifier for item in result])

    async def test_filter_items_blocked_worker_keeps_event_loop_responsive(self):
        """Keep the event loop responsive while a filtering worker is blocked."""
        # Arrange
        items = _make_tree([(str(index), None) for index in range(1024)])
        worker_started = threading.Event()
        release_worker = threading.Event()
        blocked = False

        def blocking_predicate(_item):
            """Block the first worker call until the event loop releases it."""
            nonlocal blocked
            if not blocked:
                blocked = True
                worker_started.set()
                release_worker.wait(timeout=1)
            return True

        async def release_from_event_loop():
            """Release the worker after the event loop observes its start signal."""
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

    async def test_filter_items_submits_one_worker_for_complete_filtering_transaction(self):
        """Filter, prepare names, and reparent sparse results in one worker submission."""
        # Arrange
        candidate_prim = Mock()
        candidate_path = Mock()
        candidate_path.name = "Thing"
        candidate_prim.GetPath.return_value = candidate_path
        root, excluded, candidate = _make_tree([("root", None), ("excluded", 0), ("candidate", 1)])
        candidate._data = candidate_prim
        evaluated_items = []

        def predicate(item):
            """Retain root and candidate while requesting the candidate's display name."""
            evaluated_items.append(item)
            if item is candidate:
                item.mark_display_name_candidate()
            return item in {root, candidate}

        real_to_thread = asyncio.to_thread

        # Act
        with patch.object(stage_manager_utils.asyncio, "to_thread", wraps=real_to_thread) as to_thread_mock:
            result = await StageManagerUtils.filter_items(
                [root, excluded, candidate],
                [predicate],
                include_invalid_parents=False,
            )

        # Assert
        self.assertEqual(1, to_thread_mock.call_count)
        self.assertEqual([root, excluded, candidate], evaluated_items)
        self.assertEqual([root, candidate], result)
        self.assertEqual(("Thing", None), candidate.prepared_display_name)
        self.assertTrue(root.is_valid)
        self.assertFalse(excluded.is_valid)
        self.assertTrue(candidate.is_valid)
        self.assertIsNone(root.parent)
        self.assertIs(root, candidate.parent)

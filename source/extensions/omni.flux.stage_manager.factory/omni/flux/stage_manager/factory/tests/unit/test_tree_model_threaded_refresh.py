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
from unittest.mock import AsyncMock, Mock, patch

import omni.kit.test
from omni.flux.stage_manager.factory.items import StageManagerItem
from omni.flux.stage_manager.factory.plugins.filter_plugin import StageManagerFilterPlugin
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel, TreeRefreshResult
from pydantic import Field, PrivateAttr
from pxr import Sdf

__all__ = ["TestStageManagerTreeModelThreadedRefresh"]


class _ConcreteTreeModel(StageManagerTreeModel):
    @property
    def default_attr(self) -> dict:
        return super().default_attr


class _BuildItemsTreeModel(_ConcreteTreeModel):
    def __init__(self):
        super().__init__()
        self.build_thread_id = None

    def _build_items(self, items, cancel_event):
        self.build_thread_id = threading.get_ident()
        return super()._build_items(items, cancel_event)


class _DuplicatePathTreeModel(_ConcreteTreeModel):
    def _build_items(self, items, cancel_event):
        items = list(items)
        group_a = self._build_item("GroupA", None, tooltip="Group A")
        group_b = self._build_item("GroupB", None, tooltip="Group B")
        for group in (group_a, group_b):
            prim_path = items[0].data.GetPath()
            child = self._build_item("SharedPrim", items[0].data, tooltip=str(prim_path))
            child.path = str(prim_path)
            child.parent = group
        return [group_a, group_b]


class _BlockingTreeModel(_ConcreteTreeModel):
    def __init__(self):
        super().__init__()
        self.first_build_started = threading.Event()
        self.release_first_build = threading.Event()
        self._build_count = 0
        self._build_count_lock = threading.Lock()

    def _build_items(self, items, cancel_event):
        with self._build_count_lock:
            self._build_count += 1
            build_count = self._build_count

        if build_count == 1:
            self.first_build_started.set()
            if not self.release_first_build.wait(timeout=5):
                raise TimeoutError("Timed out waiting to release the stale worker")

        if cancel_event.is_set():
            return None
        return super()._build_items(items, cancel_event)


class _PreparedFilterPlugin(StageManagerFilterPlugin):
    display_name: str = Field(default="Prepared Filter", exclude=True)
    tooltip: str = Field(default="Prepared Filter", exclude=True)

    _prepare_call_count: int = PrivateAttr(default=0)
    _preparation_thread_id: int | None = PrivateAttr(default=None)
    _predicate_thread_ids: list[int] = PrivateAttr(default_factory=list)

    def prepare_filter_predicate(self):
        self._preparation_thread_id = threading.get_ident()
        self._prepare_call_count += 1

        def _predicate(item):
            self._predicate_thread_ids.append(threading.get_ident())
            return str(item.identifier).endswith("Child/Leaf")

        return _predicate

    def filter_predicate(self, item):
        raise AssertionError("Worker refresh should use the prepared predicate")

    def build_ui(self):
        pass


class _InactivePreparedFilterPlugin(_PreparedFilterPlugin):
    filter_active: bool = Field(default=False)

    def prepare_filter_predicate(self):
        raise AssertionError("Inactive filters must not prepare predicates")


def _make_context_tree() -> list[StageManagerItem]:
    root_prim = Mock()
    root_prim.GetPath.return_value = Sdf.Path("/World")

    child_prim = Mock()
    child_prim.GetPath.return_value = Sdf.Path("/World/Child")

    leaf_prim = Mock()
    leaf_prim.GetPath.return_value = Sdf.Path("/World/Child/Leaf")

    root = StageManagerItem("/World", data=root_prim)
    child = StageManagerItem("/World/Child", data=child_prim, parent=root)
    leaf = StageManagerItem("/World/Child/Leaf", data=leaf_prim, parent=child)
    return [root, child, leaf]


class TestStageManagerTreeModelThreadedRefresh(omni.kit.test.AsyncTestCase):
    async def test_set_context_items_transfers_collection_ownership(self):
        # Arrange
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)
        context_items = _make_context_tree()

        # Act
        model.set_context_items(context_items)

        # Assert
        self.assertIs(context_items, model._context_items)

    async def test_publish_refresh_result_transfers_collection_ownership(self):
        # Arrange
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)
        root_items = []
        items_by_path = {}
        item_by_hash = {}
        path_by_hash = {}
        result = TreeRefreshResult(
            root_items=root_items,
            items_by_path=items_by_path,
            item_by_hash=item_by_hash,
            path_by_hash=path_by_hash,
            input_items_count=0,
            output_items_count=0,
        )

        # Act
        model.publish_refresh_result(result)

        # Assert
        self.assertIs(root_items, model._items)
        self.assertIs(items_by_path, model._items_by_path)
        self.assertIs(item_by_hash, model._item_by_hash)

    async def test_clear_items_clears_render_state_and_preserves_context_items(self):
        # Arrange
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)
        context_items = _make_context_tree()
        filter_plugin = _PreparedFilterPlugin()
        refresh_cancel_event = threading.Event()
        rendered_item = Mock()
        selected_item = Mock()
        model._items = [rendered_item]
        model.selection = [selected_item]
        model._items_by_path = {"/World": [rendered_item]}
        model._item_by_hash = {hash(rendered_item): rendered_item}
        model._context_items = context_items
        model._user_filter_plugins = [filter_plugin]
        model._refresh_cancel_event = refresh_cancel_event

        # Act
        with patch.object(model, "_item_changed") as item_changed:
            model.clear_items()

        # Assert
        self.assertEqual([], model._items)
        self.assertEqual([], model.selection)
        self.assertEqual({}, model._items_by_path)
        self.assertEqual({}, model._item_by_hash)
        self.assertIs(model._context_items, context_items)
        self.assertEqual([filter_plugin], model._user_filter_plugins)
        self.assertIs(refresh_cancel_event, model._refresh_cancel_event)
        item_changed.assert_called_once_with(None)

    async def test_refresh_uses_threaded_prepare_publish_path(self):
        # Arrange
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)
        model.set_context_items(_make_context_tree())
        model.selection = [Mock()]
        kit_app = Mock()
        kit_app.next_update_async = AsyncMock()

        # Act
        with (
            patch(
                "omni.flux.stage_manager.factory.plugins.tree_plugin.asyncio.to_thread",
                wraps=asyncio.to_thread,
            ) as to_thread_mock,
            patch(
                "omni.flux.stage_manager.factory.plugins.tree_plugin.omni.kit.app.get_app",
                return_value=kit_app,
            ),
        ):
            await model.refresh()

        # Assert
        self.assertEqual(to_thread_mock.call_count, 1)
        kit_app.next_update_async.assert_not_awaited()
        self.assertEqual([], model.selection)

    async def test_threaded_refresh_filters_and_builds_on_worker(self):
        # Arrange
        main_thread_id = threading.get_ident()
        model = _BuildItemsTreeModel()
        self.addCleanup(model.destroy)
        filter_plugin = _PreparedFilterPlugin()
        context_items = _make_context_tree()
        dropped_prim = Mock()
        dropped_prim.GetPath.return_value = Sdf.Path("/Dropped")
        context_items.append(StageManagerItem("/Dropped", data=dropped_prim))
        model.set_context_items(context_items)
        model.add_user_filter_plugins([filter_plugin])

        # Act
        with patch(
            "omni.flux.stage_manager.factory.plugins.tree_plugin.asyncio.to_thread",
            wraps=asyncio.to_thread,
        ) as to_thread_mock:
            result = await model.refresh_threaded()

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(1, to_thread_mock.call_count)
        self.assertNotEqual(main_thread_id, filter_plugin._preparation_thread_id)
        self.assertTrue(all(thread_id != main_thread_id for thread_id in filter_plugin._predicate_thread_ids))
        self.assertNotEqual(main_thread_id, model.build_thread_id)
        self.assertEqual(filter_plugin._preparation_thread_id, model.build_thread_id)
        self.assertTrue(all(thread_id == model.build_thread_id for thread_id in filter_plugin._predicate_thread_ids))
        self.assertEqual(["Leaf"], [item.display_name for item in result.root_items[0].children[0].children])
        self.assertEqual(4, result.input_items_count)
        self.assertEqual(3, result.output_items_count)

    async def test_threaded_refresh_skips_inactive_filters_and_filtering_when_none_are_active(self):
        # Arrange
        model = _BuildItemsTreeModel()
        self.addCleanup(model.destroy)
        active_filter = _PreparedFilterPlugin()
        model.set_context_items(_make_context_tree())
        model.add_user_filter_plugins([active_filter, _InactivePreparedFilterPlugin()])
        unfiltered_model = _BuildItemsTreeModel()
        self.addCleanup(unfiltered_model.destroy)
        unfiltered_model.set_context_items(_make_context_tree())

        # Act
        result = await model.refresh_threaded()
        with patch(
            "omni.flux.stage_manager.factory.plugins.tree_plugin._StageManagerUtils.filter_items_by_category",
            side_effect=AssertionError("No active filters should skip category filtering"),
        ):
            unfiltered_result = await unfiltered_model.refresh_threaded()

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(1, active_filter._prepare_call_count)
        self.assertIsNotNone(unfiltered_result)

    async def test_threaded_refresh_clears_owned_cancel_event_when_build_fails(self):
        # Arrange
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)
        model.set_context_items(_make_context_tree())

        # Act
        with patch.object(model, "_build_items", side_effect=RuntimeError("build failed")) as build_items:
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                await model.refresh_threaded()

        # Assert
        build_items.assert_called_once()
        self.assertIsNone(model._refresh_cancel_event)

    async def test_threaded_refresh_tracks_duplicate_items_for_same_path(self):
        # Arrange
        model = _DuplicatePathTreeModel()
        self.addCleanup(model.destroy)
        context_items = _make_context_tree()
        model.set_context_items([context_items[0]])

        # Act
        result = await model.refresh_threaded()

        # Assert
        matching_items = result.items_by_path["/World"]
        self.assertEqual(2, len(matching_items))
        self.assertEqual({hash(item): "/World" for item in matching_items}, result.path_by_hash)

    async def test_refresh_threaded_stale_worker_does_not_block_latest_refresh(self):
        # Arrange
        model = _BlockingTreeModel()
        self.addCleanup(model.destroy)
        self.addCleanup(model.release_first_build.set)
        context_items = _make_context_tree()
        original_state = [
            (item.identifier, item.data, item.parent, item.is_valid, item.is_child_valid) for item in context_items
        ]
        model.set_context_items(context_items)
        first_refresh_task = asyncio.create_task(model.refresh_threaded())
        worker_started = await asyncio.to_thread(model.first_build_started.wait, 2)
        self.assertTrue(worker_started)

        # Act
        second_result = await asyncio.wait_for(model.refresh_threaded(), timeout=2)
        model.release_first_build.set()
        first_result = await asyncio.wait_for(first_refresh_task, timeout=2)

        # Assert
        self.assertIsNone(first_result)
        self.assertIsNotNone(second_result)
        self.assertIsNone(model._refresh_cancel_event)
        self.assertEqual(
            original_state,
            [(item.identifier, item.data, item.parent, item.is_valid, item.is_child_valid) for item in context_items],
        )
        self.assertTrue(all(not hasattr(item, "tree_item") for item in context_items))

    async def test_refresh_threaded_when_task_is_cancelled_propagates_cancellation(self):
        # Arrange
        model = _BlockingTreeModel()
        self.addCleanup(model.destroy)
        self.addCleanup(model.release_first_build.set)
        model.set_context_items(_make_context_tree())
        refresh_task = asyncio.create_task(model.refresh_threaded())
        worker_started = await asyncio.to_thread(model.first_build_started.wait, 2)
        self.assertTrue(worker_started)

        # Act
        refresh_task.cancel()
        model.release_first_build.set()

        # Assert
        with self.assertRaises(asyncio.CancelledError):
            await refresh_task

    async def test_destroy_during_refresh_cancels_worker_and_prevents_publication(self):
        # Arrange
        model = _BlockingTreeModel()
        self.addCleanup(model.release_first_build.set)
        model.set_context_items(_make_context_tree())
        refresh_task = asyncio.create_task(model.refresh())
        worker_started = await asyncio.to_thread(model.first_build_started.wait, 2)
        self.assertTrue(worker_started)
        cancel_event = model._refresh_cancel_event

        # Act
        model.destroy()
        model.release_first_build.set()
        await asyncio.wait_for(refresh_task, timeout=2)

        # Assert
        self.assertTrue(cancel_event.is_set())
        self.assertIsNone(model._items)

    async def test_threaded_refresh_builds_hierarchy_and_lookups_without_mutating_context_items(self):
        # Arrange
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)
        context_items = _make_context_tree()
        original_state = [
            (item.identifier, item.data, item.parent, item.is_valid, item.is_child_valid) for item in context_items
        ]
        model.set_context_items(context_items)
        # Act
        with patch(
            "omni.flux.stage_manager.factory.plugins.tree_plugin.asyncio.to_thread",
            wraps=asyncio.to_thread,
        ) as to_thread_mock:
            result = await model.refresh_threaded()

        # Assert
        self.assertEqual(to_thread_mock.call_count, 1)
        self.assertIsNotNone(result)
        self.assertEqual(
            {hash(item): item.path for item in result.item_by_hash.values() if item.path is not None},
            result.path_by_hash,
        )
        self.assertEqual(["World"], [item.display_name for item in result.root_items])
        self.assertEqual(["Child"], [item.display_name for item in result.root_items[0].children])
        self.assertEqual(["Leaf"], [item.display_name for item in result.root_items[0].children[0].children])
        self.assertEqual(
            original_state,
            [(item.identifier, item.data, item.parent, item.is_valid, item.is_child_valid) for item in context_items],
        )
        self.assertTrue(all(not hasattr(item, "tree_item") for item in context_items))

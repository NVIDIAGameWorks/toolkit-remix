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
from omni.flux.stage_manager.factory.plugins.tree_plugin import (
    StageManagerTreeDelegate,
    StageManagerTreeItem,
    StageManagerTreeItemProxy,
    StageManagerTreeModel,
    TreeRefreshResult,
)
from pydantic import Field, PrivateAttr
from pxr import Sdf

__all__ = [
    "TestStageManagerTreeDelegate",
    "TestStageManagerTreeItemProxy",
    "TestStageManagerTreeModelThreadedRefresh",
]


class _ConcreteTreeModel(StageManagerTreeModel):
    @property
    def default_attr(self) -> dict:
        return super().default_attr


class _SpecializedTreeItem(StageManagerTreeItem):
    @property
    def default_attr(self) -> dict:
        return super().default_attr


class _ConcreteTreeDelegate(StageManagerTreeDelegate):
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


class _BlockingFilterTreeModel(_BuildItemsTreeModel):
    def __init__(self):
        super().__init__()
        self.block_filter_projection = False
        self.filter_projection_started = threading.Event()
        self.release_filter_projection = threading.Event()

    def _project_item_proxies(self, *args, **kwargs):
        if self.block_filter_projection:
            self.filter_projection_started.set()
            if not self.release_filter_projection.wait(timeout=5):
                raise TimeoutError("Timed out waiting to release the filter projection")
        return super()._project_item_proxies(*args, **kwargs)


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

    def build_filter_predicate(self):
        self._preparation_thread_id = threading.get_ident()
        self._prepare_call_count += 1

        def _predicate(item):
            self._predicate_thread_ids.append(threading.get_ident())
            return str(item.identifier).endswith("Child/Leaf")

        return _predicate

    def filter_predicate(self, item):
        raise AssertionError("Worker refresh should use the built predicate")

    def build_ui(self):
        pass


class _InactivePreparedFilterPlugin(_PreparedFilterPlugin):
    filter_active: bool = Field(default=False)

    def build_filter_predicate(self):
        raise AssertionError("Inactive filters must not prepare predicates")


class _RootPreparedFilterPlugin(_PreparedFilterPlugin):
    def build_filter_predicate(self):
        self._prepare_call_count += 1
        return lambda item: str(item.identifier) == "/World"


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


def _snapshot_hierarchy(root_items):
    """Capture item identities and ordered topology for mutation checks."""
    return tuple(
        (id(item), id(item.parent) if item.parent else None, _snapshot_hierarchy(item.children)) for item in root_items
    )


class _StageManagerTreeTestCase(omni.kit.test.AsyncTestCase):
    def _make_canonical_item(self, display_name: str, path: str | None = None):
        item = _SpecializedTreeItem(
            display_name,
            Mock(),
            tooltip=f"{display_name} tooltip",
            display_name_ancestor="Ancestor",
            path=path,
        )
        self.addCleanup(item.destroy)
        return item


class TestStageManagerTreeItemProxy(_StageManagerTreeTestCase):
    async def test_proxy_owns_canonical_link_without_forwarding_canonical_properties(self):
        # Arrange
        canonical = self._make_canonical_item("Canonical", path="/Canonical")

        # Act
        proxy = StageManagerTreeItemProxy(canonical)

        # Assert
        self.assertIs(proxy, canonical.proxy)
        self.assertIs(canonical, proxy.original_tree_item)
        self.assertIs(canonical.is_virtual, False)
        for name in (
            "display_name",
            "display_name_ancestor",
            "tooltip",
            "data",
            "path",
            "icon",
            "long_display_path_name",
        ):
            self.assertFalse(hasattr(proxy, name))

    async def test_proxy_hierarchy_mutations_are_independent_from_canonical_hierarchy(self):
        # Arrange
        canonical_parent = self._make_canonical_item("Parent", path="/Parent")
        canonical_child = self._make_canonical_item("Child", path="/Parent/Child")
        canonical_child.parent = canonical_parent
        parent_proxy = StageManagerTreeItemProxy(canonical_parent)
        child_proxy = StageManagerTreeItemProxy(canonical_child)
        proxy_has_children_before = parent_proxy.has_children

        # Act
        child_proxy.parent = parent_proxy

        # Assert
        self.assertTrue(canonical_parent.has_children)
        self.assertFalse(proxy_has_children_before)
        self.assertTrue(parent_proxy.has_children)
        self.assertIsNot(canonical_parent._children, parent_proxy._children)
        self.assertEqual([canonical_child], canonical_parent.children)
        self.assertEqual([child_proxy], parent_proxy.children)
        self.assertIs(canonical_parent, canonical_child.parent)
        self.assertIs(parent_proxy, child_proxy.parent)
        self.assertTrue(all(isinstance(child, StageManagerTreeItemProxy) for child in parent_proxy.children))

    async def test_proxy_hash_matches_canonical_without_changing_identity_equality(self):
        # Arrange
        first_canonical = self._make_canonical_item("Shared", path="/Shared")
        second_canonical = self._make_canonical_item("Shared", path="/Shared")

        # Act
        first_proxy = StageManagerTreeItemProxy(first_canonical)
        second_proxy = StageManagerTreeItemProxy(second_canonical)

        # Assert
        self.assertEqual(hash(first_canonical), hash(first_proxy))
        self.assertEqual(2, len({first_proxy, second_proxy}))


class TestStageManagerTreeDelegate(_StageManagerTreeTestCase):
    async def test_widget_click_forwards_canonical_proxy_to_tree_view(self):
        # Arrange
        canonical_item = self._make_canonical_item("Specialized", path="/World/Specialized")
        proxy_item = StageManagerTreeItemProxy(canonical_item)
        model = Mock()
        delegate = _ConcreteTreeDelegate()
        self.addCleanup(delegate.destroy)

        # Act
        with patch.object(delegate, "_item_clicked") as item_clicked:
            delegate.call_item_clicked(0, True, model, canonical_item)

        # Assert
        item_clicked.assert_called_once_with(0, True, model, proxy_item)

    async def test_widget_click_ignores_canonical_item_without_proxy(self):
        # Arrange
        canonical_item = self._make_canonical_item("Detached", path="/World/Detached")
        model = Mock()
        delegate = _ConcreteTreeDelegate()
        self.addCleanup(delegate.destroy)

        # Act
        with patch.object(delegate, "_item_clicked") as item_clicked:
            delegate.call_item_clicked(0, True, model, canonical_item)

        # Assert
        item_clicked.assert_not_called()


class TestStageManagerTreeModelThreadedRefresh(_StageManagerTreeTestCase):
    async def test_selection_property_owns_assigned_items(self):
        # Arrange
        first_item = StageManagerTreeItemProxy(self._make_canonical_item("First", path="/First"))
        second_item = StageManagerTreeItemProxy(self._make_canonical_item("Second", path="/Second"))
        assigned_items = [first_item]
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)

        # Act
        model.selection = assigned_items
        assigned_items.append(second_item)
        returned_items = model.selection
        returned_items.clear()

        # Assert
        self.assertEqual([first_item], model.selection)

    async def test_notify_canonical_item_rebuilds_its_proxy(self):
        # Arrange
        canonical_item = self._make_canonical_item("Specialized", path="/World/Specialized")
        proxy_item = StageManagerTreeItemProxy(canonical_item)
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)

        # Act
        with patch.object(model, "_item_changed") as item_changed:
            model.notify_item_changed(canonical_item)

        # Assert
        item_changed.assert_called_once_with(proxy_item)

    async def test_context_menu_payload_unwraps_proxy_to_canonical_item(self):
        # Arrange
        canonical_item = self._make_canonical_item("Specialized", path="/World/Specialized")
        proxy_item = StageManagerTreeItemProxy(canonical_item)
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)

        # Act
        payload = model.get_context_menu_payload(proxy_item)

        # Assert
        self.assertIs(model, payload["model"])
        self.assertIs(canonical_item, payload["right_clicked_item"])

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
        previous_canonical_item = _SpecializedTreeItem("Previous", Mock(), path="/Previous")
        previous_canonical_child = _SpecializedTreeItem("Child", Mock(), path="/Previous/Child")
        current_canonical_item = _SpecializedTreeItem("Current", Mock(), path="/Current")
        self.addCleanup(previous_canonical_item.destroy)
        self.addCleanup(previous_canonical_child.destroy)
        self.addCleanup(current_canonical_item.destroy)
        previous_canonical_child.parent = previous_canonical_item
        previous_proxy = StageManagerTreeItemProxy(previous_canonical_item)
        previous_child_proxy = StageManagerTreeItemProxy(previous_canonical_child)
        current_proxy = StageManagerTreeItemProxy(current_canonical_item)
        model._canonical_root_items = [previous_canonical_item]
        canonical_root_items = [current_canonical_item]
        root_items = [current_proxy]
        items_by_path = {"/Current": [current_proxy]}
        item_by_hash = {hash(current_proxy): current_proxy}
        path_by_hash = {hash(current_proxy): "/Current"}
        result = TreeRefreshResult(
            canonical_root_items=canonical_root_items,
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
        self.assertIs(canonical_root_items, model._canonical_root_items)
        self.assertIs(root_items, model._items)
        self.assertIs(items_by_path, model._items_by_path)
        self.assertIs(item_by_hash, model._item_by_hash)
        self.assertIsNone(previous_canonical_item.proxy)
        self.assertIsNone(previous_canonical_child.proxy)
        self.assertIs(previous_canonical_item, previous_proxy.original_tree_item)
        self.assertIs(previous_canonical_child, previous_child_proxy.original_tree_item)
        self.assertIs(current_proxy, current_canonical_item.proxy)

    async def test_clear_items_clears_render_state_and_preserves_context_items(self):
        # Arrange
        model = _ConcreteTreeModel()
        self.addCleanup(model.destroy)
        context_items = _make_context_tree()
        filter_plugin = _PreparedFilterPlugin()
        refresh_cancel_event = threading.Event()
        canonical_item = _SpecializedTreeItem("Canonical", Mock(), path="/Canonical")
        self.addCleanup(canonical_item.destroy)
        rendered_item = StageManagerTreeItemProxy(canonical_item)
        selected_item = Mock()
        model._canonical_root_items = [canonical_item]
        model._items = [rendered_item]
        model.selection = [selected_item]
        model._items_by_path = {"/Canonical": [rendered_item]}
        model._item_by_hash = {hash(rendered_item): rendered_item}
        model._context_items = context_items
        model._user_filter_plugins = [filter_plugin]
        model._refresh_cancel_event = refresh_cancel_event

        # Act
        with patch.object(model, "_item_changed") as item_changed:
            model.clear_items()

        # Assert
        self.assertEqual([], model._canonical_root_items)
        self.assertEqual([], model._items)
        self.assertEqual([], model.selection)
        self.assertEqual({}, model._items_by_path)
        self.assertEqual({}, model._item_by_hash)
        self.assertIs(model._context_items, context_items)
        self.assertEqual([filter_plugin], model._user_filter_plugins)
        self.assertIs(refresh_cancel_event, model._refresh_cancel_event)
        self.assertIsNone(canonical_item.proxy)
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
        with (
            patch(
                "omni.flux.stage_manager.factory.plugins.tree_plugin.asyncio.to_thread",
                wraps=asyncio.to_thread,
            ) as to_thread_mock,
            patch.object(
                model,
                "_collect_canonical_items",
                wraps=model._collect_canonical_items,
            ) as collect_canonical_items,
        ):
            result = await model.refresh_threaded()

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(1, to_thread_mock.call_count)
        collect_canonical_items.assert_not_called()
        self.assertNotEqual(main_thread_id, filter_plugin._preparation_thread_id)
        self.assertTrue(all(thread_id != main_thread_id for thread_id in filter_plugin._predicate_thread_ids))
        self.assertNotEqual(main_thread_id, model.build_thread_id)
        self.assertEqual(filter_plugin._preparation_thread_id, model.build_thread_id)
        self.assertTrue(all(thread_id == model.build_thread_id for thread_id in filter_plugin._predicate_thread_ids))
        original_root = result.root_items[0].original_tree_item
        original_leaf = result.root_items[0].children[0].children[0].original_tree_item
        dropped_item = next(item for item in result.canonical_root_items if item.path == "/Dropped")
        self.assertEqual(["Dropped", "World"], sorted(item.display_name for item in result.canonical_root_items))
        self.assertEqual("World", original_root.display_name)
        self.assertEqual("Leaf", original_leaf.display_name)
        self.assertTrue(all(isinstance(item, StageManagerTreeItemProxy) for item in result.item_by_hash.values()))
        self.assertNotIn(hash(dropped_item.proxy), result.path_by_hash)
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
        async with asyncio.TaskGroup() as task_group:
            try:
                first_refresh_task = task_group.create_task(model.refresh_threaded())
                worker_started = await asyncio.to_thread(model.first_build_started.wait, 2)
                self.assertTrue(worker_started)

                # Act
                second_result = await asyncio.wait_for(model.refresh_threaded(), timeout=2)
                model.release_first_build.set()
                first_result = await asyncio.wait_for(first_refresh_task, timeout=2)
            finally:
                model.release_first_build.set()

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
        async with asyncio.TaskGroup() as task_group:
            try:
                refresh_task = task_group.create_task(model.refresh_threaded())
                worker_started = await asyncio.to_thread(model.first_build_started.wait, 2)
                self.assertTrue(worker_started)

                # Act
                refresh_task.cancel()
                model.release_first_build.set()

                # Assert
                with self.assertRaises(asyncio.CancelledError):
                    await refresh_task
            finally:
                model.release_first_build.set()

    async def test_destroy_during_refresh_cancels_worker_and_prevents_publication(self):
        # Arrange
        model = _BlockingTreeModel()
        self.addCleanup(model.destroy)
        self.addCleanup(model.release_first_build.set)
        canonical_item = _SpecializedTreeItem("Canonical", Mock(), path="/Canonical")
        self.addCleanup(canonical_item.destroy)
        StageManagerTreeItemProxy(canonical_item)
        model._canonical_root_items = [canonical_item]
        model.set_context_items(_make_context_tree())
        async with asyncio.TaskGroup() as task_group:
            try:
                refresh_task = task_group.create_task(model.refresh())
                worker_started = await asyncio.to_thread(model.first_build_started.wait, 2)
                self.assertTrue(worker_started)
                cancel_event = model._refresh_cancel_event

                # Act
                model.destroy()
                model.release_first_build.set()
                await asyncio.wait_for(refresh_task, timeout=2)
            finally:
                model.release_first_build.set()

        # Assert
        self.assertTrue(cancel_event.is_set())
        self.assertIsNone(model._items)
        self.assertIsNone(canonical_item.proxy)

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
        self.assertTrue(all(isinstance(item, StageManagerTreeItemProxy) for item in result.item_by_hash.values()))
        expected_path_by_hash = {}
        for item in result.item_by_hash.values():
            original_item = item.original_tree_item
            if original_item.path is not None:
                expected_path_by_hash[hash(item)] = original_item.path
        self.assertEqual(expected_path_by_hash, result.path_by_hash)
        original_root = result.root_items[0].original_tree_item
        original_child = result.root_items[0].children[0].original_tree_item
        original_leaf = result.root_items[0].children[0].children[0].original_tree_item
        self.assertEqual("World", original_root.display_name)
        self.assertEqual("Child", original_child.display_name)
        self.assertEqual("Leaf", original_leaf.display_name)
        canonical_root = result.canonical_root_items[0]
        root_proxy = result.root_items[0]
        self.assertIs(root_proxy, canonical_root.proxy)
        self.assertIsNot(canonical_root._children, root_proxy._children)
        self.assertEqual(["Child"], [item.display_name for item in canonical_root.children])
        self.assertEqual(
            original_state,
            [(item.identifier, item.data, item.parent, item.is_valid, item.is_child_valid) for item in context_items],
        )
        self.assertTrue(all(not hasattr(item, "tree_item") for item in context_items))

    async def test_project_item_proxies_keeps_pathless_descendants_without_mutating_hierarchies(self):
        # Arrange
        root = _SpecializedTreeItem("Root", Mock(), path="/Root")
        child = _SpecializedTreeItem("Child", None)
        grandchild = _SpecializedTreeItem("Grandchild", None)
        self.addCleanup(root.destroy)
        self.addCleanup(child.destroy)
        self.addCleanup(grandchild.destroy)
        child.parent = root
        grandchild.parent = child
        root_proxy = StageManagerTreeItemProxy(root)
        child_proxy = StageManagerTreeItemProxy(child)
        grandchild_proxy = StageManagerTreeItemProxy(grandchild)
        canonical_items = [root, child, grandchild]
        canonical_snapshot = _snapshot_hierarchy([root])

        # Act
        projection = _ConcreteTreeModel._project_item_proxies(
            canonical_items,
            [root],
            {"/Root"},
            True,
            threading.Event(),
        )

        # Assert
        visible_roots, visible_children, items_by_path, item_by_hash = projection
        self.assertEqual([root_proxy], visible_roots)
        self.assertEqual(
            {
                root_proxy: [child_proxy],
                child_proxy: [grandchild_proxy],
                grandchild_proxy: [],
            },
            visible_children,
        )
        self.assertEqual({"/Root": [root_proxy]}, items_by_path)
        self.assertEqual({root_proxy, child_proxy, grandchild_proxy}, set(item_by_hash.values()))
        self.assertEqual(canonical_snapshot, _snapshot_hierarchy([root]))
        self.assertEqual([], root_proxy.children)
        self.assertEqual([], child_proxy.children)
        self.assertEqual([], grandchild_proxy.children)

    async def test_apply_filters_changes_only_proxy_projection(self):
        # Arrange
        model = _BuildItemsTreeModel()
        self.addCleanup(model.destroy)
        filter_plugin = _PreparedFilterPlugin(filter_active=False)
        context_items = _make_context_tree()
        dropped_prim = Mock()
        dropped_prim.GetPath.return_value = Sdf.Path("/Dropped")
        context_items.append(StageManagerItem("/Dropped", data=dropped_prim))
        model.set_context_items(context_items)
        model.add_user_filter_plugins([filter_plugin])
        await model.refresh()
        canonical_snapshot = _snapshot_hierarchy(model._canonical_root_items)
        canonical_items = model._collect_canonical_items(model._canonical_root_items)
        proxies = [item.proxy for item in canonical_items]
        selected_proxy = model.get_items_by_path("/Dropped")[0]
        model.selection = [selected_proxy]

        # Act
        with (
            patch.object(model, "_build_items", wraps=model._build_items) as build_items,
            patch.object(
                model,
                "_collect_canonical_items",
                wraps=model._collect_canonical_items,
            ) as collect_canonical_items,
            patch.object(model, "_item_changed") as item_changed,
        ):
            filter_plugin.filter_active = True
            result = await model.apply_filters()

        # Assert
        self.assertEqual((4, 3), result)
        build_items.assert_not_called()
        collect_canonical_items.assert_called_once()
        item_changed.assert_called_once_with(None)
        self.assertEqual(canonical_snapshot, _snapshot_hierarchy(model._canonical_root_items))
        self.assertEqual(proxies, [item.proxy for item in canonical_items])
        self.assertEqual([selected_proxy], model.selection)
        original_root = model.get_item_children(None)[0].original_tree_item
        self.assertEqual("World", original_root.display_name)
        self.assertEqual([], model.get_items_by_path("/Dropped"))

    async def test_apply_filters_without_active_filters_does_not_read_context_paths(self):
        # Arrange
        model = _BuildItemsTreeModel()
        self.addCleanup(model.destroy)
        filter_plugin = _PreparedFilterPlugin(filter_active=True)
        context_items = _make_context_tree()
        dropped_prim = Mock()
        dropped_prim.GetPath.return_value = Sdf.Path("/Dropped")
        context_items.append(StageManagerItem("/Dropped", data=dropped_prim))
        model.set_context_items(context_items)
        model.add_user_filter_plugins([filter_plugin])
        await model.refresh()
        dropped_item = next(item for item in model._canonical_root_items if item.path == "/Dropped")
        dropped_proxy = dropped_item.proxy
        hidden_proxies = model.get_items_by_path("/Dropped")
        filter_plugin.filter_active = False
        for item in context_items:
            item.data.GetPath.reset_mock()

        # Act
        await model.apply_filters()

        # Assert
        for item in context_items:
            item.data.GetPath.assert_not_called()
        self.assertEqual([], hidden_proxies)
        self.assertEqual([dropped_proxy], model.get_items_by_path("/Dropped"))

    async def _start_blocked_filter(self, task_group: asyncio.TaskGroup):
        """Start a filter worker paused before publication."""
        model = _BlockingFilterTreeModel()
        self.addCleanup(model.destroy)
        self.addCleanup(model.release_filter_projection.set)
        filter_plugin = _PreparedFilterPlugin(filter_active=False)
        model.set_context_items(_make_context_tree())
        model.add_user_filter_plugins([filter_plugin])
        await model.refresh()
        filter_plugin.filter_active = True
        model.block_filter_projection = True
        filter_task = task_group.create_task(model.apply_filters())
        self.assertTrue(await asyncio.to_thread(model.filter_projection_started.wait, 2))
        return model, filter_task, _snapshot_hierarchy(model._items)

    async def test_apply_filters_when_task_cancelled_does_not_publish(self):
        # Arrange
        async with asyncio.TaskGroup() as task_group:
            model, filter_task, proxy_snapshot = await self._start_blocked_filter(task_group)
            try:
                # Act
                with patch.object(model, "_item_changed") as item_changed:
                    filter_task.cancel()
                    model.release_filter_projection.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await filter_task
            finally:
                model.release_filter_projection.set()

        # Assert
        item_changed.assert_not_called()
        self.assertEqual(proxy_snapshot, _snapshot_hierarchy(model._items))

    async def test_apply_filters_when_canonical_roots_replaced_discards_projection(self):
        # Arrange
        async with asyncio.TaskGroup() as task_group:
            model, filter_task, proxy_snapshot = await self._start_blocked_filter(task_group)
            try:
                # Act
                with patch.object(model, "_item_changed") as item_changed:
                    model._canonical_root_items = list(model._canonical_root_items)
                    model.release_filter_projection.set()
                    result = await filter_task
            finally:
                model.release_filter_projection.set()

        # Assert
        self.assertIsNone(result)
        item_changed.assert_not_called()
        self.assertEqual(proxy_snapshot, _snapshot_hierarchy(model._items))

    async def test_apply_filters_keeps_duplicate_path_proxies(self):
        # Arrange
        model = _DuplicatePathTreeModel()
        self.addCleanup(model.destroy)
        filter_plugin = _RootPreparedFilterPlugin(filter_active=False)
        context_items = _make_context_tree()
        model.set_context_items([context_items[0]])
        model.add_user_filter_plugins([filter_plugin])
        refresh_result = await model.refresh_threaded()
        model.publish_refresh_result(refresh_result)
        matching_proxies = model.get_items_by_path("/World")
        filter_plugin.filter_active = True

        # Act
        result = await model.apply_filters()

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(matching_proxies, model.get_items_by_path("/World"))
        self.assertEqual(2, len(model.get_items_by_path("/World")))
        self.assertEqual(
            ["GroupA", "GroupB"],
            [item.original_tree_item.display_name for item in model.get_item_children(None)],
        )

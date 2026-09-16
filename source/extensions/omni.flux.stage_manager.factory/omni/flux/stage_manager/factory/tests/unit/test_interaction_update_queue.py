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
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, call, patch

import carb.input
import omni.kit.app
import omni.kit.test
from omni.flux.stage_manager.factory.items import StageManagerItem
from omni.flux.stage_manager.factory.plugins.interaction_plugin import StageManagerInteractionPlugin
from omni.flux.stage_manager.factory.utils import StageManagerUtils
from pydantic import PrivateAttr


class _TestInteractionPlugin(StageManagerInteractionPlugin):
    """Provide the minimum concrete interaction used by queue tests."""

    def _setup_listeners(self):
        """Skip listener setup for tests."""
        pass

    def _clear_listeners(self):
        """Skip listener cleanup for tests."""
        pass

    def build_ui(self, *args, **kwargs):
        """Skip UI construction for tests."""
        pass


class _QueueingInteractionPlugin(_TestInteractionPlugin):
    """Queue a second context update during the first update."""

    _update_calls: int = PrivateAttr(default=0)

    async def _update_context_items(self):
        """Record an update and enqueue a replacement on the first call."""
        self._update_calls += 1
        if self._update_calls == 1:
            self._update_queue.put_nowait(True)


class TestStageManagerInteractionUpdateQueue(omni.kit.test.AsyncTestCase):
    """Test Stage Manager interaction update scheduling and publication."""

    def _make_plugin(self, **kwargs):
        """Create a minimally configured interaction plugin."""
        return _TestInteractionPlugin.model_construct(display_name="TestInteraction", tooltip="For tests", **kwargs)

    async def test_tree_ctrl_a_selects_published_tree_items(self):
        """Delegate Ctrl+A to the scrolling tree's generic selection operation."""
        # Arrange
        plugin = self._make_plugin(tree=Mock())
        plugin.tree.model.get_items_by_path.return_value = []
        plugin._tree_widget = Mock()

        # Act
        plugin._on_tree_key_pressed(
            int(carb.input.KeyboardInput.A),
            carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL,
            True,
        )

        # Assert
        plugin._tree_widget.select_all.assert_called_once_with()

    async def test_tree_ctrl_a_expands_root_node(self):
        """Expand the retained RootNode row when selecting all."""
        # Arrange
        root_node = Mock()
        plugin = self._make_plugin(tree=Mock())
        plugin.tree.model.get_items_by_path.return_value = [root_node]
        plugin._tree_widget = Mock()

        # Act
        plugin._on_tree_key_pressed(
            int(carb.input.KeyboardInput.A),
            carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL,
            True,
        )

        # Assert
        plugin._tree_widget.set_expanded.assert_called_once_with(root_node, True, False)

    async def test_tree_non_ctrl_a_input_does_not_change_selection(self):
        """Ignore key input that is not an exact Ctrl+A key press."""
        cases = (
            (int(carb.input.KeyboardInput.A), 0, True, "plain A"),
            (
                int(carb.input.KeyboardInput.A),
                carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL,
                False,
                "Ctrl+A key up",
            ),
            (
                int(carb.input.KeyboardInput.A),
                carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL | carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT,
                True,
                "Ctrl+Shift+A",
            ),
        )
        for key, modifiers, is_down, title in cases:
            with self.subTest(title=title):
                # Arrange
                plugin = self._make_plugin(tree=Mock())
                plugin._tree_widget = Mock()

                # Act
                plugin._on_tree_key_pressed(key, modifiers, is_down)

                # Assert
                plugin._tree_widget.select_all.assert_not_called()

    async def test_on_hidden_clears_stale_ui_refresh_targets(self):
        """Clear stale UI refresh targets when the interaction is hidden."""
        # Arrange
        plugin = self._make_plugin(filters=[], additional_filters=[])
        plugin._result_frames = [Mock()]
        plugin._loading_frame = Mock()
        plugin._tree_widget = Mock()
        tree_widget = plugin._tree_widget

        # Act
        plugin.on_hidden()

        # Assert
        self.assertEqual([], plugin._result_frames)
        self.assertIsNone(plugin._loading_frame)
        tree_widget.destroy.assert_called_once_with()
        self.assertIsNone(plugin._tree_widget)

    async def test_refresh_tree_model_with_widget_uses_default_refresh_path(self):
        """Refresh through the widget while temporarily disabling keep-alive."""
        # Arrange
        keep_alive_disabled = False
        refresh_result = Mock(input_items_count=4, output_items_count=4)

        @asynccontextmanager
        async def _keep_alive_disabled():
            """Record the keep-alive-disabled scope."""
            nonlocal keep_alive_disabled
            keep_alive_disabled = True
            try:
                yield
            finally:
                keep_alive_disabled = False

        plugin = self._make_plugin(tree=Mock())
        plugin._tree_widget = Mock()
        plugin._tree_widget.keep_alive_disabled = Mock(side_effect=_keep_alive_disabled)
        keep_alive_during_refresh = []

        async def _refresh_model(**_kwargs):
            """Record keep-alive state during model refresh."""
            keep_alive_during_refresh.append(keep_alive_disabled)
            return refresh_result

        plugin._tree_widget.refresh_model = AsyncMock(side_effect=_refresh_model)
        plugin.tree.model.refresh = AsyncMock()
        plugin.tree.apply_filters = AsyncMock()
        plugin._wait_for_post_refresh_work = AsyncMock()

        # Act
        plugin._refresh_tree_model()
        await plugin._model_refresh_task

        # Assert
        self.assertEqual([True], keep_alive_during_refresh)
        plugin._tree_widget.keep_alive_disabled.assert_called_once_with()
        plugin._tree_widget.refresh_model.assert_awaited_once_with(expand_filtered_roots=False)
        plugin.tree.model.refresh.assert_not_called()
        plugin.tree.apply_filters.assert_not_awaited()
        plugin._wait_for_post_refresh_work.assert_awaited_once_with()

    async def test_filter_update_during_context_post_refresh_is_applied_before_completion(self):
        """Apply a filter update queued during context post-refresh work."""

        # Arrange
        @asynccontextmanager
        async def _keep_alive_disabled():
            """Provide the keep-alive-disabled scope."""
            yield

        refresh_result = Mock(input_items_count=5, output_items_count=5)
        plugin = self._make_plugin(tree=Mock())
        plugin._tree_widget = Mock()
        plugin._tree_widget.keep_alive_disabled = Mock(side_effect=_keep_alive_disabled)
        plugin._tree_widget.refresh_model = AsyncMock(return_value=refresh_result)
        plugin._tree_widget.wait_for_model_change_sync = AsyncMock()
        plugin._tree_widget.frame_items = AsyncMock()
        plugin.tree.apply_filters = AsyncMock(return_value=(5, 2))
        post_refresh_count = 0

        async def _wait_for_post_refresh_work():
            """Queue a filter refresh during the first post-refresh wait."""
            nonlocal post_refresh_count
            post_refresh_count += 1
            if post_refresh_count == 1:
                plugin._on_filter_items_changed()

        plugin._wait_for_post_refresh_work = AsyncMock(side_effect=_wait_for_post_refresh_work)

        # Act
        plugin._refresh_tree_model()
        context_refresh_task = plugin._model_refresh_task
        await context_refresh_task

        # Assert
        plugin._tree_widget.refresh_model.assert_awaited_once_with(expand_filtered_roots=False)
        plugin.tree.apply_filters.assert_awaited_once_with()
        self.assertEqual(2, plugin._wait_for_post_refresh_work.await_count)
        self.assertIs(context_refresh_task, plugin._model_refresh_task)
        self.assertIsNone(plugin._context_refresh_cancel_event)
        self.assertFalse(plugin._filter_refresh_pending)

    async def test_filter_update_uses_filter_only_tree_path(self):
        """Use proxy filtering without rebuilding the canonical tree."""
        # Arrange
        plugin = self._make_plugin(tree=Mock())
        plugin.tree.apply_filters = AsyncMock(return_value=(4, 3))
        plugin._tree_widget = Mock()
        plugin._tree_widget.refresh_model = AsyncMock()
        plugin._tree_widget.wait_for_model_change_sync = AsyncMock()
        plugin._tree_widget.frame_items = AsyncMock()
        plugin._wait_for_post_refresh_work = AsyncMock()

        # Act
        with patch.object(plugin, "_refresh_tree_model") as refresh_tree_model:
            plugin._on_filter_items_changed()
            await plugin._model_refresh_task

        # Assert
        plugin.tree.apply_filters.assert_awaited_once_with()
        refresh_tree_model.assert_not_called()
        plugin._tree_widget.refresh_model.assert_not_awaited()
        plugin._wait_for_post_refresh_work.assert_awaited_once_with()

    async def test_refresh_tree_filters_records_counts_expands_roots_and_finishes_transaction(self):
        """Record filter counts and finish a successful filter transaction."""
        # Arrange
        roots = [Mock(), Mock()]
        selection = [Mock()]
        transaction = Mock()
        plugin = self._make_plugin(tree=Mock())
        plugin.tree.apply_filters = AsyncMock(return_value=(4, 2))
        plugin.tree.model.get_item_children.return_value = roots
        plugin._tree_widget = Mock()
        plugin._tree_widget.selection = selection
        plugin._tree_widget.attach_mock(AsyncMock(), "wait_for_model_change_sync")
        plugin._tree_widget.attach_mock(AsyncMock(), "frame_items")
        plugin._refresh_transaction = transaction
        plugin._filter_refresh_pending = True
        plugin._wait_for_post_refresh_work = AsyncMock()
        plugin._get_refresh_expand_filtered_roots = Mock(return_value=True)

        # Act
        await plugin._refresh_tree_filters_async(plugin._tree_widget, transaction)

        # Assert
        transaction.set_data.assert_any_call("input_items_count", 4)
        transaction.set_data.assert_any_call("output_items_count", 2)
        plugin._tree_widget.assert_has_calls(
            [
                call.wait_for_model_change_sync(),
                *(call.set_expanded(root, True, True, False) for root in roots),
                call.frame_items(selection, update_cache=False),
            ]
        )
        plugin._tree_widget.wait_for_model_change_sync.assert_awaited_once_with()
        plugin._tree_widget.frame_items.assert_awaited_once_with(selection, update_cache=False)
        plugin._wait_for_post_refresh_work.assert_awaited_once_with()
        transaction.set_status.assert_called_once_with("ok")
        transaction.finish.assert_called_once_with()

    async def test_refresh_tree_filters_none_finishes_transaction_as_cancelled(self):
        """Finish the transaction as cancelled when filtering returns no result."""
        # Arrange
        transaction = Mock()
        plugin = self._make_plugin(tree=Mock())
        plugin.tree.apply_filters = AsyncMock(return_value=None)
        plugin._loading_frame = Mock(visible=True)
        plugin._tree_widget = Mock()
        plugin._refresh_transaction = transaction
        plugin._model_refresh_task = asyncio.current_task()
        plugin._filter_refresh_pending = True

        # Act
        await StageManagerInteractionPlugin._refresh_tree_filters_async.__wrapped__(
            plugin, plugin._tree_widget, transaction
        )

        # Assert
        self.assertFalse(plugin._loading_frame.visible)
        transaction.set_status.assert_called_once_with("cancelled")
        transaction.finish.assert_called_once_with()

    async def test_model_sync_failure_is_observed_by_filter_transaction(self):
        """Report model synchronization failures on the active transaction."""
        # Arrange
        transaction = Mock()
        plugin = self._make_plugin(tree=Mock())
        plugin.tree.apply_filters = AsyncMock(return_value=(3, 1))
        plugin._tree_widget = Mock()
        plugin._tree_widget.wait_for_model_change_sync = AsyncMock(side_effect=RuntimeError("sync failed"))
        plugin._loading_frame = Mock(visible=True)
        plugin._refresh_transaction = transaction
        plugin._model_refresh_task = asyncio.current_task()
        plugin._filter_refresh_pending = True

        # Act
        with self.assertRaisesRegex(RuntimeError, "sync failed"):
            await StageManagerInteractionPlugin._refresh_tree_filters_async.__wrapped__(
                plugin, plugin._tree_widget, transaction
            )

        # Assert
        self.assertFalse(plugin._loading_frame.visible)
        transaction.set_status.assert_called_once_with("internal_error")
        transaction.finish.assert_called_once_with()

    async def test_queue_context_update_immediately_cancels_filter_model_work(self):
        """Cancel active filter-model work when a context update is queued."""
        # Arrange
        filter_started = asyncio.Event()
        release_filter = asyncio.Event()
        release_context = asyncio.Event()

        async def _apply_filters():
            """Block filter application until cleanup releases it."""
            filter_started.set()
            await release_filter.wait()

        async def _update_context_items():
            """Block context preparation until cleanup releases it."""
            await release_context.wait()

        plugin = self._make_plugin(tree=Mock())
        plugin.tree.apply_filters = AsyncMock(side_effect=_apply_filters)
        plugin._tree_widget = Mock()
        plugin._loading_frame = Mock(visible=False)
        plugin._update_context_items = AsyncMock(side_effect=_update_context_items)
        plugin._on_filter_items_changed()
        stale_filter_task = plugin._model_refresh_task
        try:
            await filter_started.wait()

            # Act
            plugin._queue_update(update_context_items=True)
            await stale_filter_task

            # Assert
            self.assertIsNone(plugin._model_refresh_task)
            self.assertIsNotNone(plugin._context_refresh_cancel_event)
            self.assertTrue(plugin._loading_frame.visible)
        finally:
            release_filter.set()
            release_context.set()
            tasks = [task for task in (stale_filter_task, plugin._update_items_task) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_filter_update_cancels_superseded_model_task(self):
        """Cancel the prior model task before applying a newer filter update."""
        # Arrange
        release_old_task = asyncio.Event()
        old_task = asyncio.create_task(release_old_task.wait())
        plugin = self._make_plugin(tree=Mock())
        plugin.tree.apply_filters = AsyncMock(return_value=(0, 0))
        plugin._tree_widget = Mock()
        plugin._tree_widget.wait_for_model_change_sync = AsyncMock()
        plugin._tree_widget.frame_items = AsyncMock()
        plugin._wait_for_post_refresh_work = AsyncMock()
        plugin._model_refresh_task = old_task

        try:
            # Act
            plugin._on_filter_items_changed()
            new_task = plugin._model_refresh_task
            old_result, new_result = await asyncio.gather(old_task, new_task, return_exceptions=True)
        finally:
            release_old_task.set()
            if not old_task.done():
                old_task.cancel()
            await asyncio.gather(old_task, return_exceptions=True)

        # Assert
        self.assertIsInstance(old_result, asyncio.CancelledError)
        self.assertIsNone(new_result)
        plugin.tree.apply_filters.assert_awaited_once_with()

    async def test_refresh_tree_model_without_widget_skips_refresh_and_cleans_state(self):
        """Skip refresh and clear refresh state when no widget exists."""
        # Arrange
        plugin = self._make_plugin(tree=Mock())
        plugin._tree_widget = None
        plugin.tree.model.refresh = AsyncMock()
        plugin.tree.apply_filters = AsyncMock()
        plugin._filter_refresh_pending = True
        plugin._context_refresh_cancel_event = threading.Event()
        plugin._loading_frame = Mock(visible=True)

        # Act
        plugin._refresh_tree_model()
        scheduled_task = plugin._model_refresh_task
        if scheduled_task is not None:
            await scheduled_task

        # Assert
        plugin.tree.model.refresh.assert_not_awaited()
        plugin.tree.apply_filters.assert_not_awaited()
        self.assertIsNone(plugin._model_refresh_task)
        self.assertFalse(plugin._filter_refresh_pending)
        self.assertIsNone(plugin._context_refresh_cancel_event)
        self.assertFalse(plugin._loading_frame.visible)

    async def test_update_queue_worker_drains_updates_queued_during_context_refresh(self):
        """Drain an update queued while the current context update runs."""
        # Arrange
        plugin = _QueueingInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
        )
        plugin._update_queue = asyncio.Queue()
        plugin._update_queue.put_nowait(True)

        # Act
        await plugin._update_queue_worker()

        # Assert
        self.assertEqual(plugin._update_calls, 2)
        self.assertTrue(plugin._update_queue.empty())

    async def test_update_queue_worker_with_context_update_does_not_wait_frames(self):
        """Run an already-queued context update without an extra frame wait."""
        # Arrange
        plugin = self._make_plugin()
        plugin._update_queue = asyncio.Queue()
        plugin._update_queue.put_nowait(True)
        kit_app = Mock()
        kit_app.next_update_async = AsyncMock()

        # Act
        with (
            patch.object(plugin, "_update_context_items", new=AsyncMock()) as update_context_items,
            patch.object(omni.kit.app, "get_app", return_value=kit_app),
        ):
            await plugin._update_queue_worker()

        # Assert
        update_context_items.assert_awaited_once_with()
        kit_app.next_update_async.assert_not_awaited()

    async def test_update_context_items_when_active_waits_one_frame_before_getting_items(self):
        """Wait one frame before collecting active-interaction context items."""
        # Arrange
        call_order = []
        plugin = self._make_plugin(
            context_filters=[],
            internal_context_filters=[],
            allow_context_ancestors=True,
            tree=Mock(),
        )
        plugin._is_active = True
        plugin._update_queue = asyncio.Queue()
        plugin._context = Mock()
        plugin._context.get_items.side_effect = lambda _cancel_event: call_order.append("get_items") or ["source"]
        plugin._context_items_changed = Mock()
        plugin.tree.model.set_context_items = Mock()
        kit_app = Mock()

        async def _next_update():
            """Record the initial frame wait."""
            call_order.append("next_update")

        kit_app.next_update_async = AsyncMock(side_effect=_next_update)

        # Act
        with (
            patch.object(asyncio, "sleep", new=AsyncMock()) as sleep_mock,
            patch.object(omni.kit.app, "get_app", return_value=kit_app),
            patch.object(StageManagerUtils, "filter_items", new=AsyncMock(return_value=["source"])),
        ):
            await plugin._update_context_items()

        # Assert
        self.assertEqual(["next_update", "get_items"], call_order)
        kit_app.next_update_async.assert_awaited_once_with()
        sleep_mock.assert_not_awaited()

    async def test_update_context_items_culls_context_for_the_tree_model_capability(self):
        """Publish context items according to each tree model's ancestor requirement."""
        test_cases = (
            (
                "grouped model excludes invalid ancestors",
                False,
                True,
                ("retained", "matching", "matching"),
                (None, "retained", "retained"),
            ),
            (
                "hierarchical model retains invalid ancestors",
                True,
                True,
                ("root", "retained", "excluded", "matching", "matching"),
                (None, "root", "retained", "excluded", "excluded"),
            ),
            (
                "explicit sparse mode overrides hierarchy",
                True,
                False,
                ("retained", "matching", "matching"),
                (None, "retained", "retained"),
            ),
        )
        for (
            title,
            requires_context_ancestors,
            allow_context_ancestors,
            expected_identifiers,
            expected_parent_identifiers,
        ) in test_cases:
            with self.subTest(
                title=title,
                requires_context_ancestors=requires_context_ancestors,
                allow_context_ancestors=allow_context_ancestors,
            ):
                # Arrange
                kit_app = Mock()
                kit_app.next_update_async = AsyncMock()
                root = StageManagerItem("root")
                retained = StageManagerItem("retained", parent=root)
                excluded = StageManagerItem("excluded", parent=retained)
                matching = StageManagerItem("matching", parent=excluded)
                matching_duplicate = StageManagerItem("matching", parent=excluded)
                context_items = [root, retained, excluded, matching, matching_duplicate]
                published_items = []
                publication_order = []
                predicate_items = []
                tree = Mock()
                tree.model.requires_context_ancestors = requires_context_ancestors

                def _set_context_items(items, published_items=published_items, publication_order=publication_order):
                    """Record the model publication order and published items."""
                    published_items.append(items)
                    publication_order.append("set_context_items")

                context_filter = Mock(enabled=True)

                def _predicate(item, predicate_items=predicate_items):
                    """Reject the excluded source items while recording evaluation order."""
                    predicate_items.append(item)
                    return item.identifier not in {"excluded", "root"}

                def _context_items_changed(publication_order=publication_order):
                    """Record context publication after its items are available."""
                    publication_order.append("context_items_changed")

                tree.model.set_context_items.side_effect = _set_context_items
                context_filter.build_filter_predicate.return_value = _predicate
                plugin = self._make_plugin(
                    context_filters=[context_filter],
                    internal_context_filters=[],
                    allow_context_ancestors=allow_context_ancestors,
                    tree=tree,
                )
                plugin._is_active = True
                plugin._update_queue = asyncio.Queue()
                plugin._context = Mock()
                plugin._context.get_items.return_value = context_items
                plugin._context_items_changed = Mock(side_effect=_context_items_changed)

                # Act
                with patch.object(omni.kit.app, "get_app", return_value=kit_app):
                    await plugin._update_context_items()

                # Assert
                self.assertEqual(1, len(published_items))
                tree.model.set_context_items.assert_called_once_with(published_items[0])
                self.assertEqual(expected_identifiers, tuple(item.identifier for item in published_items[0]))
                self.assertEqual(
                    expected_parent_identifiers,
                    tuple(item.parent.identifier if item.parent else None for item in published_items[0]),
                )
                self.assertIs(published_items[0][-2], matching)
                self.assertIs(published_items[0][-1], matching_duplicate)
                self.assertIsNot(published_items[0][-2], published_items[0][-1])
                self.assertEqual(context_items, predicate_items)
                self.assertEqual(["set_context_items", "context_items_changed"], publication_order)
                plugin._context_items_changed.assert_called_once_with()

    async def test_update_context_items_prepares_display_names_before_sparse_culling(self):
        """Prepare display names before sparse context candidates are culled."""
        # Arrange
        relevant_path = Mock()
        relevant_path.name = "Shared"
        relevant_path.GetParentPath.return_value.name = "World"
        relevant_prim = Mock()
        relevant_prim.GetPath.return_value = relevant_path
        relevant = StageManagerItem("relevant", data=relevant_prim)

        ancestor_path = Mock()
        ancestor_path.name = "Shared"
        ancestor_path.GetParentPath.return_value.name = "Other"
        ancestor_prim = Mock()
        ancestor_prim.GetPath.return_value = ancestor_path
        ancestor = StageManagerItem("ancestor", data=ancestor_prim)

        rejected_candidate_path = Mock()
        rejected_candidate_path.name = "Child"
        rejected_candidate_path.GetParentPath.return_value.name = "Shared"
        rejected_candidate_prim = Mock()
        rejected_candidate_prim.GetPath.return_value = rejected_candidate_path
        rejected_candidate = StageManagerItem("rejected_candidate", data=rejected_candidate_prim, parent=ancestor)

        schema_filter = Mock(enabled=True)
        schema_filter.build_filter_predicate.return_value = lambda item: item is not ancestor
        intrinsic_filter = Mock(enabled=True)

        def _intrinsic_predicate(item):
            """Mark display-name candidates and retain the relevant item."""
            item.mark_display_name_candidate()
            return item is relevant

        intrinsic_filter.build_filter_predicate.return_value = _intrinsic_predicate
        tree = Mock()
        tree.model.requires_context_ancestors = False
        plugin = self._make_plugin(
            context_filters=[schema_filter],
            internal_context_filters=[intrinsic_filter],
            allow_context_ancestors=True,
            tree=tree,
        )
        plugin._is_active = True
        plugin._update_queue = asyncio.Queue()
        plugin._context = Mock()
        plugin._context.get_items.return_value = [ancestor, rejected_candidate, relevant]
        plugin._context_items_changed = Mock()
        kit_app = Mock()
        kit_app.next_update_async = AsyncMock()

        # Act
        with patch.object(omni.kit.app, "get_app", return_value=kit_app):
            await plugin._update_context_items()

        # Assert
        published_items = tree.model.set_context_items.call_args.args[0]
        self.assertEqual([relevant], published_items)
        self.assertTrue(relevant.is_display_name_candidate)
        self.assertTrue(rejected_candidate.is_display_name_candidate)
        self.assertFalse(ancestor.is_display_name_candidate)
        self.assertEqual(("Shared", "World"), relevant.prepared_display_name)
        self.assertEqual(("Shared", "Other"), ancestor.prepared_display_name)
        self.assertEqual(("Child", None), rejected_candidate.prepared_display_name)

    async def test_context_update_queued_during_initial_frame_prevents_stale_context_publication(self):
        """Discard stale context work replaced during the initial frame wait."""
        # Arrange
        frame_started = asyncio.Event()
        release_frame = asyncio.Event()
        frame_count = 0
        plugin = self._make_plugin(
            context_filters=[],
            internal_context_filters=[],
            allow_context_ancestors=True,
            tree=Mock(),
        )
        plugin._is_active = True
        plugin._tree_widget = None
        plugin._update_queue = asyncio.Queue()
        plugin._update_queue.put_nowait(True)
        plugin._context = Mock()
        plugin._context_items_changed = Mock()
        plugin.tree.model.set_context_items = Mock()
        kit_app = Mock()

        async def _next_update():
            """Block the initial frame so a replacement update can be queued."""
            nonlocal frame_count
            frame_count += 1
            if frame_count == 1:
                frame_started.set()
                await release_frame.wait()

        kit_app.next_update_async = AsyncMock(side_effect=_next_update)
        prepare_context_items = AsyncMock(return_value=["latest"])

        # Act
        with (
            patch.object(omni.kit.app, "get_app", return_value=kit_app),
            patch.object(plugin, "_prepare_context_items", prepare_context_items),
        ):
            plugin._update_items_task = asyncio.create_task(plugin._update_queue_worker())
            try:
                await frame_started.wait()
                plugin._queue_update(True)
                release_frame.set()
                await plugin._update_items_task
            finally:
                release_frame.set()
                if not plugin._update_items_task.done():
                    plugin._update_items_task.cancel()
                await asyncio.gather(plugin._update_items_task, return_exceptions=True)

        # Assert
        prepare_context_items.assert_awaited_once()
        plugin.tree.model.set_context_items.assert_called_once_with(["latest"])
        plugin._context_items_changed.assert_called_once_with()

    async def test_update_context_items_runs_collection_and_predicate_preparation_on_worker(self):
        """Run collection, predicate preparation, and evaluation on a worker."""
        # Arrange
        main_thread_id = threading.get_ident()
        worker_thread_ids = {}
        predicate_cancel_events = {}
        source_item = StageManagerItem("source", data=object())
        context_filter = Mock(enabled=True, filter_active=False)

        def _get_items(*_args):
            """Record the collection thread and return one source item."""
            worker_thread_ids["collection"] = threading.get_ident()
            return [source_item]

        def _build_filter_predicate(cancel_event):
            """Build a worker predicate while recording preparation and evaluation threads."""
            worker_thread_ids["predicate_builder"] = threading.get_ident()
            predicate_cancel_events["predicate_builder"] = cancel_event

            def _predicate(_item):
                """Record worker-thread item evaluation."""
                worker_thread_ids["predicate_evaluation"] = threading.get_ident()
                return True

            return _predicate

        context_filter.build_filter_predicate.side_effect = _build_filter_predicate
        plugin = self._make_plugin(
            context_filters=[context_filter],
            internal_context_filters=[],
            allow_context_ancestors=True,
            tree=Mock(),
        )
        plugin._is_active = True
        plugin._update_queue = asyncio.Queue()
        plugin._context = Mock()
        plugin._context.get_items.side_effect = _get_items
        plugin._context_items_changed = Mock()
        plugin.tree.model.set_context_items = Mock()
        kit_app = Mock()
        kit_app.next_update_async = AsyncMock()

        # Act
        with patch.object(omni.kit.app, "get_app", return_value=kit_app):
            await plugin._update_context_items()

        # Assert
        self.assertEqual({"collection", "predicate_builder", "predicate_evaluation"}, set(worker_thread_ids))
        self.assertTrue(all(thread_id != main_thread_id for thread_id in worker_thread_ids.values()))
        self.assertIs(predicate_cancel_events["predicate_builder"], plugin._context_refresh_cancel_event)
        plugin.tree.model.set_context_items.assert_called_once()

    async def test_update_queue_worker_when_lightweight_update_arrives_during_context_refresh_publishes_then_dirties(
        self,
    ):
        """Publish context results before dirtying widgets for a lightweight update."""
        # Arrange
        plugin = self._make_plugin(
            context_filters=[],
            internal_context_filters=[],
            allow_context_ancestors=True,
            tree=Mock(),
        )
        plugin._is_active = True
        plugin._update_queue = asyncio.Queue()
        plugin._update_queue.put_nowait(True)
        plugin._context = Mock()
        plugin._context.get_items.return_value = ["source"]
        plugin._context_items_changed = Mock()
        plugin.tree.model.set_context_items = Mock()
        plugin._tree_widget = Mock()
        kit_app = Mock()
        kit_app.next_update_async = AsyncMock()
        filter_call_count = 0

        async def _filter_items(*_args, **_kwargs):
            """Queue a lightweight update during the first filtering pass."""
            nonlocal filter_call_count
            filter_call_count += 1
            if filter_call_count == 1:
                plugin._update_queue.put_nowait(False)
            return ["completed"]

        # Act
        with (
            patch.object(omni.kit.app, "get_app", return_value=kit_app),
            patch.object(StageManagerUtils, "filter_items", new=AsyncMock(side_effect=_filter_items)) as filter_items,
        ):
            await plugin._update_queue_worker()

        # Assert
        self.assertEqual(1, filter_items.call_count)
        plugin.tree.model.set_context_items.assert_called_once_with(["completed"])
        plugin._context_items_changed.assert_called_once_with()
        plugin._tree_widget.dirty_widgets.assert_called_once_with()

    async def test_set_active_false_cancels_pending_update_and_model_refresh_tasks(self):
        """Cancel pending update and model tasks when the plugin deactivates."""
        # Arrange
        plugin = self._make_plugin()
        plugin._is_active = True
        update_items_task = Mock()
        model_refresh_task = Mock()
        plugin._update_items_task = update_items_task
        plugin._model_refresh_task = model_refresh_task
        plugin._context_refresh_cancel_event = threading.Event()

        # Act
        plugin.set_active(False)

        # Assert
        update_items_task.cancel.assert_called_once_with()
        model_refresh_task.cancel.assert_called_once_with()
        self.assertIsNone(plugin._update_items_task)
        self.assertIsNone(plugin._model_refresh_task)
        self.assertTrue(plugin._context_refresh_cancel_event.is_set())

    async def test_immediate_reactivation_restarts_cancelled_queue_worker(self):
        """Restart the queue worker after immediate deactivation and reactivation."""
        # Arrange
        plugin = self._make_plugin(filters=[], additional_filters=[])
        plugin._update_queue = asyncio.Queue()
        update_started = asyncio.Event()

        async def _update_context_items():
            """Signal that the restarted context update ran."""
            update_started.set()

        plugin._update_context_items = AsyncMock(side_effect=_update_context_items)

        # Act
        plugin.set_active(True)
        plugin.set_active(False)
        plugin.set_active(True)
        update_task = plugin._update_items_task
        try:
            await update_started.wait()
            await update_task
        finally:
            if not update_task.done():
                update_task.cancel()
            await asyncio.gather(update_task, return_exceptions=True)

        # Assert
        plugin._update_context_items.assert_awaited_once_with()
        self.assertTrue(plugin._update_queue.empty())

    async def test_update_context_items_discards_result_when_new_context_update_is_queued(self):
        """Discard context results superseded during filtering."""
        # Arrange
        plugin = self._make_plugin(
            context_filters=[],
            internal_context_filters=[],
            allow_context_ancestors=True,
            tree=Mock(),
        )
        plugin._is_active = True
        plugin._update_queue = asyncio.Queue()
        plugin._context = Mock()
        plugin._context.get_items.return_value = ["source"]
        plugin._context_items_changed = Mock()
        plugin.tree.model.set_context_items = Mock()

        async def _filter_items(*_args, **kwargs):
            """Cancel the current generation and queue its replacement."""
            kwargs["cancel_event"].set()
            plugin._update_queue.put_nowait(True)
            return ["stale"]

        # Act
        with patch.object(StageManagerUtils, "filter_items", new=AsyncMock(side_effect=_filter_items)):
            await plugin._update_context_items()

        # Assert
        plugin.tree.model.set_context_items.assert_not_called()
        plugin._context_items_changed.assert_not_called()

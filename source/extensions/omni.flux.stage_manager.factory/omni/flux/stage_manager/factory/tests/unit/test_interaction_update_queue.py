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

import omni.kit.test
from omni.flux.stage_manager.factory.items import StageManagerItem
from omni.flux.stage_manager.factory.plugins.interaction_plugin import StageManagerInteractionPlugin
from omni.flux.stage_manager.factory.utils import StageManagerUtils
from pydantic import PrivateAttr


class _TestInteractionPlugin(StageManagerInteractionPlugin):
    def _setup_listeners(self):
        pass

    def _clear_listeners(self):
        pass

    def build_ui(self, *args, **kwargs):
        pass


class _QueueingInteractionPlugin(_TestInteractionPlugin):
    _update_calls: int = PrivateAttr(default=0)

    async def _update_context_items(self):
        self._update_calls += 1
        if self._update_calls == 1:
            self._update_queue.put_nowait(True)


class TestStageManagerInteractionUpdateQueue(omni.kit.test.AsyncTestCase):
    def _make_plugin(self, **kwargs):
        return _TestInteractionPlugin.model_construct(display_name="TestInteraction", tooltip="For tests", **kwargs)

    async def test_on_hidden_clears_stale_ui_refresh_targets(self):
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
        # Arrange
        keep_alive_disabled = False
        refresh_result = Mock(input_items_count=4, output_items_count=4)

        @asynccontextmanager
        async def _keep_alive_disabled():
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
        # Arrange
        @asynccontextmanager
        async def _keep_alive_disabled():
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
        # Arrange
        filter_started = asyncio.Event()
        release_filter = asyncio.Event()
        release_context = asyncio.Event()

        async def _apply_filters():
            filter_started.set()
            await release_filter.wait()

        async def _update_context_items():
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
        # Arrange
        plugin = self._make_plugin()
        plugin._update_queue = asyncio.Queue()
        plugin._update_queue.put_nowait(True)
        kit_app = Mock()
        kit_app.next_update_async = AsyncMock()

        # Act
        with (
            patch.object(plugin, "_update_context_items", new=AsyncMock()) as update_context_items,
            patch(
                "omni.flux.stage_manager.factory.plugins.interaction_plugin.omni.kit.app.get_app",
                return_value=kit_app,
            ),
        ):
            await plugin._update_queue_worker()

        # Assert
        update_context_items.assert_awaited_once_with()
        kit_app.next_update_async.assert_not_awaited()

    async def test_update_context_items_when_active_waits_one_frame_before_getting_items(self):
        # Arrange
        call_order = []
        plugin = self._make_plugin(
            context_filters=[],
            internal_context_filters=[],
            include_invalid_parents=True,
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
            call_order.append("next_update")

        kit_app.next_update_async = AsyncMock(side_effect=_next_update)

        # Act
        with (
            patch.object(asyncio, "sleep", new=AsyncMock()) as sleep_mock,
            patch(
                "omni.flux.stage_manager.factory.plugins.interaction_plugin.omni.kit.app.get_app",
                return_value=kit_app,
            ),
            patch.object(StageManagerUtils, "filter_items", new=AsyncMock(return_value=["source"])),
        ):
            await plugin._update_context_items()

        # Assert
        self.assertEqual(["next_update", "get_items"], call_order)
        kit_app.next_update_async.assert_awaited_once_with()
        sleep_mock.assert_not_awaited()

    async def test_context_update_queued_during_initial_frame_prevents_stale_context_publication(self):
        # Arrange
        frame_started = asyncio.Event()
        release_frame = asyncio.Event()
        frame_count = 0
        plugin = self._make_plugin(
            context_filters=[],
            internal_context_filters=[],
            include_invalid_parents=True,
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
            nonlocal frame_count
            frame_count += 1
            if frame_count == 1:
                frame_started.set()
                await release_frame.wait()

        kit_app.next_update_async = AsyncMock(side_effect=_next_update)
        prepare_context_items = AsyncMock(return_value=["latest"])

        # Act
        with (
            patch(
                "omni.flux.stage_manager.factory.plugins.interaction_plugin.omni.kit.app.get_app",
                return_value=kit_app,
            ),
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
        # Arrange
        main_thread_id = threading.get_ident()
        worker_thread_ids = []
        source_item = StageManagerItem("source", data=object())
        context_filter = Mock(enabled=True)

        def _get_items(*_args):
            worker_thread_ids.append(threading.get_ident())
            return [source_item]

        def _build_filter_predicate():
            worker_thread_ids.append(threading.get_ident())

            def _predicate(_item):
                worker_thread_ids.append(threading.get_ident())
                return True

            return _predicate

        context_filter.build_filter_predicate.side_effect = _build_filter_predicate
        plugin = self._make_plugin(
            context_filters=[context_filter],
            internal_context_filters=[],
            include_invalid_parents=True,
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
        with patch(
            "omni.flux.stage_manager.factory.plugins.interaction_plugin.omni.kit.app.get_app",
            return_value=kit_app,
        ):
            await plugin._update_context_items()

        # Assert
        self.assertEqual(3, len(worker_thread_ids))
        self.assertTrue(all(thread_id != main_thread_id for thread_id in worker_thread_ids))
        plugin.tree.model.set_context_items.assert_called_once()

    async def test_update_queue_worker_when_lightweight_update_arrives_during_context_refresh_publishes_then_dirties(
        self,
    ):
        # Arrange
        plugin = self._make_plugin(
            context_filters=[],
            internal_context_filters=[],
            include_invalid_parents=True,
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
            nonlocal filter_call_count
            filter_call_count += 1
            if filter_call_count == 1:
                plugin._update_queue.put_nowait(False)
            return ["completed"]

        # Act
        with (
            patch(
                "omni.flux.stage_manager.factory.plugins.interaction_plugin.omni.kit.app.get_app",
                return_value=kit_app,
            ),
            patch.object(StageManagerUtils, "filter_items", new=AsyncMock(side_effect=_filter_items)) as filter_items,
        ):
            await plugin._update_queue_worker()

        # Assert
        self.assertEqual(1, filter_items.call_count)
        plugin.tree.model.set_context_items.assert_called_once_with(["completed"])
        plugin._context_items_changed.assert_called_once_with()
        plugin._tree_widget.dirty_widgets.assert_called_once_with()

    async def test_set_active_false_cancels_pending_update_and_model_refresh_tasks(self):
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
        # Arrange
        plugin = self._make_plugin(filters=[], additional_filters=[])
        plugin._update_queue = asyncio.Queue()
        update_started = asyncio.Event()

        async def _update_context_items():
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
        # Arrange
        plugin = self._make_plugin(
            context_filters=[],
            internal_context_filters=[],
            include_invalid_parents=True,
            tree=Mock(),
        )
        plugin._is_active = True
        plugin._update_queue = asyncio.Queue()
        plugin._context = Mock()
        plugin._context.get_items.return_value = ["source"]
        plugin._context_items_changed = Mock()
        plugin.tree.model.set_context_items = Mock()

        async def _filter_items(*_args, **kwargs):
            kwargs["cancel_event"].set()
            plugin._update_queue.put_nowait(True)
            return ["stale"]

        # Act
        with patch.object(StageManagerUtils, "filter_items", new=AsyncMock(side_effect=_filter_items)):
            await plugin._update_context_items()

        # Assert
        plugin.tree.model.set_context_items.assert_not_called()
        plugin._context_items_changed.assert_not_called()

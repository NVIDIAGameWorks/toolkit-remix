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
    async def test_on_hidden_clears_stale_ui_refresh_targets(self):
        # Arrange
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
            filters=[],
            additional_filters=[],
        )
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
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
            tree=Mock(),
        )
        plugin._tree_widget = Mock()
        plugin._tree_widget.refresh_model = AsyncMock()
        plugin.tree.model.refresh = AsyncMock()

        # Act
        plugin._refresh_tree_model()
        await plugin._model_refresh_task

        # Assert
        plugin._tree_widget.refresh_model.assert_awaited_once_with(expand_filtered_roots=False)
        plugin.tree.model.refresh.assert_not_called()
        self.assertNotIn("experimental" + "_threaded_refresh", type(plugin).model_fields)

    async def test_filter_update_is_absorbed_only_during_context_refresh(self):
        # Arrange
        context_plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
        )
        context_plugin._context_refresh_cancel_event = threading.Event()
        delegate_plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
        )
        delegate_plugin._update_items_task = Mock(done=Mock(return_value=False))

        # Act
        with (
            patch.object(context_plugin, "_refresh_tree_model") as context_refresh_tree_model,
            patch.object(delegate_plugin, "_refresh_tree_model") as delegate_refresh_tree_model,
        ):
            context_plugin._on_filter_items_changed()
            delegate_plugin._on_filter_items_changed()

        # Assert
        context_refresh_tree_model.assert_not_called()
        delegate_refresh_tree_model.assert_called_once_with()

    async def test_refresh_tree_model_without_widget_uses_model_refresh_pipeline(self):
        # Arrange
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
            tree=Mock(),
        )
        plugin._tree_widget = None
        plugin.tree.model.refresh = AsyncMock()

        # Act
        plugin._refresh_tree_model()
        await plugin._model_refresh_task

        # Assert
        plugin.tree.model.refresh.assert_awaited_once_with()

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
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
        )
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
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
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
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
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
            plugin._update_items_task = asyncio.ensure_future(plugin._update_queue_worker())
            await frame_started.wait()
            plugin._queue_update(True)
            release_frame.set()
            await plugin._update_items_task

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

        def _prepare_filter_predicate():
            worker_thread_ids.append(threading.get_ident())

            def _predicate(_item):
                worker_thread_ids.append(threading.get_ident())
                return True

            return _predicate

        context_filter.prepare_filter_predicate.side_effect = _prepare_filter_predicate
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
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
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
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
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
        )
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
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
            filters=[],
            additional_filters=[],
        )
        plugin._update_queue = asyncio.Queue()
        plugin._update_context_items = AsyncMock()

        # Act
        plugin.set_active(True)
        plugin.set_active(False)
        plugin.set_active(True)
        await asyncio.sleep(0)
        await plugin._update_items_task

        # Assert
        plugin._update_context_items.assert_awaited_once_with()
        self.assertTrue(plugin._update_queue.empty())

    async def test_update_context_items_discards_result_when_new_context_update_is_queued(self):
        # Arrange
        plugin = _TestInteractionPlugin.model_construct(
            display_name="TestInteraction",
            tooltip="For tests",
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

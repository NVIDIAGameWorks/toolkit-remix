"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from unittest.mock import patch

from lightspeed.trex.capture_tree.model import CaptureTreeModel
from lightspeed.trex.capture_tree.model import model
from omni.kit.test import AsyncTestCase
from omni.usd import StageEventType


class TestCaptureTreeModelEnableListeners(AsyncTestCase):
    """Test that CaptureTreeModel.enable_listeners() properly creates/destroys subscriptions."""

    async def test_subscriptions_none_by_default(self):
        """Test that subscriptions are None when model is created."""
        model = CaptureTreeModel("")

        self.assertIsNone(model._stage_event_sub)
        self.assertIsNone(model._layer_event_sub)

        model.destroy()

    async def test_subscriptions_created_when_enabled(self):
        """Test that subscriptions are created when enable_listeners(True) is called."""
        model = CaptureTreeModel("")

        model.enable_listeners(True)

        self.assertIsNotNone(model._stage_event_sub)
        self.assertIsNotNone(model._layer_event_sub)

        model.enable_listeners(False)
        model.destroy()

    async def test_subscriptions_destroyed_when_disabled(self):
        """Test that subscriptions are destroyed when enable_listeners(False) is called."""
        model = CaptureTreeModel("")

        # First enable
        model.enable_listeners(True)
        self.assertIsNotNone(model._stage_event_sub)
        self.assertIsNotNone(model._layer_event_sub)

        # Then disable
        model.enable_listeners(False)
        self.assertIsNone(model._stage_event_sub)
        self.assertIsNone(model._layer_event_sub)

        model.destroy()

    async def test_subscriptions_toggle_multiple_times(self):
        """Test that subscriptions can be toggled on/off multiple times."""
        model = CaptureTreeModel("")

        # Toggle on
        model.enable_listeners(True)
        self.assertIsNotNone(model._stage_event_sub)
        self.assertIsNotNone(model._layer_event_sub)

        # Toggle off
        model.enable_listeners(False)
        self.assertIsNone(model._stage_event_sub)
        self.assertIsNone(model._layer_event_sub)

        # Toggle on again
        model.enable_listeners(True)
        self.assertIsNotNone(model._stage_event_sub)
        self.assertIsNotNone(model._layer_event_sub)

        # Toggle off again
        model.enable_listeners(False)
        self.assertIsNone(model._stage_event_sub)
        self.assertIsNone(model._layer_event_sub)

        model.destroy()

    async def test_stage_opened_notifies_without_cancelling_tasks(self):
        """Notify a stage change without cancellation when the stage opens."""
        # Arrange
        capture_model, callbacks = self._create_model_with_stage_callbacks()
        with (
            patch.object(capture_model, "cancel_tasks") as cancel_tasks,
            patch.object(capture_model, "_CaptureTreeModel__on_stage_opened_or_closed") as stage_changed,
        ):
            # Act
            callbacks["opened"](None)

            # Assert
            self.assertEqual(cancel_tasks.call_count, 0)
            self.assertEqual(stage_changed.call_count, 1)

    async def test_stage_closing_cancels_tasks_without_notifying(self):
        """Cancel tasks without a stage notification before the stage closes."""
        # Arrange
        capture_model, callbacks = self._create_model_with_stage_callbacks()
        with (
            patch.object(capture_model, "cancel_tasks") as cancel_tasks,
            patch.object(capture_model, "_CaptureTreeModel__on_stage_opened_or_closed") as stage_changed,
        ):
            # Act
            callbacks["closing"](None)

            # Assert
            self.assertEqual(cancel_tasks.call_count, 1)
            self.assertEqual(stage_changed.call_count, 0)

    async def test_stage_closed_cancels_tasks_and_notifies(self):
        """Cancel tasks and notify a stage change after the stage closes."""
        # Arrange
        capture_model, callbacks = self._create_model_with_stage_callbacks()
        with (
            patch.object(capture_model, "cancel_tasks") as cancel_tasks,
            patch.object(capture_model, "_CaptureTreeModel__on_stage_opened_or_closed") as stage_changed,
        ):
            # Act
            callbacks["closed"](None)

            # Assert
            self.assertEqual(cancel_tasks.call_count, 1)
            self.assertEqual(stage_changed.call_count, 1)

    def _create_model_with_stage_callbacks(self):
        """Create an isolated model and its registered event callbacks.

        Returns:
            tuple: The model and callbacks indexed by event name.
        """
        with (
            patch.object(model, "_CaptureCoreSetup"),
            patch.object(model, "_ReplacementCoreSetup"),
            patch.object(model.usd, "get_context") as get_context,
            patch.object(model._layers, "get_layers"),
            patch.object(model._layers, "layer_event_name", return_value="sublayers_changed"),
            patch.object(model, "get_eventdispatcher") as get_dispatcher,
        ):
            get_context.return_value.stage_event_name.side_effect = {
                StageEventType.OPENED: "opened",
                StageEventType.CLOSING: "closing",
                StageEventType.CLOSED: "closed",
            }.__getitem__
            capture_model = CaptureTreeModel("")
            self.addCleanup(capture_model.destroy)
            capture_model.enable_listeners(True)
            callbacks = {
                call.kwargs["event_name"]: call.kwargs["on_event"]
                for call in get_dispatcher.return_value.observe_event.call_args_list
            }
        return capture_model, callbacks

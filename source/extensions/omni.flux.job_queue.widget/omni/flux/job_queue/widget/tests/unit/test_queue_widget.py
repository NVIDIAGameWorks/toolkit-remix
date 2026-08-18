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

from unittest.mock import MagicMock

from omni.flux.job_queue.widget.widget import QueueWidget
from omni.kit.test import AsyncTestCase


class TestQueueWidgetSubscriptions(AsyncTestCase):
    """Test product action subscription ownership without constructing native UI."""

    async def test_widget_owns_one_direct_action_event_subscription_per_adapter(self):
        """Duplicate rows share one widget-owned adapter event subscription."""
        # Arrange
        widget = object.__new__(QueueWidget)
        widget.model = MagicMock(context_name="stagecraft")
        widget._adapter_action_subscriptions = {}
        adapter = MagicMock()
        adapter.job_type = MagicMock()
        subscription = MagicMock()
        adapter.subscribe_action_events.return_value = subscription
        widget.model.all_items = [
            MagicMock(row=MagicMock(adapter=adapter)),
            MagicMock(row=MagicMock(adapter=adapter)),
        ]

        # Act
        widget._sync_adapter_action_subscriptions()

        # Assert
        adapter.subscribe_action_events.assert_called_once_with(widget.model)
        self.assertEqual(widget._adapter_action_subscriptions, {adapter.job_type: subscription})

    async def test_failing_adapter_action_subscription_does_not_block_other_adapters(self):
        """An unavailable product subscription must not prevent other adapters from subscribing."""
        # Arrange
        widget = object.__new__(QueueWidget)
        widget.model = MagicMock(context_name="stagecraft")
        widget._adapter_action_subscriptions = {}
        failing_job_type = type("FailingJob", (), {})
        healthy_job_type = type("HealthyJob", (), {})
        failing_adapter = MagicMock(job_type=failing_job_type)
        failing_adapter.name = "Failing"
        failing_adapter.subscribe_action_events.side_effect = RuntimeError("unavailable")
        healthy_adapter = MagicMock(job_type=healthy_job_type)
        healthy_adapter.name = "Healthy"
        healthy_subscription = MagicMock()
        healthy_adapter.subscribe_action_events.return_value = healthy_subscription
        widget.model.all_items = [
            MagicMock(row=MagicMock(adapter=failing_adapter)),
            MagicMock(row=MagicMock(adapter=healthy_adapter)),
        ]

        # Act
        widget._sync_adapter_action_subscriptions()

        # Assert
        healthy_adapter.subscribe_action_events.assert_called_once_with(widget.model)
        self.assertEqual(widget._adapter_action_subscriptions, {healthy_job_type: healthy_subscription})

    async def test_widget_releases_action_subscription_when_adapter_rows_disappear(self):
        """Removing an adapter's last row releases its widget-owned subscription."""
        # Arrange
        widget = object.__new__(QueueWidget)
        widget.model = MagicMock(context_name="stagecraft", all_items=[])
        job_type = type("RemovedJob", (), {})
        widget._adapter_action_subscriptions = {job_type: MagicMock()}

        # Act
        widget._sync_adapter_action_subscriptions()

        # Assert
        self.assertEqual(widget._adapter_action_subscriptions, {})

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
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from omni.kit.test import AsyncTestCase

from lightspeed.event.app_start.core import EventAppStartCore


class TestEventAppStartCore(AsyncTestCase):
    """Test application startup telemetry lifecycle behavior."""

    @staticmethod
    def _make_core():
        """Create an app-start core with a ready mocked application."""
        core = EventAppStartCore()
        core._app = MagicMock()
        core._app.is_app_ready.return_value = True
        core._app.get_time_since_start_s.return_value = 10.0
        core._app.next_update_async = AsyncMock()
        return core

    @staticmethod
    def _make_telemetry():
        """Create mocked telemetry and its startup transaction."""
        transaction = MagicMock()
        transaction_context = MagicMock()
        transaction_context.__enter__.return_value = transaction
        telemetry = MagicMock()
        telemetry.sentry_sdk.start_transaction.return_value = transaction_context
        return telemetry, transaction

    async def test_install_subscribes_to_user_ready_without_collecting_telemetry(self):
        """Wait for user readiness before collecting startup telemetry."""
        # Arrange
        core = self._make_core()
        subscription = MagicMock()

        with (
            patch("lightspeed.event.app_start.core.subscribe_user_ready", return_value=subscription) as subscribe_mock,
            patch("lightspeed.event.app_start.core.get_telemetry_instance") as telemetry_mock,
            patch("lightspeed.event.app_start.core.time.time", return_value=100.0),
        ):
            # Act
            core._install()

        # Assert
        subscribe_mock.assert_called_once()
        telemetry_mock.assert_not_called()
        self.assertIs(subscription, core._user_ready_subscription)

    async def test_user_ready_owns_telemetry_task(self):
        """Retain the telemetry task and register its completion handler."""
        # Arrange
        core = self._make_core()
        core._EventAppStartCore__record_startup_telemetry = MagicMock(return_value="telemetry-work")
        telemetry_task = MagicMock()

        with (
            patch("lightspeed.event.app_start.core.asyncio.ensure_future", return_value=telemetry_task),
            patch("lightspeed.event.app_start.core.time.time", return_value=106.0),
        ):
            # Act
            core._EventAppStartCore__on_user_ready()

        # Assert
        self.assertIs(telemetry_task, core._telemetry_task)
        telemetry_task.add_done_callback.assert_called_once()

    async def test_telemetry_preserves_kit_ready_end_and_adds_user_ready_duration(self):
        """Keep Kit-ready timing while recording the user-ready duration separately."""
        # Arrange
        core = self._make_core()
        core._app_start_time = 90.0
        core._kit_ready_time = 105.0
        core._telemetry_task = asyncio.current_task()
        telemetry, transaction = self._make_telemetry()

        with (
            patch("lightspeed.event.app_start.core.get_telemetry_instance", return_value=telemetry),
            patch("lightspeed.event.app_start.core.get_device_info", return_value=[]),
            patch("lightspeed.event.app_start.core.get_memory_info", return_value={}),
        ):
            # Act
            await core._EventAppStartCore__record_startup_telemetry(106.0)

        # Assert
        self.assertEqual(datetime.fromtimestamp(90.0, tz=UTC), transaction.start_timestamp)
        transaction.finish.assert_called_once_with(end_timestamp=datetime.fromtimestamp(105.0, tz=UTC))
        transaction.set_data.assert_any_call("user_ready_duration", 16.0)
        self.assertIsNone(core._telemetry_task)

    async def test_uninstall_cancels_pending_telemetry_task(self):
        """Cancel post-ready telemetry work when the event owner uninstalls."""
        # Arrange
        core = self._make_core()
        telemetry_task = MagicMock()
        core._telemetry_task = telemetry_task
        core._user_ready_subscription = MagicMock()

        # Act
        core._uninstall()

        # Assert
        telemetry_task.cancel.assert_called_once_with()
        self.assertIsNone(core._telemetry_task)
        self.assertIsNone(core._user_ready_subscription)

    async def test_telemetry_task_failure_is_logged(self):
        """Log an owned telemetry task failure without leaving it unobserved."""
        # Arrange
        core = self._make_core()
        telemetry_task = MagicMock()
        telemetry_task.cancelled.return_value = False
        telemetry_task.exception.return_value = RuntimeError("telemetry failed")

        with patch("lightspeed.event.app_start.core.carb.log_error") as log_error_mock:
            # Act
            core._EventAppStartCore__on_telemetry_task_done(telemetry_task)

        # Assert
        log_error_mock.assert_called_once_with(
            "[lightspeed.event.app_start] Could not record startup telemetry: telemetry failed"
        )

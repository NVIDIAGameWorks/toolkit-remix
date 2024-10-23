"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from unittest.mock import MagicMock, patch

import omni.kit.test
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.sentry_manager.core import get_instance
from lightspeed.sentry_manager.event import EventSentryManagerOnShutdown, SentryShutdownInterrupter


def sample_callback():
    pass


class TestSentryShutdownInterrupter(omni.kit.test.AsyncTestCase):
    def setUp(self):
        self.interrupter = SentryShutdownInterrupter()

    def test_should_interrupt_shutdown_no_callback(self):
        # Arrange
        mock_callback = MagicMock()

        # Act
        result = self.interrupter.should_interrupt_shutdown()

        # Assert
        self.assertFalse(result)
        mock_callback.assert_not_called()

    def test_should_interrupt_shutdown_with_callback(self):
        # Arrange
        mock_callback = MagicMock()

        # Act
        self.interrupter.set_callback(mock_callback)
        result = self.interrupter.should_interrupt_shutdown()

        # Assert
        self.assertFalse(result)
        mock_callback.assert_called_once()

    def test_set_callback(self):
        # Arrange
        orig_callback = self.interrupter._callback  # noqa PLW0212 protected-access

        # Act
        self.interrupter.set_callback(sample_callback)

        # Assert
        self.assertIsNone(orig_callback)
        self.assertIsNotNone(self.interrupter._callback)  # noqa PLW0212 protected-access
        self.assertIs(self.interrupter._callback, sample_callback)  # noqa PLW0212 protected-access


class TestEventSentryManagerOnShutdown(omni.kit.test.AsyncTestCase):
    def test_initialize(self):
        # Arrange
        evt_mgr = _get_event_manager_instance()
        with patch("lightspeed.event.shutdown_base.base.EventOnShutdownBase.register_interrupter") as mock_reg:
            with patch.object(evt_mgr, "register_event") as mock_register_event:

                # Act
                evt = EventSentryManagerOnShutdown()

        # Assert
        self.assertIsInstance(evt.interrupter, SentryShutdownInterrupter)
        mock_reg.assert_called_once_with(evt.interrupter)
        mock_register_event.assert_called_once_with(evt)

    def test_shutdown_callback(self):
        # Arrange
        evt_mgr = _get_event_manager_instance()
        with patch("lightspeed.event.shutdown_base.base.EventOnShutdownBase.register_interrupter") as mock_reg:
            with patch.object(evt_mgr, "unregister_event") as mock_unregister_event:
                evt = EventSentryManagerOnShutdown()
                manager = get_instance()
                with patch.object(manager, "app_closing") as mock_shutdown:

                    # Act
                    evt.shutdown_callback()

        # Assert
        mock_unregister_event.assert_called_once_with(evt)
        mock_reg.assert_called_once_with(evt.interrupter)
        mock_shutdown.assert_called_once_with()

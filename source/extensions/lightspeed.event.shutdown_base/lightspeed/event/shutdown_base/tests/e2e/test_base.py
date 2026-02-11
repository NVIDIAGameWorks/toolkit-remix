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

from unittest.mock import Mock, patch

import omni.kit.app
from lightspeed.event.shutdown_base import EventOnShutdownBase as _EventOnShutdownBase
from lightspeed.event.shutdown_base import InterrupterBase as _InterrupterBase
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from omni.kit.test import AsyncTestCase

EVENT_NAME = "Shutdown Test"


class MockEvent:
    type = omni.kit.app.POST_QUIT_EVENT_TYPE


class MockInterrupter(_InterrupterBase):
    def __init__(self):
        self.interruptable = True

    def should_interrupt_shutdown(self):
        return self.interruptable

    def interrupt_shutdown(self, shutdown_callback):
        if shutdown_callback:
            shutdown_callback(self)
        self.interruptable = False


class MockOnShutdown(_EventOnShutdownBase):
    def __init__(self):
        super().__init__()
        self.interrupter = MockInterrupter()
        self.register_interrupter(self.interrupter)

    @property
    def name(self):
        return EVENT_NAME


class TestEventOnShutdownBase(AsyncTestCase):
    async def setUp(self):
        self.shutdown_event = MockOnShutdown()
        # Register the event
        _get_event_manager_instance().register_event(self.shutdown_event)

    # After running each test
    async def tearDown(self):
        # Unregister the event
        _get_event_manager_instance().unregister_event(self.shutdown_event)
        self.shutdown_event = None

    async def test_has_interrupters(self):
        self.assertTrue(len(self.shutdown_event._interrupters) > 0)
        self.assertIsInstance(self.shutdown_event._interrupters[0], MockInterrupter)

    async def test_event_registered(self):
        # Ensure it is registered
        event = _get_event_manager_instance().get_registered_event(EVENT_NAME)
        self.assertEqual(event, self.shutdown_event)

    async def test_interrupter_off(self):
        # Verify that returning False for `should_interrupt_shutdown` prevents the `interrupt_shutdown` from being
        # called.
        event = self.shutdown_event
        interrupter = event.interrupter
        interrupter.interruptable = False
        with patch.object(interrupter, "interrupt_shutdown") as mock_interrupt_shutdown:
            event._EventOnShutdownBase__on_shutdown_event(MockEvent)
            mock_interrupt_shutdown.assert_not_called()

    async def test_interrupter_on(self):
        # Verify that returning True for `should_interrupt_shutdown` causes the `interrupt_shutdown` to be called.
        event = self.shutdown_event
        interrupter = event.interrupter
        interrupter.interruptable = True
        mock_shutdown_callback = Mock()
        # Since we can't actually issue a shutdown event, do the next best thing: call the interrupter
        interrupter.interrupt_shutdown(mock_shutdown_callback)
        mock_shutdown_callback.assert_called_once_with(interrupter)

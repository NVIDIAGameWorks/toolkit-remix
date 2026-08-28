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
from unittest.mock import MagicMock

import omni.kit.app
import omni.kit.test

from lightspeed.trex.app.setup import lifecycle as _lifecycle


class TestUserReadyLifecycle(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        _lifecycle._USER_READY = False
        _lifecycle._USER_READY_EVENT.clear()
        _lifecycle._HOME_INTERACTIVE.clear()
        self._subscriptions = []

    async def tearDown(self):
        self._subscriptions.clear()
        _lifecycle._USER_READY = False
        _lifecycle._USER_READY_EVENT.clear()
        _lifecycle._HOME_INTERACTIVE.clear()

    async def test_early_subscriber_is_called_once_when_published(self):
        # Arrange
        callback = MagicMock()
        self._subscriptions.append(_lifecycle.subscribe_user_ready(callback))

        # Act
        _lifecycle._publish_user_ready()
        _lifecycle._publish_user_ready()

        # Assert
        callback.assert_called_once_with()
        self.assertTrue(_lifecycle.is_user_ready())

    async def test_late_subscriber_is_called_immediately(self):
        # Arrange
        _lifecycle._publish_user_ready()
        callback = MagicMock()

        # Act
        self._subscriptions.append(_lifecycle.subscribe_user_ready(callback))

        # Assert
        callback.assert_called_once_with()

    async def test_home_interactive_wait_completes_after_mark(self):
        """Complete the Home readiness waiter after the public milestone is marked."""
        # Arrange
        wait_task = asyncio.ensure_future(_lifecycle._wait_for_home_interactive())
        await omni.kit.app.get_app().next_update_async()

        # Act
        _lifecycle.mark_home_interactive()

        # Assert
        await wait_task
        self.assertTrue(wait_task.done())

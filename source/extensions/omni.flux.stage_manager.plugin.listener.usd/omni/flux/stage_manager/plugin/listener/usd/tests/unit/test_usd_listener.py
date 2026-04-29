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

from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.stage_manager.plugin.listener.usd import usd_listener as _usd_listener_module
from omni.flux.stage_manager.plugin.listener.usd.usd_listener import StageManagerUSDNoticeListenerPlugin


class TestStageManagerUSDNoticeListenerPlugin(omni.kit.test.AsyncTestCase):
    async def test_setup_registers_deferred_listener_for_current_stage(self):
        # Arrange
        plugin = StageManagerUSDNoticeListenerPlugin()
        plugin.set_context_name("stage")
        stage = Mock()
        context = Mock()
        context.get_stage.return_value = stage
        subscription = Mock()

        with (
            patch.object(_usd_listener_module.omni.usd, "get_context", return_value=context),
            patch.object(
                _usd_listener_module,
                "_register_listener",
                return_value=subscription,
            ) as register_mock,
        ):
            # Act
            plugin.setup()

        # Assert
        self.assertIs(plugin._usd_listener, subscription)
        register_mock.assert_called_once_with(stage, plugin._on_usd_event)

    async def test_cleanup_with_registered_subscription_revokes_listener(self):
        # Arrange
        plugin = StageManagerUSDNoticeListenerPlugin()
        subscription = Mock()
        plugin._usd_listener = subscription

        # Act
        plugin.cleanup()

        # Assert
        subscription.Revoke.assert_called_once_with()
        self.assertIsNone(plugin._usd_listener)

    async def test_on_usd_event_notifies_stage_manager_subscribers(self):
        # Arrange
        plugin = StageManagerUSDNoticeListenerPlugin()
        callback = Mock()
        notice = Mock()
        subscription = plugin.subscribe_event_occurred(callback)

        # Act
        plugin._on_usd_event(notice, Mock())

        # Assert
        callback.assert_called_once_with(notice)
        self.assertIsNotNone(subscription)

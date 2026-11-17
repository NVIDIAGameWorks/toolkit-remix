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
import omni.usd
from omni.flux.stage_manager.plugin.listener.usd import layers_listener, stage_listener
from omni.flux.stage_manager.plugin.listener.usd import usd_listener as _usd_listener_module
from omni.flux.stage_manager.plugin.listener.usd.layers_listener import StageManagerUSDLayersListenerPlugin
from omni.flux.stage_manager.plugin.listener.usd.stage_listener import StageManagerUSDStageListenerPlugin
from omni.flux.stage_manager.plugin.listener.usd.usd_listener import StageManagerUSDNoticeListenerPlugin
from omni.kit.usd import layers


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


class TestStageManagerUSDStageListenerPlugin(omni.kit.test.AsyncTestCase):
    """Check stage event registration, notification, and cleanup."""

    async def test_stage_events_for_configured_context_register_and_notify_with_enums(self):
        """Register context event names and forward each stage enum."""
        for value in range(int(omni.usd.StageEventType.COUNT)):
            with self.subTest(title=omni.usd.StageEventType(value).name):
                # Arrange
                event_type = omni.usd.StageEventType(value)
                event_types = [omni.usd.StageEventType(index) for index in range(int(omni.usd.StageEventType.COUNT))]
                event_names = {item: f"test.stage_manager_listener:stage:{item.name}" for item in event_types}
                context = Mock()
                context.stage_event_name.side_effect = event_names.__getitem__
                dispatcher = Mock()
                plugin = StageManagerUSDStageListenerPlugin()
                plugin.set_context_name("stage_manager_listener")
                callback = Mock()
                subscription = plugin.subscribe_event_occurred(callback)

                with (
                    patch.object(stage_listener, "get_eventdispatcher", return_value=dispatcher),
                    patch.object(omni.usd, "get_context", return_value=context) as get_context_mock,
                    patch.object(omni.usd, "stage_event_type", return_value=event_type),
                ):
                    try:
                        plugin.setup()
                        registrations = dispatcher.observe_event.call_args_list
                        registration = registrations[value].kwargs

                        # Act
                        registration["on_event"](Mock(event_name=event_names[event_type]))

                        # Assert
                        get_context_mock.assert_called_once_with("stage_manager_listener")
                        self.assertEqual(
                            [item.kwargs["event_name"] for item in registrations],
                            [event_names[item] for item in event_types],
                        )
                        callback.assert_called_once_with(event_type)
                        self.assertIsInstance(callback.call_args.args[0], omni.usd.StageEventType)
                        omni.usd.stage_event_type.assert_called_once_with(event_names[event_type])
                    finally:
                        plugin.cleanup()
                        del subscription

    async def test_cleanup_with_stage_observers_releases_subscriptions(self):
        """Release stored stage observers during cleanup."""
        # Arrange
        plugin = StageManagerUSDStageListenerPlugin()
        plugin._stage_event_sub = [Mock()]

        # Act
        plugin.cleanup()

        # Assert
        self.assertIsNone(plugin._stage_event_sub)


class TestStageManagerUSDLayersListenerPlugin(omni.kit.test.AsyncTestCase):
    """Check layer event registration, notification, and cleanup."""

    async def test_layer_events_for_default_layer_key_register_and_notify_with_enums(self):
        """Register the default layer filter and forward each layer enum."""
        for event_type in layers.LayerEventType:
            with self.subTest(title=event_type.name):
                # Arrange
                event_names = {item: f"test.stage_manager_listener:layer:{item.name}" for item in layers.LayerEventType}
                event_key = {"context": "default"}
                default_layers = Mock()
                default_layers.get_event_key.return_value = event_key
                dispatcher = Mock()
                plugin = StageManagerUSDLayersListenerPlugin()
                plugin.set_context_name("stage_manager_listener")
                callback = Mock()
                subscription = plugin.subscribe_event_occurred(callback)

                with (
                    patch.object(layers_listener, "get_eventdispatcher", return_value=dispatcher),
                    patch.object(layers, "get_layers", return_value=default_layers) as get_layers_mock,
                    patch.object(layers, "layer_event_name", side_effect=event_names.__getitem__),
                    patch.object(layers, "layer_event_type", return_value=event_type),
                ):
                    try:
                        plugin.setup()
                        registrations = dispatcher.observe_event.call_args_list
                        registration = next(
                            item.kwargs
                            for item in registrations
                            if item.kwargs["event_name"] == event_names[event_type]
                        )

                        # Act
                        registration["on_event"](Mock(event_name=event_names[event_type]))

                        # Assert
                        get_layers_mock.assert_called_once_with()
                        self.assertEqual(
                            [item.kwargs["event_name"] for item in registrations],
                            [event_names[item] for item in layers.LayerEventType],
                        )
                        for item in registrations:
                            self.assertEqual(item.kwargs["filter"], event_key)
                        callback.assert_called_once_with(event_type)
                        self.assertIsInstance(callback.call_args.args[0], layers.LayerEventType)
                        layers.layer_event_type.assert_called_once_with(event_names[event_type])
                    finally:
                        plugin.cleanup()
                        del subscription

    async def test_cleanup_with_layer_observers_releases_subscriptions(self):
        """Release stored layer observers during cleanup."""
        # Arrange
        plugin = StageManagerUSDLayersListenerPlugin()
        plugin._layer_event_sub = [Mock()]

        # Act
        plugin.cleanup()

        # Assert
        self.assertIsNone(plugin._layer_event_sub)

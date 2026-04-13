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

from unittest.mock import Mock, call, patch

import omni.kit.test
from omni.flux.property_widget_builder.model.usd.listener import USDListener


class TestUSDListener(omni.kit.test.AsyncTestCase):
    async def test_enable_listener_existing_stage_is_noop(self):
        # Arrange
        stage = Mock()
        existing_listener = Mock()
        listener = USDListener()
        listener._listeners = {stage: existing_listener}

        # Act
        with patch("omni.flux.property_widget_builder.model.usd.listener.Tf.Notice.Register") as register_mock:
            listener._enable_listener(stage)

        # Assert
        register_mock.assert_not_called()
        self.assertIs(listener._listeners[stage], existing_listener)

    async def test_add_model_purges_stale_listener_before_registering_current_stage(self):
        # Arrange
        stale_stage = Mock()
        stale_stage.GetRootLayer.return_value = None
        stale_listener = Mock()

        current_stage = Mock()
        current_stage.GetRootLayer.return_value = Mock()
        model = Mock()
        model.stage = current_stage

        listener = USDListener()
        listener._listeners = {stale_stage: stale_listener}
        listener._models = []

        # Act
        with patch.object(USDListener, "_enable_listener") as enable_listener_mock:
            listener.add_model(model)

        # Assert
        stale_listener.Revoke.assert_called_once_with()
        self.assertNotIn(stale_stage, listener._listeners)
        enable_listener_mock.assert_called_once_with(current_stage)
        self.assertEqual([model], listener._models)

    async def test_remove_model_purges_stale_listeners_after_model_is_removed(self):
        # Arrange
        current_stage = Mock()
        current_stage.GetRootLayer.return_value = Mock()
        stale_stage = Mock()
        stale_stage.GetRootLayer.return_value = None
        stale_listener = Mock()

        model = Mock()
        model.stage = current_stage

        listener = USDListener()
        listener._listeners = {current_stage: Mock(), stale_stage: stale_listener}
        listener._models = [model]

        # Act
        with patch.object(listener, "_disable_listener", wraps=listener._disable_listener) as disable_listener_mock:
            listener.remove_model(model)

        # Assert
        disable_listener_mock.assert_has_calls([call(current_stage), call(stale_stage)], any_order=True)
        self.assertEqual(disable_listener_mock.call_count, 2)
        stale_listener.Revoke.assert_called_once_with()
        self.assertNotIn(current_stage, listener._listeners)
        self.assertNotIn(stale_stage, listener._listeners)
        self.assertEqual([], listener._models)

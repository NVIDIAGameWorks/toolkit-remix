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

from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd import listener as _listener_module
from omni.flux.property_widget_builder.model.usd.listener import DisableAllListenersBlock
from omni.flux.property_widget_builder.model.usd.listener import USDListener
from pxr import Sdf


class TestUSDListener(omni.kit.test.AsyncTestCase):
    async def test_enable_listener_existing_stage_is_noop(self):
        # Arrange
        stage = Mock()
        existing_listener = Mock()
        listener = USDListener()
        listener._listeners = {stage: existing_listener}

        # Act
        with patch.object(_listener_module, "_register_listener") as register_mock:
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

        subscription = Mock()
        listener = USDListener()
        listener._listeners = {stale_stage: stale_listener}
        listener._models = []

        # Act
        with patch.object(_listener_module, "_register_listener", return_value=subscription) as register_mock:
            listener.add_model(model)

        # Assert
        stale_listener.Revoke.assert_called_once_with()
        self.assertNotIn(stale_stage, listener._listeners)
        register_mock.assert_called_once_with(
            current_stage,
            listener._on_usd_changed,
        )
        self.assertIs(listener._listeners[current_stage], subscription)
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

    async def test_disable_all_listeners_block_disables_and_enables_listeners_for_scope(self):
        # Arrange
        listener = Mock()
        DisableAllListenersBlock.LIST_SELF.clear()

        # Act
        with DisableAllListenersBlock(listener):
            pass

        # Assert
        listener.tmp_disable_all_listeners.assert_called_once_with()
        listener.tmp_enable_all_listeners.assert_called_once_with()
        self.assertEqual([], DisableAllListenersBlock.LIST_SELF)

    async def test_tmp_disable_and_enable_all_listeners_moves_models_through_tmp_list(self):
        # Arrange
        model_1 = Mock()
        model_2 = Mock()
        listener = USDListener()
        listener._models = [model_1, model_2]

        # Act
        with (
            patch.object(listener, "remove_model") as remove_model_mock,
            patch.object(listener, "add_model") as add_model_mock,
        ):
            listener.tmp_disable_all_listeners()
            tmp_models_after_disable = list(listener._tmp_models)
            listener.tmp_enable_all_listeners()

        # Assert
        self.assertEqual([model_1, model_2], tmp_models_after_disable)
        remove_model_mock.assert_has_calls([call(model_1), call(model_2)])
        add_model_mock.assert_has_calls([call(model_1), call(model_2)])
        self.assertEqual([], listener._tmp_models)

    async def test_purge_stale_listeners_removes_stage_when_root_layer_lookup_raises(self):
        # Arrange
        stale_stage = Mock()
        stale_stage.GetRootLayer.side_effect = RuntimeError("stage is closed")
        stale_listener = Mock()
        listener = USDListener()
        listener._listeners = {stale_stage: stale_listener}

        # Act
        listener._purge_stale_listeners()

        # Assert
        stale_listener.Revoke.assert_called_once_with()
        self.assertEqual({}, listener._listeners)

    async def test_add_model_without_stage_does_not_register_listener(self):
        # Arrange
        listener = USDListener()
        model = SimpleNamespace(stage=None)

        # Act
        with patch.object(listener, "_enable_listener") as enable_listener_mock:
            listener.add_model(model)

        # Assert
        enable_listener_mock.assert_not_called()
        self.assertEqual([model], listener._models)

    async def test_remove_model_noops_when_model_is_missing_or_listener_has_no_models(self):
        # Arrange
        listener = USDListener()

        # Act
        with patch.object(listener, "_disable_listener") as disable_listener_mock:
            listener.remove_model(None)
            listener.remove_model(Mock())

        # Assert
        disable_listener_mock.assert_not_called()

    async def test_destroy_revokes_all_registered_stage_listeners(self):
        # Arrange
        listener = USDListener()
        subscriptions = [Mock(), Mock()]
        listener._listeners = {Mock(): subscriptions[0], Mock(): subscriptions[1]}

        # Act
        listener.destroy()

        # Assert
        for subscription in subscriptions:
            subscription.Revoke.assert_called_once_with()
        self.assertIsNone(listener._listeners)

    async def test_on_usd_changed_ignores_suppressed_models(self):
        # Arrange
        listener = USDListener()
        notice = Mock()
        model = SimpleNamespace(supress_usd_events_during_widget_edit=True, refresh=Mock())
        listener._models = [model]

        # Act
        listener._on_usd_changed(notice, Mock())

        # Assert
        notice.GetChangedInfoOnlyPaths.assert_not_called()
        model.refresh.assert_not_called()

    async def test_on_usd_changed_ignores_models_from_other_stages(self):
        # Arrange
        listener = USDListener()
        notice = Mock()
        model = SimpleNamespace(supress_usd_events_during_widget_edit=False, stage=Mock(), refresh=Mock())
        listener._models = [model]

        # Act
        listener._on_usd_changed(notice, Mock())

        # Assert
        notice.GetChangedInfoOnlyPaths.assert_not_called()
        model.refresh.assert_not_called()

    async def test_on_usd_changed_skips_non_attribute_and_missing_attribute_paths(self):
        # Arrange
        context = omni.usd.get_context()
        await context.new_stage_async()
        stage = context.get_stage()
        stage.DefinePrim("/ListenerPrim")
        listener = USDListener()
        model = SimpleNamespace(
            supress_usd_events_during_widget_edit=False,
            stage=stage,
            prim_paths=[Sdf.Path("/ListenerPrim")],
            refresh=Mock(),
        )
        notice = Mock()
        notice.GetChangedInfoOnlyPaths.return_value = [Sdf.Path("/ListenerPrim"), Sdf.Path("/ListenerPrim.missing")]
        notice.GetResyncedPaths.return_value = []
        listener._models = [model]

        try:
            # Act
            listener._on_usd_changed(notice, stage)

            # Assert
            model.refresh.assert_not_called()
        finally:
            await context.close_stage_async()

    async def test_on_usd_changed_refreshes_model_for_changed_attribute_on_matching_prim(self):
        # Arrange
        context = omni.usd.get_context()
        await context.new_stage_async()
        stage = context.get_stage()
        prim = stage.DefinePrim("/ListenerPrim")
        prim.CreateAttribute("testFloat", Sdf.ValueTypeNames.Float).Set(1.0)
        listener = USDListener()
        model = SimpleNamespace(
            supress_usd_events_during_widget_edit=False,
            stage=stage,
            prim_paths=[Sdf.Path("/ListenerPrim")],
            refresh=Mock(),
        )
        notice = Mock()
        notice.GetChangedInfoOnlyPaths.return_value = [Sdf.Path("/ListenerPrim.testFloat")]
        notice.GetResyncedPaths.return_value = []
        listener._models = [model]

        try:
            # Act
            listener._on_usd_changed(notice, stage)

            # Assert
            model.refresh.assert_called_once_with()
        finally:
            await context.close_stage_async()

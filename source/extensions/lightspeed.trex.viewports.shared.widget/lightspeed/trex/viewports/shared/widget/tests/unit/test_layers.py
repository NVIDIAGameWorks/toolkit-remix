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

from unittest.mock import MagicMock, patch

import omni.kit.test
import omni.ui as ui
from lightspeed.trex.viewports.shared.widget import layers as _layers

_REGISTER_ORDERED = "lightspeed.trex.viewports.shared.widget.layers.RegisterViewportLayer.ordered_factories"


class TestViewportLayersFactorySkip(omni.kit.test.AsyncTestCase):
    def _make_layers(self):
        instance = _layers.ViewportLayers.__new__(_layers.ViewportLayers)
        instance._ViewportLayers__ui_frame = MagicMock()
        instance._ViewportLayers__zstack = MagicMock()
        viewport = MagicMock()
        viewport.viewport_api.usd_context_name = ""
        instance._ViewportLayers__viewport = viewport
        instance._ViewportLayers__viewport_layers = {
            _layers._ViewportLayerItem: MagicMock(spec=_layers._ViewportLayerItem),
        }
        instance._ViewportLayers__is_active_fn = None
        instance._ViewportLayers__skipped_factories = set()
        return instance

    async def test_kit_window_layer_ids_are_in_skip_set(self):
        # Arrange / Act / Assert
        self.assertIn(
            "omni.kit.viewport.window.SceneLayer",
            _layers._SKIPPED_VIEWPORT_LAYER_FACTORY_IDS,
        )
        self.assertIn(
            "omni.kit.viewport.window.ViewportStats",
            _layers._SKIPPED_VIEWPORT_LAYER_FACTORY_IDS,
        )

    async def test_skipped_factory_is_not_instantiated(self):
        # Arrange
        lss_scene_factory = MagicMock(name="LssSceneLayerFactory")
        lss_stats_factory = MagicMock(name="LssStatsLayerFactory")
        kit_window_scene_factory = MagicMock(name="KitWindowSceneLayerFactory")
        kit_window_stats_factory = MagicMock(name="KitWindowStatsFactory")
        tools_factory = MagicMock(name="ViewportToolsFactory")

        ordered = [
            ("omni.kit.viewport.SceneLayer", lss_scene_factory),
            ("omni.kit.viewport.ViewportStats", lss_stats_factory),
            ("omni.kit.viewport.window.SceneLayer", kit_window_scene_factory),
            ("omni.kit.viewport.window.ViewportStats", kit_window_stats_factory),
            ("omni.kit.viewport.ViewportTools", tools_factory),
        ]

        instance = self._make_layers()

        with (
            patch(_REGISTER_ORDERED, return_value=ordered),
            patch.object(ui, "ZStack", MagicMock()),
            patch.object(ui, "VStack", MagicMock()),
            patch.object(ui, "HStack", MagicMock()),
            patch.object(ui, "Spacer", MagicMock()),
            patch.object(ui, "Pixel", lambda v: v),
        ):
            # Act
            instance._ViewportLayers__viewport_layer_event(MagicMock(), loading=True)

        # Assert
        instantiated = instance._ViewportLayers__viewport_layers
        skipped = instance._ViewportLayers__skipped_factories
        self.assertIn(lss_scene_factory, instantiated)
        self.assertIn(lss_stats_factory, instantiated)
        self.assertIn(tools_factory, instantiated)
        self.assertNotIn(kit_window_scene_factory, instantiated)
        self.assertNotIn(kit_window_stats_factory, instantiated)
        self.assertIn(kit_window_scene_factory, skipped)
        self.assertIn(kit_window_stats_factory, skipped)
        kit_window_scene_factory.assert_not_called()
        kit_window_stats_factory.assert_not_called()
        lss_scene_factory.assert_called_once()
        lss_stats_factory.assert_called_once()
        tools_factory.assert_called_once()

    async def test_falsy_factory_is_skipped(self):
        # Arrange
        lss_scene_factory = MagicMock(name="LssSceneLayerFactory")
        ordered = [
            ("omni.kit.viewport.SceneLayer", lss_scene_factory),
            ("not.yet.registered.Layer", None),
        ]

        instance = self._make_layers()

        with (
            patch(_REGISTER_ORDERED, return_value=ordered),
            patch.object(ui, "ZStack", MagicMock()),
            patch.object(ui, "VStack", MagicMock()),
            patch.object(ui, "HStack", MagicMock()),
            patch.object(ui, "Spacer", MagicMock()),
            patch.object(ui, "Pixel", lambda v: v),
        ):
            # Act
            instance._ViewportLayers__viewport_layer_event(MagicMock(), loading=True)

        # Assert
        instantiated = instance._ViewportLayers__viewport_layers
        self.assertIn(lss_scene_factory, instantiated)
        self.assertNotIn(None, instantiated)

    async def test_unload_of_skipped_factory_silently_clears_tracking(self):
        # Arrange
        kit_window_scene_factory = MagicMock(name="KitWindowSceneLayerFactory")

        instance = self._make_layers()
        instance._ViewportLayers__skipped_factories.add(kit_window_scene_factory)

        with patch("lightspeed.trex.viewports.shared.widget.layers.carb.log_error") as mock_log_error:
            # Act
            instance._ViewportLayers__viewport_layer_event(kit_window_scene_factory, loading=False)

        # Assert
        mock_log_error.assert_not_called()
        self.assertNotIn(kit_window_scene_factory, instance._ViewportLayers__skipped_factories)

    async def test_unload_of_unknown_factory_still_logs_error(self):
        # Arrange
        unknown_factory = MagicMock(name="UnknownFactory")

        instance = self._make_layers()

        with patch("lightspeed.trex.viewports.shared.widget.layers.carb.log_error") as mock_log_error:
            # Act
            instance._ViewportLayers__viewport_layer_event(unknown_factory, loading=False)

        # Assert
        mock_log_error.assert_called_once()

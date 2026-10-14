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

__all__ = ["TestAlphaCutoutSettings"]

from unittest.mock import MagicMock, patch

import lightspeed.trex.alpha_cutout.widget.settings as settings_module
from lightspeed.trex.alpha_cutout.widget.settings import AlphaCutoutSettings
from omni.kit.test import AsyncTestCase

_ROOT = "/persistent/exts/lightspeed.trex.alpha_cutout.widget"


class TestAlphaCutoutSettings(AsyncTestCase):
    """Test the persisted settings facade."""

    async def test_alpha_threshold_getter_clamps_persisted_value_to_range(self):
        # Arrange
        backend = MagicMock()
        backend.get_as_int.return_value = 999
        subject = AlphaCutoutSettings()

        # Act
        with patch.object(settings_module, "get_settings", return_value=backend):
            result = subject.alpha_threshold

        # Assert
        self.assertEqual(result, 255)

    async def test_set_trace_resolution_clamps_and_writes_persistent_key(self):
        # Arrange
        backend = MagicMock()
        subject = AlphaCutoutSettings()

        # Act
        with patch.object(settings_module, "get_settings", return_value=backend):
            subject.set_trace_resolution(8)

        # Assert
        backend.set.assert_called_once_with(f"{_ROOT}/trace_resolution", 64)

    async def test_set_simplify_tolerance_with_negative_value_writes_zero(self):
        # Arrange
        backend = MagicMock()
        subject = AlphaCutoutSettings()

        # Act
        with patch.object(settings_module, "get_settings", return_value=backend):
            subject.set_simplify_tolerance(-3.0)

        # Assert
        backend.set.assert_called_once_with(f"{_ROOT}/simplify_tolerance", 0.0)

    async def test_set_edge_margin_keeps_negative_values(self):
        # Arrange
        backend = MagicMock()
        subject = AlphaCutoutSettings()

        # Act
        with patch.object(settings_module, "get_settings", return_value=backend):
            subject.set_edge_margin(-0.5)

        # Assert
        backend.set.assert_called_once_with(f"{_ROOT}/edge_margin", -0.5)

    async def test_parameters_combines_persisted_values(self):
        # Arrange
        backend = MagicMock()
        backend.get_as_int.side_effect = lambda key: {
            f"{_ROOT}/alpha_threshold": 100,
            f"{_ROOT}/trace_resolution": 128,
        }[key]
        backend.get_as_float.side_effect = lambda key: {
            f"{_ROOT}/simplify_tolerance": 2.0,
            f"{_ROOT}/edge_margin": -1.0,
            f"{_ROOT}/min_island_area": 8.0,
            f"{_ROOT}/thickness": 0.5,
            f"{_ROOT}/smoothing": 0.25,
            f"{_ROOT}/up_amount": 0.75,
        }[key]
        backend.get_as_bool.side_effect = lambda key: {
            f"{_ROOT}/minimal_outline": True,
            f"{_ROOT}/thicken": True,
            f"{_ROOT}/thicken_back_face": False,
            f"{_ROOT}/thicken_anti_stretch": True,
            f"{_ROOT}/smooth_normals": True,
            f"{_ROOT}/up_normals": False,
        }[key]
        subject = AlphaCutoutSettings()

        # Act
        with patch.object(settings_module, "get_settings", return_value=backend):
            parameters = subject.parameters

        # Assert
        self.assertEqual(parameters.alpha_threshold, 100)
        self.assertEqual(parameters.trace_resolution, 128)
        self.assertEqual(parameters.simplify_tolerance, 2.0)
        self.assertEqual(parameters.edge_margin, -1.0)
        self.assertEqual(parameters.min_island_area, 8.0)
        self.assertTrue(parameters.minimal_outline)
        self.assertTrue(parameters.thicken)
        self.assertEqual(parameters.thickness, 0.5)
        self.assertFalse(parameters.thicken_back_face)
        self.assertTrue(parameters.thicken_anti_stretch)
        self.assertTrue(parameters.smooth_normals)
        self.assertEqual(parameters.smoothing, 0.25)
        self.assertFalse(parameters.up_normals)
        self.assertEqual(parameters.up_amount, 0.75)

    async def test_set_up_amount_above_one_writes_one(self):
        # Arrange
        backend = MagicMock()
        subject = AlphaCutoutSettings()

        # Act
        with patch.object(settings_module, "get_settings", return_value=backend):
            subject.set_up_amount(3.0)

        # Assert
        backend.set.assert_called_once_with(f"{_ROOT}/up_amount", 1.0)

    async def test_set_thickness_with_negative_value_writes_zero(self):
        # Arrange
        backend = MagicMock()
        subject = AlphaCutoutSettings()

        # Act
        with patch.object(settings_module, "get_settings", return_value=backend):
            subject.set_thickness(-2.0)

        # Assert
        backend.set.assert_called_once_with(f"{_ROOT}/thickness", 0.0)

    async def test_default_output_folder_without_project_returns_empty_string(self):
        # Arrange
        context = MagicMock()
        context.get_stage.return_value = None

        # Act
        with patch.object(settings_module.omni.usd, "get_context", return_value=context):
            result = AlphaCutoutSettings.default_output_folder("")

        # Assert
        self.assertEqual(result, "")

    async def test_default_output_folder_with_project_returns_ingested_subfolder(self):
        # Arrange
        root_layer = MagicMock()
        root_layer.anonymous = False
        root_layer.realPath = "C:/projects/demo/project.usda"
        stage = MagicMock()
        stage.GetRootLayer.return_value = root_layer
        context = MagicMock()
        context.get_stage.return_value = stage

        # Act
        with patch.object(settings_module.omni.usd, "get_context", return_value=context):
            result = AlphaCutoutSettings.default_output_folder("")

        # Assert
        self.assertTrue(result.replace("\\", "/").endswith("projects/demo/assets/ingested/alpha_cutout"))

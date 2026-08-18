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

from unittest.mock import patch

from omni.kit.test import AsyncTestCase
from lightspeed.trex.comfyui.core.preset import Preset


class TestPreset(AsyncTestCase):
    """Test canonical preset schema parsing and application."""

    async def test_preset_rejects_malformed_nested_fields(self):
        """Preset parsing returns no object for malformed nested schema fields."""
        # Arrange
        cases = (
            ("BadInputs", {"inputs": ["malformed"]}),
            ("BadDescription", {"description": ["malformed"], "inputs": {}}),
            (7, {"inputs": {}}),
        )

        for name, data in cases:
            with self.subTest(name=name):
                # Act
                with patch("lightspeed.trex.comfyui.core.preset.carb.log_warn") as log_warn:
                    result = Preset.from_dict(name, data)

                # Assert
                self.assertIsNone(result)
                log_warn.assert_called_once()

    async def test_preset_rejects_explicit_null_inputs(self):
        """An explicit null inputs container is malformed."""
        # Arrange
        data = {"description": "Malformed", "inputs": None}

        # Act
        with patch("lightspeed.trex.comfyui.core.preset.carb.log_warn") as log_warn:
            result = Preset.from_dict("NullInputs", data)

        # Assert
        self.assertIsNone(result)
        log_warn.assert_called_once()

    async def test_preset_without_inputs_is_rejected(self):
        """A preset must use the canonical nested inputs container."""
        # Arrange
        data = {"description": "Invalid", "68.strength": {"value": 0.5}}

        # Act
        with patch("lightspeed.trex.comfyui.core.preset.carb.log_warn") as log_warn:
            result = Preset.from_dict("Invalid", data)

        # Assert
        self.assertIsNone(result)
        log_warn.assert_called_once()

    async def test_preset_scalar_override_is_ignored(self):
        """Preset overrides must use an object containing value."""
        # Arrange
        data = {"inputs": {"68.strength": 0.5}}

        # Act
        with patch("lightspeed.trex.comfyui.core.preset.carb.log_warn") as log_warn:
            result = Preset.from_dict("Invalid", data)

        # Assert
        self.assertEqual(result.inputs, {})
        log_warn.assert_called_once()

    async def test_preset_input_without_node_port_is_ignored(self):
        """Preset input keys must identify both a node and port."""
        # Arrange
        data = {"inputs": {"invalid": {"value": 0.5}}}

        # Act
        with patch("lightspeed.trex.comfyui.core.preset.carb.log_warn") as log_warn:
            result = Preset.from_dict("Invalid", data)

        # Assert
        self.assertEqual(result.inputs, {})
        log_warn.assert_called_once()

    async def test_preset_from_dict_parses_overrides(self):
        """Preset.from_dict parses node_id.port_name overrides from a dict."""
        # Arrange
        data = {
            "inputs": {
                "68.metallic_strength": {"value": 0},
                "68.roughness_strength": {"value": 0.5},
            },
            "description": "A glass material",
        }

        # Act
        preset = Preset.from_dict("Glass", data)

        # Assert
        self.assertEqual(preset.name, "Glass")
        self.assertEqual(preset.description, "A glass material")
        self.assertEqual(preset.inputs["68.metallic_strength"], 0)
        self.assertEqual(preset.inputs["68.roughness_strength"], 0.5)

    async def test_preset_with_no_inputs_is_valid(self):
        """A preset with empty inputs dict is valid."""
        # Arrange
        data = {"inputs": {}}

        # Act
        preset = Preset.from_dict("Empty", data)

        # Assert
        self.assertEqual(preset.name, "Empty")
        self.assertEqual(preset.description, "")
        self.assertEqual(preset.inputs, {})

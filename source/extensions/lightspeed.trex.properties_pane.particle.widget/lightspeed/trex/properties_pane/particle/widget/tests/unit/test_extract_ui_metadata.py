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

__all__ = ("TestExtractUiMetadataFromSchema",)

import omni.kit.test
from lightspeed.trex.properties_pane.particle.widget.setup_ui import _extract_ui_metadata_from_schema
from pxr import Gf


class _AttrStub:
    """Minimal stand-in for Sdf.AttributeSpec — only ``customData`` is required."""

    def __init__(self, custom_data):
        self.customData = custom_data


class TestExtractUiMetadataFromSchema(omni.kit.test.AsyncTestCase):
    # ------------------------------------------------------------------
    # Guard cases — should return None
    # ------------------------------------------------------------------

    async def test_none_input_returns_none(self):
        """Passing None should return None without raising."""
        # Act
        result = _extract_ui_metadata_from_schema(None)

        # Assert
        self.assertIsNone(result)

    async def test_empty_custom_data_returns_none(self):
        """An attribute with no customData should return None."""
        # Arrange
        attr = _AttrStub({})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertIsNone(result)

    async def test_missing_limits_key_returns_none(self):
        """customData present but without a 'limits' key should return None."""
        # Arrange
        attr = _AttrStub({"other": 1})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertIsNone(result)

    async def test_empty_limits_returns_none(self):
        """An empty 'limits' dict should return None."""
        # Arrange
        attr = _AttrStub({"limits": {}})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertIsNone(result)

    async def test_limits_with_no_scalar_values_returns_none(self):
        """Limits whose min/max are non-scalar should be skipped, returning None."""
        # Arrange
        attr = _AttrStub({"limits": {"hard": {"minimum": Gf.Vec2f(0, 0), "maximum": Gf.Vec2f(1, 1)}}})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Hard-only block
    # ------------------------------------------------------------------

    async def test_hard_block_only_maps_correct_keys(self):
        """A hard-only block should populate hard_min and hard_max exclusively."""
        # Arrange
        attr = _AttrStub({"limits": {"hard": {"minimum": 1, "maximum": 10000000}}})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertEqual(result, {"hard_min": 1, "hard_max": 10000000})

    async def test_hard_block_with_step(self):
        """step in the hard block should map to ui_step."""
        # Arrange
        attr = _AttrStub({"limits": {"hard": {"minimum": 1, "maximum": 100, "step": 2}}})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertEqual(result["ui_step"], 2)

    async def test_hard_block_min_only(self):
        """Only minimum in hard block should produce hard_min without hard_max."""
        # Arrange
        attr = _AttrStub({"limits": {"hard": {"minimum": 1}}})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertEqual(result, {"hard_min": 1})

    # ------------------------------------------------------------------
    # Soft-only block
    # ------------------------------------------------------------------

    async def test_soft_block_only_maps_correct_keys(self):
        """A soft-only block should populate soft_min and soft_max exclusively."""
        # Arrange
        attr = _AttrStub({"limits": {"soft": {"minimum": 0.0, "maximum": 1.0}}})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertEqual(result, {"soft_min": 0.0, "soft_max": 1.0})

    async def test_soft_block_with_step(self):
        """step in the soft block should map to ui_step when no hard step is present."""
        # Arrange
        attr = _AttrStub({"limits": {"soft": {"minimum": 0.0, "maximum": 1.0, "step": 0.1}}})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertEqual(result["ui_step"], 0.1)

    # ------------------------------------------------------------------
    # Both blocks
    # ------------------------------------------------------------------

    async def test_both_blocks_populate_all_keys(self):
        """Both blocks present should populate all four bound keys."""
        # Arrange
        attr = _AttrStub(
            {
                "limits": {
                    "soft": {"minimum": 1.0, "maximum": 100.0},
                    "hard": {"minimum": 0.0, "maximum": 200.0},
                }
            }
        )

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertEqual(result["soft_min"], 1.0)
        self.assertEqual(result["soft_max"], 100.0)
        self.assertEqual(result["hard_min"], 0.0)
        self.assertEqual(result["hard_max"], 200.0)

    async def test_step_in_soft_wins_over_hard(self):
        """When both blocks have a step, the soft block is iterated first so its step wins."""
        # Arrange
        attr = _AttrStub(
            {
                "limits": {
                    "soft": {"minimum": 0.0, "maximum": 1.0, "step": 0.1},
                    "hard": {"minimum": -1.0, "maximum": 2.0, "step": 1.0},
                }
            }
        )

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertEqual(result["ui_step"], 0.1)

    async def test_no_step_in_either_block(self):
        """When no block has a step, ui_step should not be present in the result."""
        # Arrange
        attr = _AttrStub(
            {
                "limits": {
                    "soft": {"minimum": 0.0, "maximum": 1.0},
                    "hard": {"minimum": -1.0, "maximum": 2.0},
                }
            }
        )

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertNotIn("ui_step", result)

    # ------------------------------------------------------------------
    # Non-scalar values are silently skipped
    # ------------------------------------------------------------------

    async def test_non_scalar_minimum_skipped(self):
        """Non-scalar minimum values should be silently ignored."""
        # Arrange
        attr = _AttrStub({"limits": {"hard": {"minimum": Gf.Vec2f(0, 0), "maximum": 100}}})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertNotIn("hard_min", result)
        self.assertEqual(result["hard_max"], 100)

    async def test_float_bounds_accepted(self):
        """Float bounds should be accepted as scalar values."""
        # Arrange
        attr = _AttrStub({"limits": {"hard": {"minimum": 0.5, "maximum": 99.5}}})

        # Act
        result = _extract_ui_metadata_from_schema(attr)

        # Assert
        self.assertAlmostEqual(result["hard_min"], 0.5)
        self.assertAlmostEqual(result["hard_max"], 99.5)

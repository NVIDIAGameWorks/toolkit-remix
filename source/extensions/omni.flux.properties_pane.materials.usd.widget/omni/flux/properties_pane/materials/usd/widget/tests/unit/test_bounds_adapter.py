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

import omni.kit.test
from omni.flux.properties_pane.materials.usd.widget.bounds_adapter import MaterialBoundsAdapter
from pxr import Gf, Sdf, UsdShade

_HARD_RANGE_KEY = "hard_range"
_SOFT_RANGE_KEY = "soft_range"


class TestMaterialBoundsAdapter(omni.kit.test.AsyncTestCase):
    """Unit tests for material placeholder bounds normalization."""

    async def test_mdl_hard_range_only_sets_hard_bounds_and_visible_bounds(self):
        # Arrange
        adapter = MaterialBoundsAdapter(
            {
                UsdShade.Tokens.sdrMetadata: {
                    _HARD_RANGE_KEY: {"min": 1.0, "max": 3.0},
                }
            }
        )

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertEqual(bounds, (1.0, 3.0, 1.0, 3.0))
        self.assertIsNone(step)

    async def test_mdl_soft_and_hard_ranges_remain_separate(self):
        # Arrange
        adapter = MaterialBoundsAdapter(
            {
                UsdShade.Tokens.sdrMetadata: {
                    _SOFT_RANGE_KEY: {"min": 1.1, "max": 2.5},
                    _HARD_RANGE_KEY: {"min": 1.0, "max": 3.0},
                }
            }
        )

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (1.1, 2.5, 1.0, 3.0))

    async def test_mdl_bounds_win_over_custom_data_range_and_preserve_custom_step(self):
        # Arrange
        adapter = MaterialBoundsAdapter(
            {
                UsdShade.Tokens.sdrMetadata: {
                    _HARD_RANGE_KEY: {"min": 1.0, "max": 3.0},
                },
                Sdf.AttributeSpec.CustomDataKey: {
                    "range": {"min": -100.0, "max": 100.0},
                    "ui:step": 0.25,
                },
            }
        )

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertEqual(bounds, (1.0, 3.0, 1.0, 3.0))
        self.assertEqual(step, 0.25)

    async def test_legacy_custom_data_range_is_used_when_mdl_ranges_are_absent(self):
        # Arrange
        adapter = MaterialBoundsAdapter(
            {
                Sdf.AttributeSpec.CustomDataKey: {
                    "range": {"min": -2.0, "max": 12.0},
                    "ui:step": 0.5,
                }
            }
        )

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertEqual(bounds, (-2.0, 12.0, None, None))
        self.assertEqual(step, 0.5)

    async def test_top_level_legacy_range_is_used_when_custom_data_is_absent(self):
        # Arrange
        adapter = MaterialBoundsAdapter({"range": {"min": 2.0, "max": 4.0}, "ui:step": 0.2})

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertEqual(bounds, (2.0, 4.0, None, None))
        self.assertEqual(step, 0.2)

    async def test_non_dict_input_has_no_bounds_or_step(self):
        # Arrange
        adapter = MaterialBoundsAdapter("not metadata")

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertIsNone(bounds)
        self.assertIsNone(step)

    async def test_empty_payload_has_no_bounds_or_step(self):
        # Arrange
        adapter = MaterialBoundsAdapter({})

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertIsNone(bounds)
        self.assertIsNone(step)

    async def test_non_dict_sdr_metadata_falls_back_to_custom_data(self):
        # Arrange
        adapter = MaterialBoundsAdapter(
            {
                UsdShade.Tokens.sdrMetadata: "not sdr metadata",
                Sdf.AttributeSpec.CustomDataKey: {
                    "range": {"min": 0.0, "max": 1.0},
                },
            }
        )

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (0.0, 1.0, None, None))

    async def test_empty_sdr_metadata_falls_back_to_custom_data(self):
        # Arrange
        adapter = MaterialBoundsAdapter(
            {
                UsdShade.Tokens.sdrMetadata: {},
                Sdf.AttributeSpec.CustomDataKey: {
                    "range": {"min": 0.0, "max": 1.0},
                },
            }
        )

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (0.0, 1.0, None, None))

    async def test_non_dict_mdl_ranges_are_ignored_and_fall_back_to_custom_data(self):
        # Arrange
        adapter = MaterialBoundsAdapter(
            {
                UsdShade.Tokens.sdrMetadata: {
                    _SOFT_RANGE_KEY: "not a range",
                    _HARD_RANGE_KEY: "not a range",
                },
                Sdf.AttributeSpec.CustomDataKey: {
                    "range": {"min": 0.0, "max": 1.0},
                },
            }
        )

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (0.0, 1.0, None, None))

    async def test_partial_mdl_hard_range_preserves_available_bound(self):
        # Arrange
        adapter = MaterialBoundsAdapter(
            {
                UsdShade.Tokens.sdrMetadata: {
                    _HARD_RANGE_KEY: {"min": 1.0},
                }
            }
        )

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (1.0, None, 1.0, None))

    async def test_vector_like_mdl_hard_range_values_are_preserved(self):
        # Arrange
        min_value = Gf.Vec3f(0.0, 0.0, 0.0)
        max_value = Gf.Vec3f(1.0, 1.0, 1.0)
        adapter = MaterialBoundsAdapter(
            {
                UsdShade.Tokens.sdrMetadata: {
                    _HARD_RANGE_KEY: {"min": min_value, "max": max_value},
                }
            }
        )

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (min_value, max_value, min_value, max_value))

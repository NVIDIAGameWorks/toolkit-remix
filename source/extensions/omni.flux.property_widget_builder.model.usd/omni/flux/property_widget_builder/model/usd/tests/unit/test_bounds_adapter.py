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
from omni.flux.property_widget_builder.model.usd import BoundsAdapter
from omni.flux.property_widget_builder.model.usd.bounds_adapter import NormalizedBoundsStepData
from pxr import Gf


class TestBoundsAdapter(omni.kit.test.AsyncTestCase):
    """Unit tests for legacy base adapter normalization contract."""

    async def test_extract_bounds_legacy_range_supported(self):
        # Arrange
        adapter = BoundsAdapter({"range": {"min": -100.0, "max": 100.0}})

        # Act
        result = adapter.bounds

        # Assert
        self.assertEqual(result, (-100.0, 100.0, None, None))

    async def test_extract_step_legacy_ui_step_supported(self):
        # Arrange
        adapter = BoundsAdapter({"range": {"min": -100.0, "max": 100.0}, "ui:step": 10.0})

        # Act
        step = adapter.step

        # Assert
        self.assertEqual(step, 10.0)

    async def test_extract_step_legacy_ui_step_supported_without_range(self):
        # Arrange
        adapter = BoundsAdapter({"ui:step": 0.5})

        # Act
        step = adapter.step
        bounds = adapter.bounds

        # Assert
        self.assertEqual(step, 0.5)
        self.assertIsNone(bounds)

    async def test_extract_bounds_legacy_range_vectors_are_preserved(self):
        # Arrange
        adapter = BoundsAdapter({"range": {"min": Gf.Vec2f(-2.0, -1.0), "max": Gf.Vec2f(4.0, 8.0)}})

        # Act
        result = adapter.bounds

        # Assert
        self.assertEqual(result, (Gf.Vec2f(-2.0, -1.0), Gf.Vec2f(4.0, 8.0), None, None))

    async def test_extract_step_ignores_limits_without_source_adapter(self):
        # Arrange
        adapter = BoundsAdapter({"limits": {"step": 0.5}})

        # Act
        step = adapter.step

        # Assert
        self.assertIsNone(step)

    async def test_extract_bounds_ignores_limits_without_source_adapter(self):
        # Arrange
        adapter = BoundsAdapter({"limits": {"hard": {"minimum": Gf.Vec2f(0.0, 1.0), "maximum": Gf.Vec2f(7.0, 3.0)}}})

        # Act
        result = adapter.bounds

        # Assert
        self.assertIsNone(result)

    async def test_extract_bounds_ignores_non_legacy_ui_metadata_shape(self):
        # Arrange
        adapter = BoundsAdapter({"soft_min": 0.0, "soft_max": 1.0})

        # Act
        result = adapter.bounds

        # Assert
        self.assertIsNone(result)

    async def test_init_with_normalized_data_skips_raw_normalization(self):
        # Arrange
        adapter = BoundsAdapter(
            raw_bounds_step_data={"soft_min": 0.0, "soft_max": 1.0},
            normalized_data=NormalizedBoundsStepData(
                soft_min=-2.0,
                soft_max=8.0,
                hard_min=None,
                hard_max=None,
                step=0.25,
            ),
        )

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertEqual(bounds, (-2.0, 8.0, None, None))
        self.assertEqual(step, 0.25)

    async def test_merge_bounds_adapters_intersects_numeric_soft_bounds_and_uses_coarsest_step(self):
        # Arrange
        adapter_a = BoundsAdapter({"range": {"min": 1.0, "max": 4.0}, "ui:step": 0.5})
        adapter_b = BoundsAdapter({"range": {"min": -3.0, "max": 10.0}, "ui:step": 1.5})

        # Act
        merged_adapter = BoundsAdapter.merge_bounds_adapters([adapter_a, adapter_b])

        # Assert
        self.assertEqual(merged_adapter.bounds, (1.0, 4.0, None, None))
        self.assertEqual(merged_adapter.step, 1.5)

    async def test_merge_bounds_adapters_preserves_single_payload_vectors(self):
        # Arrange
        adapter = BoundsAdapter({"range": {"min": Gf.Vec2f(-2.0, -1.0), "max": Gf.Vec2f(4.0, 8.0)}})

        # Act
        merged_adapter = BoundsAdapter.merge_bounds_adapters([adapter])

        # Assert
        self.assertEqual(merged_adapter.bounds, (Gf.Vec2f(-2.0, -1.0), Gf.Vec2f(4.0, 8.0), None, None))
        self.assertIsNone(merged_adapter.step)

    async def test_merge_bounds_adapters_returns_none_bounds_when_soft_ranges_do_not_overlap(self):
        # Arrange
        adapter_a = BoundsAdapter({"range": {"min": 0.0, "max": 1.0}, "ui:step": 0.25})
        adapter_b = BoundsAdapter({"range": {"min": 100.0, "max": 200.0}, "ui:step": 0.5})

        # Act
        merged_adapter = BoundsAdapter.merge_bounds_adapters([adapter_a, adapter_b])

        # Assert
        self.assertIsNone(merged_adapter.bounds)
        self.assertEqual(merged_adapter.step, 0.5)

    async def test_merge_bounds_adapters_sets_soft_and_hard_when_selection_is_mixed(self):
        # Arrange
        adapter_soft_only = BoundsAdapter({"range": {"min": 0.0, "max": 10.0}, "ui:step": 0.25})
        adapter_hard_only = BoundsAdapter(
            normalized_data=NormalizedBoundsStepData(
                soft_min=None,
                soft_max=None,
                hard_min=2.0,
                hard_max=8.0,
                step=1.0,
            )
        )

        # Act
        merged_adapter = BoundsAdapter.merge_bounds_adapters([adapter_soft_only, adapter_hard_only])

        # Assert
        self.assertEqual(merged_adapter.bounds, (2.0, 8.0, 2.0, 8.0))
        self.assertEqual(merged_adapter.step, 1.0)
        self.assertEqual(merged_adapter._soft_min, 2.0)
        self.assertEqual(merged_adapter._soft_max, 8.0)
        self.assertEqual(merged_adapter._hard_min, 2.0)
        self.assertEqual(merged_adapter._hard_max, 8.0)

    async def test_merge_bounds_adapters_does_not_set_soft_when_all_objects_are_hard_only(self):
        # Arrange
        adapter_hard_a = BoundsAdapter(
            normalized_data=NormalizedBoundsStepData(
                soft_min=None,
                soft_max=None,
                hard_min=0.0,
                hard_max=5.0,
                step=0.25,
            )
        )
        adapter_hard_b = BoundsAdapter(
            normalized_data=NormalizedBoundsStepData(
                soft_min=None,
                soft_max=None,
                hard_min=2.0,
                hard_max=4.0,
                step=1.0,
            )
        )

        # Act
        merged_adapter = BoundsAdapter.merge_bounds_adapters([adapter_hard_a, adapter_hard_b])

        # Assert
        self.assertEqual(merged_adapter.bounds, (2.0, 4.0, 2.0, 4.0))
        self.assertIsNone(merged_adapter._soft_min)
        self.assertIsNone(merged_adapter._soft_max)
        self.assertEqual(merged_adapter._hard_min, 2.0)
        self.assertEqual(merged_adapter._hard_max, 4.0)

    async def test_merge_bounds_adapters_clears_all_bounds_for_mixed_disjoint_selection(self):
        # Arrange
        adapter_soft_only = BoundsAdapter({"range": {"min": 0.0, "max": 1.0}, "ui:step": 0.25})
        adapter_hard_only = BoundsAdapter(
            normalized_data=NormalizedBoundsStepData(
                soft_min=None,
                soft_max=None,
                hard_min=100.0,
                hard_max=200.0,
                step=0.5,
            )
        )

        # Act
        merged_adapter = BoundsAdapter.merge_bounds_adapters([adapter_soft_only, adapter_hard_only])

        # Assert
        self.assertIsNone(merged_adapter.bounds)
        self.assertIsNone(merged_adapter._soft_min)
        self.assertIsNone(merged_adapter._soft_max)
        self.assertIsNone(merged_adapter._hard_min)
        self.assertIsNone(merged_adapter._hard_max)
        self.assertEqual(merged_adapter.step, 0.5)

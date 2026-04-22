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

__all__ = ("TestIntDragFieldUnit",)

import omni.kit.test
from omni.flux.property_widget_builder.delegates.int_value.drag import IntDragFieldGroup


class TestIntDragFieldUnit(omni.kit.test.AsyncTestCase):
    """Unit tests for IntDragFieldGroup logic (no UI rendering)."""

    # ------------------------------------------------------------------
    # Default constructor values
    # ------------------------------------------------------------------

    async def test_default_constructor_values(self):
        """IntDragFieldGroup defaults: min=None, max=None, step=None, style='DragField'."""
        # Arrange
        field = IntDragFieldGroup()

        # Act
        min_value = field.min_value
        max_value = field.max_value
        step_value = field._step
        style_name = field.style_name

        # Assert
        self.assertIsNone(min_value)
        self.assertIsNone(max_value)
        self.assertIsNone(step_value)
        self.assertEqual(style_name, "DragField")

    async def test_bounded_constructor(self):
        """When both bounds are provided they should be stored."""
        # Arrange
        field = IntDragFieldGroup(min_value=0, max_value=100)

        # Act
        min_value = field.min_value
        max_value = field.max_value

        # Assert
        self.assertEqual(min_value, 0)
        self.assertEqual(max_value, 100)

    # ------------------------------------------------------------------
    # Step calculation (overrides base)
    # ------------------------------------------------------------------

    async def test_default_step_small_range(self):
        """For range <= 100, default step should be 1."""
        # Arrange
        field = IntDragFieldGroup(min_value=0, max_value=100)

        # Act
        step_value = field.step

        # Assert
        self.assertEqual(step_value, 1)

    async def test_default_step_very_small_range(self):
        """For a tiny range (e.g. 0 to 10), default step should still be 1."""
        # Arrange
        field = IntDragFieldGroup(min_value=0, max_value=10)

        # Act
        step_value = field.step

        # Assert
        self.assertEqual(step_value, 1)

    async def test_default_step_negative_small_range(self):
        """A negative-to-positive range of 100 should yield step 1."""
        # Arrange
        field = IntDragFieldGroup(min_value=-50, max_value=50)

        # Act
        step_value = field.step

        # Assert
        self.assertEqual(step_value, 1)

    async def test_default_step_large_range(self):
        """For range > 100, default step should be max(1, int(range * 0.01))."""
        # Arrange
        field = IntDragFieldGroup(min_value=0, max_value=1000)

        # Act
        step_value = field.step

        # Assert
        self.assertEqual(step_value, 10)

    async def test_default_step_very_large_range(self):
        """For a very large range, step scales with the range."""
        # Arrange
        field = IntDragFieldGroup(min_value=0, max_value=10000)

        # Act
        step_value = field.step

        # Assert
        self.assertEqual(step_value, 100)

    async def test_default_step_boundary_101(self):
        """Range of exactly 101 crosses the > 100 threshold but int(101 * 0.01) = 1."""
        # Arrange
        field = IntDragFieldGroup(min_value=0, max_value=101)

        # Act
        step_value = field.step

        # Assert
        self.assertEqual(step_value, 1)

    async def test_default_step_boundary_200(self):
        """Range of 200 should yield step 2."""
        # Arrange
        field = IntDragFieldGroup(min_value=0, max_value=200)

        # Act
        step_value = field.step

        # Assert
        self.assertEqual(step_value, 2)

    async def test_default_step_unbounded(self):
        """Default step should be 1 when bounds are not set."""
        # Arrange
        field = IntDragFieldGroup()

        # Act
        step_value = field.step

        # Assert
        self.assertEqual(step_value, 1)

    async def test_custom_step_overrides_default(self):
        """An explicitly provided step should override the computed default."""
        # Arrange
        field = IntDragFieldGroup(min_value=0, max_value=100, step=10)

        # Act
        step_value = field.step

        # Assert
        self.assertEqual(step_value, 10)

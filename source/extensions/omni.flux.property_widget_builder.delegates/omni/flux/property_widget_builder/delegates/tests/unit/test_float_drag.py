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

__all__ = ("TestFloatDragFieldUnit",)

from typing import cast

import omni.kit.test
from omni.flux.property_widget_builder.delegates.float_value.drag import FloatDragFieldGroup


class TestFloatDragFieldUnit(omni.kit.test.AsyncTestCase):
    """Unit tests for FloatDragFieldGroup logic (no UI rendering)."""

    # ------------------------------------------------------------------
    # Default constructor values
    # ------------------------------------------------------------------

    async def test_default_constructor_values(self):
        """FloatDragFieldGroup defaults: min=None, max=None, step=None, style='DragField'."""
        # Arrange
        field = FloatDragFieldGroup()

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
        field = FloatDragFieldGroup(min_value=0.0, max_value=100.0)

        # Act
        min_value = field.min_value
        max_value = field.max_value

        # Assert
        self.assertEqual(min_value, 0.0)
        self.assertEqual(max_value, 100.0)

    # ------------------------------------------------------------------
    # Step calculation (overrides base)
    # ------------------------------------------------------------------

    async def test_default_step_standard_range(self):
        """Default step should be (max - min) * 0.005 when both bounds set."""
        # Arrange
        field = FloatDragFieldGroup(min_value=0.0, max_value=100.0)

        # Act
        step_value = cast(float, field.step)

        # Assert
        self.assertAlmostEqual(step_value, 0.5)

    async def test_default_step_negative_range(self):
        """Default step should work for ranges spanning negative to positive."""
        # Arrange
        field = FloatDragFieldGroup(min_value=-50.0, max_value=50.0)

        # Act
        step_value = cast(float, field.step)

        # Assert
        self.assertAlmostEqual(step_value, 0.5)

    async def test_default_step_small_range(self):
        """Default step for a small range (0 to 1)."""
        # Arrange
        field = FloatDragFieldGroup(min_value=0.0, max_value=1.0)

        # Act
        step_value = cast(float, field.step)

        # Assert
        self.assertAlmostEqual(step_value, 0.005)

    async def test_default_step_unbounded(self):
        """Default step should be 1.0 when bounds are not set."""
        # Arrange
        field = FloatDragFieldGroup()

        # Act
        step_value = cast(float, field.step)

        # Assert
        self.assertAlmostEqual(step_value, 1.0)

    async def test_default_step_partial_bound(self):
        """Default step should be 1.0 when only one bound is set."""
        # Arrange
        field = FloatDragFieldGroup(min_value=0.0)

        # Act
        step_value = cast(float, field.step)

        # Assert
        self.assertAlmostEqual(step_value, 1.0)

    async def test_custom_step_overrides_default(self):
        """An explicitly provided step should override the computed default."""
        # Arrange
        field = FloatDragFieldGroup(min_value=0.0, max_value=100.0, step=2.5)

        # Act
        step_value = cast(float, field.step)

        # Assert
        self.assertAlmostEqual(step_value, 2.5)

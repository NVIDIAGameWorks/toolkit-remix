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

import omni.kit.test
from omni.flux.property_widget_builder.delegates.float_value.drag import FloatDragField

from .mocks import MockValueModel


class TestFloatDragFieldUnit(omni.kit.test.AsyncTestCase):
    """Unit tests for FloatDragField logic (no UI rendering)."""

    # ------------------------------------------------------------------
    # Default constructor values
    # ------------------------------------------------------------------

    async def test_default_constructor_values(self):
        """FloatDragField defaults: min=None, max=None, step=None, style='DragField'."""
        field = FloatDragField()
        self.assertIsNone(field.min_value)
        self.assertIsNone(field.max_value)
        self.assertIsNone(field._step)
        self.assertEqual(field.style_name, "DragField")

    async def test_bounded_constructor(self):
        """When both bounds are provided they should be stored."""
        field = FloatDragField(min_value=0.0, max_value=100.0)
        self.assertEqual(field.min_value, 0.0)
        self.assertEqual(field.max_value, 100.0)

    # ------------------------------------------------------------------
    # Step calculation (overrides base)
    # ------------------------------------------------------------------

    async def test_default_step_standard_range(self):
        """Default step should be (max - min) * 0.005 when both bounds set."""
        field = FloatDragField(min_value=0.0, max_value=100.0)
        self.assertAlmostEqual(field.step, 0.5)

    async def test_default_step_negative_range(self):
        """Default step should work for ranges spanning negative to positive."""
        field = FloatDragField(min_value=-50.0, max_value=50.0)
        self.assertAlmostEqual(field.step, 0.5)

    async def test_default_step_small_range(self):
        """Default step for a small range (0 to 1)."""
        field = FloatDragField(min_value=0.0, max_value=1.0)
        self.assertAlmostEqual(field.step, 0.005)

    async def test_default_step_unbounded(self):
        """Default step should be 1.0 when bounds are not set."""
        field = FloatDragField()
        self.assertAlmostEqual(field.step, 1.0)

    async def test_default_step_partial_bound(self):
        """Default step should be 1.0 when only one bound is set."""
        field = FloatDragField(min_value=0.0)
        self.assertAlmostEqual(field.step, 1.0)

    async def test_custom_step_overrides_default(self):
        """An explicitly provided step should override the computed default."""
        field = FloatDragField(min_value=0.0, max_value=100.0, step=2.5)
        self.assertAlmostEqual(field.step, 2.5)

    # ------------------------------------------------------------------
    # _get_value_from_model
    # ------------------------------------------------------------------

    async def test_get_value_from_model(self):
        """_get_value_from_model should return a float from the model."""
        field = FloatDragField()
        model = MockValueModel(value=3.14)
        result = field._get_value_from_model(model)
        self.assertIsInstance(result, float)
        self.assertAlmostEqual(result, 3.14)

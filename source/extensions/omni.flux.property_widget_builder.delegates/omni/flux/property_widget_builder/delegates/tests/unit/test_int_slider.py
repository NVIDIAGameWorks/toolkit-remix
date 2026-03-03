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

__all__ = ("TestIntSliderFieldUnit",)

import omni.kit.test
from omni.flux.property_widget_builder.delegates.int_value.slider import IntSliderField

from .mocks import MockValueModel


class TestIntSliderFieldUnit(omni.kit.test.AsyncTestCase):
    """Unit tests for IntSliderField logic (no UI rendering)."""

    # ------------------------------------------------------------------
    # Default constructor values
    # ------------------------------------------------------------------

    async def test_default_constructor_values(self):
        """IntSliderField defaults: min=0, max=100, step=None, style='IntSliderField'."""
        field = IntSliderField()
        self.assertEqual(field.min_value, 0)
        self.assertEqual(field.max_value, 100)
        self.assertIsNone(field._step)
        self.assertEqual(field.style_name, "IntSliderField")

    # ------------------------------------------------------------------
    # Step calculation (overrides base)
    # ------------------------------------------------------------------

    async def test_default_step_small_range(self):
        """For range <= 100, default step should be 1."""
        field = IntSliderField(min_value=0, max_value=100)
        self.assertEqual(field.step, 1)

    async def test_default_step_very_small_range(self):
        """For a tiny range (e.g. 0 to 10), default step should still be 1."""
        field = IntSliderField(min_value=0, max_value=10)
        self.assertEqual(field.step, 1)

    async def test_default_step_negative_small_range(self):
        """A negative-to-positive range of 100 should yield step 1."""
        field = IntSliderField(min_value=-50, max_value=50)
        self.assertEqual(field.step, 1)

    async def test_default_step_large_range(self):
        """For range > 100, default step should be max(1, int(range * 0.01))."""
        field = IntSliderField(min_value=0, max_value=1000)
        self.assertEqual(field.step, 10)

    async def test_default_step_very_large_range(self):
        """For a very large range, step scales with the range."""
        field = IntSliderField(min_value=0, max_value=10000)
        self.assertEqual(field.step, 100)

    async def test_default_step_boundary_101(self):
        """Range of exactly 101 crosses the > 100 threshold but int(101 * 0.01) = 1."""
        field = IntSliderField(min_value=0, max_value=101)
        self.assertEqual(field.step, 1)

    async def test_default_step_boundary_200(self):
        """Range of 200 should yield step 2."""
        field = IntSliderField(min_value=0, max_value=200)
        self.assertEqual(field.step, 2)

    async def test_custom_step_overrides_default(self):
        """An explicitly provided step should override the computed default."""
        field = IntSliderField(min_value=0, max_value=100, step=10)
        self.assertEqual(field.step, 10)

    # ------------------------------------------------------------------
    # _get_value_from_model
    # ------------------------------------------------------------------

    async def test_get_value_from_model(self):
        """_get_value_from_model should return an int from the model."""
        field = IntSliderField()
        model = MockValueModel(value=42.7)
        result = field._get_value_from_model(model)
        self.assertIsInstance(result, int)
        self.assertEqual(result, 42)

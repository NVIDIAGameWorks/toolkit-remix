"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ("TestIntSliderField",)

import uuid

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.int_value.slider import IntSliderField

from .test_abstract_slider import MockItem


class TestIntSliderField(omni.kit.test.AsyncTestCase):
    """Tests for behaviour unique to IntSliderField."""

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
        # range = 1000 → int(1000 * 0.01) = 10
        self.assertEqual(field.step, 10)

    async def test_default_step_very_large_range(self):
        """For a very large range, step scales with the range."""
        field = IntSliderField(min_value=0, max_value=10000)
        # range = 10000 → int(10000 * 0.01) = 100
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
    # Widget type
    # ------------------------------------------------------------------

    async def test_build_drag_widget_creates_int_drag(self):
        """build_ui should produce ui.IntDrag widgets."""
        window = ui.Window(
            f"TestIntSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[25])
        field = IntSliderField(min_value=0, max_value=100)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 1)
        self.assertIsInstance(widgets[0], ui.IntDrag)

        for w in widgets:
            w.destroy()
        window.destroy()

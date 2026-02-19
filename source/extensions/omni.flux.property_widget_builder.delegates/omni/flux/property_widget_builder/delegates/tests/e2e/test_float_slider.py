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

__all__ = ("TestFloatSliderField",)

import uuid

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.float_value.slider import FloatSliderField

from .test_abstract_slider import MockItem


class TestFloatSliderField(omni.kit.test.AsyncTestCase):
    """Tests for behaviour unique to FloatSliderField."""

    # ------------------------------------------------------------------
    # Default constructor values
    # ------------------------------------------------------------------

    async def test_default_constructor_values(self):
        """FloatSliderField defaults: min=0.0, max=100.0, step=None, style='FloatSliderField'."""
        field = FloatSliderField()
        self.assertEqual(field.min_value, 0.0)
        self.assertEqual(field.max_value, 100.0)
        self.assertIsNone(field._step)
        self.assertEqual(field.style_name, "FloatSliderField")

    # ------------------------------------------------------------------
    # Step calculation (overrides base)
    # ------------------------------------------------------------------

    async def test_default_step_standard_range(self):
        """Default step should be (max - min) * 0.005."""
        field = FloatSliderField(min_value=0.0, max_value=100.0)
        self.assertAlmostEqual(field.step, 0.5)

    async def test_default_step_negative_range(self):
        """Default step should work for ranges spanning negative to positive."""
        field = FloatSliderField(min_value=-50.0, max_value=50.0)
        self.assertAlmostEqual(field.step, 0.5)

    async def test_default_step_small_range(self):
        """Default step for a small range (0 to 1)."""
        field = FloatSliderField(min_value=0.0, max_value=1.0)
        self.assertAlmostEqual(field.step, 0.005)

    async def test_custom_step_overrides_default(self):
        """An explicitly provided step should override the computed default."""
        field = FloatSliderField(min_value=0.0, max_value=100.0, step=2.5)
        self.assertAlmostEqual(field.step, 2.5)

    # ------------------------------------------------------------------
    # Widget type
    # ------------------------------------------------------------------

    async def test_build_drag_widget_creates_float_drag(self):
        """build_ui should produce ui.FloatDrag widgets."""
        window = ui.Window(
            f"TestFloatSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[25.0])
        field = FloatSliderField(min_value=0.0, max_value=100.0)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 1)
        self.assertIsInstance(widgets[0], ui.FloatDrag)

        for w in widgets:
            w.destroy()
        window.destroy()

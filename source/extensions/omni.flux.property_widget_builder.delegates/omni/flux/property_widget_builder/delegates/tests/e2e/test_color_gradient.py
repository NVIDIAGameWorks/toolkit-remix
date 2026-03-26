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

__all__ = ("TestColorGradientField",)

import uuid

import omni.kit.app
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.float_value.color_gradient import ColorGradientField


async def _wait_updates(n: int = 3):
    for _ in range(n):
        await omni.kit.app.get_app().next_update_async()


class _MockValueModel(ui.AbstractValueModel):
    """Minimal mock for the value model subscription interface."""

    def __init__(self):
        super().__init__()
        self.read_only = False

    def get_value(self):
        return None

    def set_value(self, value):
        self._value_changed()


class _MockItem(ui.AbstractItem):
    """Minimal mock that provides value_models for subscription."""

    def __init__(self):
        super().__init__()
        self.value_models = [_MockValueModel()]


class TestColorGradientField(omni.kit.test.AsyncTestCase):
    """Tests for the ColorGradientField delegate as a pure UI component."""

    async def setUp(self):
        self._window = ui.Window(
            f"TestGradientField_{uuid.uuid1()}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        self._field = None
        self._widgets = None

    async def tearDown(self):
        if self._widgets:
            for w in self._widgets:
                w.destroy()
            self._widgets = None
        if self._field and self._field._gradient_widget:
            self._field._gradient_widget.destroy()
        self._field = None
        if self._window:
            self._window.destroy()
            self._window = None

    def _build_field(self, keyframes=None):
        """Build the ColorGradientField in the test window."""
        item = _MockItem()
        with self._window.frame:
            self._field = ColorGradientField(
                keyframes=keyframes,
                on_gradient_changed_fn=lambda times, values: None,
            )
            self._widgets = self._field.build_ui(item)

    # ------------------------------------------------------------------
    # Basic construction
    # ------------------------------------------------------------------

    async def test_build_empty_gradient(self):
        """Field should build successfully with no keyframes."""
        self._build_field()
        await _wait_updates()

        self.assertIsNotNone(self._field._gradient_widget)
        self.assertEqual(len(self._field._gradient_widget.get_keyframes()), 0)

    async def test_build_returns_widgets(self):
        """build_ui should return a non-empty list of widgets."""
        self._build_field()
        await _wait_updates()

        self.assertIsNotNone(self._widgets)
        self.assertGreater(len(self._widgets), 0)

    async def test_build_with_existing_data(self):
        """Field should display keyframes passed at construction."""
        keyframes = [(0.0, (1.0, 0.0, 0.0, 1.0)), (0.5, (0.0, 1.0, 0.0, 1.0)), (1.0, (0.0, 0.0, 1.0, 1.0))]
        self._build_field(keyframes=keyframes)
        await _wait_updates()

        kfs = self._field._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 3)
        self.assertAlmostEqual(kfs[0][0], 0.0)
        self.assertAlmostEqual(kfs[1][0], 0.5)
        self.assertAlmostEqual(kfs[2][0], 1.0)

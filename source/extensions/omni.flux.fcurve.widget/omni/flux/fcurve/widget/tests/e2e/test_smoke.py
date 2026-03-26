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

E2E Smoke Test for FCurveWidget.

Verifies that the widget can render a simple curve in a ui.Frame.
"""

import asyncio
import omni.kit.app
import omni.kit.test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, InfinityType

__all__ = ["TestFCurveWidgetSmoke"]


class TestFCurveWidgetSmoke(omni.kit.test.AsyncTestCase):
    """Smoke test that renders a simple curve from (0,0) to (1,1)."""

    async def setUp(self):
        """Set up test environment."""
        self.widget = None
        self.window = None

    async def tearDown(self):
        """Clean up test environment."""
        if self.widget:
            self.widget.destroy()
            self.widget = None

        if self.window:
            self.window.destroy()
            self.window = None

    async def test_render_simple_curve(self):
        """Render a single curve from (0,0) to (1,1) in a ui.Frame."""
        # Create a window to host the widget
        self.window = ui.Window(
            "FCurve Widget Smoke Test",
            width=600,
            height=400,
        )

        # Create the FCurveWidget with padding via inner container
        with self.window.frame:
            with ui.VStack():
                ui.Spacer(height=20)
                with ui.HStack():
                    ui.Spacer(width=20)
                    with ui.ZStack():
                        # Background for curve area
                        ui.Rectangle(style={"background_color": 0xFF1A1A1A})
                        # The FCurve widget
                        self.widget = FCurveWidget(
                            time_range=(0.0, 1.0),
                            value_range=(0.0, 1.0),
                        )
                    ui.Spacer(width=20)
                ui.Spacer(height=20)

        # Wait for layout to compute before setting curves
        for _ in range(3):
            await omni.kit.app.get_app().next_update_async()

        # Set a curve with multiple keyframes and LINEAR infinity extrapolation
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.0),
                        FCurveKey(time=0.3, value=0.7),
                        FCurveKey(time=0.5, value=0.2),
                        FCurveKey(time=0.7, value=0.6),
                        FCurveKey(time=0.85, value=0.6),
                        FCurveKey(time=1.0, value=1.0),
                    ],
                    color=0xFF00FF00,  # Green
                    pre_infinity=InfinityType.LINEAR,
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )

        # Let the UI render curves
        for _ in range(3):
            await omni.kit.app.get_app().next_update_async()

        # Wait to visually inspect (if running interactively)
        await asyncio.sleep(10.0)

        # Verify widget state
        self.assertIsNotNone(self.widget)
        self.assertEqual(len(self.widget.curves), 1)
        self.assertIn("test", self.widget.curves)

        curve = self.widget.curves["test"]
        self.assertEqual(len(curve.keys), 6)
        self.assertEqual(curve.keys[0].time, 0.0)
        self.assertEqual(curve.keys[0].value, 0.0)
        self.assertEqual(curve.keys[1].time, 1.0)
        self.assertEqual(curve.keys[1].value, 1.0)

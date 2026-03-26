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

Full CurveEditorWidget test with toolbar, canvas, grid, and rulers.

Tests that the complete curve editor renders and responds to interaction:
- Toolbar with keyframe and tangent buttons
- Canvas with pan/zoom (Middle/Right-click drag, scroll wheel)
- Grid lines and rulers
"""

import asyncio
import unittest

import omni.kit.app
import omni.kit.test
from omni import ui

from omni.flux.fcurve.widget import FCurve, FCurveKey, TangentType
from omni.flux.curve_editor.widget import CurveEditorWidget, InMemoryCurveModel

__all__ = ["TestFCurveOnly"]


@unittest.skip("Interactive sandbox — run manually, not in CI")
class TestFCurveOnly(omni.kit.test.AsyncTestCase):
    """Full CurveEditorWidget test with toolbar."""

    async def setUp(self):
        self._exit_clicked = False

        # Create model with test curves
        self._model = InMemoryCurveModel(
            display_names={
                "position:x": "Position X",
                "position:y": "Position Y",
            },
        )
        curve = FCurve(
            id="position:x",
            keys=[
                FCurveKey(time=0.0, value=0.2, in_tangent_type=TangentType.LINEAR, out_tangent_type=TangentType.LINEAR),
                FCurveKey(time=0.3, value=0.8, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.LINEAR),
                FCurveKey(time=0.7, value=0.4, in_tangent_type=TangentType.SMOOTH, out_tangent_type=TangentType.SMOOTH),
                FCurveKey(time=1.0, value=0.9, in_tangent_type=TangentType.LINEAR, out_tangent_type=TangentType.LINEAR),
            ],
            color=0xFF3560FF,
        )
        curve2 = FCurve(
            id="position:y",
            keys=[
                FCurveKey(time=0.0, value=0.9, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO),
                FCurveKey(time=0.35, value=0.2, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO),
                FCurveKey(time=0.6, value=0.7, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO),
                FCurveKey(time=1.0, value=0.1, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO),
            ],
            color=0xFF60FF35,
        )
        self._model.commit_curve("position:x", curve)
        self._model.commit_curve("position:y", curve2)

        # Create window
        self.window = ui.Window(
            "Curve Editor Widget Test",
            width=1000,
            height=700,
        )

        with self.window.frame:
            with ui.VStack(spacing=4):
                # CurveEditorWidget with toolbar
                with ui.Frame():
                    # Widget builds automatically in constructor (omni.ui pattern)
                    self._widget = CurveEditorWidget(
                        model=self._model,
                        time_range=(0.0, 1.0),
                        value_range=(0.0, 1.0),
                        show_toolbar=True,
                    )

        await omni.kit.app.get_app().next_update_async()

    async def tearDown(self):
        if self.window:
            self.window.destroy()
            self.window = None

    def _on_exit(self):
        self._exit_clicked = True

    async def _wait_for_exit(self):
        """Wait for user to click Exit."""
        while not self._exit_clicked:
            await asyncio.sleep(0.1)

    async def test_fcurve_widget_standalone(self):
        """Interactive test - Full CurveEditorWidget with toolbar."""
        await self._wait_for_exit()
        self.assertTrue(True)

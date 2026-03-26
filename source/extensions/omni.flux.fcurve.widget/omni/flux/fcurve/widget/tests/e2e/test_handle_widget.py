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

Sandbox: CurveWidgetsManager with 2 keys, full math, drag anything.
"""

import asyncio
import unittest

import omni.kit.app
import omni.kit.test
from omni import ui

from omni.flux.fcurve.widget import FCurve, FCurveKey, CurveBounds, InfinityType, TangentType
from omni.flux.fcurve.widget._internal.viewport import ViewportState
from omni.flux.fcurve.widget._internal.curve_widgets_manager import CurveWidgetsManager

__all__ = ["TestHandleWidgetOnly"]

CANVAS_W, CANVAS_H = 500, 350

KEY_STYLE = {
    "size": 10,
    "background_color": 0xFF00AA00,
    "selected_color": 0xFFFFAA00,
    "hovered_color": 0xFFCCCCCC,
    "border_radius": 2,
}
TAN_STYLE = {"size": 6, "background_color": 0x80FFFFFF, "border_radius": 3}
SEG_STYLE = {"color": 0xFF00AA00, "border_width": 1.5}


@unittest.skip("Interactive sandbox — run manually, not in CI")
class TestHandleWidgetOnly(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._exit = False
        self.window = self.mgr = None

    async def tearDown(self):
        if self.mgr:
            self.mgr.destroy()
        if self.window:
            self.window.destroy()
        self.mgr = self.window = None

    async def test_handle_widget_only(self):
        """2 keys + tangents, full math, drag anything."""
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(
                    time=0.2,
                    value=0.3,
                    in_tangent_type=TangentType.SMOOTH,
                    out_tangent_type=TangentType.STEP,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.SMOOTH,
                    out_tangent_type=TangentType.CUSTOM,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=0.8,
                    value=0.7,
                    in_tangent_type=TangentType.SMOOTH,
                    out_tangent_type=TangentType.CUSTOM,
                    tangent_broken=True,
                ),
            ],
            pre_infinity=InfinityType.LINEAR,
            post_infinity=InfinityType.LINEAR,
        )
        vp = ViewportState(time_min=0, time_max=1, value_min=0, value_max=1, width=CANVAS_W, height=CANVAS_H)
        bounds = CurveBounds(time_min=0, time_max=1, value_min=0, value_max=1)

        self.window = ui.Window("HandleWidget Sandbox", width=CANVAS_W + 20, height=CANVAS_H + 60)
        with self.window.frame:
            with ui.VStack(spacing=0):
                with ui.ZStack(spacing=0):
                    ui.Rectangle(style={"background_color": 0xFF1A1A1A}, width=CANVAS_W, height=CANVAS_H)
                    cf = ui.CanvasFrame(width=CANVAS_W, height=CANVAS_H, style={"background_color": 0x0})
                    with cf:
                        with ui.ZStack() as zstack:
                            self.mgr = CurveWidgetsManager(
                                curve,
                                vp,
                                bounds,
                                KEY_STYLE,
                                TAN_STYLE,
                                SEG_STYLE,
                            )
                            self.mgr.build(zstack)
                    cf.set_zoom_changed_fn(lambda z: self.mgr.set_zoom(z))
                with ui.HStack(height=ui.Pixel(30)):
                    ui.Spacer()
                    ui.Button("Exit", width=80, clicked_fn=lambda: setattr(self, "_exit", True))
                    ui.Spacer()

        await omni.kit.app.get_app().next_update_async()
        while not self._exit:
            await asyncio.sleep(0.1)

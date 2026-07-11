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

import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.usd
from carb.input import KeyboardEventType, KeyboardInput
from omni import ui
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.fcurve.widget import FCurve, FCurveKey
from omni.flux.property_widget_builder.model.usd.field_builders.curve import _open_curve_editor
from pxr import Sdf, UsdGeom


class TestCurveEditorPopupLifecycle(omni.kit.test.AsyncTestCase):
    """E2E coverage for the curve editor popup window lifecycle."""

    _CURVE_ID = "escape_test"
    _PRIM_PATH = "/World/CurveEditorPopupLifecycle"

    async def setUp(self):
        """Create a stage with one curve."""
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()
        UsdGeom.Xform.Define(self._stage, self._PRIM_PATH)
        self._seed_curve()

    async def tearDown(self):
        """Destroy test windows and close the stage."""
        popup_window = ui.Workspace.get_window(self._popup_title)
        if popup_window:
            popup_window.destroy()
        if self._context:
            await self._context.close_stage_async()
        self._context = None
        self._stage = None

    @property
    def _popup_title(self) -> str:
        """Return the curve editor popup title."""
        return f"CurveEditor_{self._CURVE_ID}"

    def _seed_curve(self) -> None:
        """Write one valid curve to the test prim."""
        curve = FCurve(
            id=self._CURVE_ID,
            keys=[
                FCurveKey(time=0.0, value=0.0),
                FCurveKey(time=1.0, value=1.0),
            ],
        )
        prim = self._stage.GetPrimAtPath(self._PRIM_PATH)
        for suffix, value in curve_to_payload(curve).items():
            if suffix in {
                "times",
                "values",
                "inTangentTimes",
                "inTangentValues",
                "outTangentTimes",
                "outTangentValues",
            }:
                value_type = Sdf.ValueTypeNames.DoubleArray
            elif suffix in {"inTangentTypes", "outTangentTypes"}:
                value_type = Sdf.ValueTypeNames.TokenArray
            elif suffix == "tangentBrokens":
                value_type = Sdf.ValueTypeNames.BoolArray
            else:
                value_type = Sdf.ValueTypeNames.Token
            prim.CreateAttribute(f"primvars:{self._CURVE_ID}:{suffix}", value_type).Set(value)

    async def test_close_curve_editor_with_escape_defers_popup_cleanup_until_next_update(self):
        """Closing the curve editor with Escape hides it before destroying it on the next update."""
        _open_curve_editor([self._PRIM_PATH], [self._CURVE_ID], "")
        await ui_test.human_delay()

        popup_window = ui.Workspace.get_window(self._popup_title)
        self.assertIsNotNone(popup_window)
        self.assertTrue(popup_window.visible)
        popup_window.focus()

        await ui_test.input.emulate_keyboard(KeyboardEventType.KEY_PRESS, KeyboardInput.ESCAPE)
        try:
            await ui_test.wait_n_updates(1)

            popup_window = ui.Workspace.get_window(self._popup_title)
            self.assertIsNotNone(popup_window)
            self.assertFalse(popup_window.visible)
        finally:
            await ui_test.input.emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.ESCAPE)
        await ui_test.wait_n_updates(4)

        self.assertIsNone(ui.Workspace.get_window(self._popup_title))

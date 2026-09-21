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

import omni.ui as ui
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.usd import get_context
from pxr import UsdGeom

from ... import SetupUI

__all__ = ["TestCameraPropertiesSetupUI"]

_CAMERA_PATH = "/Camera"
_CONTEXT_NAME = ""


class TestCameraPropertiesSetupUI(AsyncTestCase):
    """Test the camera properties UI workflow."""

    async def setUp(self):
        """Create a camera on a fresh stage."""
        self._context = get_context(_CONTEXT_NAME)
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()
        UsdGeom.Camera.Define(self._stage, _CAMERA_PATH)

    async def tearDown(self):
        """Close the stage after each test."""
        await self._context.close_stage_async()

    async def test_clipping_range_tooltips_identify_near_and_far_planes(self):
        """Clipping-range controls should identify their near and far planes."""
        window = ui.Window("TestCameraProperties", width=600, height=800)
        try:
            with window.frame:
                setup_ui = SetupUI(_CONTEXT_NAME)
            try:
                # A user selects a camera and waits for its properties to appear.
                setup_ui.refresh(_CAMERA_PATH)
                await ui_test.human_delay()

                # Hover the rendered clipping-range fields so their dynamic tooltips are populated.
                tooltips = set()
                fields = ui_test.find_all(
                    f"{window.title}//Frame/**/FloatBoundedDrag[*].identifier=='/Camera.clippingRange,/Camera.clippingRange'"
                )
                self.assertEqual(len(fields), 2)
                for field in fields:
                    await ui_test.emulate_mouse_move(field.center)
                    await ui_test.human_delay()
                    tooltips.add(field.widget.tooltip)

                self.assertIn("Clipping Range Near: 1.0", tooltips)
                self.assertIn("Clipping Range Far: 1000000.0", tooltips)
            finally:
                setup_ui.destroy()
        finally:
            window.destroy()

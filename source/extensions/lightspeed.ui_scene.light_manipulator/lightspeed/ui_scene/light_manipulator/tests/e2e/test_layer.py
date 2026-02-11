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

import omni.kit.test
import omni.usd
from lightspeed.ui_scene.light_manipulator.layer import LightManipulatorLayer
from omni.kit.widget.viewport.api import ViewportAPI
from omni.ui.tests.test_base import OmniUiTest
from pxr import Usd


class TestLightLayer(OmniUiTest):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage: Usd.Stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_layer_create_manipulators(self):
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})

        # create a few lights
        lights = ["DiskLight", "RectLight", "RectLight"]
        for i, light_type in enumerate(lights):
            light = self.stage.DefinePrim(f"/TestLight{i}")
            light.SetTypeName(light_type)

        # simulate a hierarchy change
        class MockEvent:
            type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

        # trigger change
        layer._on_stage_event(MockEvent())

        # make sure a manipulator object was created for each light in the stage
        self.assertEqual(len(layer.manipulators), len(lights))

        # make sure we can destroy layer properly
        layer.destroy()

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

from pathlib import Path
from unittest.mock import MagicMock

import carb
import omni.kit
import omni.kit.app
import omni.kit.test
import omni.usd
from lightspeed.ui_scene.light_manipulator import get_manipulator_class
from omni.kit.test_suite.helpers import wait_stage_loading
from omni.ui import scene as sc
from omni.ui.tests.test_base import OmniUiTest
from pxr import UsdGeom, UsdLux

CURRENT_PATH = Path(carb.tokens.get_tokens_interface().resolve("${lightspeed.ui_scene.light_manipulator}/data"))
TEST_DATA_DIR = CURRENT_PATH.absolute().resolve().joinpath("tests")
OUTPUTS_DIR = Path(omni.kit.test.get_test_output_path())


class TestLightManipulator(OmniUiTest):
    """Test to make sure manipulators draw properly"""

    # Before running each test
    async def setUp(self):
        await super().setUp()
        await omni.usd.get_context().new_stage_async()

    # After running each test
    async def tearDown(self):
        await super().tearDown()
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    def create_and_select_test_light(self, light_prim_type: str):
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()

        omni.kit.commands.execute(
            "CreatePrim",
            prim_path="/TestLight",
            prim_type=light_prim_type,
            select_new_prim=True,
            attributes={},
        )

        return stage.GetPrimAtPath("/TestLight")

    async def draw_manipulator_and_compare(self, window, light_prim):
        usd_context = omni.usd.get_context()
        viewport_layers = MagicMock()

        with window.frame:
            # Camera matrices
            projection = [1e-1, 0, 0, 0]
            projection += [0, 1e-1, 0, 0]
            projection += [0, 0, -2e-6, 0]
            projection += [0, 0, 1, 1]
            view = sc.Matrix44.get_translation_matrix(0, 0, 0)
            scene_view = sc.SceneView(sc.CameraModel(projection, view))

            manipulator_class = get_manipulator_class(light_prim)
            # Add the manipulator into the SceneView's scene
            with scene_view.scene:
                manipulator_class(
                    viewport_layers, model=manipulator_class.model_class(light_prim, usd_context.get_name())
                )

        for _ in range(10):
            await omni.kit.app.get_app().next_update_async()

        await self.wait_n_updates(10)

        carb.log_info(f"Comparing golden with test image in dir: {OUTPUTS_DIR}")
        await self.finalize_test(golden_img_dir=TEST_DATA_DIR)

    async def test_disklight_manipulator(self):
        window = await self.create_test_window(width=256, height=256)

        prim = self.create_and_select_test_light("DiskLight")
        light = UsdLux.DiskLight(prim)
        light.GetRadiusAttr().Set(5)
        light.GetIntensityAttr().Set(500)
        # rotate the light to have a better angle
        light_x = UsdGeom.Xformable(light)
        light_x.AddRotateXOp().Set(30)
        light_x.AddRotateYOp().Set(45)

        await self.draw_manipulator_and_compare(window, prim)

    async def test_distantlight_manipulator(self):
        window = await self.create_test_window(width=256, height=256)

        prim = self.create_and_select_test_light("DistantLight")
        light = UsdLux.DistantLight(prim)
        light.GetIntensityAttr().Set(25)
        # rotate the light to have a better angle
        light_x = UsdGeom.Xformable(light)
        light_x.AddRotateXOp().Set(30)
        light_x.AddRotateYOp().Set(20)

        await self.draw_manipulator_and_compare(window, prim)

    async def test_rectlight_manipulator(self):
        window = await self.create_test_window(width=256, height=256)

        prim = self.create_and_select_test_light("RectLight")
        light = UsdLux.RectLight(prim)
        light.GetHeightAttr().Set(10)
        light.GetWidthAttr().Set(10)
        light.GetIntensityAttr().Set(400)
        # rotate the light to have a better angle
        light_x = UsdGeom.Xformable(light)
        light_x.AddRotateXOp().Set(30)
        light_x.AddRotateYOp().Set(45)

        await self.draw_manipulator_and_compare(window, prim)

    async def test_spherelight_manipulator(self):
        window = await self.create_test_window(width=256, height=256)

        prim = self.create_and_select_test_light("SphereLight")
        light = UsdLux.SphereLight(prim)
        light.GetRadiusAttr().Set(5)
        light.GetIntensityAttr().Set(100)
        # rotate the light to have a better angle
        light_x = UsdGeom.Xformable(light)
        light_x.AddRotateXOp().Set(30)
        light_x.AddRotateYOp().Set(45)

        await self.draw_manipulator_and_compare(window, prim)

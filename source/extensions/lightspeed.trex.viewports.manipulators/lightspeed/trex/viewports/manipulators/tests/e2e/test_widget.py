# noqa PLC0302
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
import unittest

import omni.ui as ui
import omni.usd
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from omni.kit.ui_test import Vec2
from pxr import Gf

WINDOW_HEIGHT = 1000
WINDOW_WIDTH = 1436

_CONTEXT_NAME = ""


class TestViewportManipulators(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        usd_context_1 = omni.usd.get_context(_CONTEXT_NAME)
        await open_stage(_get_test_data("usd/project_example/combined.usda"), usd_context=usd_context_1)

    # After running each test
    async def tearDown(self):
        await self.release_hydra_engines_workaround()
        omni.usd.get_context(_CONTEXT_NAME).close_stage()

    async def release_hydra_engines_workaround(self, usd_context_name: str = ""):
        # copied from omni/kit/widget/viewport/tests/test_ray_query.py
        await ui_test.human_delay(human_delay_speed=10)
        omni.usd.release_all_hydra_engines(omni.usd.get_context(usd_context_name))
        await ui_test.human_delay(human_delay_speed=10)

    async def __setup_widget(self, width=WINDOW_WIDTH, height=WINDOW_HEIGHT):
        window = ui.Window("TestViewportManipulator", width=width, height=height)
        with window.frame:
            with omni.ui.HStack():
                widget1 = _create_viewport_instance(_CONTEXT_NAME)

        await ui_test.human_delay(human_delay_speed=1)
        widget1.set_active(True)
        await ui_test.human_delay(human_delay_speed=10)

        return window, widget1

    async def __destroy(self, window, widget):
        widget.destroy()
        window.destroy()

    @unittest.skip("Skipping temporarily, viewport selection is broken in this test")
    async def test_manipulator_set_value_good_prim(self):
        """Test that when we use the manipulator, this is update the good prim"""
        # setup
        _window, _widget = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        # select the object
        dpi_scale = ui.Workspace.get_dpi_scale()
        click_object = Vec2(WINDOW_WIDTH - 170, WINDOW_HEIGHT - 200) / 2 / dpi_scale
        await ui_test.input.emulate_mouse_move(click_object)
        await ui_test.human_delay(human_delay_speed=15)
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay(human_delay_speed=100)  # flakey on ci, needs 3 frames locally

        # check that the selection is ok
        current_selection = usd_context.get_selection().get_selected_prim_paths()
        self.assertEqual(
            current_selection,
            ["/RootNode/instances/inst_BAC90CAA733B0859_1/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube_01"],
        )

        # grab the translate value
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath(
            "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube_01"
        )
        xf_tr = prim.GetAttribute("xformOp:translate")
        translate = xf_tr.Get()
        self.assertEqual(translate, Gf.Vec3d(0.0, 50.0, 0.0))

        # move the mouse over the manipulator and move the object
        manipulator_z = Vec2(WINDOW_WIDTH - 300, WINDOW_HEIGHT - 210) / 2 / dpi_scale
        await ui_test.input.emulate_mouse_move(manipulator_z)
        await ui_test.human_delay(human_delay_speed=5)
        await ui_test.emulate_mouse_drag_and_drop(manipulator_z, manipulator_z - Vec2(100, 0))
        await ui_test.human_delay(human_delay_speed=5)

        # check the value changed
        translate = xf_tr.Get()
        self.assertEqual(int(translate[0]), 299)

        # check that the override was applied on the mesh and not the instance
        root_layer = stage.GetRootLayer()
        self.assertIsNotNone(
            root_layer.GetPropertyAtPath(
                "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube_01.xformOp:translate"
            )
        )
        self.assertIsNone(
            root_layer.GetPropertyAtPath(
                "/RootNode/instances/inst_BAC90CAA733B0859_1/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube_01.xformOp:translate"  # noqa
            )
        )

        await self.__destroy(_window, _widget)

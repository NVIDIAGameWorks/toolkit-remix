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

import carb.input
import omni.kit.clipboard
import omni.kit.undo
import omni.ui as ui
import omni.usd
from omni.flux.properties_pane.properties.usd.widget import PropertyWidget as _PropertyWidget
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path, open_stage, wait_stage_loading
from pxr import Gf

WINDOW_HEIGHT = 1000
WINDOW_WIDTH = 1436

_CONTEXT_NAME = ""


class TestUSDPropertiesWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await open_stage(get_test_data_path(__name__, "usd/cubes.usda"))

    # After running each test
    async def tearDown(self):
        # Note: this func seems to be context independent (same val for both contexts)
        await wait_stage_loading()

    async def __setup_widget(self, width=WINDOW_WIDTH, height=WINDOW_HEIGHT) -> (ui.Window, "_PropertyWidget"):
        window = ui.Window("TestPropertyWidget", width=width, height=height)
        with window.frame:
            with omni.ui.HStack():
                widget1 = _PropertyWidget(_CONTEXT_NAME)

        await ui_test.human_delay(human_delay_speed=1)

        return window, widget1

    async def __destroy(self, window, widget):
        # if we destroy viewports before the stage is fully loaded than it will be stuck in loading state.
        await wait_stage_loading()

        widget.destroy()
        window.destroy()

    async def test_setting_a_value_by_script_update_ui(self):
        """
        Test that if we set a value not from the UI (for example here, directly in USD), check that the UI is updated
        """
        # setup
        _window, _widget = await self.__setup_widget()  # Keep in memory during test
        _widget.refresh(["/Xform/Cube"])

        # find the translate field UI
        property_branches = ui_test.find_all(
            f"{_window.title}//Frame/**/FloatField[*].identifier=='/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate'"  # noqa
        )
        self.assertEqual(len(property_branches), 3)

        # Set the value of the cube
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        xf_tr = prim.GetAttribute("xformOp:translate")
        xf_tr.Set(Gf.Vec3d(123456789.0, 0.0, 0.0))

        # we check that the value of the UI element changed
        self.assertEqual(property_branches[0].widget.model.get_value_as_int(), 123456789.0)

        await self.__destroy(_window, _widget)

    async def test_multi_prim_bool_widget(self):
        """
        Test that a property can be edited on multiple prims and that it will be accurately represented.
        """
        # setup
        _window, _widget = await self.__setup_widget()  # Keep in memory during test
        _widget.refresh(["/Xform/Cube", "/Xform/Cube2"])
        await omni.kit.ui_test.wait_n_updates(15)

        double_sided_widget = ui_test.find(
            f"{_window.title}//Frame/**/CheckBox[*].identifier=='/Xform/Cube.doubleSided,/Xform/Cube2.doubleSided'"  # noqa
        )
        # one cube is double sided and the other is not, so this should be mixed
        self.assertEqual(double_sided_widget.widget.model.is_mixed, True)
        self.assertEqual(double_sided_widget.widget.model.get_value(), True)
        self.assertEqual(double_sided_widget.widget.model.get_value_as_bool(), True)

        # Act: toggle bool widget
        self.assertEqual(double_sided_widget.widget.checked, True)  # returns False!
        await omni.kit.ui_test.emulate_mouse_move(double_sided_widget.position + omni.kit.ui_test.Vec2(3, 3))
        await omni.kit.ui_test.emulate_mouse_click()
        self.assertEqual(double_sided_widget.widget.checked, False)

        # we check that the value of the UI element changed
        self.assertEqual(double_sided_widget.widget.model.get_value(), False)
        self.assertEqual(double_sided_widget.widget.model.get_value_as_bool(), False)
        self.assertEqual(double_sided_widget.widget.model.is_mixed, False)
        # and that both cubes now have the correct value
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        for prim_path in ("/Xform/Cube", "/Xform/Cube2"):
            prim = stage.GetPrimAtPath(prim_path)
            xf_tr = prim.GetAttribute("doubleSided")
            self.assertEqual(xf_tr.Get(), False)

        await self.__destroy(_window, _widget)

    async def test_multi_prim_xform_widget(self):
        """
        Test that a property can be edited on multiple prims and that it will be accurately represented.
        """
        # setup
        _window, _widget = await self.__setup_widget()  # Keep in memory during test
        _widget.refresh(["/Xform/Cube", "/Xform/Cube2"])
        await omni.kit.ui_test.wait_n_updates(15)

        # find the translate field UI
        property_branches = ui_test.find_all(
            f"{_window.title}//Frame/**/FloatField[*].identifier=='/Xform/Cube.xformOp:translate,"
            f"/Xform/Cube2.xformOp:translate,/Xform/Cube.xformOp:translate,/Xform/Cube2.xformOp:translate,"
            f"/Xform/Cube.xformOp:translate,/Xform/Cube2.xformOp:translate'"  # noqa
        )
        self.assertEqual(len(property_branches), 3)
        translate_x_widget = property_branches[0]
        self.assertEqual(translate_x_widget.widget.model.is_mixed, True)
        # Act: click on field, set a value and then click off of it
        await translate_x_widget.double_click()
        await omni.kit.ui_test.emulate_char_press("2.2")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)

        # we check that the value of the UI element changed
        self.assertEqual(property_branches[0].widget.model.get_value_as_float(), 2.2)
        self.assertEqual(translate_x_widget.widget.model.is_mixed, False)
        # and that both cubes now have the correct value
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        for prim_path in ("/Xform/Cube", "/Xform/Cube2"):
            prim = stage.GetPrimAtPath(prim_path)
            xf_tr = prim.GetAttribute("xformOp:translate")
            self.assertEqual(xf_tr.Get(), Gf.Vec3d(2.2, 0.0, 0.0))

        await self.__destroy(_window, _widget)

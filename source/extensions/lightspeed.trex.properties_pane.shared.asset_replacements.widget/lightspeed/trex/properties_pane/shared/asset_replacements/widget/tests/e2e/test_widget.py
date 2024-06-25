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

import omni.ui as ui
import omni.usd
from lightspeed.trex.properties_pane.shared.asset_replacements.widget import (
    AssetReplacementsPane as _AssetReplacementsPane,
)
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading


class TestAssetReplacementsWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await arrange_windows()
        await open_stage(_get_test_data("usd/project_example/combined.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def __setup_widget(self, title: str):
        window = ui.Window(title, height=800, width=400)
        with window.frame:
            wid = _AssetReplacementsPane("")
            wid.show(True)

        await ui_test.human_delay(human_delay_speed=1)

        return window, wid

    async def __destroy(self, window, wid):
        wid.destroy()
        window.destroy()

    async def test_collapse_frames_here(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_frames_here")  # Keep in memory during test
        collapsable_frames = ui_test.find_all(
            f"{_window.title}//Frame/**/CollapsableFrame[*].identifier=='PropertyCollapsableFrame'"
        )
        self.assertEqual(len(collapsable_frames), 6)
        await self.__destroy(_window, _wid)

    async def test_collapse_refresh_object_property_when_collapsed(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_refresh_object_property_when_collapsed")

        collapsable_frame_arrows = ui_test.find_all(
            f"{_window.title}//Frame/**/Image[*].identifier=='PropertyCollapsableFrameArrow'"
        )
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")

        self.assertEqual(len(collapsable_frame_arrows), 6)
        self.assertIsNotNone(frame_mesh_ref)
        self.assertIsNotNone(frame_mesh_prim)

        # by default, no frame are visible
        self.assertFalse(frame_mesh_prim.widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)

        # we close the object property frame
        await collapsable_frame_arrows[4].click()

        # we select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)

        # we re-open the object property frame
        await collapsable_frame_arrows[4].click()

        # no we should see the mesh property
        self.assertTrue(frame_mesh_prim.widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)

        # we close the object property frame
        await collapsable_frame_arrows[4].click()

        # we select the mesh ref
        await item_prims[0].click()

        # we re-open the object property frame
        await collapsable_frame_arrows[4].click()

        # no we should see the ref property
        self.assertFalse(frame_mesh_prim.widget.visible)
        self.assertTrue(frame_mesh_ref.widget.visible)
        await self.__destroy(_window, _wid)

    async def test_collapse_refresh_material_property_when_collapsed(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_refresh_material_property_when_collapsed")

        collapsable_frame_arrows = ui_test.find_all(
            f"{_window.title}//Frame/**/Image[*].identifier=='PropertyCollapsableFrameArrow'"
        )
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")

        self.assertEqual(len(collapsable_frame_arrows), 6)
        self.assertIsNotNone(frame_material)

        # by default, no frame are visible
        self.assertFalse(frame_material.widget.visible)

        # we close the material property frame
        await collapsable_frame_arrows[5].click()

        # we select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)

        # we re-open the material property frame
        await collapsable_frame_arrows[5].click()

        # no we should see the material property
        self.assertTrue(frame_material.widget.visible)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)

        # we close the material property frame
        await collapsable_frame_arrows[5].click()

        # we select the mesh ref
        await item_prims[0].click()

        # we re-open the material property frame
        # because the size of the frame change, we need to re-grab the widgets
        collapsable_frame_arrows = ui_test.find_all(
            f"{_window.title}//Frame/**/Image[*].identifier=='PropertyCollapsableFrameArrow'"
        )
        await collapsable_frame_arrows[5].click()

        # we still not see the material property
        self.assertFalse(frame_material.widget.visible)
        await self.__destroy(_window, _wid)

    async def test_object_properties_cleared_when_none_selected(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_refresh_material_property_when_collapsed")

        # ensure the proper frames exist
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")

        # ensure the none frames exist and the relevant one is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        self.assertEqual(len(none_frames), 3)
        self.assertTrue(none_frames[0].widget.visible)

        # select a mesh prim
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        await item_prims[0].click()

        # ensure the none frame is no longer visible
        self.assertFalse(none_frames[0].widget.visible)

        # ensure the mesh ref frame is visible
        self.assertTrue(frame_mesh_ref.widget.visible)

        # we un-select
        await item_prims[1].click()
        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the none frame is now visible and ref frame is not
        self.assertTrue(none_frames[0].widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)

        await self.__destroy(_window, _wid)

    async def test_material_properties_cleared_when_none_selected(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_refresh_material_property_when_collapsed")

        # ensure the proper frames exist
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # ensure the none frames exist and the relevant one is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        self.assertEqual(len(none_frames), 3)
        self.assertTrue(none_frames[1].widget.visible)

        # we select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the none frame is no longer visible
        self.assertFalse(none_frames[1].widget.visible)

        # the material properties should be visible
        self.assertTrue(frame_material.widget.visible)

        # we un-select
        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the none frame is visible and material property frame is not
        self.assertTrue(none_frames[1].widget.visible)
        self.assertFalse(frame_material.widget.visible)

        await self.__destroy(_window, _wid)

    async def test_object_pinning(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_refresh_object_property_when_collapsed")

        # ensure the mesh reference and prim frames exist
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        self.assertIsNotNone(frame_mesh_ref)
        self.assertIsNotNone(frame_mesh_prim)

        # select a mesh
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # select the mesh reference and ensure only the reference properties are visible
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        await item_prims[0].click()
        self.assertTrue(frame_mesh_ref.widget.visible)
        self.assertFalse(frame_mesh_prim.widget.visible)

        # click the pin icons to pin
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        self.assertEqual(len(pin_icon_images), 2)
        await pin_icon_images[0].click()
        await ui_test.human_delay()

        # change the selection to the mesh prim
        await item_prims[1].click()

        # ensure the property visibility hasn't changed
        self.assertTrue(frame_mesh_ref.widget.visible)
        self.assertFalse(frame_mesh_prim.widget.visible)

        # click the pin icons to un-pin
        await pin_icon_images[0].click()
        await ui_test.human_delay()

        # ensure that only the mesh prim widget is now visible
        self.assertFalse(frame_mesh_ref.widget.visible)
        self.assertTrue(frame_mesh_prim.widget.visible)
        await self.__destroy(_window, _wid)

    async def test_material_pinning(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_refresh_object_property_when_collapsed")

        # ensure the material frame exists
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # select a mesh and ensure the material properties are visible
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)
        self.assertTrue(frame_material.widget.visible)

        # click the pin icons to pin
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        self.assertEqual(len(pin_icon_images), 2)
        await pin_icon_images[1].click()
        await ui_test.human_delay()

        # change selection to the mesh reference
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        await item_prims[0].click()
        await ui_test.human_delay()

        # material properties should still be visible since pinned
        self.assertTrue(frame_material.widget.visible)

        # click the pin icons to un-pin
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        await pin_icon_images[1].click()
        await ui_test.human_delay()

        # material properties should no longer be visible since un-pinned
        self.assertFalse(frame_material.widget.visible)
        await self.__destroy(_window, _wid)

    async def test_object_and_material_pin_labels_exist(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_refresh_object_property_when_collapsed")

        # ensure the material frame exists
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # select a mesh and ensure the material properties are visible
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)
        self.assertTrue(frame_material.widget.visible)

        # click the pin icons to pin and reveal text
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        self.assertEqual(len(pin_icon_images), 2)
        for pin_icon_image in pin_icon_images:
            await pin_icon_image.click()
            await ui_test.human_delay()

        # ensure the pin label texts are not empty
        pin_label_texts = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        for pin_label_text in pin_label_texts:
            self.assertNotEqual(pin_label_text, "")

        await self.__destroy(_window, _wid)

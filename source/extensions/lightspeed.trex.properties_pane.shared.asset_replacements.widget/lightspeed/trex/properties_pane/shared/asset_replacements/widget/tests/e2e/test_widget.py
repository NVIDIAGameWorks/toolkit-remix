"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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

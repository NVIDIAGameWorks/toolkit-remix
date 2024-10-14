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

import asyncio
from unittest import skip

import omni.kit.app
import omni.kit.commands
import omni.usd
from lightspeed.event.waypoint_creation.core import WaypointCreationCore as _WaypointCreationCore
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, wait_stage_loading
from pxr import Sdf, Usd


class TestCore(AsyncTestCase):

    _GAME_CAM_WAYPOINT_PATH = (
        f"{_WaypointCreationCore.WAYPOINT_ROOT_PRIM_PATH}/{_WaypointCreationCore.WAYPOINT_GAME_CAM_NAME}"
    )

    # Before running each test
    async def setUp(self):
        await arrange_windows()
        self.viewport = _create_viewport_instance(Contexts.STAGE_CRAFT.value)  # viewport needed for waypoint camera

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

        # NOTE: Viewport cannot be destroyed because waypoint extensions reference the viewport
        #   - The waypoint extensions rely on a reference to the viewport
        # self.viewport.destroy()
        # self.viewport = None

    async def _check_waypoint_is_created(self, stage: Usd.Stage, waypoint_path: str):
        # Need to wait few frame to get the waypoint
        timeout = 100
        for i in range(timeout):
            await omni.kit.app.get_app().next_update_async()
            waypoint_prim = stage.GetPrimAtPath(waypoint_path)
            valid = waypoint_prim.IsValid()
            if valid:
                return waypoint_prim
            if i == timeout - 1 and not valid:
                self.assertTrue(valid)
        return None

    async def test_open_stage_should_create_game_waypoint(self):
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            # Set the context
            _trex_contexts_instance().set_current_context(Contexts.STAGE_CRAFT)
            context = omni.usd.get_context()

            # Wait for the initial GameCam waypoint creation and save the stage
            await wait_stage_loading()
            for _ in range(10):
                await omni.kit.app.get_app().next_update_async()
            stage = context.get_stage()
            stage.Save()

            # Ensure that the GameCam waypoint was created
            waypoint_prim = stage.GetPrimAtPath(TestCore._GAME_CAM_WAYPOINT_PATH)
            self.assertTrue(waypoint_prim.IsValid())
            current_waypoint_prim = await self._check_waypoint_is_created(stage, TestCore._GAME_CAM_WAYPOINT_PATH)

            # Save some waypoint and camera to later ensure waypoint and camera changes
            created_time = current_waypoint_prim.GetAttribute("created").Get()
            camera_prim = stage.GetPrimAtPath("/RootNode/Camera")
            initial_waypoint_xf_translate = camera_prim.GetProperty("xformOp:translate")

            # Wait 2 seconds so that the capture switch changes the waypoint data
            await asyncio.sleep(2)

            # Open a different capture, wait for the waypoint to change, and then save
            capture_core_setup = _CaptureCoreSetup(Contexts.STAGE_CRAFT.value)
            capture_core_setup.import_capture_layer(f"{project_url.parent_url}/deps/captures/capture2.usda")

            # Wait for the stage to load and for the waypoint to update and save
            await wait_stage_loading()
            for _ in range(10):
                await omni.kit.app.get_app().next_update_async()
            stage.Save()

            # Ensure the waypoint is still valid
            waypoint_prim = stage.GetPrimAtPath(TestCore._GAME_CAM_WAYPOINT_PATH)
            self.assertTrue(waypoint_prim.IsValid())
            current_waypoint_prim = await self._check_waypoint_is_created(stage, TestCore._GAME_CAM_WAYPOINT_PATH)

            # Ensure that the waypoint time data has changed
            created_time_updated = current_waypoint_prim.GetAttribute("created").Get()
            self.assertNotEquals(created_time, created_time_updated)

            # Ensure that the camera translation has changed
            camera_prim = stage.GetPrimAtPath("/RootNode/Camera")
            capture_waypoint_xf_translate = camera_prim.GetProperty("xformOp:translate")
            self.assertNotEquals(initial_waypoint_xf_translate, capture_waypoint_xf_translate)

    @skip("Waypoint migration does not occur, probably due to discrepancies between E2E test startup vs app startup")
    async def test_open_stage_should_migrate_mod_layer_waypoints(self):

        # TODO: Fix this test
        #   - In this test environment, the game cam waypoint creator considers "Viewport_Waypoints" to be an override
        #       instead of a prim definition on the project layer. This occurs because the mod layer contains a
        #       "Viewport_Waypoints" prim definition containing the waypoints that should be migrated beforehand.
        #   - The above migration issue does not occur within Remix app startup and both waypoint migration and game cam
        #       creation occur gracefully.
        #   - This may be a timing issue where this test environment loads differently than how projects load in Remix.

        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            # Set the context
            _trex_contexts_instance().set_current_context(Contexts.STAGE_CRAFT)
            context = omni.usd.get_context()

            # Wait for the auto waypoint migration
            await wait_stage_loading()
            for _ in range(10):
                await omni.kit.app.get_app().next_update_async()

            # Before saving, check that the waypoints are on not yet on the project layer
            stage = context.get_stage()
            expected_waypoints = ["WaypointThatShouldBeMigrated", "OtherWaypointThatShouldBeMigrated"]

            project_layer = Sdf.Layer.FindOrOpen(project_url.path)
            for waypoint in expected_waypoints:
                expected_waypoint_path = f"{_WaypointCreationCore.WAYPOINT_ROOT_PRIM_PATH}/{waypoint}"
                self.assertFalse(bool(project_layer.GetPrimAtPath(Sdf.Path(expected_waypoint_path))))

            # Save the stage, and check that the waypoints are now on the project layer
            stage.Save()
            await wait_stage_loading()
            for _ in range(10):
                await omni.kit.app.get_app().next_update_async()

            for waypoint in expected_waypoints:
                expected_waypoint_path = f"{_WaypointCreationCore.WAYPOINT_ROOT_PRIM_PATH}/{waypoint}"
                self.assertTrue(bool(project_layer.GetPrimAtPath(Sdf.Path(expected_waypoint_path))))

    @skip("Waypoint migration does not occur, probably due to discrepancies between E2E test startup vs app startup")
    async def test_open_stage_should_migrate_overlapping_mod_layer_waypoints(self):
        # TODO: After fixing the above test, create a test case where waypoints exist on both project and mod layer
        #   - It would also be good to test overlapping prims (mod layer waypoints should overwrite the project layers)
        #   - This will require adding to or adding new USDA files
        pass

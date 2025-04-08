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
import contextlib
import shutil
import tempfile

import omni.kit.app
import omni.kit.commands
import omni.usd
from lightspeed.event.waypoint_game_camera.core import WaypointGameCameraCore as _WaypointGameCameraCore
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading
from pxr import Gf, Usd

_CONTEXT_NAME = ""


@contextlib.asynccontextmanager
async def make_temp_directory(context):
    temp_dir = tempfile.TemporaryDirectory()  # noqa PLR1732
    viewport = _create_viewport_instance(
        _CONTEXT_NAME
    )  # create the viewport object because the viewport generate the persp camera
    try:
        yield temp_dir
    finally:
        await wait_stage_loading()
        await context.new_stage_async()
        await wait_stage_loading()
        await omni.kit.app.get_app().next_update_async()
        if context.can_close_stage():
            await context.close_stage_async()
        temp_dir.cleanup()
        viewport.destroy()


class TestCore(AsyncTestCase):

    _WAYPOINT_PATH = f"/Viewport_Waypoints/{_WaypointGameCameraCore.WAYPOINT_NAME}"

    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        # If the wait is not disabled, `test_open_stage_with_camera_in_metadata` freezes here when executed after
        # another test in the suite.
        # await wait_stage_loading()
        pass

    async def _check_waypoint_is_created(self, stage):
        # need to wait few frame to get the waypoint
        timeout = 100
        for i in range(timeout):
            await omni.kit.app.get_app().next_update_async()
            waypoint_prim = stage.GetPrimAtPath(TestCore._WAYPOINT_PATH)
            valid = waypoint_prim.IsValid()
            if valid:
                # good
                return waypoint_prim
            # timeout
            if i == timeout - 1 and not valid:
                self.assertTrue(valid)
        return None

    async def test_open_stage_should_create_game_waypoint(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            second_capture = f"{temp_dir.name}/project_example/deps/captures/capture2.usda"

            # create another capture
            shutil.copy(_get_test_data("usd/project_example/deps/captures/capture.usda"), second_capture)
            stage = Usd.Stage.Open(second_capture)

            # change the value of the camera of the second capture
            camera_path = "/RootNode/Camera"
            camera_prim = stage.GetPrimAtPath(camera_path)
            xf_tr = camera_prim.GetProperty("xformOp:translate")
            xf_tr.Set(Gf.Vec3d(20.0, 20.0, 20.0))
            stage.Save()

            path = f"{temp_dir.name}/project_example/combined.usda"
            await open_stage(path)
            # Let the event trigger
            await wait_stage_loading()
            for _ in range(10):
                await omni.kit.app.get_app().next_update_async()

            stage = context.get_stage()
            waypoint_prim = stage.GetPrimAtPath(TestCore._WAYPOINT_PATH)

            self.assertTrue(waypoint_prim.IsValid())

            current_waypoint_prim = await self._check_waypoint_is_created(stage)
            created_time = current_waypoint_prim.GetAttribute("created").Get()

            # switch to another capture
            # wait 2sc to switch to the capture to change the waypoint created time
            await asyncio.sleep(2)
            capture_core_setup = _CaptureCoreSetup(_CONTEXT_NAME)
            capture_core_setup.import_capture_layer(second_capture)
            # Let the event trigger
            await wait_stage_loading()
            await omni.kit.app.get_app().next_update_async()

            # we should have a new waypoint
            current_waypoint_prim2 = await self._check_waypoint_is_created(stage)
            created_time2 = current_waypoint_prim2.GetAttribute("created").Get()
            self.assertNotEqual(created_time, created_time2)

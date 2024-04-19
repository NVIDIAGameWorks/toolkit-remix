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
import contextlib
import shutil
import tempfile
from typing import Optional, Tuple
from unittest.mock import MagicMock, patch

import omni.kit.app
import omni.kit.commands
import omni.usd
from lightspeed.event.capture_persp_to_persp.core import CopyCapturePerspToPerspCore as _CopyCapturePerspToPerspCore
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading

# from omni.kit.test_suite.helpers wait_stage_loading
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


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):  # noqa PLW0236
        return super().__call__(*args, **kwargs)


class TestCore(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        # If the wait is not disabled, `test_open_stage_with_camera_in_metadata` freezes here when executed after
        # another test in the suite.
        # await wait_stage_loading()
        pass

    def __get_camera_translate_from_stage(self, context) -> Optional[Tuple[float, float, float]]:
        stage = context.get_stage()
        camera_path = "/OmniverseKit_Persp"
        camera_prim = stage.GetPrimAtPath(camera_path)
        if not camera_prim.IsValid():
            return None
        xf_tr = camera_prim.GetProperty("xformOp:translate")
        return tuple(xf_tr.Get())

    def __set_camera_translate_from_stage(self, value: Tuple[float, float, float]):
        camera_path = "/OmniverseKit_Persp"
        omni.kit.commands.execute(
            "TransformPrimCommand",
            path=camera_path,
            new_transform_matrix=Gf.Matrix4d().SetTranslate(Gf.Vec3d(value[0], value[1], value[2])),
            usd_context_name=_CONTEXT_NAME,
        )

    def __get_camera_translate_from_stage_custom_data(self, context) -> Optional[Tuple[float]]:
        root_layer = context.get_stage().GetRootLayer()
        return root_layer.customLayerData.get("cameraSettings").get("Perspective").get("position")

    async def test_open_stage_with_camera_in_metadata(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            await open_stage(f"{temp_dir.name}/project_example/combined.usda")

            # flaky test. Wait 100 frames to test
            i = 0
            while True:
                # Check the camera value. Should be the same as metadata
                translate_values = self.__get_camera_translate_from_stage(context)

                metadata_value = self.__get_camera_translate_from_stage_custom_data(context)
                if translate_values == metadata_value:
                    break
                await omni.kit.app.get_app().next_update_async()
                i += 1
                if i == 100:
                    raise ValueError("Camera is in the wrong position")
            # now wait 100 frames and test again that the camera didn't move
            translate_values = self.__get_camera_translate_from_stage(context)
            metadata_value = self.__get_camera_translate_from_stage_custom_data(context)
            for _ in range(100):
                await omni.kit.app.get_app().next_update_async()
            self.assertEqual(translate_values, metadata_value)  # if we are here, it should fail

    async def test_open_stage_with_no_camera_in_metadata(self):

        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            path = f"{temp_dir.name}/project_example/combined.usda"
            stage = Usd.Stage.Open(path)
            value = stage.GetRootLayer().customLayerData
            del value["cameraSettings"]
            stage.GetRootLayer().customLayerData = value
            stage.Save()
            stage = None

            await open_stage(path)
            # Check the camera value. Should be different than default camera value (500.0)
            translate_values = self.__get_camera_translate_from_stage(context)
            self.assertNotEqual(translate_values, (500.0, 500.0, 500.0))

    async def test_open_stage_with_no_camera_in_metadata_disable(self):

        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            path = f"{temp_dir.name}/project_example/combined.usda"
            stage = Usd.Stage.Open(path)
            value = stage.GetRootLayer().customLayerData
            del value["cameraSettings"]
            stage.GetRootLayer().customLayerData = value
            stage.Save()
            stage = None

            # mock the function to disable the execution. Camera value should be the default
            with patch.object(
                _CopyCapturePerspToPerspCore,
                "_deferred_setup_perspective_camera",
                new_callable=AsyncMock,
            ):
                await open_stage(path)
                # Check the camera value. Should be different than default camera value (500.0)
                translate_values = self.__get_camera_translate_from_stage(context)
                self.assertEqual(translate_values, (500.0, 500.0, 500.0))

    async def test_open_stage_change_capture(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            # create a second capture
            new_capture = f"{temp_dir.name}/project_example/.deps/captures/capture2.usda"
            shutil.copy2(f"{temp_dir.name}/project_example/.deps/captures/capture.usda", new_capture)
            await open_stage(f"{temp_dir.name}/project_example/combined.usda")

            layer_manager = _LayerManagerCore(_CONTEXT_NAME)

            # remove the capture, camera should not change
            translate_values = self.__get_camera_translate_from_stage(context)
            layer_manager.remove_layer(_LayerType.capture)
            await omni.kit.app.get_app().next_update_async()
            translate_values1 = self.__get_camera_translate_from_stage(context)

            self.assertEqual(translate_values, translate_values1)

            # move the camera
            random_value = (10.0, 20.0, 30.0)
            self.__set_camera_translate_from_stage(random_value)
            await omni.kit.app.get_app().next_update_async()
            translate_values1 = self.__get_camera_translate_from_stage(context)
            self.assertEqual(random_value, translate_values1)

            # add a new capture
            capture_core_setup = _CaptureCoreSetup(_CONTEXT_NAME)
            capture_core_setup.import_capture_layer(new_capture)
            for _ in range(2):  # 1 frame for the layer, 1 for the camera event
                await omni.kit.app.get_app().next_update_async()

            # camera should be moved
            self.assertNotEqual(self.__get_camera_translate_from_stage(context), random_value)

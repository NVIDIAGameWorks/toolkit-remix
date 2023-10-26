"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import contextlib
import shutil
import tempfile

import omni.kit.app
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path, open_stage, wait_stage_loading


@contextlib.asynccontextmanager
async def make_temp_directory(context):
    temp_dir = tempfile.TemporaryDirectory()  # noqa PLR1732
    try:
        yield temp_dir
    finally:
        if context.can_close_stage():
            await context.close_stage_async()
        temp_dir.cleanup()


class TestCore(AsyncTestCase):
    async def setUp(self):
        pass

    async def tearDown(self):
        pass

    async def test_cleaup_layers_removed_invalid_capture_layer(self):
        # Arrange
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            temp_project = f"{temp_dir.name}/project"
            shutil.copytree(get_test_data_path(__name__, "usd/invalid_capture"), temp_project)

            # Act
            await open_stage(f"{temp_project}/project.usda")

            # Let the event trigger
            await wait_stage_loading()
            await omni.kit.app.get_app().next_update_async()

            # Assert
            sublayer_paths = list(context.get_stage().GetRootLayer().subLayerPaths)

            self.assertListEqual(sublayer_paths, ["./mod.usda"])

    async def test_cleaup_layers_didnt_modify_valid_project(self):
        # Arrange
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            temp_project = f"{temp_dir.name}/project"
            shutil.copytree(get_test_data_path(__name__, "usd/valid_capture"), temp_project)

            # Act
            await open_stage(f"{temp_project}/project.usda")

            # Let the event trigger
            await wait_stage_loading()
            await omni.kit.app.get_app().next_update_async()

            # Assert
            sublayer_paths = list(context.get_stage().GetRootLayer().subLayerPaths)

            self.assertListEqual(sublayer_paths, ["./mod.usda", "./capture.usda"])

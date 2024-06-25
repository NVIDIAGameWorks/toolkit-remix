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

import carb
import omni.kit.app
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage, wait_stage_loading

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

    async def __open_file(self, temp_dir):
        shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
        await open_stage(f"{temp_dir.name}/project_example/combined.usda")
        await wait_stage_loading()

        for _ in range(10):
            await omni.kit.app.get_app().next_update_async()

    async def test_set_camera_light(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            await self.__open_file(temp_dir)

            # Turn on camera light mode
            settings = carb.settings.get_settings()
            settings.set("/rtx/useViewLightingMode", True)

            log_file = settings.get("log/file")
            with open(log_file, "r", encoding="utf-8") as log:
                lines = log.readlines()

            # Check log file to make sure event was triggered
            check = False
            for line in reversed(lines):
                if "[Info] [lightspeed.event.camera_light.core] Camera light set..." in line:
                    check = True
                    break
            self.assertTrue(check)

    async def test_reset_camera_light(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            await self.__open_file(temp_dir)

            # Turn on camera light mode
            settings = carb.settings.get_settings()
            settings.set("/rtx/useViewLightingMode", False)

            log_file = settings.get("log/file")
            with open(log_file, "r", encoding="utf-8") as log:
                lines = log.readlines()

            # Check log file to make sure event was triggered
            check = False
            for line in reversed(lines):
                if "[Info] [lightspeed.event.camera_light.core] Camera light reset..." in line:
                    check = True
                    break
            self.assertTrue(check)

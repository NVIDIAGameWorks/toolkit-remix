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
import tempfile

import omni.kit.app
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.layer_types import LayerType as _LayerType
from omni.kit.test.async_unittest import AsyncTestCase
from pxr import Usd, UsdGeom


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
        self._layer_manager = _LayerManagerCore()

    async def tearDown(self):
        pass

    async def __create_stage_and_layers(self, temp_dir: tempfile.TemporaryDirectory = None):
        context = omni.usd.get_context()
        if temp_dir is not None:
            stage = Usd.Stage.CreateNew(f"{temp_dir.name}/test.usd")
        else:
            stage = Usd.Stage.CreateInMemory("test.usd")
        await context.attach_stage_async(stage)

        # create a fake replacement layer and add it
        if temp_dir is not None:
            stage_replacement = Usd.Stage.CreateNew(f"{temp_dir.name}/replacement.usd")
        else:
            stage_replacement = Usd.Stage.CreateInMemory("replacement.usd")
        layer_replacement = stage_replacement.GetRootLayer()
        self._layer_manager.set_custom_data_layer_type(layer_replacement, _LayerType.replacement)
        stage.GetRootLayer().subLayerPaths.insert(0, layer_replacement.identifier)

        # create a fake capture layer and add it
        if temp_dir is not None:
            stage_capture = Usd.Stage.CreateNew(f"{temp_dir.name}/capture.usd")
        else:
            stage_capture = Usd.Stage.CreateInMemory("capture.usd")
        layer_capture = stage_capture.GetRootLayer()
        self._layer_manager.set_custom_data_layer_type(layer_capture, _LayerType.capture)
        stage.GetRootLayer().subLayerPaths.insert(1, layer_capture.identifier)

        # return stage, layer_replacement
        return stage, layer_replacement, layer_capture

    async def __create_a_cube(self, stage, layer_replacement):
        # set the replacement layer as target
        edit_target = stage.GetEditTargetForLocalLayer(layer_replacement)
        stage.SetEditTarget(edit_target)
        # create a random cube and save
        UsdGeom.Cube.Define(stage, "/Cube")

    async def test_capture_baker_is_not_created_when_adding_layer(self):
        # create a fake replacement layer and add it
        stage, layer_replacement, _ = await self.__create_stage_and_layers()
        current_sublayers = list(stage.GetRootLayer().subLayerPaths)

        # wait for the event
        await omni.kit.app.get_app().next_update_async()

        # nothing should have changed. We dont have any capture baker layer created when we add new layer
        self.assertEqual(current_sublayers, stage.GetRootLayer().subLayerPaths)
        self.assertFalse(layer_replacement.subLayerPaths)

    async def test_capture_baker_is_created_when_saving_replacement(self):
        context = omni.usd.get_context()
        # create on a disk because capture baker should be created when we save any replacement layer
        # (and we can't save layers in memory)
        async with make_temp_directory(context) as temp_dir:
            stage, layer_replacement, _ = await self.__create_stage_and_layers(temp_dir=temp_dir)
            current_sublayers = list(layer_replacement.subLayerPaths)

            await self.__create_a_cube(stage, layer_replacement)
            await omni.kit.app.get_app().next_update_async()
            layer_replacement.Save()

            # wait for the event
            await omni.kit.app.get_app().next_update_async()

            # we should have a new capture baker
            self.assertNotEqual(current_sublayers, layer_replacement.subLayerPaths)

    async def test_capture_baker_is_muted_when_created(self):
        context = omni.usd.get_context()
        # create on a disk because capture baker should be created when we save any replacement layer
        # (and we can't save layers in memory)
        async with make_temp_directory(context) as temp_dir:
            stage, layer_replacement, _ = await self.__create_stage_and_layers(temp_dir=temp_dir)

            await self.__create_a_cube(stage, layer_replacement)
            await omni.kit.app.get_app().next_update_async()
            layer_replacement.Save()

            # wait for the event
            await omni.kit.app.get_app().next_update_async()

            # we should have a new capture baker muted
            self.assertTrue(stage.IsLayerMuted(layer_replacement.subLayerPaths[-1]))

    async def test_capture_baker_at_bottom_stack(self):
        context = omni.usd.get_context()
        # create on a disk because capture baker should be created when we save any replacement layer
        # (and we can't save layers in memory)
        async with make_temp_directory(context) as temp_dir:
            stage, layer_replacement, _ = await self.__create_stage_and_layers(temp_dir=temp_dir)
            # create 2 layers at the end of the stack
            random_stage_01 = Usd.Stage.CreateInMemory("random_layer01.usd")
            layer_random_01 = random_stage_01.GetRootLayer()
            layer_replacement.subLayerPaths.insert(len(layer_replacement.subLayerPaths), layer_random_01.identifier)
            random_stage_02 = Usd.Stage.CreateInMemory("random_layer02.usd")
            layer_random_02 = random_stage_02.GetRootLayer()
            layer_replacement.subLayerPaths.insert(len(layer_replacement.subLayerPaths), layer_random_02.identifier)

            await self.__create_a_cube(stage, layer_replacement)
            await omni.kit.app.get_app().next_update_async()
            layer_replacement.Save()

            # wait for the event
            await omni.kit.app.get_app().next_update_async()

            # we should have a new capture baker at the bottom of the stack
            self.assertEqual(len(layer_replacement.subLayerPaths), 3)
            self.assertEqual(
                layer_replacement.subLayerPaths[:2], [layer_random_01.identifier, layer_random_02.identifier]
            )

            # now we add a new layer at the bottom of the stack
            random_stage_03 = Usd.Stage.CreateInMemory("random_layer03.usd")
            layer_random_03 = random_stage_03.GetRootLayer()
            layer_replacement.subLayerPaths.insert(len(layer_replacement.subLayerPaths), layer_random_03.identifier)

            # the last layer is the random layer
            self.assertEqual(layer_replacement.subLayerPaths[-1], layer_random_03.identifier)
            self.assertEqual(len(layer_replacement.subLayerPaths), 4)

            # wait for the event
            await omni.kit.app.get_app().next_update_async()

            # now the last layer is the capture baker
            self.assertEqual(len(layer_replacement.subLayerPaths), 4)
            self.assertEqual(
                layer_replacement.subLayerPaths[:3],
                [layer_random_01.identifier, layer_random_02.identifier, layer_random_03.identifier],
            )

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

import omni.kit.test
import omni.usd
from lightspeed.ui_scene.light_manipulator import DiskLightModel
from omni.kit.test_suite.helpers import wait_stage_loading
from omni.ui.tests.test_base import OmniUiTest
from pxr import Usd, UsdLux


class MockManip:
    def __init__(self, model):
        self._model = model

    @property
    def model(self):
        return self._model


class MockLayer:
    def __init__(self):
        self._manipulators = {}

    def create_manipulator(self, prim_path, manipulator):
        self._manipulators[prim_path] = manipulator

    @property
    def manipulators(self):
        return self._manipulators


class TestLightModel(OmniUiTest):

    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage: Usd.Stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_model_usd_interaction(self):
        """
        Test to make sure manipulators will be able to interact well with model and get get updates
        flowing through to USD at the right time.
        """
        # create a light
        light = self.stage.DefinePrim("/TestLight")
        light.SetTypeName("DiskLight")
        disk_light = UsdLux.DiskLight(light)
        disk_light.CreateIntensityAttr().Set(10.0)
        disk_light.CreateRadiusAttr().Set(10.0)

        mock_viewport_layer = MockLayer()
        disk_model = DiskLightModel(
            light, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )
        mock_viewport_layer.create_manipulator("/TestLight", MockManip(disk_model))
        # mock selecting a light
        omni.usd.get_context().get_selection().set_selected_prim_paths(["/TestLight"], True)
        disk_model._on_kit_selection_changed()  # noqa PSW0212 protected member

        with self.subTest("Test setting just the model, and reverting via updating from USD"):
            # set only the model item (not USD)
            disk_model.set_item_value(disk_model.radius, 100.0)
            self.assertNotEquals(disk_model.get_as_float("radius"), 100.0)
            # update the model from USD
            disk_model.update_from_prim()
            self.assertEquals(disk_model.get_as_float("radius"), 10.0)

        with self.subTest("Test set_float() behavior"):
            # make sure set_float forwards changes to USD
            disk_model.set_float(disk_model.radius, 100.0)
            self.assertEqual(disk_light.GetRadiusAttr().Get(), 100.0)
            # get_as_float should read from USD
            self.assertEqual(disk_model.get_as_float("radius"), 100.0)
            # but not the model itself
            self.assertEqual(disk_model.radius.value, 10.0)

            # until we update the model from USD
            disk_model.update_from_prim()
            self.assertEquals(disk_model.get_as_float("radius"), 100.0)

        with self.subTest("Test set_float_commands() behavior"):
            # set an initial value and then simulate a manipulator move to a new value
            disk_model.set_item_value(disk_model.radius, 5.0)
            disk_model.set_float(disk_model.radius, 15.0)  # intermediate value
            disk_model.set_float_commands(disk_model.radius, 50.0)
            self.assertEqual(disk_light.GetRadiusAttr().Get(), 50.0)
            omni.kit.undo.undo()
            self.assertEqual(disk_light.GetRadiusAttr().Get(), 5.0)

        with self.subTest("Test set_float_multiple()"):
            disk_model.set_float_multiple("radius", disk_model.radius, 60.0)
            self.assertNotEqual(disk_model.radius.value, 60.0)

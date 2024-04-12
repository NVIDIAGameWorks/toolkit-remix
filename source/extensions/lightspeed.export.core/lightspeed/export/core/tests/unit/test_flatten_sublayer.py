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
from pathlib import Path

import carb.tokens
import omni.kit.test
import omni.usd
from pxr import Sdf, Usd


class TestFlattenSublayersCommand(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self._dataFolder = Path(carb.tokens.get_tokens_interface().resolve("${lightspeed.export.core}/data/tests"))
        self._context = omni.usd.create_context()
        self._context.open_stage(str(self._dataFolder / "flatten_sublayer_test_root.usda"))
        self._stage = self._context.get_stage()

    # Actual test, notice it is "async" function, so "await" can be used if needed
    async def test_flatten_sublayer(self):
        # Load data/flatten_sublayer_test_root.usda
        root_layer = self._stage.GetRootLayer()
        flatten_layer = Sdf.Find(root_layer.ComputeAbsolutePath(root_layer.subLayerPaths[0]))

        omni.kit.commands.execute("FlattenSubLayers", usd_context=self._context, layer_to_flatten=flatten_layer)

        self.assertEqual(len(flatten_layer.subLayerPaths), 0)
        self.assertTrue(flatten_layer.GetPrimAtPath("/World/A"))
        self.assertTrue(flatten_layer.GetPrimAtPath("/World/B"))

        # Close without saving so we can verify the flattening didn't auto-save anything
        self._context.close_stage()

        # Existing save files should not be modified:
        stage_a = Usd.Stage.Open(str(self._dataFolder / "flatten_sublayer_test_a.usda"))
        self.assertFalse(stage_a.GetPrimAtPath("/World/B"))

        stage_b = Usd.Stage.Open(str(self._dataFolder / "flatten_sublayer_test_b.usda"))
        self.assertFalse(stage_b.GetPrimAtPath("/World/A"))

        stage_flattened = Usd.Stage.Open(str(self._dataFolder / "flatten_sublayer_test_sublayer.usda"))
        self.assertEqual(len(stage_flattened.GetRootLayer().subLayerPaths), 2)
        self.assertTrue(stage_flattened.GetPrimAtPath("/World/A"))
        self.assertTrue(stage_flattened.GetPrimAtPath("/World/B"))
        self.assertFalse(stage_flattened.GetRootLayer().GetPrimAtPath("/World/A"))
        self.assertFalse(stage_flattened.GetRootLayer().GetPrimAtPath("/World/B"))

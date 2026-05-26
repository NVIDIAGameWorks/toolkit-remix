"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import tempfile
from pathlib import Path

import omni.kit.test
import omni.usd
from lightspeed.trex.packaging.window.tree.item import PackagingErrorItem
from lightspeed.trex.packaging.window.tree.model import PackagingErrorModel
from pxr import Sdf


class TestPackagingErrorModelE2E(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context_name = ""
        self.context = omni.usd.get_context(self.context_name)

    async def tearDown(self):
        if self.context and self.context.get_stage():
            await self.context.close_stage_async()
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def test_apply_new_paths_remove_reference_from_referenced_layer_should_save_external_layer(self):
        # Arrange
        tmp_dir = Path(self.temp_dir.name)
        asset_layer_path = tmp_dir / "asset.usda"
        root_layer_path = tmp_dir / "mod.usda"
        missing_prim_path = "/RootNode/Asset/MissingReference"
        authored_missing_prim_path = "/ReferencedAsset/MissingReference"
        asset_layer = Sdf.Layer.CreateNew(str(asset_layer_path))
        asset_layer.defaultPrim = "ReferencedAsset"
        referenced_root_spec = Sdf.CreatePrimInLayer(asset_layer, "/ReferencedAsset")
        referenced_root_spec.specifier = Sdf.SpecifierDef
        referenced_root_spec.typeName = "Xform"
        missing_ref_spec = Sdf.CreatePrimInLayer(asset_layer, authored_missing_prim_path)
        missing_ref_spec.specifier = Sdf.SpecifierDef
        missing_ref_spec.typeName = "Xform"
        missing_ref_spec.referenceList.Append(Sdf.Reference("./missing_asset.usda"))
        asset_layer.Save()

        root_layer = Sdf.Layer.CreateNew(str(root_layer_path))
        root_layer.defaultPrim = "RootNode"
        root_spec = Sdf.CreatePrimInLayer(root_layer, "/RootNode")
        root_spec.specifier = Sdf.SpecifierDef
        root_spec.typeName = "Xform"
        ref_spec = Sdf.CreatePrimInLayer(root_layer, "/RootNode/Asset")
        ref_spec.specifier = Sdf.SpecifierDef
        ref_spec.typeName = "Xform"
        ref_spec.referenceList.Append(Sdf.Reference("./asset.usda"))
        root_layer.Save()

        await self.context.open_stage_async(str(root_layer_path))
        stage = self.context.get_stage()
        self.assertIsNotNone(stage)
        self.assertNotIn(asset_layer.identifier, [layer.identifier for layer in stage.GetLayerStack()])

        missing_reference_path = Path(asset_layer.ComputeAbsolutePath("./missing_asset.usda")).as_posix()
        item = PackagingErrorItem(asset_layer.identifier, missing_prim_path, missing_reference_path)
        item.fixed_asset_path = None

        model = PackagingErrorModel(context_name=self.context_name)

        # Act
        ignored_items = model.apply_new_paths(items=[item])

        # Assert
        self.assertEqual([], ignored_items)

        asset_layer.Reload()
        authored_prim_spec = asset_layer.GetPrimAtPath(authored_missing_prim_path)
        self.assertIsNotNone(authored_prim_spec)
        self.assertEqual(1, len(list(authored_prim_spec.referenceList.GetAddedOrExplicitItems())))

        override_prim_spec = root_layer.GetPrimAtPath(missing_prim_path)
        self.assertIsNotNone(override_prim_spec)
        self.assertEqual([], list(override_prim_spec.referenceList.GetAddedOrExplicitItems()))

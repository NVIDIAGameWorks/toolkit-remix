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

import omni.kit.test
import omni.usd
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementCore
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf, Usd, UsdGeom


class TestAssetReplacementsTransferSpecsE2E(omni.kit.test.AsyncTestCase):
    """Real in-memory USD stage tests for OpenUSD composition and layer mutation behavior."""

    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self._stage = omni.usd.get_context().get_stage()
        self._asset_replacement_core = _AssetReplacementCore("")

    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_transfer_property_should_only_move_selected_source_layers(self):
        # Arrange
        source_layer = Sdf.Layer.CreateAnonymous("source.usda")
        other_source_layer = Sdf.Layer.CreateAnonymous("other_source.usda")
        target_layer = Sdf.Layer.CreateAnonymous("target.usda")
        self._stage.GetRootLayer().subLayerPaths.append(other_source_layer.identifier)
        self._stage.GetRootLayer().subLayerPaths.insert(0, source_layer.identifier)
        self._stage.GetRootLayer().subLayerPaths.insert(0, target_layer.identifier)
        visibility_path = Sdf.Path("/World/TestPrim.visibility")

        with Usd.EditContext(self._stage, other_source_layer):
            prim = self._stage.DefinePrim("/World/TestPrim", "Xform")
            prim.GetAttribute("visibility").Set(UsdGeom.Tokens.invisible)
        with Usd.EditContext(self._stage, source_layer):
            prim = self._stage.OverridePrim("/World/TestPrim")
            prim.GetAttribute("visibility").Set(UsdGeom.Tokens.inherited)

        # Act
        layer_undos = self._asset_replacement_core.transfer_property_spec_to_layer(
            str(visibility_path), [source_layer.identifier], target_layer.identifier
        )

        # Assert
        self.assertIsNotNone(layer_undos)
        self.assertIsNone(source_layer.GetPropertyAtPath(visibility_path))
        self.assertIsNotNone(other_source_layer.GetPropertyAtPath(visibility_path))
        self.assertEqual(target_layer.GetAttributeAtPath(visibility_path).default, UsdGeom.Tokens.inherited)

    async def test_transfer_property_should_reject_locked_layers_without_mutation(self):
        # Arrange
        source_layer = Sdf.Layer.CreateAnonymous("source.usda")
        target_layer = Sdf.Layer.CreateAnonymous("target.usda")
        self._stage.GetRootLayer().subLayerPaths.append(source_layer.identifier)
        self._stage.GetRootLayer().subLayerPaths.insert(0, target_layer.identifier)
        visibility_path = Sdf.Path("/World/TestPrim.visibility")

        with Usd.EditContext(self._stage, source_layer):
            prim = self._stage.DefinePrim("/World/TestPrim", "Xform")
            prim.GetAttribute("visibility").Set(UsdGeom.Tokens.invisible)
        source_layer_before = source_layer.ExportToString()
        target_layer_before = target_layer.ExportToString()
        LayerUtils.set_layer_lock_status(self._stage.GetRootLayer(), target_layer.identifier, True)

        # Act
        layer_undos = self._asset_replacement_core.transfer_property_spec_to_layer(
            str(visibility_path), [source_layer.identifier], target_layer.identifier
        )

        # Assert
        self.assertIsNone(layer_undos)
        self.assertEqual(source_layer.ExportToString(), source_layer_before)
        self.assertEqual(target_layer.ExportToString(), target_layer_before)

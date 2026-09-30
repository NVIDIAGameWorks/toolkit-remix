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

from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

from pxr import Sdf, Usd, UsdGeom

import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared.data_models import AssetReplacementsValidators, ReplacementAssetType
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS
from omni.kit.test import AsyncTestCase


class TestAssetReplacementsValidators(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()

    # After running each test
    async def tearDown(self):
        if self.context.can_close_stage():
            await self.context.close_stage_async()
        self.context = None

    async def test_is_valid_prim_returns_expected_value_or_raises(self):
        # Arrange
        valid_prim_path = "/test/prim/value"

        test_cases = {
            valid_prim_path: (True, None),
            "This.Is/Not A Prim": (False, "The string is not a valid prim path"),
            "/test/non/existent/prim": (False, "The prim path does not exist in the current stage"),
        }

        for prim_path, expected_value in test_cases.items():
            success, message = expected_value

            with self.subTest(title=f"prim_path_{prim_path}_success_{success}"):
                self.context.get_stage().DefinePrim(valid_prim_path, "Scope")

                # Act
                with nullcontext() if success else self.assertRaises(ValueError) as cm:
                    value = AssetReplacementsValidators.is_valid_prim(prim_path, "")

                # Assert
                if success:
                    self.assertEqual(value, prim_path)
                else:
                    self.assertEqual(str(cm.exception), f"{message}: {prim_path}")

    async def test_get_replacement_asset_type_should_match_asset_extension(self):
        # Arrange
        test_cases = [
            ("missing.usda", ReplacementAssetType.MESH),
            ("missing.mdl", ReplacementAssetType.MDL),
            ("missing.png", ReplacementAssetType.TEXTURE),
            ("missing.unknown", ReplacementAssetType.ANY),
        ]

        for asset_path, expected_type in test_cases:
            with self.subTest(asset_path=asset_path):
                # Act
                result = AssetReplacementsValidators.get_replacement_asset_type(asset_path)

                # Assert
                self.assertEqual(result, expected_type)

    async def test_get_replacement_asset_extensions_should_match_asset_type(self):
        # Arrange
        expected_any_extensions = (*constants.USD_EXTENSIONS, ".mdl", *SUPPORTED_TEXTURE_EXTENSIONS)
        test_cases = [
            (ReplacementAssetType.MESH, tuple(constants.USD_EXTENSIONS)),
            (ReplacementAssetType.MDL, (".mdl",)),
            (ReplacementAssetType.TEXTURE, tuple(SUPPORTED_TEXTURE_EXTENSIONS)),
            (ReplacementAssetType.ANY, expected_any_extensions),
        ]

        for asset_type, expected_extensions in test_cases:
            with self.subTest(asset_type=asset_type):
                # Act
                result = AssetReplacementsValidators.get_replacement_asset_extensions(asset_type)

                # Assert
                self.assertEqual(result, expected_extensions)

    async def test_is_valid_replacement_asset_should_accept_compatible_existing_files(self):
        # Arrange
        test_cases = [
            (ReplacementAssetType.MESH, "replacement.usdc"),
            (ReplacementAssetType.MDL, "replacement.mdl"),
            (ReplacementAssetType.TEXTURE, "replacement.dds"),
            (ReplacementAssetType.ANY, "replacement.usda"),
        ]

        with TemporaryDirectory() as temp_dir:
            for asset_type, replacement_filename in test_cases:
                replacement_path = Path(temp_dir) / replacement_filename
                replacement_path.touch()

                with self.subTest(asset_type=asset_type, replacement_path=replacement_path):
                    # Act
                    result = AssetReplacementsValidators.is_valid_replacement_asset(
                        str(replacement_path),
                        asset_type,
                    )

                    # Assert
                    self.assertTrue(result)

    async def test_get_prim_references_walks_to_the_referencing_ancestor_and_fills_the_cache(self):
        """A descendant resolves to the ancestor that introduces the reference. The cache records every visited path."""
        with TemporaryDirectory() as temp_dir:
            # Arrange: a model layer referenced by /World/mesh; /World/other has no reference anywhere above it.
            model_path = Path(temp_dir) / "model.usda"
            model = Usd.Stage.CreateNew(str(model_path))
            model.SetDefaultPrim(UsdGeom.Xform.Define(model, "/Root").GetPrim())
            UsdGeom.Mesh.Define(model, "/Root/Shape")
            model.GetRootLayer().Save()
            stage = self.context.get_stage()
            UsdGeom.Xform.Define(stage, "/World")
            mesh = UsdGeom.Xform.Define(stage, "/World/mesh").GetPrim()
            mesh.GetReferences().AddReference(str(model_path))
            UsdGeom.Xform.Define(stage, "/World/other/leaf")
            cache = {}

            # Act
            owner, references = AssetReplacementsValidators.get_prim_references(
                "/World/mesh/Shape", "", stage=stage, ancestor_cache=cache
            )
            other, other_references = AssetReplacementsValidators.get_prim_references(
                "/World/other/leaf", "", stage=stage, ancestor_cache=cache
            )
            # A seeded ancestor entry wins over the stage walk and is back-filled onto the visited descendant.
            marker = (stage.GetPrimAtPath("/World"), [])
            seeded = {Sdf.Path("/World/mesh"): marker}
            hit = AssetReplacementsValidators.get_prim_references(
                "/World/mesh/Shape", "", stage=stage, ancestor_cache=seeded
            )

            # Assert
            self.assertEqual(owner, mesh)
            self.assertEqual([reference.assetPath for reference, _ in references], [model_path.as_posix()])
            self.assertEqual(hit, marker)
            self.assertEqual(seeded[Sdf.Path("/World/mesh/Shape")], marker)
            self.assertEqual(other_references, [])
            self.assertEqual(cache[Sdf.Path("/World/mesh/Shape")], (mesh, references))
            self.assertEqual(cache[Sdf.Path("/World/mesh")], (mesh, references))
            for path in ("/World/other/leaf", "/World/other", "/World"):
                self.assertEqual(cache[Sdf.Path(path)][1], [], path)

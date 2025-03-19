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

import tempfile
from contextlib import nullcontext
from unittest.mock import patch

import omni.usd
from lightspeed.trex.texture_replacements.core.shared.data_models import TextureReplacementsValidators
from omni.kit.test import AsyncTestCase
from pxr import Sdf, UsdShade


class TestTextureReplacementsValidators(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()

    # After running each test
    async def tearDown(self):
        if self.context.can_close_stage():
            await self.context.close_stage_async()
        self.context = None

    async def test_is_valid_texture_prim_returns_expected_value_or_raises(self):
        # Arrange
        invalid_prim_path = "/test/prim/not/a/shader/prim"
        invalid_prop_name = "test"

        valid_prim_path = "/test/prim/value/Shader"
        valid_prop_name = "diffuse_texture"

        test_cases = {
            f"{valid_prim_path}.inputs:{valid_prop_name}": (True, None),
            f"{invalid_prim_path}.{invalid_prop_name}": (
                False,
                "The property path does not point to a valid USD shader property",
            ),
            f"{valid_prim_path}.{invalid_prop_name}": (
                False,
                "The property path does not point to a valid USD shader input",
            ),
            valid_prim_path: (False, "The property path does not point to a valid USD shader input"),
            invalid_prim_path: (False, "The property path does not point to a valid USD shader property"),
            "This.Is/Not A Prim": (False, "The string is not a valid path"),
            "/test/non/existent/prim": (False, "The prim path does not exist in the current stage"),
        }

        for prim_path, expected_value in test_cases.items():
            success, message = expected_value

            with self.subTest(title=f"prim_path_{prim_path}_success_{success}"):
                stage = self.context.get_stage()

                prim = stage.DefinePrim(invalid_prim_path, "Scope")
                prim.CreateAttribute(invalid_prop_name, Sdf.ValueTypeNames.Float).Set(100.0)

                shader = UsdShade.Shader.Define(stage, valid_prim_path)
                shader.CreateInput(valid_prop_name, Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("C:/Test/texture.png"))
                shader.GetPrim().CreateAttribute(invalid_prop_name, Sdf.ValueTypeNames.Float).Set(100.0)

                input_val = (prim_path, None)

                # Act
                with nullcontext() if success else self.assertRaises(ValueError) as cm:
                    value = TextureReplacementsValidators.is_valid_texture_prim(input_val, "")

                # Assert
                if success:
                    self.assertEqual(value, input_val)
                else:
                    self.assertEqual(str(cm.exception), f"{message}: {prim_path}")

    async def test_is_valid_texture_asset_returns_expected_value_or_raises(self):
        # Arrange
        valid_asset_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png")

        test_cases = {
            (valid_asset_path.name, True): (True, None),
            (valid_asset_path.name, False): (
                False,
                "The asset was not ingested. Ingest the asset before replacing the texture",
            ),
            ("Z:/Test/invalid_type.docx", True): (False, "The asset path points to an unsupported texture file type"),
            ("Z:/Test/invalid_type.docx", False): (False, "The asset path points to an unsupported texture file type"),
            ("Z:/Test/non_existent.png", True): (False, "The asset path does not point to an existing file"),
            ("Z:/Test/non_existent.png", False): (False, "The asset path does not point to an existing file"),
        }

        for input_value, expected_value in test_cases.items():
            asset_path, force = input_value
            success, message = expected_value

            with self.subTest(title=f"asset_path_{asset_path}_force_{force}_success_{success}"):
                input_val = (None, asset_path)

                with patch(
                    "lightspeed.trex.texture_replacements.core.shared.data_models.validators.is_asset_ingested"
                ) as was_ingested_mock:
                    was_ingested_mock.return_value = False

                    # Act
                    with nullcontext() if success else self.assertRaises(ValueError) as cm:
                        value = TextureReplacementsValidators.is_valid_texture_asset(input_val, force)

                # Assert
                if success:
                    self.assertEqual(value, input_val)
                else:
                    self.assertEqual(str(cm.exception), f"{message}: {asset_path}")

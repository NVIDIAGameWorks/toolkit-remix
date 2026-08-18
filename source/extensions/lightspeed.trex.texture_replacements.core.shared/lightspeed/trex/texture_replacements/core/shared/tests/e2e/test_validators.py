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

from unittest.mock import MagicMock, patch

import omni.usd
from lightspeed.trex.texture_replacements.core.shared.data_models import TextureReplacementsValidators
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Tf, UsdShade


class TestTextureReplacementsValidatorsE2E(AsyncTestCase):
    """Test texture property validation against a real Kit USD stage."""

    async def setUp(self):
        """Create an empty stage for each validation scenario."""
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.invalid_prim_path = "/test/prim/not/a/shader/prim"
        self.shader_path = "/test/prim/value/Shader"
        stage = self.context.get_stage()
        scope = stage.DefinePrim(self.invalid_prim_path, "Scope")
        scope.CreateAttribute("test", Sdf.ValueTypeNames.Float).Set(100.0)
        shader = UsdShade.Shader.Define(stage, self.shader_path)
        shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("C:/Test/texture.png"))
        shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.String).Set("C:/Test/normal.png")
        shader.CreateInput("roughness_texture", Sdf.ValueTypeNames.Float).Set(0.5)
        shader.GetPrim().CreateAttribute("test", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("C:/Test/not_input.png"))

    async def tearDown(self):
        """Close the stage created for the validation scenario."""
        if self.context.can_close_stage():
            await self.context.close_stage_async()
        self.context = None

    async def test_is_valid_texture_prim_accepts_authored_asset_input(self):
        """An authored Asset shader input passes validation."""
        # Validate the Asset input authored on the live test-stage shader.
        input_value = (f"{self.shader_path}.inputs:diffuse_texture", None)

        result = TextureReplacementsValidators.is_valid_texture_prim(input_value, "")

        # The public validator returns the original selection unchanged.
        self.assertEqual(result, input_value)

    async def test_is_valid_texture_prim_accepts_authored_string_input(self):
        """An authored String shader input passes validation."""
        # Validate the String input authored on the live test-stage shader.
        input_value = (f"{self.shader_path}.inputs:normalmap_texture", None)

        result = TextureReplacementsValidators.is_valid_texture_prim(input_value, "")

        # The public validator returns the original selection unchanged.
        self.assertEqual(result, input_value)

    async def test_is_valid_texture_prim_rejects_unsupported_authored_type(self):
        """An authored non-texture shader input fails validation."""
        # Select the real Float input authored on the test-stage shader.
        property_path = f"{self.shader_path}.inputs:roughness_texture"

        with self.assertRaises(ValueError) as error_context:
            TextureReplacementsValidators.is_valid_texture_prim((property_path, None), "")

        # Validation explains that the authored property is not a supported texture input.
        self.assertEqual(
            str(error_context.exception),
            f"The property path does not point to a valid USD shader input: {property_path}",
        )

    async def test_is_valid_texture_prim_rejects_non_shader_property(self):
        """A property on a non-shader prim fails validation."""
        # Select a real attribute on the test stage whose owner is not a shader.
        property_path = f"{self.invalid_prim_path}.test"

        with self.assertRaises(ValueError) as error_context:
            TextureReplacementsValidators.is_valid_texture_prim((property_path, None), "")

        # Validation identifies the invalid USD owner rather than accepting the Asset-like value.
        self.assertEqual(
            str(error_context.exception),
            f"The property path does not point to a valid USD shader property: {property_path}",
        )

    async def test_is_valid_texture_prim_rejects_non_input_shader_attribute(self):
        """An Asset attribute outside the shader input namespace fails validation."""
        # Select a real Asset attribute authored outside the shader input namespace.
        property_path = f"{self.shader_path}.test"

        with self.assertRaises(ValueError) as error_context:
            TextureReplacementsValidators.is_valid_texture_prim((property_path, None), "")

        # Validation rejects the property even though its native value type is Asset.
        self.assertEqual(
            str(error_context.exception),
            f"The property path does not point to a valid USD shader input: {property_path}",
        )

    async def test_is_valid_texture_prim_rejects_prim_path_without_property(self):
        """A prim path without a property component fails validation."""
        # Pass the live shader prim path without selecting one of its authored properties.
        with self.assertRaises(ValueError) as error_context:
            TextureReplacementsValidators.is_valid_texture_prim((self.shader_path, None), "")

        # Validation asks for a shader input property instead of guessing one.
        self.assertEqual(
            str(error_context.exception),
            f"The property path does not point to a valid USD shader input: {self.shader_path}",
        )

    async def test_is_valid_texture_prim_rejects_invalid_path_string(self):
        """An invalid USD path string fails validation."""
        # Submit a malformed path through the same public selection validator.
        property_path = "This.Is/Not A Prim"

        with self.assertRaises(ValueError) as error_context:
            TextureReplacementsValidators.is_valid_texture_prim((property_path, None), "")

        # The error is user-facing and identifies the invalid path.
        self.assertEqual(str(error_context.exception), f"The string is not a valid path: {property_path}")

    async def test_is_valid_texture_prim_rejects_missing_prim(self):
        """A property path whose prim does not exist fails validation."""
        # Select a syntactically valid property path whose owner is absent from the live stage.
        property_path = "/test/non/existent/prim.inputs:file"

        with self.assertRaises(ValueError) as error_context:
            TextureReplacementsValidators.is_valid_texture_prim((property_path, None), "")

        # Validation distinguishes a missing stage prim from malformed property syntax.
        self.assertEqual(
            str(error_context.exception),
            "The prim path does not exist in the current stage: /test/non/existent/prim",
        )

    async def test_is_valid_texture_prim_with_authored_input_does_not_require_shader_registry(self):
        """An authored shader input validates without consulting the shader registry."""
        # Author the complete input metadata directly on a live USD shader.
        property_path = "/test/Shader.inputs:diffuse_texture"
        shader = UsdShade.Shader.Define(self.context.get_stage(), "/test/Shader")
        shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset)
        input_value = (property_path, None)

        # Validation succeeds from USD even when the external shader registry cannot start.
        with patch(
            "lightspeed.trex.texture_replacements.core.shared.data_models.validators.ShaderInfoAPI",
            side_effect=Tf.ErrorException("Shader registry unavailable"),
        ) as shader_info_api:
            value = TextureReplacementsValidators.is_valid_texture_prim(input_value, "")

        self.assertEqual(value, input_value)
        shader_info_api.assert_not_called()

    async def test_is_valid_texture_prim_with_unavailable_shader_registry_reports_operational_failure(self):
        """An unavailable registry remains distinguishable from an invalid candidate."""
        # Leave the live shader input unauthored so validation must consult registry metadata.
        property_path = "/test/Shader.inputs:diffuse_texture"
        UsdShade.Shader.Define(self.context.get_stage(), "/test/Shader")
        input_value = (property_path, None)

        with (
            patch(
                "lightspeed.trex.texture_replacements.core.shared.data_models.validators.ShaderInfoAPI",
                side_effect=Tf.ErrorException("Shader registry unavailable"),
            ),
            self.assertRaises(RuntimeError) as exception_context,
        ):
            TextureReplacementsValidators.is_valid_texture_prim(input_value, "")

        self.assertEqual(
            str(exception_context.exception),
            f"Could not read shader input metadata for: {property_path}",
        )

    async def test_texture_batch_reads_shader_metadata_once(self):
        """Unauthored inputs on one shader share one stable metadata lookup."""
        # Create two unauthored inputs that belong to the same live shader prim.
        shader_path = "/test/BatchShader"
        UsdShade.Shader.Define(self.context.get_stage(), shader_path)
        diffuse = MagicMock()
        diffuse.GetName.return_value = "inputs:diffuse_texture"
        diffuse.GetTypeName.return_value = Sdf.ValueTypeNames.Asset
        normal = MagicMock()
        normal.GetName.return_value = "inputs:normalmap_texture"
        normal.GetTypeName.return_value = Sdf.ValueTypeNames.String
        paths = [f"{shader_path}.inputs:diffuse_texture", f"{shader_path}.inputs:normalmap_texture"]
        shader_info = MagicMock()
        shader_info.get_input_properties.return_value = [diffuse, normal]

        # Resolve the batch together so the shader metadata is loaded only once.
        with patch(
            "lightspeed.trex.texture_replacements.core.shared.data_models.validators.ShaderInfoAPI",
            return_value=shader_info,
        ) as shader_info_api:
            result = TextureReplacementsValidators.get_texture_input_types(paths, "")

        self.assertEqual(
            result,
            {
                paths[0]: Sdf.ValueTypeNames.Asset,
                paths[1]: Sdf.ValueTypeNames.String,
            },
        )
        shader_info_api.assert_called_once()

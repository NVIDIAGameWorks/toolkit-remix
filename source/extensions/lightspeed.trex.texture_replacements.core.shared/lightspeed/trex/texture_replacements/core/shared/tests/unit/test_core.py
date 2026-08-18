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

from unittest.mock import Mock, call, patch

import omni.usd
from lightspeed.trex.texture_replacements.core.shared import setup
from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from lightspeed.trex.texture_replacements.core.shared.data_models import TextureReplacementsValidators
from lightspeed.trex.texture_replacements.core.shared.data_models.models import TextureReplacement
from lightspeed.trex.texture_replacements.core.shared.data_models.validators import InvalidTextureInputError
from omni.flux.material_api import ShaderInfoAPI
from omni.kit.test import AsyncTestCase
from pxr import Sdf


class TestTextureReplacementValidation(AsyncTestCase):
    """Test replacement validation and authoring without loading a USD stage."""

    async def test_validator_accepts_shader_info_type_name_strings(self):
        """ShaderInfoAPI placeholders expose declared USD types as strings."""
        # Arrange
        texture_path = "/World/Shader.inputs:diffuse_texture"
        context = Mock()
        stage = Mock()
        prim = Mock()
        input_property = Mock()
        context.get_stage.return_value = stage
        stage.GetPrimAtPath.return_value = prim
        prim.IsA.return_value = True
        prim.GetAttribute.return_value = None
        input_property.GetName.return_value = "inputs:diffuse_texture"
        input_property.GetTypeName.return_value = str(Sdf.ValueTypeNames.Asset)

        with (
            patch.object(omni.usd, "get_context", return_value=context),
            patch.object(ShaderInfoAPI, "__init__", return_value=None),
            patch.object(ShaderInfoAPI, "get_input_properties", return_value=[input_property]),
        ):
            # Act
            result = TextureReplacementsValidators.is_valid_texture_prim((texture_path, None), "test_context")

        # Assert
        self.assertEqual(result, (texture_path, None))

    async def test_get_valid_texture_inputs_filters_invalid_paths(self):
        """The local helper keeps only paths accepted by the texture-input validator."""
        # Arrange
        valid_path = "/World/Shader.inputs:diffuse_texture"
        invalid_path = "/World/Shader.inputs:not_a_texture"
        context_name = "test_context"

        with (
            patch.object(setup, "get_context"),
            patch.object(
                TextureReplacementsValidators,
                "is_valid_texture_prim",
                side_effect=[None, InvalidTextureInputError("invalid texture input")],
            ) as validate,
        ):
            core = TextureReplacementsCore(context_name)

            # Act
            result = core.get_valid_texture_inputs([valid_path, invalid_path])

        # Assert
        self.assertEqual(result, [valid_path])
        self.assertEqual(
            validate.call_args_list,
            [
                call((valid_path, None), context_name),
                call((invalid_path, None), context_name),
            ],
        )

    async def test_replace_textures_propagates_validation_errors(self):
        """An invalid replacement cannot be reported as successfully applied."""
        # Arrange
        texture_entry = ("/World/Shader.inputs:diffuse_texture", "C:/textures/albedo.dds")

        with (
            patch.object(setup, "get_context"),
            patch.object(
                TextureReplacementsValidators,
                "get_texture_input_types",
                side_effect=InvalidTextureInputError("invalid texture input"),
            ),
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            with self.assertRaisesRegex(ValueError, "invalid texture input") as error_context:
                core.replace_textures([texture_entry])

        # Assert
        self.assertIsInstance(error_context.exception, ValueError)

    async def test_replace_textures_validates_batch_before_mutating(self):
        """An invalid batch entry prevents every replacement in that batch."""
        # Arrange
        textures = [
            ("/World/Shader.inputs:diffuse_texture", "C:/textures/albedo.dds"),
            ("/World/Shader.inputs:normalmap_texture", "C:/textures/normal.dds"),
        ]

        with (
            patch.object(setup, "get_context"),
            patch.object(
                TextureReplacementsValidators,
                "get_texture_input_types",
                side_effect=InvalidTextureInputError("invalid texture input"),
            ),
            patch.object(TextureReplacementsValidators, "is_valid_texture_asset"),
            patch.object(setup.commands, "execute") as execute,
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            with self.assertRaisesRegex(ValueError, "invalid texture input"):
                core.replace_textures(textures)

        # Assert
        execute.assert_not_called()

    async def test_replace_textures_creates_an_unauthored_shader_input_with_its_declared_type(self):
        """A shader input declared by ShaderInfoAPI need not already exist on the stage."""
        # Arrange
        texture_path = "/World/Shader.inputs:diffuse_texture"
        context = Mock()
        stage = Mock()
        context.get_stage.return_value = stage

        with (
            patch.object(setup, "get_context", return_value=context),
            patch.object(TextureReplacementsValidators, "is_valid_texture_asset"),
            patch.object(
                TextureReplacementsValidators,
                "get_texture_input_types",
                return_value={texture_path: Sdf.ValueTypeNames.Asset},
            ),
            patch.object(setup.commands, "execute", return_value=(True, None)) as execute,
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            core.replace_textures(
                [(texture_path, "C:/textures/albedo.dds")],
                target_layer=Mock(),
            )

        # Assert
        execute.assert_called_once()
        self.assertEqual(
            execute.call_args.kwargs["replacements"],
            [TextureReplacement(Sdf.Path(texture_path), "C:/textures/albedo.dds", Sdf.ValueTypeNames.Asset)],
        )

    async def test_replace_textures_makes_asset_path_relative_to_target_layer(self):
        """A replacement path resolves from the layer receiving the authored value."""
        # Arrange
        texture_path = "/World/Shader.inputs:diffuse_texture"
        new_texture = "C:/project/textures/albedo.dds"
        context = Mock()
        stage = Mock()
        context.get_stage.return_value = stage
        target_layer = Mock(
            realPath="C:/project/layers/replacements.usda",
            anonymous=False,
        )

        with (
            patch.object(setup, "get_context", return_value=context),
            patch.object(TextureReplacementsValidators, "is_valid_texture_asset"),
            patch.object(
                TextureReplacementsValidators,
                "get_texture_input_types",
                return_value={texture_path: Sdf.ValueTypeNames.Asset},
            ),
            patch.object(setup.commands, "execute", return_value=(True, None)) as execute,
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            core.replace_textures(
                [(texture_path, new_texture)],
                target_layer=target_layer,
            )

        # Assert
        self.assertEqual(execute.call_args.kwargs["replacements"][0].value, "../textures/albedo.dds")

    async def test_replace_textures_keeps_original_path_for_anonymous_layer(self):
        """An anonymous target layer keeps the validated replacement path unchanged."""
        # Arrange
        texture_path = "/World/Shader.inputs:diffuse_texture"
        new_texture = "C:/project/textures/albedo.dds"
        context = Mock()
        context.get_stage.return_value = Mock()
        target_layer = Mock(realPath="", anonymous=True)

        with (
            patch.object(setup, "get_context", return_value=context),
            patch.object(TextureReplacementsValidators, "is_valid_texture_asset"),
            patch.object(
                TextureReplacementsValidators,
                "get_texture_input_types",
                return_value={texture_path: Sdf.ValueTypeNames.Asset},
            ),
            patch.object(setup, "_make_relative_url_if_possible") as make_relative,
            patch.object(setup.commands, "execute", return_value=(True, None)) as execute,
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            core.replace_textures(
                [(texture_path, new_texture)],
                target_layer=target_layer,
            )

        # Assert
        self.assertEqual(execute.call_args.kwargs["replacements"][0].value, new_texture)
        make_relative.assert_not_called()

    async def test_replace_textures_keeps_original_path_when_relative_conversion_fails(self):
        """A failed relative conversion keeps the validated replacement path unchanged."""
        # Arrange
        texture_path = "/World/Shader.inputs:diffuse_texture"
        new_texture = "C:/project/textures/albedo.dds"
        context = Mock()
        context.get_stage.return_value = Mock()
        target_layer = Mock(realPath="C:/project/layers/replacements.usda", anonymous=False)

        with (
            patch.object(setup, "get_context", return_value=context),
            patch.object(TextureReplacementsValidators, "is_valid_texture_asset"),
            patch.object(
                TextureReplacementsValidators,
                "get_texture_input_types",
                return_value={texture_path: Sdf.ValueTypeNames.Asset},
            ),
            patch.object(setup, "_make_relative_url_if_possible", return_value="") as make_relative,
            patch.object(setup.commands, "execute", return_value=(True, None)) as execute,
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            core.replace_textures(
                [(texture_path, new_texture)],
                target_layer=target_layer,
            )

        # Assert
        self.assertEqual(execute.call_args.kwargs["replacements"][0].value, new_texture)
        make_relative.assert_called_once()

    async def test_replace_textures_rejects_duplicate_targets_before_mutating_batch(self):
        """A batch cannot author the same shader input more than once."""
        # Arrange
        texture_path = "/World/Shader.inputs:diffuse_texture"
        context = Mock()
        stage = Mock()
        prim = Mock()
        context.get_stage.return_value = stage
        stage.GetPrimAtPath.return_value = prim
        prim.IsValid.return_value = True
        prim.GetPath.return_value = Sdf.Path("/RootNode")

        with (
            patch.object(setup, "get_context", return_value=context),
            patch.object(TextureReplacementsValidators, "is_valid_texture_asset"),
            patch.object(
                TextureReplacementsValidators,
                "get_texture_input_types",
                return_value={texture_path: Sdf.ValueTypeNames.Asset},
            ) as resolve_input_type,
            patch.object(setup.commands, "execute") as execute_command,
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            with self.assertRaisesRegex(ValueError, "target paths must be unique"):
                core.replace_textures(
                    [
                        (texture_path, None),
                        (texture_path, "C:/textures/albedo.dds"),
                    ],
                )

        # Assert
        execute_command.assert_not_called()
        resolve_input_type.assert_not_called()

    async def test_forced_replace_textures_requires_expected_current_values(self):
        """Force cannot bypass asset checks without an explicit target-layer baseline."""
        # Arrange
        texture_path = "/World/Shader.inputs:diffuse_texture"

        with (
            patch.object(setup, "get_context"),
            patch.object(TextureReplacementsValidators, "is_valid_texture_asset"),
            patch.object(setup.commands, "execute") as execute_command,
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            with self.assertRaisesRegex(ValueError, "expected current values"):
                core.replace_textures([(texture_path, "C:/missing/original.dds")], force=True)

        # Assert
        execute_command.assert_not_called()

    async def test_forced_replace_textures_forwards_expected_current_values_to_command(self):
        """Force dispatches the confirmed target-layer baseline with the replacement batch."""
        # Arrange
        texture_path = "/World/Shader.inputs:diffuse_texture"
        context = Mock()
        stage = Mock()
        context.get_stage.return_value = stage
        target_layer = Mock(realPath="", anonymous=True, identifier="target")
        target_layer.GetAttributeAtPath.return_value.default = Sdf.AssetPath("C:/project/applied.dds")

        with (
            patch.object(setup, "get_context", return_value=context),
            patch.object(TextureReplacementsValidators, "is_valid_texture_asset"),
            patch.object(
                TextureReplacementsValidators,
                "get_texture_input_types",
                return_value={texture_path: Sdf.ValueTypeNames.Asset},
            ),
            patch.object(setup.commands, "execute", return_value=(True, None)) as execute_command,
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            core.replace_textures(
                [(texture_path, "C:/missing/original.dds")],
                force=True,
                target_layer=target_layer,
                expected_current_textures=[(texture_path, "C:/project/applied.dds")],
            )

        # Assert
        self.assertEqual(
            execute_command.call_args.kwargs["expected_replacements"],
            [TextureReplacement(Sdf.Path(texture_path), "C:/project/applied.dds", Sdf.ValueTypeNames.Asset)],
        )

    async def test_replace_textures_rejects_inconsistent_shader_input_before_mutating(self):
        """A shader input missing after validation fails before any command executes."""
        # Arrange
        texture_path = "/World/Shader.inputs:diffuse_texture"
        context = Mock()
        stage = Mock()
        context.get_stage.return_value = stage
        stage.GetPrimAtPath.return_value = Mock()

        with (
            patch.object(setup, "get_context", return_value=context),
            patch.object(TextureReplacementsValidators, "is_valid_texture_asset"),
            patch.object(
                TextureReplacementsValidators,
                "get_texture_input_types",
                side_effect=ValueError("The property path does not point to a valid USD shader input"),
            ),
            patch.object(setup.commands, "execute") as execute_command,
        ):
            core = TextureReplacementsCore("test_context")

            # Act
            with self.assertRaisesRegex(ValueError, "valid USD shader input") as error_context:
                core.replace_textures(
                    [(texture_path, "C:/textures/albedo.dds")],
                )

        # Assert
        self.assertIsInstance(error_context.exception, ValueError)
        execute_command.assert_not_called()

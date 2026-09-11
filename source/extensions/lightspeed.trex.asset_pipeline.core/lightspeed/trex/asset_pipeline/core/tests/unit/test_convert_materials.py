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

import pathlib
from unittest.mock import AsyncMock, MagicMock, call, patch

import omni.kit.test
from omni.flux.utils.material_converter.utils import SupportedShaderInputs, SupportedShaderOutputs

from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.constants import ORPHAN_PARAMETER_CLEANUP_SETTING_PATH
from lightspeed.trex.asset_pipeline.core.steps import ConvertMaterialsStep
import lightspeed.trex.asset_pipeline.core.steps.convert_materials as convert_materials_module
from lightspeed.trex.asset_pipeline.core.steps.convert_materials import (
    _build_converter,
    _convert_material_if_needed,
    _select_output_shader,
)


class TestConvertMaterials(omni.kit.test.AsyncTestCase):
    """Test material conversion and shader identifier discovery."""

    async def test_build_converter_with_omni_glass_uses_omni_glass_builder(self):
        """OmniGlass conversion delegates to the OmniGlass converter builder."""
        # Arrange
        material_prim = MagicMock()
        converter = MagicMock()
        builder = MagicMock()
        builder.build.return_value = converter

        with patch.object(convert_materials_module, "OmniGlassToAperturePBRConverterBuilder", return_value=builder):
            # Act
            result = await _build_converter(
                material_prim,
                SupportedShaderInputs.OMNI_GLASS.value,
                SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT,
            )

        # Assert
        self.assertIs(result, converter)
        builder.build.assert_called_once_with(
            material_prim,
            SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT.value,
        )

    async def test_build_converter_with_translucent_omni_pbr_uses_none_builder(self):
        """A non-glass input that becomes translucent starts from a bare shader, as legacy did."""
        # Arrange
        material_prim = MagicMock()
        converter = MagicMock()
        builder = MagicMock()
        builder.build.return_value = converter

        with (
            patch.object(convert_materials_module, "NoneToAperturePBRConverterBuilder", return_value=builder),
            patch.object(convert_materials_module, "OmniPBRToAperturePBRConverterBuilder") as omni_pbr_builder,
        ):
            # Act
            result = await _build_converter(
                material_prim,
                SupportedShaderInputs.OMNI_PBR.value,
                SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT,
            )

        # Assert
        self.assertIs(result, converter)
        builder.build.assert_called_once_with(
            material_prim,
            SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT.value,
        )
        omni_pbr_builder.assert_not_called()

    async def test_build_converter_raises_for_unsupported_target_output(self):
        """Unsupported target shader outputs fail at the converter boundary."""
        # Arrange
        material_prim = MagicMock()
        target_output = _UnsupportedShaderOutput()

        # Act
        with self.assertRaises(ValueError) as error:
            await _build_converter(material_prim, SupportedShaderInputs.OMNI_PBR.value, target_output)

        # Assert
        self.assertIn("Unsupported material shader output", str(error.exception))

    def test_select_output_shader_preserves_aperture_variants(self):
        """AperturePBR inputs retain their authored output variant."""
        # Act
        outputs = (
            _select_output_shader(SupportedShaderOutputs.APERTURE_PBR_OPACITY.value),
            _select_output_shader(SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT.value),
        )

        # Assert
        self.assertEqual(
            outputs,
            (
                SupportedShaderOutputs.APERTURE_PBR_OPACITY,
                SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT,
            ),
        )

    def test_select_output_shader_maps_omni_glass_to_translucent(self):
        """OmniGlass converts to AperturePBR Translucent."""
        # Act
        output = _select_output_shader(SupportedShaderInputs.OMNI_GLASS.value)

        # Assert
        self.assertIs(output, SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT)

    def test_select_output_shader_maps_opaque_inputs_to_opacity(self):
        """Opaque input shaders convert to AperturePBR Opacity."""
        # Act
        outputs = tuple(
            _select_output_shader(shader.value)
            for shader in (
                SupportedShaderInputs.OMNI_PBR,
                SupportedShaderInputs.OMNI_PBR_OPACITY,
                SupportedShaderInputs.USD_PREVIEW_SURFACE,
            )
        )

        # Assert
        self.assertEqual(outputs, (SupportedShaderOutputs.APERTURE_PBR_OPACITY,) * 3)

    async def test_convert_material_without_converter_raises(self):
        """A supported shader without a converter fails before conversion."""
        # Arrange
        material_prim = MagicMock()
        material_prim.GetPath.return_value = "/World/Looks/MissingConverter"
        with (
            patch.object(
                convert_materials_module,
                "_get_material_shader_subidentifier",
                return_value=SupportedShaderInputs.OMNI_PBR.value,
            ),
            patch.object(convert_materials_module, "_build_converter", AsyncMock(return_value=None)),
        ):
            # Act
            with self.assertRaisesRegex(RuntimeError, "cannot convert"):
                await _convert_material_if_needed("", material_prim)

    async def test_convert_material_with_unsupported_shader_raises(self):
        """An unsupported authored shader fails through the converter error path."""
        # Arrange
        material_prim = MagicMock()
        material_prim.GetPath.return_value = "/World/Looks/Unsupported"

        with patch.object(
            convert_materials_module,
            "_get_material_shader_subidentifier",
            return_value="Unsupported",
        ):
            # Act
            with self.assertRaisesRegex(RuntimeError, "Unsupported material shader"):
                await _convert_material_if_needed("", material_prim)

    async def test_run_does_not_save_stage_when_materials_are_already_converted(self):
        """No-op material conversion does not rewrite the model file."""
        # Arrange
        material_prim = MagicMock()
        material_prim.GetPath.return_value = "/World/Looks/Material"
        material_prim.GetName.return_value = "Material"
        stage = MagicMock()
        stage.Traverse.return_value = [material_prim]
        stage.GetPrimAtPath.return_value = material_prim
        item = RemixAssetItem.from_model(pathlib.Path("/models/chair.usd"))
        context = RemixAssetPipelineContext(items=[item])
        context.open_stage = AsyncMock(return_value=stage)
        context.save_stage = AsyncMock()

        with patch.object(convert_materials_module, "_convert_material_if_needed", AsyncMock(return_value=False)):
            # Act
            await ConvertMaterialsStep().run(context)

        # Assert
        context.save_stage.assert_not_called()

    async def test_orphan_parameter_cleanup_restores_after_last_context(self):
        """Concurrent material conversion guards keep cleanup disabled until the last user exits."""
        # Arrange
        settings = MagicMock()
        settings.get.return_value = False
        setting_path = ORPHAN_PARAMETER_CLEANUP_SETTING_PATH

        with patch.object(convert_materials_module.carb.settings, "get_settings", return_value=settings):
            # Act
            with convert_materials_module._orphan_parameter_cleanup_disabled():
                with convert_materials_module._orphan_parameter_cleanup_disabled():
                    settings.set.assert_called_once_with(setting_path, True)
                settings.set.assert_called_once_with(setting_path, True)

        # Assert
        self.assertEqual(settings.set.call_args_list, [call(setting_path, True), call(setting_path, False)])


class _UnsupportedShaderOutput:
    value = "Unsupported"

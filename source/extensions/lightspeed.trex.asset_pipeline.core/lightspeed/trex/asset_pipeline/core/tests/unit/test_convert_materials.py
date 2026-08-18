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
from omni.flux.asset_pipeline.core import PipelineContext
from omni.flux.utils.material_converter.utils import SupportedShaderInputs, SupportedShaderOutputs

from lightspeed.trex.asset_pipeline.core import AssetKind, MaterialType, RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.constants import ORPHAN_PARAMETER_CLEANUP_SETTING_PATH
from lightspeed.trex.asset_pipeline.core.steps import ConvertMaterialsStep
import lightspeed.trex.asset_pipeline.core.steps.convert_materials as convert_materials_module
from lightspeed.trex.asset_pipeline.core.steps.convert_materials import _build_converter


class TestConvertMaterials(omni.kit.test.AsyncTestCase):
    """Test material conversion and shader identifier discovery."""

    async def test_validate_with_model_missing_material_type_returns_error(self):
        """The pipeline does not guess opacity/translucent; the caller sends that decision."""
        # Arrange
        item = RemixAssetItem(
            value=pathlib.Path("/models/chair.usd"),
            kind=AssetKind.MODEL,
            source_path=pathlib.Path("/models/chair.usd"),
        )
        context = RemixAssetPipelineContext(items=[item])

        # Act
        errors = ConvertMaterialsStep().validate(context)

        # Assert
        self.assertIn("must provide material_type", "\n".join(errors))

    async def test_validate_keeps_material_type_error_with_other_errors(self):
        """Material type validation stays visible when base validation also reports errors."""
        # Arrange
        item = RemixAssetItem(
            value=pathlib.Path("/models/chair.usd"),
            kind=AssetKind.MODEL,
            source_path=pathlib.Path("/models/chair.usd"),
        )
        context = PipelineContext(items=[item])

        # Act
        errors = ConvertMaterialsStep().validate(context)

        # Assert
        self.assertIn("expected context RemixAssetPipelineContext", "\n".join(errors))
        self.assertIn("must provide material_type", "\n".join(errors))

    async def test_build_converter_with_translucent_omni_pbr_uses_omni_pbr_builder(self):
        """Translucent conversion delegates to the OmniPBR converter builder."""
        # Arrange
        material_prim = MagicMock()
        converter = MagicMock()
        builder = MagicMock()
        builder.build.return_value = converter

        with patch.object(convert_materials_module, "OmniPBRToAperturePBRConverterBuilder", return_value=builder):
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

    async def test_run_does_not_save_stage_when_materials_are_already_converted(self):
        """No-op material conversion does not rewrite the model file."""
        # Arrange
        material_prim = MagicMock()
        material_prim.GetPath.return_value = "/World/Looks/Material"
        stage = MagicMock()
        stage.Traverse.return_value = [material_prim]
        stage.GetPrimAtPath.return_value = material_prim
        item = RemixAssetItem.from_model(pathlib.Path("/models/chair.usd"), MaterialType.OPAQUE)
        context = RemixAssetPipelineContext(items=[item])
        context.open_stage = MagicMock(return_value=stage)
        context.save_stage = MagicMock()

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

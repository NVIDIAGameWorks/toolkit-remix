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
from lightspeed.trex.asset_pipeline.core.steps.convert_materials import _convert_material_if_needed


class TestConvertMaterials(omni.kit.test.AsyncTestCase):
    """Test material conversion and shader identifier discovery."""

    async def test_aperture_materials_remain_unchanged(self):
        """Existing Aperture materials need no converter."""
        for output in SupportedShaderOutputs:
            with self.subTest(title=output.name):
                # Arrange
                material = MagicMock()
                with (
                    patch.object(convert_materials_module, "get_material_shader_prim", return_value=MagicMock()),
                    patch.object(
                        convert_materials_module, "_get_authored_shader_subidentifier", return_value=output.value
                    ),
                ):
                    # Act
                    converted = await _convert_material_if_needed("test_context", material)

                # Assert
                self.assertFalse(converted)

    async def test_convert_material_without_converter_raises(self):
        """A supported shader without a converter fails before conversion."""
        # Arrange
        material = MagicMock()
        material.GetPath.return_value = "/World/Looks/MissingConverter"
        material.GetName.return_value = "MissingConverter"
        builder = MagicMock()
        builder.build.return_value = None
        with (
            patch.object(convert_materials_module, "get_material_shader_prim", return_value=MagicMock()),
            patch.object(
                convert_materials_module,
                "_get_authored_shader_subidentifier",
                return_value=SupportedShaderInputs.OMNI_PBR.value,
            ),
            patch.object(convert_materials_module, "get_converter_builder", return_value=builder),
        ):
            # Act
            with self.assertRaisesRegex(RuntimeError, "Unsupported material shader"):
                await _convert_material_if_needed("test_context", material)

    async def test_convert_material_with_unsupported_shader_raises(self):
        """An unsupported authored shader fails through the registry error path."""
        # Arrange
        material = MagicMock()
        material.GetPath.return_value = "/World/Looks/Unsupported"
        with (
            patch.object(convert_materials_module, "get_material_shader_prim", return_value=MagicMock()),
            patch.object(convert_materials_module, "_get_authored_shader_subidentifier", return_value="Unsupported"),
        ):
            # Act
            with self.assertRaisesRegex(RuntimeError, "Unsupported material shader"):
                await _convert_material_if_needed("test_context", material)

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

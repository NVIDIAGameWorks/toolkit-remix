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

__all__ = ["TestApplyProcessedTexturesStep"]

import pathlib
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import lightspeed.trex.asset_pipeline.core.steps.apply_processed_textures as apply_module
import omni.kit.test
from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.jobs.models import ProcessedTexture
from lightspeed.trex.asset_pipeline.core.steps import ApplyProcessedTexturesStep
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.material_converter.utils import (
    TEXTURE_SOURCE_CHANNEL_CUSTOM_DATA_KEY,
    TEXTURE_SOURCE_FACTOR_CUSTOM_DATA_KEY,
)
from pxr import Sdf

_NAMESPACE, _CHANNEL_KEY = TEXTURE_SOURCE_CHANNEL_CUSTOM_DATA_KEY.split(":", 1)
_FACTOR_KEY = TEXTURE_SOURCE_FACTOR_CUSTOM_DATA_KEY.split(":", 1)[1]
_MATERIAL_PATH = "/World/Looks/Material"
_INPUT_NAME = "inputs:diffuse_texture"


class TestApplyProcessedTexturesStep(omni.kit.test.AsyncTestCase):
    """Test how texture application edits the source-marker metadata of one binding."""

    async def _run_with_custom_data(self, custom_data: dict, processed: bool) -> dict:
        """Run the step over one mocked material binding and return the authoring spec customData.

        Args:
            custom_data: Attribute customData authored on the binding before the step runs.
            processed: Whether a processed texture exists for the binding identity.

        Returns:
            The customData dictionary of the authoring spec after the step ran.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            model_path = temp_path / "work" / "mesh.usd"
            model_path.parent.mkdir()
            item = RemixAssetItem.from_model(model_path)
            context = RemixAssetPipelineContext(
                items=[item], work_dir=temp_path / "work", output_dir=temp_path / "processed"
            )
            processed_textures = {}
            if processed:
                processed_textures[(_MATERIAL_PATH, TextureTypes.DIFFUSE)] = ProcessedTexture(
                    key="albedo",
                    source_path=temp_path / "albedo.png",
                    asset_url=str(temp_path / "work" / "albedo.a.rtex.dds"),
                    texture_type=TextureTypes.DIFFUSE,
                )

            attr = MagicMock()
            attr.HasAuthoredValue.return_value = True
            attr.Get.return_value = Sdf.AssetPath("albedo.png", str(temp_path / "albedo.png"))
            attr.GetPath.return_value = Sdf.Path(f"{_MATERIAL_PATH}/Shader.{_INPUT_NAME}")
            shader = MagicMock()
            shader.GetPath.return_value = Sdf.Path(f"{_MATERIAL_PATH}/Shader")
            shader.GetAttribute.return_value = attr
            material = MagicMock()
            material.IsA.return_value = True
            material.GetPath.return_value = Sdf.Path(_MATERIAL_PATH)
            stage = MagicMock()
            stage.Traverse.return_value = [material]
            stage.GetPrimAtPath.return_value = shader
            authoring_layer = MagicMock(realPath=str(model_path), identifier=str(model_path))
            authoring_spec = MagicMock(layer=authoring_layer, default=Sdf.AssetPath("albedo.png"))
            authoring_spec.customData = custom_data

            with (
                patch.object(RemixAssetPipelineContext, "open_stage", AsyncMock(return_value=stage)),
                patch.object(apply_module, "get_source_texture_paths", return_value={}),
                patch.object(apply_module, "get_texture_source_identity", return_value=temp_path / "albedo.png"),
                patch.object(apply_module, "get_material_shader_prim", return_value=shader),
                patch.object(apply_module, "iter_texture_inputs", return_value=[(TextureTypes.DIFFUSE, _INPUT_NAME)]),
                patch.object(apply_module, "run_in_worker_thread", AsyncMock(return_value=True)),
                patch.object(apply_module, "get_authoring_spec", return_value=authoring_spec),
                patch.object(apply_module.omni.client, "make_relative_url", return_value="./albedo.a.rtex.dds"),
                patch.object(Sdf, "ChangeBlock"),
            ):
                await ApplyProcessedTexturesStep(processed_textures).run(context)
            return authoring_spec.customData

    async def test_run_removes_markers_and_keeps_sibling_metadata_of_processed_binding(self):
        """Marker removal on a processed binding keeps unrelated keys in the same namespace."""
        # Arrange
        custom_data = {_NAMESPACE: {_CHANNEL_KEY: "G", _FACTOR_KEY: (0.5,), "sibling": "kept"}}

        # Act
        result = await self._run_with_custom_data(custom_data, processed=True)

        # Assert
        self.assertEqual(result, {_NAMESPACE: {"sibling": "kept"}})

    async def test_run_deletes_namespace_when_markers_were_its_only_entries(self):
        """Marker removal deletes the namespace once no entry remains."""
        # Arrange
        custom_data = {_NAMESPACE: {_CHANNEL_KEY: "G"}, "other": {"kept": True}}

        # Act
        result = await self._run_with_custom_data(custom_data, processed=True)

        # Assert
        self.assertEqual(result, {"other": {"kept": True}})

    async def test_run_keeps_markers_of_unprocessed_binding(self):
        """A binding without a processed texture keeps its source markers."""
        # Arrange
        custom_data = {_NAMESPACE: {_CHANNEL_KEY: "G"}}

        # Act
        result = await self._run_with_custom_data(custom_data, processed=False)

        # Assert
        self.assertEqual(result, {_NAMESPACE: {_CHANNEL_KEY: "G"}})

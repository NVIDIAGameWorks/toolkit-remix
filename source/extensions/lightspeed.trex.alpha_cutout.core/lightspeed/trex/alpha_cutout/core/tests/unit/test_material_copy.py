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

__all__ = ["TestCopyMaterialFlattened"]

import tempfile
from pathlib import Path

import numpy as np
import omni.client
from lightspeed.trex.alpha_cutout.core.material_copy import ALPHA_TEST_ALWAYS, copy_material_flattened
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdShade

from .fixtures import MATERIAL_PATH, build_capture_stage, write_alpha_texture

_DESTINATION_PATH = "/cutout_AAAAAAAAAAAAAAAA/Looks/AlphaCutoutMaterial"


class TestCopyMaterialFlattened(AsyncTestCase):
    """Test the flattened material copy."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        textures = Path(self._temp_dir.name) / "textures"
        textures.mkdir()
        self._texture = write_alpha_texture(textures / "alpha.png", np.full((4, 4), 255, np.uint8))
        self._output_file = omni.client.normalize_url(str(Path(self._temp_dir.name) / "out" / "mesh_cutout.usda"))
        Path(self._output_file).parent.mkdir()
        self._source_stage = build_capture_stage(self._texture)
        self._source_material = UsdShade.Material(self._source_stage.GetPrimAtPath(MATERIAL_PATH))
        self._destination_stage = Usd.Stage.CreateNew(self._output_file)

    def tearDown(self):
        self._destination_stage = None
        self._source_stage = None
        self._temp_dir.cleanup()

    async def test_copy_material_copies_shader_attributes_and_kind(self):
        # Arrange
        destination = self._destination_stage

        # Act
        material = copy_material_flattened(
            self._source_material, destination, _DESTINATION_PATH, self._output_file, False
        )

        # Assert
        shader = UsdShade.Shader(destination.GetPrimAtPath(f"{_DESTINATION_PATH}/Shader"))
        self.assertEqual(material.GetPath(), Sdf.Path(_DESTINATION_PATH))
        self.assertEqual(shader.GetSourceAssetSubIdentifier("mdl"), "AperturePBR_Opacity")
        self.assertEqual(shader.GetSourceAsset("mdl").path, "AperturePBR_Opacity.mdl")
        self.assertFalse(shader.GetInput("enable_opacity").Get())
        self.assertEqual(shader.GetPrim().GetMetadata("kind"), "Material")
        self.assertEqual(shader.GetInput("diffuse_texture").GetAttr().GetColorSpace(), "auto")

    async def test_copy_material_rewrites_texture_path_relative_to_output_file(self):
        # Arrange
        destination = self._destination_stage

        # Act
        copy_material_flattened(self._source_material, destination, _DESTINATION_PATH, self._output_file, False)

        # Assert
        asset = destination.GetAttributeAtPath(f"{_DESTINATION_PATH}/Shader.inputs:diffuse_texture").Get()
        self.assertFalse(Path(asset.path).is_absolute())
        resolved = destination.GetRootLayer().ComputeAbsolutePath(asset.path)
        self.assertEqual(omni.client.normalize_url(resolved).lower(), omni.client.normalize_url(self._texture).lower())

    async def test_copy_material_connects_surface_output_to_copied_shader(self):
        # Arrange
        destination = self._destination_stage

        # Act
        material = copy_material_flattened(
            self._source_material, destination, _DESTINATION_PATH, self._output_file, False
        )

        # Assert
        shader, source_name, _ = material.ComputeSurfaceSource("mdl")
        self.assertEqual(shader.GetPath(), Sdf.Path(f"{_DESTINATION_PATH}/Shader"))
        self.assertEqual(source_name, "out")

    async def test_copy_material_with_disable_alpha_test_authors_opaque_alpha_state(self):
        # Arrange
        destination = self._destination_stage

        # Act
        copy_material_flattened(self._source_material, destination, _DESTINATION_PATH, self._output_file, True)

        # Assert
        shader = UsdShade.Shader(destination.GetPrimAtPath(f"{_DESTINATION_PATH}/Shader"))
        self.assertFalse(shader.GetInput("use_legacy_alpha_state").Get())
        self.assertFalse(shader.GetInput("blend_enabled").Get())
        self.assertEqual(shader.GetInput("alpha_test_type").Get(), ALPHA_TEST_ALWAYS)
        self.assertEqual(ALPHA_TEST_ALWAYS, 7)

    async def test_copy_material_without_disable_alpha_test_leaves_alpha_state_unauthored(self):
        # Arrange
        destination = self._destination_stage

        # Act
        copy_material_flattened(self._source_material, destination, _DESTINATION_PATH, self._output_file, False)

        # Assert
        shader = UsdShade.Shader(destination.GetPrimAtPath(f"{_DESTINATION_PATH}/Shader"))
        self.assertFalse(bool(shader.GetInput("use_legacy_alpha_state")))
        self.assertFalse(bool(shader.GetInput("alpha_test_type")))

    async def test_copy_material_name_does_not_use_capture_material_prefix(self):
        # Arrange
        destination = self._destination_stage

        # Act
        material = copy_material_flattened(
            self._source_material, destination, _DESTINATION_PATH, self._output_file, False
        )

        # Assert
        self.assertFalse(material.GetPrim().GetName().startswith("mat_"))

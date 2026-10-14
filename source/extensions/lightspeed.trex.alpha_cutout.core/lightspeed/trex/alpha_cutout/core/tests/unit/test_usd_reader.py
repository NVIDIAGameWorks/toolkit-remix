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

__all__ = ["TestReadMeshSource"]

import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import omni.client
from lightspeed.trex.alpha_cutout.core.usd_reader import (
    REPLACEMENT_SUFFIX,
    get_mesh_hash,
    read_mesh_source,
    read_mesh_sources,
    read_replacement_mesh_source,
    replacement_original_path,
    replacement_output_path,
    resolve_conversion_target,
)
from omni.kit.test import AsyncTestCase
from pxr import Gf, Sdf, UsdGeom, UsdSkel

from .fixtures import (
    MESH_HASH,
    MESH_PRIM_PATH,
    MESH_ROOT_PATH,
    REPLACEMENT_CARD_FILE_PATH,
    REPLACEMENT_CARD_PATH,
    REPLACEMENT_REF_PATH,
    REPLACEMENT_TRUNK_PATH,
    build_capture_stage,
    build_replacement_stage,
    write_alpha_texture,
    write_replacement_file,
)

_CAPTURE_CHECK = "lightspeed.trex.alpha_cutout.core.usd_reader._AssetReplacementsCore.prim_is_from_a_capture_reference"


class TestReadMeshSource(AsyncTestCase):
    """Test reading capture meshes into worker-safe sources."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._texture = write_alpha_texture(Path(self._temp_dir.name) / "alpha.png", np.full((4, 4), 255, np.uint8))

    def tearDown(self):
        self._temp_dir.cleanup()

    async def test_get_mesh_hash_with_prototype_path_returns_hash(self):
        # Arrange
        path = MESH_ROOT_PATH

        # Act
        result = get_mesh_hash(path)

        # Assert
        self.assertEqual(result, MESH_HASH)

    async def test_get_mesh_hash_with_other_path_returns_empty_string(self):
        # Arrange
        path = "/RootNode/Looks/mat_BBBBBBBBBBBBBBBB"

        # Act
        result = get_mesh_hash(path)

        # Assert
        self.assertEqual(result, "")

    async def test_read_mesh_source_with_vertex_st_reads_geometry_normals_transform_and_texture(self):
        # Arrange
        stage = build_capture_stage(self._texture)

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        self.assertIsNone(source.skip_reason)
        self.assertEqual(source.mesh_hash, MESH_HASH)
        self.assertEqual(source.points.shape, (4, 3))
        self.assertEqual(source.triangles.tolist(), [[0, 1, 2], [0, 2, 3]])
        self.assertEqual(source.st.shape, (2, 3, 2))
        np.testing.assert_allclose(source.st[1], [[0, 0], [1, 1], [0, 1]])
        self.assertEqual(source.normals.shape, (2, 3, 3))
        self.assertEqual(len(source.transform), 16)
        self.assertAlmostEqual(source.transform[6], 1.0)
        self.assertTrue(source.double_sided)
        self.assertEqual(source.orientation, UsdGeom.Tokens.leftHanded)
        self.assertEqual(source.texture_path, omni.client.normalize_url(self._texture))
        self.assertFalse(source.time_sampled)

    async def test_read_mesh_source_with_quad_face_fan_triangulates(self):
        # Arrange
        stage = build_capture_stage(self._texture, face_counts=[4])

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        self.assertEqual(source.triangles.tolist(), [[0, 1, 2], [0, 2, 3]])

    async def test_read_mesh_source_with_face_varying_st_reads_per_corner_values(self):
        # Arrange
        stage = build_capture_stage(self._texture, st_interpolation=UsdGeom.Tokens.faceVarying)

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        self.assertIsNone(source.skip_reason)
        np.testing.assert_allclose(source.st[0], [[0, 0], [1, 0], [1, 1]])

    async def test_read_mesh_source_with_indexed_st_flattens_indices(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        primvar = UsdGeom.PrimvarsAPI(stage.GetPrimAtPath(MESH_PRIM_PATH)).GetPrimvar("st")
        primvar.Set([Gf.Vec2f(0, 0), Gf.Vec2f(1, 1)])
        primvar.SetIndices([0, 1, 1, 0])

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        np.testing.assert_allclose(source.st[0], [[0, 0], [1, 1], [1, 1]])

    async def test_read_mesh_source_with_constant_st_reports_skip_reason(self):
        # Arrange
        stage = build_capture_stage(self._texture, st_interpolation=UsdGeom.Tokens.constant)

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        self.assertIn("interpolation", source.skip_reason)

    async def test_read_mesh_source_with_time_sampled_points_falls_back_to_first_sample(self):
        # Arrange
        stage = build_capture_stage(self._texture, time_sampled_points=True)

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        self.assertIsNone(source.skip_reason)
        self.assertTrue(source.time_sampled)
        self.assertEqual(source.points.shape, (4, 3))

    async def test_read_mesh_source_with_skeleton_binding_reports_skip_reason(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        UsdSkel.BindingAPI.Apply(stage.GetPrimAtPath(MESH_PRIM_PATH))

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        self.assertIn("Skinned", source.skip_reason)

    async def test_read_mesh_source_without_diffuse_texture_reports_skip_reason(self):
        # Arrange
        stage = build_capture_stage(None)

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        self.assertIn("diffuse texture", source.skip_reason)

    async def test_read_mesh_source_without_transform_op_returns_no_transform(self):
        # Arrange
        stage = build_capture_stage(self._texture, with_transform=False, with_normals=False)

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        self.assertIsNone(source.transform)
        self.assertIsNone(source.normals)

    async def test_read_mesh_source_with_missing_prim_reports_skip_reason(self):
        # Arrange
        stage = build_capture_stage(self._texture)

        # Act
        source = read_mesh_source(stage, "/RootNode/meshes/mesh_CCCCCCCCCCCCCCCC")

        # Assert
        self.assertEqual(source.skip_reason, "The prim does not exist.")

    async def test_replacement_output_path_adds_suffix_and_original_path_strips_it(self):
        # Arrange
        original = "C:/mods/assets/fern01.usd"

        # Act
        output = replacement_output_path(original)
        back = replacement_original_path(output)

        # Assert
        self.assertEqual(output, f"C:/mods/assets/fern01{REPLACEMENT_SUFFIX}.usd")
        self.assertEqual(back, original)
        self.assertEqual(replacement_original_path(original), original)

    async def test_resolve_conversion_target_with_replacement_mesh_lists_textured_meshes_and_output_file(self):
        # Arrange
        replacement = write_replacement_file(Path(self._temp_dir.name) / "fern01.usda", self._texture)
        stage = build_replacement_stage(replacement)

        # Act
        target = resolve_conversion_target(stage, REPLACEMENT_TRUNK_PATH)

        # Assert
        self.assertTrue(target.is_replacement)
        self.assertEqual(target.root_path, REPLACEMENT_REF_PATH)
        self.assertEqual(target.prim_path, REPLACEMENT_TRUNK_PATH)
        self.assertEqual(target.meshes, (REPLACEMENT_CARD_PATH,))
        self.assertEqual(target.original_file, replacement)
        self.assertEqual(target.output_file, replacement_output_path(replacement))

    async def test_resolve_conversion_target_with_reference_to_cutout_file_strips_suffix_for_original(self):
        # Arrange
        cutout = write_replacement_file(Path(self._temp_dir.name) / f"fern01{REPLACEMENT_SUFFIX}.usda", self._texture)
        stage = build_replacement_stage(cutout)

        # Act
        target = resolve_conversion_target(stage, REPLACEMENT_CARD_PATH)

        # Assert
        self.assertEqual(target.original_file, replacement_original_path(cutout))
        self.assertEqual(target.output_file, cutout)

    async def test_resolve_conversion_target_with_reference_to_capture_cutout_returns_capture_target(self):
        # Arrange
        cutout = write_replacement_file(Path(self._temp_dir.name) / f"cutout_{MESH_HASH}.usda", self._texture)
        stage = build_replacement_stage(cutout)

        # Act
        with patch(_CAPTURE_CHECK, return_value=True):
            target = resolve_conversion_target(stage, REPLACEMENT_CARD_PATH)

        # Assert
        self.assertFalse(target.is_replacement)
        self.assertEqual(target.root_path, MESH_ROOT_PATH)
        self.assertEqual(target.meshes, (MESH_ROOT_PATH,))

    async def test_resolve_conversion_target_with_capture_mesh_returns_capture_target(self):
        # Arrange
        stage = build_capture_stage(self._texture)

        # Act
        with patch(_CAPTURE_CHECK, return_value=True):
            target = resolve_conversion_target(stage, MESH_PRIM_PATH)

        # Assert
        self.assertFalse(target.is_replacement)
        self.assertEqual(target.prim_path, MESH_ROOT_PATH)

    async def test_read_replacement_mesh_source_reads_file_geometry_and_stage_material(self):
        # Arrange
        replacement = write_replacement_file(Path(self._temp_dir.name) / "fern01.usda", self._texture)
        stage = build_replacement_stage(replacement)
        target = resolve_conversion_target(stage, REPLACEMENT_CARD_PATH)

        # Act
        source = read_replacement_mesh_source(stage, target, REPLACEMENT_CARD_PATH)

        # Assert
        self.assertIsNone(source.skip_reason)
        self.assertEqual(source.points.shape, (4, 3))
        self.assertEqual(source.triangles.shape, (2, 3))
        self.assertEqual(source.file_prim_path, REPLACEMENT_CARD_FILE_PATH)
        self.assertEqual(source.ref_prim_path, REPLACEMENT_REF_PATH)
        self.assertEqual(source.replacement_file, replacement)
        self.assertEqual(source.texture_path.lower(), omni.client.normalize_url(self._texture).lower())
        self.assertEqual(source.up_axis, "Z")

    async def test_read_mesh_sources_with_replacement_target_skips_untextured_mesh(self):
        # Arrange
        replacement = write_replacement_file(Path(self._temp_dir.name) / "fern01.usda", self._texture)
        stage = build_replacement_stage(replacement)
        target = resolve_conversion_target(stage, REPLACEMENT_CARD_PATH)

        # Act
        sources = read_mesh_sources(stage, [REPLACEMENT_CARD_PATH, REPLACEMENT_TRUNK_PATH], target)

        # Assert
        self.assertIsNone(sources[0].skip_reason)
        self.assertEqual(sources[1].skip_reason, "The bound material has no diffuse texture.")

    async def test_read_mesh_sources_returns_one_source_per_path_in_order(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        paths = ["/RootNode/meshes/mesh_CCCCCCCCCCCCCCCC", MESH_ROOT_PATH]

        # Act
        sources = read_mesh_sources(stage, paths)

        # Assert
        self.assertEqual([source.prim_path for source in sources], paths)
        self.assertIsNotNone(sources[0].skip_reason)
        self.assertIsNone(sources[1].skip_reason)

    async def test_read_mesh_source_with_asset_path_without_resolved_path_computes_absolute_path(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        attribute = stage.GetAttributeAtPath("/RootNode/Looks/mat_BBBBBBBBBBBBBBBB/Shader.inputs:diffuse_texture")
        attribute.Set(Sdf.AssetPath(str(Path(self._temp_dir.name) / "missing.png")))

        # Act
        source = read_mesh_source(stage, MESH_ROOT_PATH)

        # Assert
        self.assertTrue(source.texture_path.endswith("missing.png"))

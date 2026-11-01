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

import numpy as np
import omni.client
from lightspeed.trex.alpha_cutout.core.usd_reader import (
    get_bound_material,
    get_diffuse_texture_path,
    is_convertible_mesh,
    read_mesh_source,
)
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom, UsdSkel

from .fixtures import MESH_PRIM_PATH, build_capture_stage, write_alpha_texture

_TEXTURE = "unused.png"


class TestReadMeshSource(AsyncTestCase):
    """Test reading mesh geometry and material lookups."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._texture = write_alpha_texture(Path(self._temp_dir.name) / "alpha.png", np.full((4, 4), 255, np.uint8))

    def tearDown(self):
        self._temp_dir.cleanup()

    async def test_read_mesh_source_with_vertex_st_reads_geometry_normals_and_transform(self):
        # Arrange
        stage = build_capture_stage(self._texture)

        # Act
        source = read_mesh_source(stage, MESH_PRIM_PATH, _TEXTURE)

        # Assert
        self.assertIsNone(source.skip_reason)
        self.assertEqual(source.points.shape, (4, 3))
        self.assertEqual(source.triangles.shape, (2, 3))
        self.assertEqual(source.st.shape, (2, 3, 2))
        self.assertEqual(source.normals.shape, (2, 3, 3))
        self.assertEqual(len(source.transform), 16)
        self.assertTrue(source.double_sided)
        self.assertEqual(source.orientation, UsdGeom.Tokens.leftHanded)
        self.assertEqual(source.texture_path, _TEXTURE)
        self.assertEqual(source.up_axis, "Z")

    async def test_read_mesh_source_with_quad_face_fan_triangulates(self):
        # Arrange
        stage = build_capture_stage(self._texture, face_counts=[4])

        # Act
        source = read_mesh_source(stage, MESH_PRIM_PATH, _TEXTURE)

        # Assert
        np.testing.assert_array_equal(source.triangles, [[0, 1, 2], [0, 2, 3]])

    async def test_read_mesh_source_with_face_varying_st_reads_per_corner_values(self):
        # Arrange
        stage = build_capture_stage(self._texture, st_interpolation=UsdGeom.Tokens.faceVarying)

        # Act
        source = read_mesh_source(stage, MESH_PRIM_PATH, _TEXTURE)

        # Assert
        np.testing.assert_allclose(source.st[1], [[0, 0], [1, 1], [0, 1]])

    async def test_read_mesh_source_with_indexed_st_flattens_indices(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        primvar = UsdGeom.PrimvarsAPI(stage.GetPrimAtPath(MESH_PRIM_PATH)).GetPrimvar("st")
        primvar.Set([(0, 0), (1, 1)])
        primvar.SetIndices([0, 1, 1, 0])

        # Act
        source = read_mesh_source(stage, MESH_PRIM_PATH, _TEXTURE)

        # Assert
        np.testing.assert_allclose(source.st[0], [[0, 0], [1, 1], [1, 1]])

    async def test_read_mesh_source_with_constant_st_reports_skip_reason(self):
        # Arrange
        stage = build_capture_stage(self._texture, st_interpolation=UsdGeom.Tokens.constant)

        # Act
        source = read_mesh_source(stage, MESH_PRIM_PATH, _TEXTURE)

        # Assert
        self.assertIn("not supported", source.skip_reason)

    async def test_read_mesh_source_with_time_sampled_points_falls_back_to_first_sample(self):
        # Arrange
        stage = build_capture_stage(self._texture, time_sampled_points=True)

        # Act
        source = read_mesh_source(stage, MESH_PRIM_PATH, _TEXTURE)

        # Assert
        self.assertIsNone(source.skip_reason)
        self.assertTrue(source.time_sampled)

    async def test_read_mesh_source_with_skeleton_binding_reports_skip_reason(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        UsdSkel.BindingAPI.Apply(stage.GetPrimAtPath(MESH_PRIM_PATH))

        # Act
        source = read_mesh_source(stage, MESH_PRIM_PATH, _TEXTURE)

        # Assert
        self.assertEqual(source.skip_reason, "Skinned meshes are not supported.")

    async def test_read_mesh_source_without_transform_op_returns_no_transform(self):
        # Arrange
        stage = build_capture_stage(self._texture, with_transform=False, with_normals=False)

        # Act
        source = read_mesh_source(stage, MESH_PRIM_PATH, _TEXTURE)

        # Assert
        self.assertIsNone(source.transform)
        self.assertIsNone(source.normals)

    async def test_read_mesh_source_with_missing_prim_reports_skip_reason(self):
        # Arrange
        stage = build_capture_stage(self._texture)

        # Act
        source = read_mesh_source(stage, "/RootNode/meshes/missing/mesh", _TEXTURE)

        # Assert
        self.assertEqual(source.skip_reason, "The mesh does not exist in the model file.")

    async def test_get_diffuse_texture_path_returns_absolute_texture_of_bound_material(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        material = get_bound_material(stage.GetPrimAtPath(MESH_PRIM_PATH))

        # Act
        texture = get_diffuse_texture_path(material)

        # Assert
        self.assertEqual(texture.lower(), omni.client.normalize_url(self._texture).lower())

    async def test_get_diffuse_texture_path_without_texture_returns_none(self):
        # Arrange
        stage = build_capture_stage(None)
        material = get_bound_material(stage.GetPrimAtPath(MESH_PRIM_PATH))

        # Act
        texture = get_diffuse_texture_path(material)

        # Assert
        self.assertIsNone(texture)

    async def test_get_diffuse_texture_path_with_unresolved_asset_computes_absolute_path(self):
        # Arrange: a relative asset path only resolves against a layer on disk.
        scene = Path(self._temp_dir.name) / "scene.usda"
        source_stage = build_capture_stage(self._texture)
        source_stage.GetRootLayer().Export(str(scene))
        stage = Usd.Stage.Open(str(scene))
        material = get_bound_material(stage.GetPrimAtPath(MESH_PRIM_PATH))
        shader_input = stage.GetAttributeAtPath(f"{material.GetPath()}/Shader.inputs:diffuse_texture")
        shader_input.Set(Sdf.AssetPath(Path(self._texture).name))

        # Act
        texture = get_diffuse_texture_path(material)

        # Assert
        self.assertTrue(texture.lower().endswith("/alpha.png"))

    async def test_is_convertible_mesh_rejects_subsets_and_skinned_meshes(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        mesh = stage.GetPrimAtPath(MESH_PRIM_PATH)
        plain = is_convertible_mesh(mesh)
        UsdGeom.Subset.Define(stage, mesh.GetPath().AppendChild("subset"))

        # Act
        with_subset = is_convertible_mesh(mesh)

        # Assert
        self.assertTrue(plain)
        self.assertFalse(with_subset)
        self.assertFalse(is_convertible_mesh(mesh.GetParent()))

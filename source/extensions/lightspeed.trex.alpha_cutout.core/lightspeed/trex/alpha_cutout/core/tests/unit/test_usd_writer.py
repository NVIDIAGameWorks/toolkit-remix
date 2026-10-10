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

__all__ = ["TestWriteCutoutMesh"]

import dataclasses
import tempfile
from pathlib import Path

import numpy as np
from lightspeed.trex.alpha_cutout.core.data_models import CutMesh
from lightspeed.trex.alpha_cutout.core.usd_reader import (
    REPLACEMENT_SUFFIX,
    read_mesh_source,
    replacement_output_path,
)
from lightspeed.trex.alpha_cutout.core.usd_writer import (
    MATERIAL_PRIM_NAME,
    REFERENCE_TARGET_PRIM_NAME,
    cutout_file_name,
    cutout_output_path,
    cutout_root_prim_name,
    write_cutout_mesh,
    write_cutout_replacement,
)
from lightspeed.trex.utils.common.asset_utils import is_asset_ingested
from omni.flux.utils.common import path_utils
from omni.flux.validator.factory import BASE_HASH_KEY, VALIDATION_PASSED
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom, UsdShade

from .fixtures import (
    MESH_HASH,
    MESH_ROOT_PATH,
    REPLACEMENT_CARD_FILE_PATH,
    build_capture_stage,
    quad_cut_mesh,
    write_alpha_texture,
    write_replacement_file,
)


def _cutout_root(stage: Usd.Stage) -> Usd.Prim:
    """Return the cutout Xform below the ingestion style wrapper prims."""
    return stage.GetDefaultPrim().GetChild("XForms").GetChild(cutout_root_prim_name(MESH_HASH))


class TestWriteCutoutMesh(AsyncTestCase):
    """Test writing the replacement file."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._texture = write_alpha_texture(Path(self._temp_dir.name) / "alpha.png", np.full((4, 4), 255, np.uint8))
        self._stage = build_capture_stage(self._texture)
        self._source = read_mesh_source(self._stage, MESH_ROOT_PATH)
        self._output_dir = str(Path(self._temp_dir.name) / "out")

    def tearDown(self):
        self._stage = None
        self._temp_dir.cleanup()

    async def test_cutout_file_name_and_root_prim_name_avoid_capture_naming(self):
        # Arrange
        mesh_hash = MESH_HASH

        # Act
        file_name = cutout_file_name(mesh_hash)
        prim_name = cutout_root_prim_name(mesh_hash)

        # Assert
        self.assertEqual(file_name, f"cutout_{MESH_HASH}.usda")
        self.assertEqual(prim_name, f"cutout_{MESH_HASH}")
        self.assertFalse(prim_name.startswith("mesh_"))

    async def test_write_cutout_mesh_creates_default_prim_mesh_and_bound_material_copy(self):
        # Arrange
        cut_mesh = quad_cut_mesh()

        # Act
        path = write_cutout_mesh(self._output_dir, self._source, cut_mesh, self._stage, True)

        # Assert
        self.assertEqual(path, cutout_output_path(self._output_dir, MESH_HASH))
        stage = Usd.Stage.Open(path)
        reference_target = stage.GetDefaultPrim()
        self.assertEqual(reference_target.GetName(), REFERENCE_TARGET_PRIM_NAME)
        self.assertEqual(UsdGeom.Xform(reference_target).GetOrderedXformOps()[0].GetOpName(), "xformOp:translate")
        root = reference_target.GetChild("XForms").GetChild(cutout_root_prim_name(MESH_HASH))
        self.assertTrue(root.IsValid())
        mesh = UsdGeom.Mesh(root.GetChild("mesh"))
        self.assertEqual(len(mesh.GetPointsAttr().Get()), 4)
        self.assertEqual(list(mesh.GetFaceVertexCountsAttr().Get()), [3, 3])
        self.assertEqual(list(mesh.GetFaceVertexIndicesAttr().Get()), [0, 1, 2, 0, 2, 3])
        st = UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
        self.assertEqual(st.GetInterpolation(), UsdGeom.Tokens.vertex)
        self.assertEqual(len(st.Get()), 4)
        self.assertEqual(mesh.GetNormalsInterpolation(), UsdGeom.Tokens.vertex)
        self.assertTrue(mesh.GetDoubleSidedAttr().Get())
        self.assertEqual(mesh.GetOrientationAttr().Get(), UsdGeom.Tokens.leftHanded)
        self.assertEqual(mesh.GetSubdivisionSchemeAttr().Get(), UsdGeom.Tokens.none)
        self.assertIsNotNone(mesh.GetExtentAttr().Get())
        self.assertEqual(UsdGeom.GetStageUpAxis(stage), UsdGeom.Tokens.z)
        bound, _ = UsdShade.MaterialBindingAPI(mesh.GetPrim()).ComputeBoundMaterial()
        self.assertEqual(bound.GetPrim().GetName(), MATERIAL_PRIM_NAME)
        self.assertEqual(bound.GetPath(), root.GetPath().AppendChild("Looks").AppendChild(MATERIAL_PRIM_NAME))
        shader = UsdShade.Shader(bound.GetPrim().GetChild("Shader"))
        self.assertEqual(shader.GetInput("alpha_test_type").Get(), 7)

    async def test_write_cutout_mesh_round_trips_transform_op(self):
        # Arrange
        cut_mesh = quad_cut_mesh()

        # Act
        path = write_cutout_mesh(self._output_dir, self._source, cut_mesh, self._stage, False)

        # Assert
        stage = Usd.Stage.Open(path)
        mesh = UsdGeom.Mesh(_cutout_root(stage).GetChild("mesh"))
        ops = mesh.GetOrderedXformOps()
        self.assertEqual(len(ops), 1)
        matrix = ops[0].Get()
        self.assertAlmostEqual(matrix[1][2], 1.0)
        self.assertAlmostEqual(matrix[2][1], -1.0)

    async def test_write_cutout_mesh_writes_ingestion_sidecar(self):
        # Arrange
        cut_mesh = quad_cut_mesh()

        # Act
        path = write_cutout_mesh(self._output_dir, self._source, cut_mesh, self._stage, False)

        # Assert
        self.assertTrue(Path(path + ".meta").exists())
        self.assertEqual(path_utils.read_metadata(path, BASE_HASH_KEY), path_utils.hash_file(path))
        self.assertTrue(path_utils.read_metadata(path, VALIDATION_PASSED))
        self.assertTrue(is_asset_ingested(path, ignore_invalid_paths=False))

    async def test_write_cutout_mesh_twice_overwrites_file_and_keeps_single_prim_tree(self):
        # Arrange
        first = write_cutout_mesh(self._output_dir, self._source, quad_cut_mesh(), self._stage, False)
        quad = quad_cut_mesh()
        smaller = CutMesh(
            points=quad.points[:3], triangles=quad.triangles[:1], st=quad.st[:3], normals=quad.normals[:3]
        )

        # Act
        second = write_cutout_mesh(self._output_dir, self._source, smaller, self._stage, False)

        # Assert
        self.assertEqual(first, second)
        stage = Usd.Stage.Open(second)
        root = _cutout_root(stage)
        self.assertEqual([child.GetName() for child in root.GetChildren()], ["mesh", "Looks"])
        self.assertEqual(len(UsdGeom.Mesh(root.GetChild("mesh")).GetPointsAttr().Get()), 3)

    async def test_write_cutout_mesh_with_layer_open_in_memory_reuses_that_layer(self):
        # Arrange
        first = write_cutout_mesh(self._output_dir, self._source, quad_cut_mesh(), self._stage, False)
        held = Sdf.Layer.FindOrOpen(first)

        # Act
        write_cutout_mesh(self._output_dir, self._source, quad_cut_mesh(), self._stage, True)

        # Assert
        material_path = (
            f"/{REFERENCE_TARGET_PRIM_NAME}/XForms/{cutout_root_prim_name(MESH_HASH)}/Looks/{MATERIAL_PRIM_NAME}"
        )
        shader_spec = held.GetAttributeAtPath(f"{material_path}/Shader.inputs:alpha_test_type")
        self.assertIsNotNone(shader_spec)
        self.assertEqual(shader_spec.default, 7)

    async def test_write_cutout_replacement_rewrites_only_the_listed_mesh_and_keeps_the_rest(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            texture = write_alpha_texture(Path(temp_dir) / "card.png", np.full((8, 8), 255, dtype=np.uint8))
            original = write_replacement_file(Path(temp_dir) / "fern01.usda", texture)
            original_text = Path(original).read_text()
            cut_mesh = dataclasses.replace(quad_cut_mesh(), triangles=np.array([[0, 1, 2]], dtype=np.int32))

            # Act
            output = write_cutout_replacement(
                original, replacement_output_path(original), [(REPLACEMENT_CARD_FILE_PATH, cut_mesh)], True
            )

            # Assert
            stage = Usd.Stage.Open(output)
            card = UsdGeom.Mesh(stage.GetPrimAtPath(REPLACEMENT_CARD_FILE_PATH))
            trunk = UsdGeom.Mesh(stage.GetPrimAtPath("/ReferenceTarget/XForms/trunk/mesh"))
            shader = UsdShade.Shader(stage.GetPrimAtPath("/ReferenceTarget/Looks/card_mat/Shader"))
            trunk_shader = UsdShade.Shader(stage.GetPrimAtPath("/ReferenceTarget/Looks/trunk_mat/Shader"))
            self.assertTrue(output.endswith(f"{REPLACEMENT_SUFFIX}.usda"))
            self.assertEqual(len(card.GetFaceVertexCountsAttr().Get()), 1)
            self.assertEqual(len(trunk.GetFaceVertexCountsAttr().Get()), 2)
            self.assertEqual(stage.GetDefaultPrim().GetName(), "ReferenceTarget")
            self.assertEqual(shader.GetInput("alpha_test_type").Get(), 7)
            self.assertIsNone(trunk_shader.GetInput("alpha_test_type").Get())
            self.assertEqual(Path(original).read_text(), original_text)
            self.assertTrue(is_asset_ingested(output))

    async def test_write_cutout_replacement_with_output_equal_to_original_raises_value_error(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            original = write_replacement_file(Path(temp_dir) / "fern01.usda", None)

            # Act / Assert
            with self.assertRaises(ValueError):
                write_cutout_replacement(original, original, [], False)

    async def test_write_cutout_mesh_without_material_raises_value_error(self):
        # Arrange
        source = dataclasses.replace(self._source, material_path=None)

        # Act / Assert
        with self.assertRaises(ValueError):
            write_cutout_mesh(self._output_dir, source, quad_cut_mesh(), self._stage, False)

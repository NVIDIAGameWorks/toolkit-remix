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

__all__ = ["TestWriteCutoutFile"]

import dataclasses
import tempfile
from pathlib import Path

import numpy as np
import omni.client
from lightspeed.trex.alpha_cutout.core.cutout_file import (
    MATERIAL_PRIM_ATTR,
    MATERIAL_PRIM_NAME,
    SOURCE_FILE_ATTR,
    SOURCE_PRIM_ATTR,
    MeshConversion,
    author_geometry,
    read_origin,
    write_cutout_file,
)
from lightspeed.trex.alpha_cutout.core.material_snapshot import ALPHA_TEST_ALWAYS, snapshot_material
from lightspeed.trex.alpha_cutout.core.usd_reader import get_bound_material, get_surface_shader
from omni.kit.test import AsyncTestCase
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

from .fixtures import (
    MATERIAL_PATH,
    MESH_PRIM_PATH,
    REPLACEMENT_CARD_FILE_PATH,
    REPLACEMENT_TRUNK_FILE_PATH,
    build_capture_stage,
    quad_cut_mesh,
    write_alpha_texture,
    write_replacement_file,
)

_CAPTURE_MESH_FILE_PATH = "/mesh_AAAAAAAAAAAAAAAA/mesh"


def _single_triangle() -> dataclasses.dataclass:
    return dataclasses.replace(quad_cut_mesh(), triangles=np.array([[0, 1, 2]], dtype=np.int32))


class TestWriteCutoutFile(AsyncTestCase):
    """Test writing the model copy that feeds the asset pipeline."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._root = Path(self._temp_dir.name)
        self._texture = write_alpha_texture(self._root / "alpha.png", np.full((4, 4), 255, np.uint8))

    def tearDown(self):
        self._temp_dir.cleanup()

    def _write_capture_mesh_file(self) -> tuple[str, dict]:
        """Write a capture-like mesh file without a material and return it with a material snapshot."""
        stage = build_capture_stage(self._texture)
        file_stage = Usd.Stage.CreateNew(str(self._root / "mesh.usda"))
        root = UsdGeom.Xform.Define(file_stage, "/mesh_AAAAAAAAAAAAAAAA")
        file_stage.SetDefaultPrim(root.GetPrim())
        Sdf.CopySpec(
            stage.GetRootLayer(), Sdf.Path(MESH_PRIM_PATH), file_stage.GetRootLayer(), Sdf.Path(_CAPTURE_MESH_FILE_PATH)
        )
        file_stage.GetRootLayer().Save()
        snapshot = snapshot_material(UsdShade.Material(stage.GetPrimAtPath(MATERIAL_PATH)))
        return str(self._root / "mesh.usda"), snapshot

    async def test_write_cutout_file_for_capture_defines_bound_material_with_absolute_texture(self):
        # Arrange
        source, snapshot = self._write_capture_mesh_file()
        output = self._root / "out" / "cutout.usda"
        output.parent.mkdir()

        # Act
        write_cutout_file(
            source, output, [MeshConversion(_CAPTURE_MESH_FILE_PATH, _single_triangle(), snapshot, MATERIAL_PATH)], True
        )

        # Assert
        stage = Usd.Stage.Open(str(output))
        mesh = stage.GetPrimAtPath(_CAPTURE_MESH_FILE_PATH)
        self.assertEqual(len(UsdGeom.Mesh(mesh).GetFaceVertexCountsAttr().Get()), 1)
        material = get_bound_material(mesh)
        self.assertEqual(material.GetPrim().GetName(), MATERIAL_PRIM_NAME)
        shader = UsdShade.Shader(material.GetPrim().GetChild("Shader"))
        texture = shader.GetInput("diffuse_texture").Get().path
        self.assertTrue(Path(texture).is_absolute())
        self.assertEqual(Path(texture), output.parent / "textures" / "alpha.png")
        self.assertTrue((output.parent / "textures" / "alpha.png").is_file())
        self.assertEqual(read_origin(mesh), (omni.client.normalize_url(source), _CAPTURE_MESH_FILE_PATH, MATERIAL_PATH))
        self.assertEqual(mesh.GetAttribute(SOURCE_FILE_ATTR).GetTypeName(), Sdf.ValueTypeNames.String)
        self.assertEqual(shader.GetSourceAsset("mdl").path, "AperturePBR_Opacity.mdl")
        self.assertEqual(shader.GetInput("alpha_test_type").Get(), ALPHA_TEST_ALWAYS)
        self.assertTrue(stage.GetDefaultPrim().GetName().startswith("mesh_"))

    async def test_write_cutout_file_for_replacement_keeps_materials_and_untouched_meshes(self):
        # Arrange
        source = write_replacement_file(self._root / "fern01.usda", self._texture)
        output = self._root / "cutout.usda"

        # Act
        write_cutout_file(source, output, [MeshConversion(REPLACEMENT_CARD_FILE_PATH, _single_triangle())], True)

        # Assert
        stage = Usd.Stage.Open(str(output))
        card = stage.GetPrimAtPath(REPLACEMENT_CARD_FILE_PATH)
        trunk = stage.GetPrimAtPath(REPLACEMENT_TRUNK_FILE_PATH)
        self.assertEqual(len(UsdGeom.Mesh(card).GetFaceVertexCountsAttr().Get()), 1)
        self.assertEqual(len(UsdGeom.Mesh(trunk).GetFaceVertexCountsAttr().Get()), 2)
        card_shader = UsdShade.Shader(stage.GetPrimAtPath("/ReferenceTarget/Looks/card_mat/Shader"))
        trunk_shader = UsdShade.Shader(stage.GetPrimAtPath("/ReferenceTarget/Looks/trunk_mat/Shader"))
        self.assertEqual(get_bound_material(card).GetPath(), Sdf.Path("/ReferenceTarget/Looks/card_mat"))
        self.assertEqual(card_shader.GetInput("alpha_test_type").Get(), ALPHA_TEST_ALWAYS)
        self.assertIsNone(trunk_shader.GetInput("alpha_test_type").Get())
        self.assertTrue(Path(card_shader.GetInput("diffuse_texture").Get().path).is_absolute())
        self.assertEqual(card_shader.GetSourceAsset("mdl").path, "AperturePBR_Opacity.mdl")
        self.assertEqual(read_origin(card), (omni.client.normalize_url(source), REPLACEMENT_CARD_FILE_PATH, None))
        self.assertEqual(card.GetAttribute(MATERIAL_PRIM_ATTR).Get(), "")
        self.assertIsNone(read_origin(trunk))
        self.assertEqual(card.GetAttribute(SOURCE_PRIM_ATTR).Get(), REPLACEMENT_CARD_FILE_PATH)

    async def test_write_cutout_file_copies_a_material_that_an_unconverted_mesh_shares(self):
        # Arrange
        source = write_replacement_file(self._root / "fern01.usda", self._texture)
        source_stage = Usd.Stage.Open(source)
        shared = UsdShade.Material(source_stage.GetPrimAtPath("/ReferenceTarget/Looks/card_mat"))
        UsdShade.MaterialBindingAPI(source_stage.GetPrimAtPath(REPLACEMENT_TRUNK_FILE_PATH)).Bind(shared)
        source_stage.GetRootLayer().Save()
        output = self._root / "cutout.usda"

        # Act
        write_cutout_file(source, output, [MeshConversion(REPLACEMENT_CARD_FILE_PATH, _single_triangle())], True)

        # Assert
        stage = Usd.Stage.Open(str(output))
        card_material = get_bound_material(stage.GetPrimAtPath(REPLACEMENT_CARD_FILE_PATH))
        trunk_material = get_bound_material(stage.GetPrimAtPath(REPLACEMENT_TRUNK_FILE_PATH))
        card_shader = get_surface_shader(card_material)
        trunk_shader = get_surface_shader(trunk_material)
        self.assertEqual(trunk_material.GetPath(), Sdf.Path("/ReferenceTarget/Looks/card_mat"))
        self.assertNotEqual(card_material.GetPath(), trunk_material.GetPath())
        self.assertTrue(card_shader.GetPath().HasPrefix(card_material.GetPath()))
        self.assertEqual(card_shader.GetInput("alpha_test_type").Get(), ALPHA_TEST_ALWAYS)
        self.assertIsNone(trunk_shader.GetInput("alpha_test_type").Get())
        self.assertEqual(
            card_shader.GetInput("diffuse_texture").Get().path, trunk_shader.GetInput("diffuse_texture").Get().path
        )

    async def test_write_cutout_file_keeps_textures_that_share_a_file_name_apart(self):
        # Arrange
        for folder in ("first", "second"):
            (self._root / folder).mkdir()
        first = write_alpha_texture(self._root / "first" / "leaf.png", np.full((4, 4), 255, np.uint8))
        second = write_alpha_texture(self._root / "second" / "leaf.png", np.full((8, 8), 0, np.uint8))
        source = write_replacement_file(self._root / "fern01.usda", first)
        source_stage = Usd.Stage.Open(source)
        trunk_shader = UsdShade.Shader(source_stage.GetPrimAtPath("/ReferenceTarget/Looks/trunk_mat/Shader"))
        trunk_shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(second))
        source_stage.GetRootLayer().Save()
        output = self._root / "out" / "cutout.usda"
        output.parent.mkdir()

        # Act
        write_cutout_file(source, output, [], False)

        # Assert
        stage = Usd.Stage.Open(str(output))
        staged = [
            Path(
                UsdShade.Shader(stage.GetPrimAtPath(f"/ReferenceTarget/Looks/{name}/Shader"))
                .GetInput("diffuse_texture")
                .Get()
                .path
            )
            for name in ("card_mat", "trunk_mat")
        ]
        self.assertNotEqual(staged[0], staged[1])
        self.assertEqual([path.read_bytes() for path in staged], [Path(first).read_bytes(), Path(second).read_bytes()])

    async def test_write_cutout_file_gives_every_snapshot_material_its_own_path(self):
        # Arrange: three meshes of one capture-like file share their prim name.
        source, snapshot = self._write_capture_mesh_file()
        source_stage = Usd.Stage.Open(source)
        layer = source_stage.GetRootLayer()
        paths = [_CAPTURE_MESH_FILE_PATH]
        for name in ("second", "third"):
            UsdGeom.Xform.Define(source_stage, f"/mesh_AAAAAAAAAAAAAAAA/{name}")
            paths.append(f"/mesh_AAAAAAAAAAAAAAAA/{name}/mesh")
            Sdf.CopySpec(layer, Sdf.Path(_CAPTURE_MESH_FILE_PATH), layer, Sdf.Path(paths[-1]))
        layer.Save()
        output = self._root / "out" / "cutout.usda"
        output.parent.mkdir()

        # Act
        write_cutout_file(source, output, [MeshConversion(path, _single_triangle(), snapshot) for path in paths], False)

        # Assert
        stage = Usd.Stage.Open(str(output))
        materials = {get_bound_material(stage.GetPrimAtPath(path)).GetPath() for path in paths}
        self.assertEqual(len(materials), 3)

    async def test_author_geometry_removes_a_normals_primvar_of_the_source_topology(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        mesh = UsdGeom.Mesh(stage.GetPrimAtPath(MESH_PRIM_PATH))
        primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
            "normals", Sdf.ValueTypeNames.Normal3fArray, UsdGeom.Tokens.faceVarying
        )
        primvar.Set([Gf.Vec3f(0, 0, 1)])
        primvar.SetIndices([0] * 6)

        # Act
        author_geometry(mesh, _single_triangle())

        # Assert
        self.assertFalse(UsdGeom.PrimvarsAPI(mesh).HasPrimvar("normals"))
        self.assertFalse(mesh.GetPrim().HasAttribute("primvars:normals:indices"))
        self.assertEqual(len(mesh.GetNormalsAttr().Get()), 4)

    async def test_write_cutout_file_with_missing_mesh_raises_value_error(self):
        # Arrange
        source = write_replacement_file(self._root / "fern01.usda", self._texture)

        # Act / Assert
        with self.assertRaises(ValueError):
            write_cutout_file(
                source, self._root / "cutout.usda", [MeshConversion("/ReferenceTarget/nope", _single_triangle())], False
            )

    async def test_write_cutout_file_keeps_transform_ops_of_the_converted_mesh(self):
        # Arrange
        source, snapshot = self._write_capture_mesh_file()
        output = self._root / "cutout.usda"

        # Act
        write_cutout_file(source, output, [MeshConversion(_CAPTURE_MESH_FILE_PATH, quad_cut_mesh(), snapshot)], False)

        # Assert
        stage = Usd.Stage.Open(str(output))
        mesh = UsdGeom.Xformable(stage.GetPrimAtPath(_CAPTURE_MESH_FILE_PATH))
        self.assertNotEqual(mesh.GetLocalTransformation(), Gf.Matrix4d(1.0))

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

__all__ = [
    "MATERIAL_PATH",
    "MESH_HASH",
    "MESH_PRIM_PATH",
    "MESH_ROOT_PATH",
    "REPLACEMENT_CARD_FILE_PATH",
    "REPLACEMENT_CARD_PATH",
    "REPLACEMENT_REF_PATH",
    "REPLACEMENT_TRUNK_PATH",
    "build_capture_stage",
    "build_replacement_stage",
    "quad_cut_mesh",
    "write_alpha_texture",
    "write_replacement_file",
]

from pathlib import Path

import numpy as np
import omni.client
from lightspeed.common import constants
from lightspeed.trex.alpha_cutout.core.data_models import CutMesh
from PIL import Image
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

MESH_HASH = "AAAAAAAAAAAAAAAA"
MESH_ROOT_PATH = f"/RootNode/meshes/mesh_{MESH_HASH}"
MESH_PRIM_PATH = f"{MESH_ROOT_PATH}/mesh"
MATERIAL_PATH = "/RootNode/Looks/mat_BBBBBBBBBBBBBBBB"
REPLACEMENT_REF_PATH = f"{MESH_ROOT_PATH}/ref_abc"
REPLACEMENT_CARD_PATH = f"{REPLACEMENT_REF_PATH}/XForms/card/mesh"
REPLACEMENT_TRUNK_PATH = f"{REPLACEMENT_REF_PATH}/XForms/trunk/mesh"
REPLACEMENT_CARD_FILE_PATH = "/ReferenceTarget/XForms/card/mesh"

_QUAD_POINTS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
_QUAD_ST = [(0, 0), (1, 0), (1, 1), (0, 1)]


def write_alpha_texture(path: Path, alpha: np.ndarray) -> str:
    """Write an RGBA PNG with the given alpha channel.

    Args:
        path: Destination file.
        alpha: ``(H, W)`` uint8 alpha values.

    Returns:
        The path as a string.
    """
    rgba = np.dstack([np.full_like(alpha, 128)] * 3 + [alpha])
    Image.fromarray(rgba, "RGBA").save(path)
    return str(path)


def build_capture_stage(
    texture_path: str | None,
    *,
    st_interpolation: str = UsdGeom.Tokens.vertex,
    face_counts: list[int] | None = None,
    with_normals: bool = True,
    with_transform: bool = True,
    time_sampled_points: bool = False,
) -> Usd.Stage:
    """Build an in-memory stage shaped like a capture: a bound material and a quad prototype mesh.

    Args:
        texture_path: Absolute diffuse texture path, or ``None`` to leave the material without one.
        st_interpolation: Interpolation of the ``st`` primvar.
        face_counts: ``faceVertexCounts`` to author; defaults to two triangles.
        with_normals: Whether to author vertex normals.
        with_transform: Whether to author an ``xformOp:transform`` on the mesh prim.
        time_sampled_points: Whether the points are authored as a time sample only.

    Returns:
        The stage.
    """
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.SetTimeCodesPerSecond(24)
    UsdGeom.Xform.Define(stage, "/RootNode")
    UsdGeom.Scope.Define(stage, "/RootNode/Looks")

    material = UsdShade.Material.Define(stage, MATERIAL_PATH)
    shader = UsdShade.Shader.Define(stage, f"{MATERIAL_PATH}/Shader")
    shader.GetPrim().SetMetadata("kind", "Material")
    shader.SetSourceAsset(Sdf.AssetPath("AperturePBR_Opacity.mdl"), "mdl")
    shader.SetSourceAssetSubIdentifier("AperturePBR_Opacity", "mdl")
    shader.CreateInput("enable_opacity", Sdf.ValueTypeNames.Bool).Set(False)
    if texture_path:
        texture_input = shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset)
        texture_input.Set(Sdf.AssetPath(texture_path))
        texture_input.GetAttr().SetColorSpace("auto")
    shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")

    UsdGeom.Scope.Define(stage, "/RootNode/meshes")
    root = UsdGeom.Xform.Define(stage, MESH_ROOT_PATH)
    UsdShade.MaterialBindingAPI.Apply(root.GetPrim()).Bind(material)

    counts = face_counts or [3, 3]
    if counts == [4]:
        indices = [0, 1, 2, 3]
    else:
        indices = [0, 1, 2, 0, 2, 3]
    mesh = UsdGeom.Mesh.Define(stage, MESH_PRIM_PATH)
    points = [Gf.Vec3f(*point) for point in _QUAD_POINTS]
    if time_sampled_points:
        mesh.GetPointsAttr().Set(points, Usd.TimeCode(0))
    else:
        mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, st_interpolation)
    if st_interpolation == UsdGeom.Tokens.faceVarying:
        primvar.Set([Gf.Vec2f(*_QUAD_ST[index]) for index in indices])
    else:
        primvar.Set([Gf.Vec2f(*st) for st in _QUAD_ST])
    if with_normals:
        mesh.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)] * 4)
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateDoubleSidedAttr(True)
    mesh.CreateOrientationAttr(UsdGeom.Tokens.leftHanded)
    if with_transform:
        mesh.AddTransformOp().Set(Gf.Matrix4d(1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1))
    return stage


def _define_quad(stage: Usd.Stage, path: str, material: UsdShade.Material) -> UsdGeom.Mesh:
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr([Gf.Vec3f(*point) for point in _QUAD_POINTS])
    mesh.CreateFaceVertexCountsAttr([3, 3])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 0, 2, 3])
    primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    primvar.Set([Gf.Vec2f(*st) for st in _QUAD_ST])
    mesh.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)] * 4)
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateDoubleSidedAttr(True)
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return mesh


def _define_material(stage: Usd.Stage, path: str, texture_path: str | None) -> UsdShade.Material:
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/Shader")
    shader.SetSourceAsset(Sdf.AssetPath("AperturePBR_Opacity.mdl"), "mdl")
    shader.SetSourceAssetSubIdentifier("AperturePBR_Opacity", "mdl")
    if texture_path:
        shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(texture_path))
    shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    return material


def write_replacement_file(path: Path, texture_path: str | None) -> str:
    """Write a replacement file shaped like an ingested asset: a textured card and an untextured trunk.

    Args:
        path: File to write.
        texture_path: Absolute diffuse texture of the card material, or ``None``.

    Returns:
        Normalized path of the file.
    """
    layer = Sdf.Layer.CreateNew(str(path))
    stage = Usd.Stage.Open(layer)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    root = UsdGeom.Xform.Define(stage, "/ReferenceTarget")
    stage.SetDefaultPrim(root.GetPrim())
    UsdGeom.Xform.Define(stage, "/ReferenceTarget/XForms")
    UsdGeom.Scope.Define(stage, "/ReferenceTarget/Looks")
    card_material = _define_material(stage, "/ReferenceTarget/Looks/card_mat", texture_path)
    trunk_material = _define_material(stage, "/ReferenceTarget/Looks/trunk_mat", None)
    UsdGeom.Xform.Define(stage, "/ReferenceTarget/XForms/card")
    _define_quad(stage, REPLACEMENT_CARD_FILE_PATH, card_material)
    UsdGeom.Xform.Define(stage, "/ReferenceTarget/XForms/trunk")
    _define_quad(stage, "/ReferenceTarget/XForms/trunk/mesh", trunk_material)
    layer.Save()
    return omni.client.normalize_url(str(path))


def build_replacement_stage(replacement_file: str) -> Usd.Stage:
    """Build an in-memory stage whose prototype holds a Remix reference prim pointing at a replacement file.

    Args:
        replacement_file: Absolute path of the file written by ``write_replacement_file``.

    Returns:
        The stage.
    """
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.Xform.Define(stage, "/RootNode")
    UsdGeom.Scope.Define(stage, "/RootNode/meshes")
    UsdGeom.Xform.Define(stage, MESH_ROOT_PATH)
    ref_prim = UsdGeom.Xform.Define(stage, REPLACEMENT_REF_PATH).GetPrim()
    ref_prim.CreateAttribute(constants.IS_REMIX_REF_ATTR, Sdf.ValueTypeNames.Bool).Set(True)
    ref_prim.GetReferences().AddReference(replacement_file)
    return stage


def quad_cut_mesh() -> CutMesh:
    """Return the unit quad as a cut mesh.

    Returns:
        Two-triangle quad with vertex normals.
    """
    return CutMesh(
        points=np.array(_QUAD_POINTS, dtype=np.float32),
        triangles=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32),
        st=np.array(_QUAD_ST, dtype=np.float32),
        normals=np.tile(np.array([0, 0, 1], dtype=np.float32), (4, 1)),
    )

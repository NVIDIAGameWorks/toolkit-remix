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

from __future__ import annotations

__all__ = [
    "MATERIAL_PRIM_NAME",
    "REFERENCE_TARGET_PRIM_NAME",
    "cutout_file_name",
    "cutout_output_path",
    "cutout_root_prim_name",
    "write_cutout_mesh",
    "write_cutout_replacement",
]

import os

import numpy as np
import omni.client
from omni.flux.utils.common import path_utils
from omni.flux.validator.factory import BASE_HASH_KEY, VALIDATION_EXTENSIONS, VALIDATION_PASSED
from pxr import Gf, Kind, Sdf, Usd, UsdGeom, UsdShade, Vt

from .data_models import CutMesh, MeshSource
from .material_copy import author_opaque_alpha_state, copy_material_flattened, get_surface_shader
from .usd_reader import is_replacement_cutout_path

# The prim names deliberately avoid the capture naming scheme (``mesh_HASH`` / ``mat_HASH``) because the
# toolkit classifies prims by those prefixes.
MATERIAL_PRIM_NAME = "AlphaCutoutMaterial"
REFERENCE_TARGET_PRIM_NAME = "ReferenceTarget"
_XFORMS_PRIM_NAME = "XForms"
_PRIM_PREFIX = "cutout_"
_ST_PRIMVAR = "st"
_LOOKS_SCOPE = "Looks"
_MESH_PRIM_NAME = "mesh"
_FILE_SUFFIX = ".usda"


def cutout_file_name(mesh_hash: str) -> str:
    """Return the file name of the generated replacement for a mesh hash.

    Args:
        mesh_hash: Hash part of the ``mesh_HASH`` prototype name.

    Returns:
        File name ``cutout_<HASH>.usda``.
    """
    return f"{_PRIM_PREFIX}{mesh_hash}{_FILE_SUFFIX}"


def cutout_output_path(output_dir: str, mesh_hash: str) -> str:
    """Return the normalized path of the generated replacement for a mesh hash.

    Args:
        output_dir: Folder the replacement is written to.
        mesh_hash: Hash part of the ``mesh_HASH`` prototype name.

    Returns:
        Normalized absolute file path with forward slashes.
    """
    return omni.client.normalize_url(os.path.join(output_dir, cutout_file_name(mesh_hash))).replace("\\", "/")


def cutout_root_prim_name(mesh_hash: str) -> str:
    """Return the default prim name of the generated replacement.

    Args:
        mesh_hash: Hash part of the ``mesh_HASH`` prototype name.

    Returns:
        Prim name that does not match the capture mesh naming scheme.
    """
    return f"{_PRIM_PREFIX}{mesh_hash}"


def _define_default_xform(stage: Usd.Stage, path: Sdf.Path, kind: str) -> UsdGeom.Xform:
    """Define an Xform with the identity translate, rotate and scale ops the ingestion pipeline authors.

    Args:
        stage: Stage of the generated file.
        path: Path of the new prim.
        kind: Model kind of the prim.

    Returns:
        The defined Xform.
    """
    xform = UsdGeom.Xform.Define(stage, path)
    Usd.ModelAPI(xform.GetPrim()).SetKind(kind)
    xform.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))
    xform.AddRotateXYZOp().Set(Gf.Vec3f(0.0, 0.0, 0.0))
    xform.AddScaleOp().Set(Gf.Vec3f(1.0, 1.0, 1.0))
    return xform


def _open_output_layer(path: str) -> Sdf.Layer:
    """Return an empty layer for the output path, reusing the layer when the project already holds it open.

    Args:
        path: Normalized output path.

    Returns:
        Cleared layer bound to the path.

    Raises:
        RuntimeError: If the layer cannot be created or opened.
    """
    layer = Sdf.Layer.Find(path)
    if layer is None and os.path.exists(path):
        layer = Sdf.Layer.FindOrOpen(path)
    if layer is None:
        layer = Sdf.Layer.CreateNew(path)
    if layer is None:
        raise RuntimeError(f"The layer {path} could not be created.")
    layer.Clear()
    return layer


def _write_metadata(path: str) -> None:
    """Write the sidecar that marks the generated file as ingested.

    Args:
        path: Path of the generated file.

    Raises:
        RuntimeError: If the file cannot be hashed.
    """
    file_hash = path_utils.hash_file(path)
    if file_hash is None:
        raise RuntimeError(f"The file {path} could not be hashed.")
    path_utils.write_metadata(path, BASE_HASH_KEY, file_hash)
    path_utils.write_metadata(path, VALIDATION_PASSED, True)
    path_utils.write_metadata(path, VALIDATION_EXTENSIONS, [])


def _author_geometry(mesh: UsdGeom.Mesh, cut_mesh: CutMesh) -> None:
    """Replace the topology, texture coordinates, normals and extent of a mesh with cut geometry.

    Existing values and time samples are cleared first so the cut geometry is the only authored opinion.

    Args:
        mesh: Mesh to rewrite.
        cut_mesh: Geometry to author.
    """
    prim = mesh.GetPrim()
    for attribute in (mesh.GetPointsAttr(), mesh.GetFaceVertexCountsAttr(), mesh.GetFaceVertexIndicesAttr()):
        attribute.Clear()
    mesh.CreatePointsAttr().Set(Vt.Vec3fArray.FromNumpy(cut_mesh.points.astype(np.float32)))
    mesh.CreateFaceVertexCountsAttr().Set(
        Vt.IntArray.FromNumpy(np.full(cut_mesh.triangles.shape[0], 3, dtype=np.int32))
    )
    mesh.CreateFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(cut_mesh.triangles.astype(np.int32).reshape(-1)))
    primvars = UsdGeom.PrimvarsAPI(prim)
    st = primvars.GetPrimvar(_ST_PRIMVAR)
    if st:
        st.GetAttr().Clear()
        if st.GetIndicesAttr():
            prim.RemoveProperty(st.GetIndicesAttr().GetName())
    st = primvars.CreatePrimvar(_ST_PRIMVAR, Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    st.SetInterpolation(UsdGeom.Tokens.vertex)
    st.Set(Vt.Vec2fArray.FromNumpy(cut_mesh.st.astype(np.float32)))
    normals = mesh.GetNormalsAttr()
    if normals:
        normals.Clear()
    if cut_mesh.normals is not None and cut_mesh.normals.shape[0] == cut_mesh.points.shape[0]:
        mesh.CreateNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(cut_mesh.normals.astype(np.float32)))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    extent = mesh.GetExtentAttr()
    if extent:
        extent.Clear()
    if cut_mesh.points.shape[0]:
        computed = UsdGeom.Boundable.ComputeExtentFromPlugins(mesh, Usd.TimeCode.Default())
        if computed:
            mesh.CreateExtentAttr().Set(computed)


def write_cutout_mesh(
    output_dir: str,
    source: MeshSource,
    cut_mesh: CutMesh,
    source_stage: Usd.Stage,
    disable_alpha_test: bool,
) -> str:
    """Write the cut geometry and its material copy as a standalone replacement file.

    Args:
        output_dir: Folder the file is written to; created when missing.
        source: Mesh the geometry was cut from.
        cut_mesh: Geometry to write.
        source_stage: Stage of the capture, used for stage metadata and the material to copy.
        disable_alpha_test: Whether the material copy authors the opaque alpha state.

    Returns:
        Normalized path of the written file.

    Raises:
        RuntimeError: If the layer cannot be created, saved or hashed.
        ValueError: If the source carries no material.
    """
    if not source.material_path:
        raise ValueError(f"The mesh {source.prim_path} has no bound material to copy.")
    os.makedirs(output_dir, exist_ok=True)
    path = cutout_output_path(output_dir, source.mesh_hash)
    layer = _open_output_layer(path)
    stage = Usd.Stage.Open(layer)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.GetStageUpAxis(source_stage))
    UsdGeom.SetStageMetersPerUnit(stage, UsdGeom.GetStageMetersPerUnit(source_stage))
    stage.SetTimeCodesPerSecond(source_stage.GetTimeCodesPerSecond())

    # The prim tree mirrors what the ingestion pipeline writes so the toolkit treats the file like an ingested asset.
    reference_target = _define_default_xform(stage, Sdf.Path(f"/{REFERENCE_TARGET_PRIM_NAME}"), Kind.Tokens.group)
    stage.SetDefaultPrim(reference_target.GetPrim())
    xforms = _define_default_xform(stage, reference_target.GetPath().AppendChild(_XFORMS_PRIM_NAME), Kind.Tokens.group)
    root_path = xforms.GetPath().AppendChild(cutout_root_prim_name(source.mesh_hash))
    _define_default_xform(stage, root_path, Kind.Tokens.component)

    mesh = UsdGeom.Mesh.Define(stage, root_path.AppendChild(_MESH_PRIM_NAME))
    _author_geometry(mesh, cut_mesh)
    mesh.CreateDoubleSidedAttr(source.double_sided)
    mesh.CreateOrientationAttr(source.orientation)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    if source.transform is not None:
        mesh.AddTransformOp().Set(Gf.Matrix4d(*source.transform))

    UsdGeom.Scope.Define(stage, root_path.AppendChild(_LOOKS_SCOPE))
    source_material = UsdShade.Material(source_stage.GetPrimAtPath(source.material_path))
    material = copy_material_flattened(
        source_material,
        stage,
        str(root_path.AppendChild(_LOOKS_SCOPE).AppendChild(MATERIAL_PRIM_NAME)),
        path,
        disable_alpha_test,
    )
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    if not layer.Save():
        raise RuntimeError(f"The layer {path} could not be saved.")
    _write_metadata(path)
    return path


def write_cutout_replacement(
    original_file: str,
    output_file: str,
    meshes: list[tuple[str, CutMesh]],
    disable_alpha_test: bool,
) -> str:
    """Write a copy of a replacement file in which the given meshes carry cut geometry.

    The whole original layer is copied so prim names, materials and relative texture paths survive; only the
    listed mesh prims are rewritten. The original file is never touched.

    Args:
        original_file: Path of the original replacement file.
        output_file: Path of the cutout file, next to the original and carrying the cutout suffix.
        meshes: Pairs of mesh prim path inside the file and the geometry to author.
        disable_alpha_test: Whether materials of this file bound to the rewritten meshes get the opaque alpha state.

    Returns:
        Normalized path of the written file.

    Raises:
        ValueError: If the output would overwrite the original or a mesh prim is missing.
        RuntimeError: If a layer cannot be opened, saved or hashed.
    """
    original = omni.client.normalize_url(original_file)
    output = omni.client.normalize_url(output_file)
    if output.lower() == original.lower() or not is_replacement_cutout_path(output):
        raise ValueError(f"The cutout path {output} must differ from the original and carry the cutout suffix.")
    source_layer = Sdf.Layer.FindOrOpen(original)
    if source_layer is None:
        raise RuntimeError(f"The replacement file {original} could not be opened.")
    layer = _open_output_layer(output)
    layer.TransferContent(source_layer)
    stage = Usd.Stage.Open(layer)
    for prim_path, cut_mesh in meshes:
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsA(UsdGeom.Mesh):
            raise ValueError(f"The replacement file has no mesh at {prim_path}.")
        _author_geometry(UsdGeom.Mesh(prim), cut_mesh)
        if not disable_alpha_test:
            continue
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        shader = get_surface_shader(material) if material else None
        if shader and layer.GetPrimAtPath(shader.GetPath()):
            author_opaque_alpha_state(shader)
    if not layer.Save():
        raise RuntimeError(f"The layer {output} could not be saved.")
    _write_metadata(output)
    return output

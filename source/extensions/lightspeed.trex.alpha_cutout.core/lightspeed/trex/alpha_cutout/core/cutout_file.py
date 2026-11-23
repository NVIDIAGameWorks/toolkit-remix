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
    "MATERIAL_PRIM_ATTR",
    "MATERIAL_PRIM_NAME",
    "SOURCE_FILE_ATTR",
    "SOURCE_PRIM_ATTR",
    "MeshConversion",
    "author_geometry",
    "read_origin",
    "write_cutout_file",
]

import hashlib
import pathlib
import shutil
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import omni.client
from omni.flux.utils.common.path_utils import get_absolute_path_from_relative
from pxr import Sdf, Usd, UsdGeom, UsdShade, UsdUtils, Vt

from .data_models import CutMesh
from .material_snapshot import APERTURE_SHADERS, author_opaque_alpha_state, define_material
from .usd_reader import get_bound_material, get_surface_shader

MATERIAL_PRIM_NAME = "AlphaCutoutMaterial"
# A converted mesh records where it came from so a later run converts the original model again.
SOURCE_FILE_ATTR = "remix:alphaCutoutSource"
SOURCE_PRIM_ATTR = "remix:alphaCutoutSourcePrim"
MATERIAL_PRIM_ATTR = "remix:alphaCutoutMaterialPrim"
_LOOKS_SCOPE = "Looks"
_ST_PRIMVAR = "st"
_NORMALS_PRIMVAR = "normals"
_OPAQUE_COPY_SUFFIX = "_AlphaCutout"
_MDL_SUFFIX = ".mdl"
_MDL_RENDER_CONTEXT = "mdl"
_TEXTURES_FOLDER = "textures"


@dataclass(frozen=True)
class MeshConversion:
    """Cut geometry to author on one mesh of the model file.

    Attributes:
        prim_path: Path of the mesh prim inside the file.
        cut_mesh: Geometry that replaces the mesh.
        material: Snapshot of the material to define and bind when the file has none for this mesh.
        material_prim: Project path of the material the snapshot was taken from, recorded for later runs.
    """

    prim_path: str
    cut_mesh: CutMesh
    material: dict | None = None
    material_prim: str | None = None


def author_geometry(mesh: UsdGeom.Mesh, cut_mesh: CutMesh) -> None:
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
    # A normals primvar takes precedence over the normals attribute and still describes the source topology.
    if primvars.HasPrimvar(_NORMALS_PRIMVAR):
        primvars.RemovePrimvar(_NORMALS_PRIMVAR)
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


def _stage_textures(layer: Sdf.Layer, texture_dir: pathlib.Path) -> None:
    """Copy every texture the layer references into the texture folder and point the layer at the copies.

    Args:
        layer: Flattened layer whose asset paths are absolute.
        texture_dir: Folder next to the output file that receives the copies.
    """
    copies: dict[str, str] = {}

    def staged(path: str) -> str:
        if not path or path.lower().endswith((_MDL_SUFFIX, ".usd", ".usda", ".usdc")):
            return path
        source = pathlib.Path(path)
        if not source.is_file():
            return path
        key = source.as_posix().lower()
        if key not in copies:
            texture_dir.mkdir(parents=True, exist_ok=True)
            destination = texture_dir / source.name
            if destination.as_posix().lower() in {copy.lower() for copy in copies.values()}:
                digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
                destination = texture_dir / f"{source.stem}_{digest}{source.suffix}"
            shutil.copyfile(source, destination)
            copies[key] = destination.as_posix()
        return copies[key]

    UsdUtils.ModifyAssetPaths(layer, staged)


def _author_origin(prim: Usd.Prim, source_url: str, conversion: MeshConversion) -> None:
    """Record the model, prim and project material a converted mesh was made from.

    Args:
        prim: Converted mesh prim.
        source_url: Model file the geometry was read from.
        conversion: Conversion that names the prim and the project material.
    """
    values = (
        (SOURCE_FILE_ATTR, omni.client.normalize_url(source_url)),
        (SOURCE_PRIM_ATTR, conversion.prim_path),
        (MATERIAL_PRIM_ATTR, conversion.material_prim or ""),
    )
    for name, value in values:
        prim.CreateAttribute(name, Sdf.ValueTypeNames.String, custom=True).Set(value)


def read_origin(prim: Usd.Prim) -> tuple[str, str, str | None] | None:
    """Return the model, prim and project material a converted mesh records as its origin.

    Args:
        prim: Mesh prim of a published cutout.

    Returns:
        Model file path, prim path inside it and the project material path (``None`` when the model carries its
        own materials), or ``None`` when the prim is not a converted mesh.
    """
    source_file = prim.GetAttribute(SOURCE_FILE_ATTR).Get() if prim and prim.IsValid() else None
    source_prim = prim.GetAttribute(SOURCE_PRIM_ATTR).Get() if source_file else None
    if not source_file or not source_prim:
        return None
    return source_file, source_prim, prim.GetAttribute(MATERIAL_PRIM_ATTR).Get() or None


def _free_child_path(stage: Usd.Stage, parent: Sdf.Path, name: str) -> Sdf.Path:
    """Return a child path of a prim that no prim uses yet.

    Args:
        stage: Stage of the file being written.
        parent: Path of the parent prim.
        name: Preferred name of the child.

    Returns:
        The child path with the preferred name when it is free, else with the first free numbered name.
    """
    path = parent.AppendChild(name)
    index = 2
    while stage.GetPrimAtPath(path):
        path = parent.AppendChild(f"{name}_{index}")
        index += 1
    return path


def _material_path(stage: Usd.Stage, mesh_prim: Usd.Prim) -> str:
    """Return a free path for the material of a mesh under the model's Looks scope.

    Args:
        stage: Stage of the file being written.
        mesh_prim: Mesh the material is for.

    Returns:
        Path of a material prim that does not exist yet.
    """
    root = stage.GetDefaultPrim()
    scope = (root.GetPath() if root and root.IsValid() else mesh_prim.GetParent().GetPath()).AppendChild(_LOOKS_SCOPE)
    path = scope.AppendChild(MATERIAL_PRIM_NAME)
    if stage.GetPrimAtPath(path):
        path = _free_child_path(stage, scope, f"{MATERIAL_PRIM_NAME}_{mesh_prim.GetName()}")
    return str(path)


def _unconverted_material_paths(stage: Usd.Stage, converted: set[Sdf.Path]) -> set[Sdf.Path]:
    """Return the materials of the geometry that keeps its source shape.

    Args:
        stage: Stage of the file being written.
        converted: Paths of the meshes that are rewritten.

    Returns:
        Paths of the materials bound to unconverted geometry and geometry subsets.
    """
    paths = set()
    for prim in stage.Traverse():
        if prim.GetPath() in converted or not (prim.IsA(UsdGeom.Gprim) or prim.IsA(UsdGeom.Subset)):
            continue
        material = get_bound_material(prim)
        if material:
            paths.add(material.GetPath())
    return paths


def _author_opaque_state_in_file(
    stage: Usd.Stage, mesh_prim: Usd.Prim, kept_materials: set[Sdf.Path], copies: dict[Sdf.Path, Sdf.Path]
) -> None:
    """Author the opaque alpha state on the Aperture material of a converted mesh, when it has one.

    A material that unconverted geometry also uses is copied first and the copy is bound to the mesh, so that
    geometry keeps its alpha behavior. Converted meshes that share a material share its copy.

    Args:
        stage: Stage of the file being written.
        mesh_prim: Converted mesh whose bound material lives in the file.
        kept_materials: Paths of the materials that unconverted geometry uses.
        copies: Paths of the copies made so far, by the path of their source material.
    """
    material = get_bound_material(mesh_prim)
    shader = get_surface_shader(material) if material else None
    if not shader or shader.GetSourceAssetSubIdentifier(_MDL_RENDER_CONTEXT) not in APERTURE_SHADERS:
        return
    source_path = material.GetPath()
    if source_path in kept_materials:
        if source_path not in copies:
            copies[source_path] = _free_child_path(
                stage, source_path.GetParentPath(), f"{source_path.name}{_OPAQUE_COPY_SUFFIX}"
            )
            layer = stage.GetRootLayer()
            Sdf.CopySpec(layer, source_path, layer, copies[source_path])
        material = UsdShade.Material(stage.GetPrimAtPath(copies[source_path]))
        UsdShade.MaterialBindingAPI.Apply(mesh_prim).Bind(material)
        shader = get_surface_shader(material)
    author_opaque_alpha_state(shader)


def write_cutout_file(
    source_url: str,
    output_path: pathlib.Path,
    conversions: Sequence[MeshConversion],
    disable_alpha_test: bool,
) -> pathlib.Path:
    """Write a flattened copy of a model file with cut geometry on the converted meshes.

    Textures are copied into a ``textures`` folder next to the output and referenced by absolute path, so the
    asset pipeline publishes them beside the mesh instead of under an external hash folder; sub-USD paths are
    made absolute and MDL module names are kept. A mesh without a material in the file gets one defined from its
    snapshot. A mesh with one keeps it and only receives the opaque alpha state when requested, on a copy of the
    material when unconverted geometry shares it.

    Args:
        source_url: Path of the model file to convert.
        output_path: Path of the file to write.
        conversions: Meshes to rewrite; the other prims are copied unchanged.
        disable_alpha_test: Whether the materials of the converted meshes get the opaque alpha state.

    Returns:
        The written path.

    Raises:
        RuntimeError: If the model file cannot be opened.
        ValueError: If a conversion names a prim that is not a mesh of the file.
    """
    stage = Usd.Stage.Open(source_url)
    if not stage:
        raise RuntimeError(f"The model file {source_url} could not be opened.")
    source_layer = stage.GetRootLayer()
    flattened = stage.Flatten()
    UsdUtils.ModifyAssetPaths(
        flattened,
        lambda path: (
            path
            if not path or path.lower().endswith(_MDL_SUFFIX)
            else get_absolute_path_from_relative(path, source_layer)
        ),
    )
    output_stage = Usd.Stage.Open(flattened)
    kept_materials = _unconverted_material_paths(
        output_stage, {Sdf.Path(conversion.prim_path) for conversion in conversions}
    )
    opaque_copies: dict[Sdf.Path, Sdf.Path] = {}
    for conversion in conversions:
        prim = output_stage.GetPrimAtPath(conversion.prim_path)
        if not prim or not prim.IsA(UsdGeom.Mesh):
            raise ValueError(f"The model file has no mesh at {conversion.prim_path}.")
        author_geometry(UsdGeom.Mesh(prim), conversion.cut_mesh)
        _author_origin(prim, source_url, conversion)
        if conversion.material is not None:
            material = define_material(
                output_stage, _material_path(output_stage, prim), conversion.material, disable_alpha_test
            )
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
        elif disable_alpha_test:
            _author_opaque_state_in_file(output_stage, prim, kept_materials, opaque_copies)
    _stage_textures(flattened, output_path.parent / _TEXTURES_FOLDER)
    flattened.Export(str(output_path))
    return output_path

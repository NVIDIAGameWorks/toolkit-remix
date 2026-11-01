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
    "get_bound_material",
    "get_diffuse_texture_path",
    "get_surface_shader",
    "is_convertible_mesh",
    "is_skinned",
    "read_mesh_geometry",
    "read_mesh_source",
]

import numpy as np
import omni.client
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdSkel

from .data_models import MeshSource

_DIFFUSE_INPUT = "diffuse_texture"
_SKEL_PRIMVAR_PREFIX = "primvars:skel:"
_MDL_RENDER_CONTEXT = "mdl"


class _AttributeReader:
    """Read attribute values at the default time, falling back to the first authored time sample."""

    def __init__(self):
        self.time_sampled = False

    def read(self, attribute: Usd.Attribute):
        """Return the value of an attribute, or ``None`` when nothing is authored.

        Args:
            attribute: Attribute to read.

        Returns:
            The default value, else the first time sample, else ``None``.
        """
        if not attribute or not attribute.IsValid():
            return None
        value = attribute.Get(Usd.TimeCode.Default())
        if value is not None:
            return value
        samples = attribute.GetTimeSamples()
        if not samples:
            return None
        self.time_sampled = True
        return attribute.Get(samples[0])


def get_bound_material(prim: Usd.Prim) -> UsdShade.Material | None:
    """Return the material bound to a prim, inherited bindings included.

    Args:
        prim: Mesh or ancestor prim.

    Returns:
        The bound material, or ``None``.
    """
    material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    return material or None


def get_surface_shader(material: UsdShade.Material) -> UsdShade.Shader | None:
    """Return the surface shader of a material, trying the universal then the MDL render context.

    Args:
        material: Material to inspect.

    Returns:
        The surface shader, or ``None``.
    """
    shader, _, _ = material.ComputeSurfaceSource()
    if not shader:
        shader, _, _ = material.ComputeSurfaceSource(_MDL_RENDER_CONTEXT)
    return shader or None


def get_diffuse_texture_path(material: UsdShade.Material) -> str | None:
    """Return the absolute path of the diffuse texture of an Aperture material.

    Args:
        material: Material whose surface shader declares ``inputs:diffuse_texture``.

    Returns:
        Normalized absolute texture path, or ``None`` when the material has no diffuse texture.
    """
    shader = get_surface_shader(material)
    if shader is None:
        return None
    shader_input = shader.GetInput(_DIFFUSE_INPUT)
    if not shader_input:
        return None
    asset = shader_input.Get()
    if not isinstance(asset, Sdf.AssetPath) or not asset.path:
        return None
    if asset.resolvedPath:
        return omni.client.normalize_url(asset.resolvedPath)
    stack = shader_input.GetAttr().GetPropertyStack(Usd.TimeCode.Default())
    if not stack:
        return None
    return omni.client.normalize_url(stack[0].layer.ComputeAbsolutePath(asset.path))


def is_skinned(mesh_prim: Usd.Prim) -> bool:
    """Return whether a mesh carries skeleton bindings that the cutout cannot preserve.

    Args:
        mesh_prim: Mesh prim to inspect.

    Returns:
        ``True`` when the mesh is skinned or has blend shapes.
    """
    if mesh_prim.HasAPI(UsdSkel.BindingAPI):
        return True
    return any(attribute.GetName().startswith(_SKEL_PRIMVAR_PREFIX) for attribute in mesh_prim.GetAttributes())


def is_convertible_mesh(prim: Usd.Prim) -> bool:
    """Return whether a prim is a mesh the cutout can rewrite as a whole.

    Args:
        prim: Prim to inspect.

    Returns:
        ``True`` for an unskinned mesh without geometry subsets.
    """
    if not prim or not prim.IsValid() or not prim.IsA(UsdGeom.Mesh) or is_skinned(prim):
        return False
    return not any(child.IsA(UsdGeom.Subset) for child in prim.GetChildren())


def _triangulate_faces(counts: np.ndarray, indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fan-triangulate polygon faces.

    Args:
        counts: ``faceVertexCounts`` values.
        indices: ``faceVertexIndices`` values.

    Returns:
        ``(T, 3)`` point indices and ``(T, 3)`` positions of those corners within ``indices``.
    """
    offsets = np.concatenate(([0], np.cumsum(counts)[:-1]))
    corner_positions = []
    for offset, count in zip(offsets, counts):
        for fan in range(1, int(count) - 1):
            corner_positions.append((offset, offset + fan, offset + fan + 1))
    corners = np.asarray(corner_positions, dtype=np.int64).reshape(-1, 3)
    return indices[corners].astype(np.int32), corners


def _read_st(
    mesh_prim: Usd.Prim, reader: _AttributeReader, triangles: np.ndarray, corners: np.ndarray
) -> tuple[np.ndarray | None, str | None]:
    """Read the ``st`` primvar as per-corner texture coordinates.

    Args:
        mesh_prim: Mesh prim to read.
        reader: Attribute reader shared with the other mesh attributes.
        triangles: ``(T, 3)`` point indices.
        corners: ``(T, 3)`` face-vertex positions.

    Returns:
        ``(T, 3, 2)`` texture coordinates and ``None``, or ``None`` and a skip reason.
    """
    primvars = UsdGeom.PrimvarsAPI(mesh_prim)
    primvar = primvars.GetPrimvar("st")
    if not primvar or not primvar.HasValue():
        texcoord_primvars = [
            candidate
            for candidate in primvars.GetPrimvars()
            if candidate.GetTypeName() == Sdf.ValueTypeNames.TexCoord2fArray and candidate.HasValue()
        ]
        if not texcoord_primvars:
            return None, "The mesh has no texture coordinates."
        primvar = texcoord_primvars[0]
    values = reader.read(primvar.GetAttr())
    if values is None:
        return None, "The mesh has no texture coordinates."
    values = np.asarray(values, dtype=np.float32).reshape(-1, 2)
    indices = primvar.GetIndices()
    if indices:
        values = values[np.asarray(indices, dtype=np.int64)]
    interpolation = primvar.GetInterpolation()
    if interpolation in (UsdGeom.Tokens.vertex, UsdGeom.Tokens.varying):
        return values[triangles], None
    if interpolation == UsdGeom.Tokens.faceVarying:
        return values[corners], None
    return None, f"The texture coordinate interpolation '{interpolation}' is not supported."


def _read_normals(
    mesh: UsdGeom.Mesh, reader: _AttributeReader, triangles: np.ndarray, corners: np.ndarray
) -> np.ndarray | None:
    """Read mesh normals as per-corner vectors.

    Args:
        mesh: Mesh schema to read.
        reader: Attribute reader shared with the other mesh attributes.
        triangles: ``(T, 3)`` point indices.
        corners: ``(T, 3)`` face-vertex positions.

    Returns:
        ``(T, 3, 3)`` normals, or ``None`` when the mesh has no usable normals.
    """
    values = reader.read(mesh.GetNormalsAttr())
    if values is None or len(values) == 0:
        return None
    values = np.asarray(values, dtype=np.float32).reshape(-1, 3)
    interpolation = mesh.GetNormalsInterpolation()
    if interpolation in (UsdGeom.Tokens.vertex, UsdGeom.Tokens.varying) and values.shape[0] > triangles.max():
        return values[triangles]
    if interpolation == UsdGeom.Tokens.faceVarying and values.shape[0] > corners.max():
        return values[corners]
    return None


def _read_transform(mesh_prim: Usd.Prim, root_prim: Usd.Prim) -> tuple[float, ...] | None:
    """Read the transform of the mesh relative to the model root.

    Args:
        mesh_prim: Mesh prim to read.
        root_prim: Model root the transform is relative to.

    Returns:
        Sixteen row-major values, or ``None`` when the transform is the identity.
    """
    matrix = UsdGeom.XformCache(Usd.TimeCode.Default()).ComputeRelativeTransform(mesh_prim, root_prim)[0]
    if matrix == Gf.Matrix4d(1.0):
        return None
    return tuple(float(value) for value in np.asarray(matrix, dtype=np.float64).reshape(16))


def read_mesh_geometry(mesh_prim: Usd.Prim, transform_root: Usd.Prim) -> tuple[dict | None, str | None]:
    """Read the geometry fields of a mesh prim.

    Args:
        mesh_prim: Mesh prim to read.
        transform_root: Prim the mesh transform is expressed relative to.

    Returns:
        The ``MeshSource`` geometry fields, or ``None`` with the reason the mesh cannot be converted.
    """
    if is_skinned(mesh_prim):
        return None, "Skinned meshes are not supported."
    reader = _AttributeReader()
    mesh = UsdGeom.Mesh(mesh_prim)
    points = reader.read(mesh.GetPointsAttr())
    counts = reader.read(mesh.GetFaceVertexCountsAttr())
    indices = reader.read(mesh.GetFaceVertexIndicesAttr())
    if points is None or counts is None or indices is None or len(points) == 0 or len(indices) == 0:
        return None, "The mesh has no geometry."
    points = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    triangles, corners = _triangulate_faces(np.asarray(counts, dtype=np.int64), np.asarray(indices, dtype=np.int64))
    if triangles.shape[0] == 0 or triangles.max() >= points.shape[0]:
        return None, "The mesh has no valid faces."
    st, reason = _read_st(mesh_prim, reader, triangles, corners)
    if st is None:
        return None, reason
    double_sided = reader.read(mesh.GetDoubleSidedAttr())
    orientation = reader.read(mesh.GetOrientationAttr())
    return {
        "points": points,
        "triangles": triangles,
        "st": st,
        "normals": _read_normals(mesh, reader, triangles, corners),
        "transform": _read_transform(mesh_prim, transform_root),
        "double_sided": bool(double_sided),
        "orientation": str(orientation) if orientation else UsdGeom.Tokens.rightHanded,
        "time_sampled": reader.time_sampled,
        "up_axis": str(UsdGeom.GetStageUpAxis(mesh_prim.GetStage())),
    }, None


def read_mesh_source(stage: Usd.Stage, prim_path: str, texture_path: str) -> MeshSource:
    """Read everything the conversion needs about one mesh of a model file.

    Args:
        stage: Stage of the model file.
        prim_path: Path of the mesh prim inside the file.
        texture_path: Absolute path of the diffuse texture the mesh is cut along.

    Returns:
        The mesh source, carrying a skip reason when the mesh cannot be converted.
    """
    mesh_prim = stage.GetPrimAtPath(prim_path)
    if not mesh_prim or not mesh_prim.IsA(UsdGeom.Mesh):
        return MeshSource.skipped(prim_path, "The mesh does not exist in the model file.")
    root = stage.GetDefaultPrim()
    geometry, reason = read_mesh_geometry(mesh_prim, root if root and root.IsValid() else stage.GetPseudoRoot())
    if geometry is None:
        return MeshSource.skipped(prim_path, reason)
    return MeshSource(prim_path=prim_path, texture_path=texture_path, **geometry)

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
    "REPLACEMENT_SUFFIX",
    "find_capture_mesh_prim",
    "find_remix_ref_prim",
    "get_bound_material",
    "get_capture_mesh_root",
    "get_diffuse_texture_path",
    "get_mesh_hash",
    "open_capture_mesh_stage",
    "read_mesh_source",
    "read_mesh_sources",
    "read_replacement_mesh_source",
    "replacement_original_path",
    "replacement_output_path",
    "resolve_conversion_target",
    "resolve_conversion_targets",
]

import os
import re

import numpy as np
import omni.client
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.utils.common import prim_utils
from lightspeed.trex.utils.common.asset_utils import is_layer_from_capture
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdSkel

from .data_models import CAPTURE_KIND, REPLACEMENT_KIND, ConversionTarget, MeshSource

_DIFFUSE_INPUT = "diffuse_texture"
_SKEL_PRIMVAR_PREFIX = "primvars:skel:"
_MDL_RENDER_CONTEXT = "mdl"
_MESH_ROOT_NAME = re.compile(rf"^{constants.MESH_NAME_PREFIX}[A-Z0-9]{{16}}$")
_CAPTURE_CUTOUT_FILE = re.compile(r"^cutout_[A-Z0-9]{16}\.usd[ac]?$", re.IGNORECASE)
REPLACEMENT_SUFFIX = "_cutout_replacement"


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


def get_capture_mesh_root(prim: Usd.Prim | None) -> Usd.Prim | None:
    """Resolve a prim to the capture mesh prototype root it belongs to.

    Args:
        prim: Any prim, an instance or a prototype descendant included.

    Returns:
        The ``mesh_HASH`` root when it comes from a capture and holds a Mesh, else ``None``.
    """
    if not prim or not prim.IsValid():
        return None
    prototype = prim_utils.get_prototype(prim)
    if prototype is None:
        return None
    root = prototype
    while root.IsValid() and root.GetPath() != Sdf.Path.absoluteRootPath:
        if _MESH_ROOT_NAME.match(root.GetName()) and str(root.GetParent().GetPath()) == constants.ROOTNODE_MESHES:
            break
        root = root.GetParent()
    else:
        return None
    if not _AssetReplacementsCore.prim_is_from_a_capture_reference(root):
        return None
    has_mesh = any(descendant.IsA(UsdGeom.Mesh) for descendant in Usd.PrimRange(root) if descendant != root)
    return root if has_mesh else None


def replacement_output_path(original_file: str) -> str:
    """Return the cutout path written next to a replacement file.

    Args:
        original_file: Path of the original replacement file.

    Returns:
        The same path with ``_cutout_replacement`` inserted before the extension, with forward slashes.
    """
    stem, extension = os.path.splitext(original_file)
    return omni.client.normalize_url(f"{stem}{REPLACEMENT_SUFFIX}{extension}")


def replacement_original_path(path: str) -> str:
    """Return the original replacement file of a cutout path, or the path itself when it carries no suffix.

    Args:
        path: Replacement or cutout file path.

    Returns:
        The path without the ``_cutout_replacement`` suffix, with forward slashes.
    """
    stem, extension = os.path.splitext(path)
    stem = stem.removesuffix(REPLACEMENT_SUFFIX)
    return omni.client.normalize_url(f"{stem}{extension}")


def is_replacement_cutout_path(path: str) -> bool:
    """Return whether a path names a replacement cutout file.

    Args:
        path: File path.

    Returns:
        ``True`` when the file stem ends with the cutout suffix.
    """
    return os.path.splitext(path)[0].endswith(REPLACEMENT_SUFFIX)


def find_remix_ref_prim(prim: Usd.Prim | None) -> Usd.Prim | None:
    """Return the nearest ancestor-or-self that the toolkit created to hold a replacement reference.

    Args:
        prim: Any prim.

    Returns:
        The prim carrying the ``IsRemixRef`` attribute, or ``None``.
    """
    current = prim
    while current and current.IsValid() and current.GetPath() != Sdf.Path.absoluteRootPath:
        if current.GetAttribute(constants.IS_REMIX_REF_ATTR).IsValid():
            return current
        current = current.GetParent()
    return None


def _first_reference(prim: Usd.Prim) -> tuple[Sdf.Reference, Sdf.Layer] | None:
    for reference, layer in omni.usd.get_composed_references_from_prim(prim, False):
        if reference.assetPath:
            return reference, layer
    return None


def _is_convertible_mesh(prim: Usd.Prim) -> bool:
    if not prim.IsA(UsdGeom.Mesh) or _is_skinned(prim):
        return False
    if any(child.IsA(UsdGeom.Subset) for child in prim.GetChildren()):
        return False
    material = get_bound_material(prim)
    return bool(material and get_diffuse_texture_path(material))


def _candidate_meshes(ref_prim: Usd.Prim) -> tuple[str, ...]:
    return tuple(
        str(descendant.GetPath())
        for descendant in Usd.PrimRange(ref_prim)
        if descendant != ref_prim and _is_convertible_mesh(descendant)
    )


def resolve_conversion_target(stage: Usd.Stage, prim_path: str) -> ConversionTarget | None:
    """Resolve a selected prim to the capture prototype or replacement reference it belongs to.

    A mesh inside a Remix reference prim is a replacement, unless the reference points at a capture cutout this
    tool wrote, in which case the capture prototype is converted again. Anything else resolves through the
    capture prototype rules.

    Args:
        stage: Stage that holds the prim.
        prim_path: Path of the selected prim, an instance descendant included.

    Returns:
        The target, or ``None`` when nothing convertible is selected.
    """
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return None
    prototype = prim_utils.get_prototype(prim)
    if prototype and prototype.IsValid():
        ref_prim = find_remix_ref_prim(prototype)
        reference = _first_reference(ref_prim) if ref_prim is not None else None
        if reference is not None:
            file_path = omni.client.normalize_url(reference[1].ComputeAbsolutePath(reference[0].assetPath))
            if not _CAPTURE_CUTOUT_FILE.match(os.path.basename(file_path)):
                original = replacement_original_path(file_path)
                return ConversionTarget(
                    REPLACEMENT_KIND,
                    str(prototype.GetPath()),
                    str(ref_prim.GetPath()),
                    _candidate_meshes(ref_prim),
                    original,
                    replacement_output_path(original),
                )
    root = get_capture_mesh_root(prim)
    if root is None:
        return None
    return ConversionTarget(CAPTURE_KIND, str(root.GetPath()), str(root.GetPath()), (str(root.GetPath()),))


def resolve_conversion_targets(stage: Usd.Stage, prim_paths: list[str]) -> list[ConversionTarget]:
    """Map prim paths to their unique conversion targets.

    Args:
        stage: Stage that holds the prims.
        prim_paths: Paths to resolve, in selection order.

    Returns:
        Targets without duplicate roots, in first-seen order.
    """
    targets: dict[str, ConversionTarget] = {}
    for prim_path in prim_paths:
        target = resolve_conversion_target(stage, prim_path)
        if target is not None and target.root_path not in targets:
            targets[target.root_path] = target
    return list(targets.values())


def get_mesh_hash(prim_path: str) -> str:
    """Return the hash part of a ``mesh_HASH`` prototype path.

    Args:
        prim_path: Path whose last component is a capture mesh prototype name.

    Returns:
        The hash, or an empty string when the path is not a prototype path.
    """
    match = re.match(constants.REGEX_MESH_PATH, prim_path)
    return match.group(3) if match else ""


def find_capture_mesh_prim(root_prim: Usd.Prim) -> Usd.Prim | None:
    """Return the Mesh prim that holds the captured geometry of a prototype root.

    Args:
        root_prim: The ``mesh_HASH`` Xform prim.

    Returns:
        The ``mesh`` child when it is a Mesh, else the first Mesh descendant, else ``None``.
    """
    if not root_prim or not root_prim.IsValid():
        return None
    child = root_prim.GetChild(constants.MESH_SUB_MESH_NAME)
    if child and child.IsA(UsdGeom.Mesh):
        return child
    for descendant in Usd.PrimRange(root_prim):
        if descendant != root_prim and descendant.IsA(UsdGeom.Mesh):
            return descendant
    return None


def open_capture_mesh_stage(root_prim: Usd.Prim) -> tuple[Usd.Stage, Usd.Prim] | None:
    """Open the capture mesh file a prototype root references in the capture layer.

    The capture layer's prim spec keeps its reference even after a replacement layer masks it, so the
    original geometry stays reachable once the prototype has been replaced.

    Args:
        root_prim: The ``mesh_HASH`` Xform prim of the project stage.

    Returns:
        The opened stage and the referenced prim inside it, or ``None`` without a capture reference.
    """
    for spec in root_prim.GetPrimStack():
        if not spec.layer.realPath or not is_layer_from_capture(spec.layer.realPath) or not spec.hasReferences:
            continue
        references = spec.referenceList
        for reference in (
            list(references.prependedItems) + list(references.appendedItems) + list(references.explicitItems)
        ):
            if not reference.assetPath:
                continue
            capture_stage = Usd.Stage.Open(spec.layer.ComputeAbsolutePath(reference.assetPath))
            if not capture_stage:
                continue
            prim = (
                capture_stage.GetPrimAtPath(reference.primPath)
                if reference.primPath
                else capture_stage.GetDefaultPrim()
            )
            if prim and prim.IsValid():
                return capture_stage, prim
    return None


def get_bound_material(prim: Usd.Prim) -> UsdShade.Material | None:
    """Return the material bound to a prim, inherited bindings included.

    Args:
        prim: Mesh or ancestor prim.

    Returns:
        The bound material, or ``None``.
    """
    material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    return material or None


def get_diffuse_texture_path(material: UsdShade.Material) -> str | None:
    """Return the absolute path of the diffuse texture of an Aperture material.

    Args:
        material: Material whose surface shader declares ``inputs:diffuse_texture``.

    Returns:
        Normalized absolute texture path, or ``None`` when the material has no diffuse texture.
    """
    shader = _get_surface_shader(material)
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


def _get_surface_shader(material: UsdShade.Material) -> UsdShade.Shader | None:
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


def _is_skinned(mesh_prim: Usd.Prim) -> bool:
    """Return whether a mesh carries skeleton bindings that the cutout cannot preserve.

    Args:
        mesh_prim: Mesh prim to inspect.

    Returns:
        ``True`` when the mesh is skinned or has blend shapes.
    """
    if mesh_prim.HasAPI(UsdSkel.BindingAPI):
        return True
    return any(attribute.GetName().startswith(_SKEL_PRIMVAR_PREFIX) for attribute in mesh_prim.GetAttributes())


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
    """Read the transform of the mesh relative to the prototype root.

    Captures can place a correction Xform between the root and the mesh, so every xform op below the root is
    folded into one matrix that the generated file authors on its mesh.

    Args:
        mesh_prim: Mesh prim to read.
        root_prim: Prototype root the transform is relative to.

    Returns:
        Sixteen row-major values, or ``None`` when the transform is the identity.
    """
    matrix = UsdGeom.XformCache(Usd.TimeCode.Default()).ComputeRelativeTransform(mesh_prim, root_prim)[0]
    if matrix == Gf.Matrix4d(1.0):
        return None
    return tuple(float(value) for value in np.asarray(matrix, dtype=np.float64).reshape(16))


def _read_geometry(mesh_prim: Usd.Prim, transform_root: Usd.Prim) -> tuple[dict | None, str | None]:
    """Read the geometry fields of a mesh prim.

    Args:
        mesh_prim: Mesh prim to read.
        transform_root: Prim the mesh transform is expressed relative to.

    Returns:
        The ``MeshSource`` geometry fields, or ``None`` with the reason the mesh cannot be converted.
    """
    if _is_skinned(mesh_prim):
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


def read_mesh_source(stage: Usd.Stage, mesh_root_path: str) -> MeshSource:
    """Read everything the conversion needs about one capture mesh.

    Args:
        stage: Stage that holds the capture.
        mesh_root_path: Path of the ``mesh_HASH`` prototype root.

    Returns:
        The mesh source, carrying a skip reason when the mesh cannot be converted.
    """
    mesh_hash = get_mesh_hash(mesh_root_path)
    root_prim = stage.GetPrimAtPath(mesh_root_path)
    if not root_prim or not root_prim.IsValid():
        return MeshSource.skipped(mesh_root_path, mesh_hash, "The prim does not exist.")
    # The capture file is read directly so a mesh whose capture reference is already masked by an earlier
    # conversion still yields the original geometry instead of the cutout that replaced it.
    capture = open_capture_mesh_stage(root_prim)
    geometry_root = capture[1] if capture else root_prim
    mesh_prim = find_capture_mesh_prim(geometry_root)
    if mesh_prim is None:
        return MeshSource.skipped(mesh_root_path, mesh_hash, "The prototype has no Mesh prim.")
    geometry, reason = _read_geometry(mesh_prim, geometry_root)
    if geometry is None:
        return MeshSource.skipped(mesh_root_path, mesh_hash, reason)
    material = get_bound_material(root_prim) or get_bound_material(mesh_prim)
    texture_path = get_diffuse_texture_path(material) if material else None
    if not texture_path:
        return MeshSource.skipped(mesh_root_path, mesh_hash, "The bound material has no diffuse texture.")
    return MeshSource(
        prim_path=mesh_root_path,
        mesh_hash=mesh_hash,
        texture_path=texture_path,
        material_path=str(material.GetPath()),
        **geometry,
    )


def read_replacement_mesh_source(stage: Usd.Stage, target: ConversionTarget, mesh_path: str) -> MeshSource:
    """Read one mesh of a replacement: geometry from the original file, material from the composed stage.

    The original file is read so a reference that already points at a cutout still yields the untouched
    geometry, while the stage prim carries the user's material overrides.

    Args:
        stage: Project stage.
        target: Replacement target that owns the mesh.
        mesh_path: Stage path of the mesh prim under the reference prim.

    Returns:
        The mesh source, carrying a skip reason when the mesh cannot be converted.
    """
    mesh_hash = get_mesh_hash(str(Sdf.Path(target.root_path).GetParentPath()))

    def skipped(reason: str) -> MeshSource:
        return MeshSource.skipped(mesh_path, mesh_hash, reason, target.root_path, target.original_file)

    stage_prim = stage.GetPrimAtPath(mesh_path)
    ref_prim = stage.GetPrimAtPath(target.root_path)
    if not stage_prim or not stage_prim.IsValid() or not ref_prim or not ref_prim.IsValid():
        return skipped("The prim does not exist.")
    reference = _first_reference(ref_prim)
    if reference is None:
        return skipped("The replacement has no reference.")
    file_stage = Usd.Stage.Open(target.original_file) if target.original_file else None
    if not file_stage:
        return skipped("The original replacement file could not be opened.")
    file_root = (
        file_stage.GetPrimAtPath(reference[0].primPath) if reference[0].primPath else file_stage.GetDefaultPrim()
    )
    if not file_root or not file_root.IsValid():
        return skipped("The original replacement file has no default prim.")
    relative = mesh_path[len(target.root_path) :].strip("/")
    file_prim_path = file_root.GetPath().AppendPath(relative) if relative else file_root.GetPath()
    file_mesh = file_stage.GetPrimAtPath(file_prim_path)
    if not file_mesh or not file_mesh.IsA(UsdGeom.Mesh):
        return skipped("The mesh does not exist in the original replacement file.")
    geometry, reason = _read_geometry(file_mesh, file_root)
    if geometry is None:
        return skipped(reason)
    material = get_bound_material(stage_prim)
    texture_path = get_diffuse_texture_path(material) if material else None
    if not texture_path:
        return skipped("The bound material has no diffuse texture.")
    return MeshSource(
        prim_path=mesh_path,
        mesh_hash=mesh_hash,
        texture_path=texture_path,
        material_path=str(material.GetPath()),
        ref_prim_path=target.root_path,
        replacement_file=target.original_file,
        file_prim_path=str(file_prim_path),
        **geometry,
    )


def read_mesh_sources(
    stage: Usd.Stage, mesh_paths: list[str], target: ConversionTarget | None = None
) -> list[MeshSource]:
    """Read several meshes of one target.

    Args:
        stage: Project stage.
        mesh_paths: Prototype roots for captures, mesh prim paths for replacements.
        target: The target the paths belong to; ``None`` reads capture prototypes.

    Returns:
        One source per path, in order.
    """
    if target is not None and target.is_replacement:
        return [read_replacement_mesh_source(stage, target, path) for path in mesh_paths]
    return [read_mesh_source(stage, path) for path in mesh_paths]

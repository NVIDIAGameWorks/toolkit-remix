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
    "ConversionTarget",
    "CutMesh",
    "CutoutParameters",
    "MeshCutoutResult",
    "MeshSource",
    "StageEditOutcome",
]

import dataclasses
from dataclasses import dataclass

import numpy as np

CAPTURE_KIND = "capture"
REPLACEMENT_KIND = "replacement"


@dataclass(frozen=True)
class ConversionTarget:
    """What a selection resolves to: a capture prototype or a replacement reference with its meshes.

    Attributes:
        kind: ``"capture"`` or ``"replacement"``.
        prim_path: Path of the selected prim, shown to the user.
        root_path: The ``mesh_HASH`` prototype root for captures, the ``ref_*`` reference prim for replacements.
        meshes: Stage paths of the meshes that can be converted; the prototype root itself for captures.
        original_file: Absolute path of the original replacement file, or ``None`` for captures.
        output_file: Absolute path of the cutout file written next to the original, or ``None`` for captures.
    """

    kind: str
    prim_path: str
    root_path: str
    meshes: tuple[str, ...]
    original_file: str | None = None
    output_file: str | None = None

    @property
    def is_replacement(self) -> bool:
        """Return whether the target is a replacement reference.

        Returns:
            ``True`` for replacements.
        """
        return self.kind == REPLACEMENT_KIND


@dataclass(frozen=True)
class CutoutParameters:
    """Tunable settings of one conversion run.

    Attributes:
        alpha_threshold: Alpha value (0-255) at or above which a texel counts as opaque.
        trace_resolution: Longest side, in texels, of the downscaled mask that is traced.
        simplify_tolerance: Douglas-Peucker tolerance in traced texels.
        edge_margin: Distance in traced texels the outline grows (positive) or shrinks (negative).
        min_island_area: Outline islands smaller than this many traced texels are dropped.
        minimal_outline: Connect the traced outline with the fewest vertices within ``simplify_tolerance``
            instead of the greedy Douglas-Peucker pass.
        thicken: Extrude the cut mesh backwards, against the surface normal.
        thickness: Extrusion distance in mesh units.
        thicken_back_face: Close the extrusion with a reversed copy of the front face.
        thicken_anti_stretch: Texture the extruded sides with a band inside the outline instead of smearing
            the edge.
        smooth_normals: Blend the normals of the thickened mesh towards the average around each position.
        smoothing: Strength of the normal smoothing from 0 to 1.
        up_normals: Blend every normal towards the stage up axis.
        up_amount: Strength of the up-facing blend from 0 to 1.
    """

    alpha_threshold: int = 128
    trace_resolution: int = 256
    simplify_tolerance: float = 1.0
    edge_margin: float = 1.0
    min_island_area: float = 4.0
    minimal_outline: bool = True
    thicken: bool = False
    thickness: float = 1.0
    thicken_back_face: bool = True
    thicken_anti_stretch: bool = False
    smooth_normals: bool = False
    smoothing: float = 1.0
    up_normals: bool = False
    up_amount: float = 1.0


@dataclass(frozen=True)
class MeshSource:
    """Everything the worker needs about one capture mesh, read from USD on the main thread.

    Attributes:
        prim_path: Path of the ``mesh_HASH`` prototype root.
        mesh_hash: Hash part of the prototype name.
        points: ``(N, 3)`` float32 vertex positions.
        triangles: ``(T, 3)`` int32 indices into ``points``.
        st: ``(T, 3, 2)`` float32 texture coordinates per triangle corner.
        normals: ``(T, 3, 3)`` float32 normals per triangle corner, or ``None``.
        transform: Sixteen row-major values of the mesh ``xformOp:transform``, or ``None``.
        double_sided: Value of the mesh ``doubleSided`` attribute.
        orientation: Value of the mesh ``orientation`` attribute.
        texture_path: Absolute path of the bound material's diffuse texture, or ``None``.
        material_path: Path of the bound material prim, or ``None``.
        time_sampled: Whether geometry came from the first time sample instead of the default value.
        skip_reason: Why the mesh cannot be converted, or ``None``.
        up_axis: Stage up axis token, ``"Y"`` or ``"Z"``.
        ref_prim_path: Path of the ``ref_*`` prim that references the replacement file, or ``None``.
        replacement_file: Absolute path of the original replacement file, or ``None`` for captures.
        file_prim_path: Path of the mesh prim inside the replacement file, or ``None`` for captures.
    """

    prim_path: str
    mesh_hash: str
    points: np.ndarray
    triangles: np.ndarray
    st: np.ndarray
    normals: np.ndarray | None
    transform: tuple[float, ...] | None
    double_sided: bool
    orientation: str
    texture_path: str | None
    material_path: str | None
    time_sampled: bool = False
    skip_reason: str | None = None
    up_axis: str = "Y"
    ref_prim_path: str | None = None
    replacement_file: str | None = None
    file_prim_path: str | None = None

    @classmethod
    def skipped(
        cls,
        prim_path: str,
        mesh_hash: str,
        reason: str,
        ref_prim_path: str | None = None,
        replacement_file: str | None = None,
    ) -> MeshSource:
        """Build a source that only carries a skip reason.

        Args:
            prim_path: Path of the ``mesh_HASH`` prototype root, or of the replacement mesh.
            mesh_hash: Hash part of the prototype name.
            reason: Why the mesh cannot be converted.
            ref_prim_path: Reference prim of a replacement mesh.
            replacement_file: Original file of a replacement mesh.

        Returns:
            Source with empty geometry and the given reason.
        """
        return cls(
            prim_path=prim_path,
            mesh_hash=mesh_hash,
            points=np.zeros((0, 3), dtype=np.float32),
            triangles=np.zeros((0, 3), dtype=np.int32),
            st=np.zeros((0, 3, 2), dtype=np.float32),
            normals=None,
            transform=None,
            double_sided=False,
            orientation="rightHanded",
            texture_path=None,
            material_path=None,
            skip_reason=reason,
            ref_prim_path=ref_prim_path,
            replacement_file=replacement_file,
        )


@dataclass(frozen=True)
class CutMesh:
    """Welded output geometry of one conversion.

    Attributes:
        points: ``(V, 3)`` float32 vertex positions.
        triangles: ``(T, 3)`` int32 indices into ``points``.
        st: ``(V, 2)`` float32 texture coordinates per vertex.
        normals: ``(V, 3)`` float32 normals per vertex, or ``None``.
    """

    points: np.ndarray
    triangles: np.ndarray
    st: np.ndarray
    normals: np.ndarray | None


@dataclass(frozen=True)
class MeshCutoutResult:
    """Outcome of converting one mesh.

    Attributes:
        source: Mesh the result was computed from.
        cut_mesh: Output geometry, or ``None`` when the mesh was skipped.
        input_triangle_count: Triangle count of the source mesh.
        output_triangle_count: Triangle count of the output mesh.
        removed_uv_area_percent: Share of the source texture area that was cut away.
        skip_reason: Why no geometry was produced, or ``None``.
        output_path: Path of the written replacement file, or ``None`` before writing.
    """

    source: MeshSource
    cut_mesh: CutMesh | None
    input_triangle_count: int
    output_triangle_count: int
    removed_uv_area_percent: float
    skip_reason: str | None = None
    output_path: str | None = None

    @classmethod
    def skipped(cls, source: MeshSource, reason: str) -> MeshCutoutResult:
        """Build a result for a mesh that produced no geometry.

        Args:
            source: Mesh that was skipped.
            reason: Why no geometry was produced.

        Returns:
            Result without geometry.
        """
        return cls(
            source=source,
            cut_mesh=None,
            input_triangle_count=int(source.triangles.shape[0]),
            output_triangle_count=0,
            removed_uv_area_percent=0.0,
            skip_reason=reason,
        )

    def with_output_path(self, output_path: str) -> MeshCutoutResult:
        """Return a copy that records where the geometry was written.

        Args:
            output_path: Path of the written replacement file.

        Returns:
            Copy with ``output_path`` set.
        """
        return dataclasses.replace(self, output_path=output_path)

    def with_skip_reason(self, reason: str) -> MeshCutoutResult:
        """Return a copy that records a late failure, such as a write error.

        Args:
            reason: Why the result could not be applied.

        Returns:
            Copy with ``skip_reason`` set and no output path.
        """
        return dataclasses.replace(self, skip_reason=reason, output_path=None)


@dataclass(frozen=True)
class StageEditOutcome:
    """What the stage edit did for one converted mesh.

    Attributes:
        prim_path: Path of the ``mesh_HASH`` prototype root.
        reference_prim_path: Path of the child prim that references the cutout file, or ``None``.
        reference_added: Whether a new reference was added, as opposed to reused.
        skip_reason: Why no edit was made, or ``None``.
    """

    prim_path: str
    reference_prim_path: str | None
    reference_added: bool
    skip_reason: str | None = None

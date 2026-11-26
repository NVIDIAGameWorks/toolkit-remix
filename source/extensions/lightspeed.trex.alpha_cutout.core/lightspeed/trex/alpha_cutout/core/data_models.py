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

__all__ = ["CutMesh", "CutoutParameters", "MeshCutoutResult", "MeshSource"]

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CutoutParameters:
    """Tunable settings of one conversion run.

    Attributes:
        alpha_threshold: Alpha value (0-255) at or above which a texel counts as opaque.
        trace_resolution: Longest side, in texels, of the downscaled mask that is traced.
        simplify_tolerance: Largest deviation from the traced outline, in traced texels.
        edge_margin: Distance in traced texels the outline grows (positive) or shrinks (negative).
        min_island_area: Outline islands smaller than this many traced texels are dropped.
        minimal_outline: Connect the traced outline with the fewest vertices within ``simplify_tolerance``
            instead of the greedy Douglas-Peucker pass.
        disable_alpha_test: Author the opaque alpha state on the material so the runtime skips alpha testing.
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
    edge_margin: float = 0.0
    min_island_area: float = 4.0
    minimal_outline: bool = True
    disable_alpha_test: bool = True
    thicken: bool = False
    thickness: float = 1.0
    thicken_back_face: bool = True
    thicken_anti_stretch: bool = True
    smooth_normals: bool = False
    smoothing: float = 1.0
    up_normals: bool = False
    up_amount: float = 1.0


@dataclass(frozen=True)
class MeshSource:
    """Everything the worker needs about one mesh, read from USD on the main thread.

    Attributes:
        prim_path: Path of the mesh prim inside its model file.
        points: ``(N, 3)`` float32 vertex positions.
        triangles: ``(T, 3)`` int32 indices into ``points``.
        st: ``(T, 3, 2)`` float32 texture coordinates per triangle corner.
        normals: ``(T, 3, 3)`` float32 normals per triangle corner, or ``None``.
        transform: Sixteen row-major values of the mesh transform relative to the model root, or ``None``.
        double_sided: Value of the mesh ``doubleSided`` attribute.
        orientation: Value of the mesh ``orientation`` attribute.
        texture_path: Absolute path of the diffuse texture, or ``None``.
        time_sampled: Whether geometry came from the first time sample instead of the default value.
        skip_reason: Why the mesh cannot be converted, or ``None``.
        up_axis: Stage up axis token, ``"Y"`` or ``"Z"``.
    """

    prim_path: str
    points: np.ndarray
    triangles: np.ndarray
    st: np.ndarray
    normals: np.ndarray | None
    transform: tuple[float, ...] | None
    double_sided: bool
    orientation: str
    texture_path: str | None
    time_sampled: bool = False
    skip_reason: str | None = None
    up_axis: str = "Y"

    @classmethod
    def skipped(cls, prim_path: str, reason: str) -> MeshSource:
        """Build a source that only carries a skip reason.

        Args:
            prim_path: Path of the mesh prim.
            reason: Why the mesh cannot be converted.

        Returns:
            Source with empty geometry and the given reason.
        """
        return cls(
            prim_path=prim_path,
            points=np.zeros((0, 3), dtype=np.float32),
            triangles=np.zeros((0, 3), dtype=np.int32),
            st=np.zeros((0, 3, 2), dtype=np.float32),
            normals=None,
            transform=None,
            double_sided=False,
            orientation="rightHanded",
            texture_path=None,
            skip_reason=reason,
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
    """

    source: MeshSource
    cut_mesh: CutMesh | None
    input_triangle_count: int
    output_triangle_count: int
    removed_uv_area_percent: float
    skip_reason: str | None = None

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

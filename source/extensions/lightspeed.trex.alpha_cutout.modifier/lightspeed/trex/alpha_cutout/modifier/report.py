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

__all__ = ["REPORT_CODECS", "ConversionReport", "MeshReport"]

from dataclasses import dataclass

from lightspeed.trex.alpha_cutout.core import CutMesh, MeshSource
from omni.flux.job_queue.core.persistence_codec import PersistenceCodec, decode_positional_payload

_SUMMARY_MESHES = 4


@dataclass(frozen=True, slots=True)
class MeshReport:
    """Geometry counts of one mesh before and after the cut.

    Attributes:
        prim_path: Path of the mesh inside the model file.
        source_vertices: Vertex count of the source mesh.
        source_faces: Triangle count of the source mesh.
        vertices: Vertex count of the cut mesh, ``0`` when the mesh was skipped.
        faces: Triangle count of the cut mesh, ``0`` when the mesh was skipped.
        skip_reason: Why the mesh was copied unchanged, or ``None`` when it was cut.
    """

    prim_path: str
    source_vertices: int
    source_faces: int
    vertices: int
    faces: int
    skip_reason: str | None = None

    @classmethod
    def from_conversion(
        cls, prim_path: str, source: MeshSource, cut_mesh: CutMesh | None, skip_reason: str | None = None
    ) -> MeshReport:
        """Count the geometry of a source and of what the cut produced.

        Args:
            prim_path: Path of the mesh inside the model file.
            source: Mesh that was read from the model file.
            cut_mesh: Cut geometry, or ``None`` when the mesh was skipped.
            skip_reason: Why the mesh was skipped.

        Returns:
            The counts of both meshes.
        """
        return cls(
            prim_path,
            int(source.points.shape[0]),
            int(source.triangles.shape[0]),
            int(cut_mesh.points.shape[0]) if cut_mesh is not None else 0,
            int(cut_mesh.triangles.shape[0]) if cut_mesh is not None else 0,
            skip_reason,
        )

    def describe(self) -> str:
        """Describe what the cut did to the mesh in one line.

        The mesh is named by its path below the model's root prim, so the meshes of one model stay
        distinguishable.

        Returns:
            The mesh name with its face and vertex counts before and after the cut, or with the skip reason.
        """
        parts = self.prim_path.strip("/").split("/")
        name = "/".join(parts[1:]) if len(parts) > 1 else self.prim_path
        if self.skip_reason:
            return f"{name}: Skipped: {self.skip_reason}"
        return (
            f"{name}: {self.source_faces:,} -> {self.faces:,} faces, "
            f"{self.source_vertices:,} -> {self.vertices:,} vertices"
        )


@dataclass(frozen=True, slots=True)
class ConversionReport:
    """Counts of every mesh a job handled, in job order.

    Attributes:
        meshes: One report per listed mesh.
    """

    meshes: tuple[MeshReport, ...]

    def __post_init__(self) -> None:
        """Validate the persisted report boundary.

        Raises:
            TypeError: If the meshes are not a tuple of mesh reports.
        """
        if type(self.meshes) is not tuple or not all(type(item) is MeshReport for item in self.meshes):
            raise TypeError("meshes must be a tuple of MeshReport values")

    def summarize(self) -> str:
        """Describe the report in a few lines.

        Returns:
            The number of converted meshes, one line per mesh up to a short limit, then a count of the
            remaining meshes.
        """
        total = len(self.meshes)
        converted = sum(item.skip_reason is None for item in self.meshes)
        lines = [f"Converted {converted} of {total} mesh{'es' if total != 1 else ''}"]
        lines.extend(item.describe() for item in self.meshes[:_SUMMARY_MESHES])
        remaining = total - _SUMMARY_MESHES
        if remaining > 0:
            lines.append(f"and {remaining} more mesh{'es' if remaining != 1 else ''}")
        return "\n".join(lines)


# The field order is the persisted schema: only append fields, with defaults, and keep decoding older shapes.
REPORT_CODECS = (
    PersistenceCodec(
        "alpha_cutout.MeshReport",
        MeshReport,
        lambda value: (
            value.prim_path,
            value.source_vertices,
            value.source_faces,
            value.vertices,
            value.faces,
            value.skip_reason,
        ),
        lambda payload: decode_positional_payload(MeshReport, payload, 6),
    ),
    PersistenceCodec(
        "alpha_cutout.ConversionReport",
        ConversionReport,
        lambda value: (value.meshes,),
        lambda payload: decode_positional_payload(ConversionReport, payload, 1),
    ),
)

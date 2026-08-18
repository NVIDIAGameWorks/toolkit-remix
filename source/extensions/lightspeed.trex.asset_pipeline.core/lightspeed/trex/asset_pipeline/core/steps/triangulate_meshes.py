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

__all__ = ["TriangulateMeshesStep"]

from dataclasses import dataclass

import carb
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from pxr import Sdf, Usd, UsdGeom, Vt

from ..pipeline_context import RemixAssetPipelineContext
from ..pipeline_item import AssetKind, RemixAssetItem


@dataclass
class _SubsetFaces:
    subset: UsdGeom.Subset
    new_faces: list[int]


class TriangulateMeshesStep(PipelineStep):
    """Triangulate model meshes after input standardization."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier.

        Returns:
            Stable pipeline step name.
        """
        return "triangulate_meshes"

    @property
    def description(self) -> str:
        """Return a human-readable description.

        Returns:
            User-facing phase description.
        """
        return "Prepare model geometry"

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return true when any model mesh contains non-triangle faces.

        Args:
            context: Remix pipeline state containing standardized model stages.

        Returns:
            Whether any model mesh requires triangulation.
        """
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue
            stage = context.open_stage(item.value)

            predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
            for prim in Usd.PrimRange(stage.GetPseudoRoot(), predicate):
                if prim.IsA(UsdGeom.Mesh) and not _is_triangulated(_get_face_counts(prim)):
                    return True
        return False

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no mesh triangulation work.

        Args:
            context: Pipeline state without triangulation work.

        Returns:
            User-readable skip reason.
        """
        if not any(item.kind is AssetKind.MODEL for item in context.items):
            return "no model items"
        return "all model meshes are already triangulated"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Triangulate mesh face counts/indices and matching geom subsets in place.

        Args:
            context: Remix pipeline state containing standardized model stages.

        Raises:
            ValueError: If a mesh is missing authored face counts.
        """
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            stage = context.open_stage(item.value)

            changed = False
            with Sdf.ChangeBlock():
                predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
                for prim in Usd.PrimRange(stage.GetPseudoRoot(), predicate):
                    if prim.IsA(UsdGeom.Mesh) and _triangulate_mesh(prim):
                        changed = True

            if changed:
                context.save_stage()
                carb.log_info(f"[TriangulateMeshes] Saved triangulated stage {item.value}")


def _get_face_counts(prim: Usd.Prim) -> Vt.IntArray | None:
    """Return authored face counts for one mesh prim.

    Args:
        prim: Candidate mesh prim.

    Returns:
        Authored face counts, or ``None`` when unavailable.
    """
    mesh = UsdGeom.Mesh(prim)
    if not mesh:
        return None
    return mesh.GetFaceVertexCountsAttr().Get()


def _is_triangulated(face_counts: Vt.IntArray | None) -> bool:
    """Return whether every authored face has exactly three vertices.

    Args:
        face_counts: Authored per-face vertex counts, if available.

    Returns:
        Whether the face counts describe only triangles.
    """
    return face_counts is not None and all(face_count == 3 for face_count in face_counts)


def _triangulate_mesh(prim: Usd.Prim) -> bool:
    """Triangulate one mesh using the existing validation fan algorithm.

    The fan split preserves current validator behavior and assumes triangles,
    quads, or convex N-gons. It is not a general concave polygon tessellator.

    Args:
        prim: Mesh prim to triangulate in place.

    Returns:
        Whether the mesh topology changed.

    Raises:
        ValueError: If the mesh is missing authored face counts.
    """
    mesh = UsdGeom.Mesh(prim)
    face_counts = mesh.GetFaceVertexCountsAttr().Get()
    if face_counts is None:
        raise ValueError(f"{prim.GetPath()} is missing faceVertexCounts")
    if _is_triangulated(face_counts):
        return False

    indices = mesh.GetFaceVertexIndicesAttr().Get()
    if not indices or not face_counts:
        return False

    indices_offset = 0
    new_face_counts = []
    triangles = []
    subsets: list[_SubsetFaces] = []
    face_to_subsets: dict[int, list[_SubsetFaces]] = {}

    for child_prim in prim.GetChildren():
        if child_prim.IsA(UsdGeom.Subset):
            subset = UsdGeom.Subset.Get(prim.GetStage(), child_prim.GetPath())
            subset_indices_attr = subset.GetIndicesAttr()
            if not subset_indices_attr.HasAuthoredValue():
                continue
            subset_indices = subset_indices_attr.Get()
            if subset_indices is None:
                continue
            subset_faces = _SubsetFaces(subset=subset, new_faces=[])
            subsets.append(subset_faces)
            for old_face_index in subset_indices:
                face_to_subsets.setdefault(old_face_index, []).append(subset_faces)

    for old_face_index, face_count in enumerate(face_counts):
        start_index = indices[indices_offset]
        for face_index in range(face_count - 2):
            for subset in face_to_subsets.get(old_face_index, []):
                subset.new_faces.append(len(new_face_counts))
            new_face_counts.append(3)
            triangles.append(start_index)
            triangles.append(indices[indices_offset + face_index + 1])
            triangles.append(indices[indices_offset + face_index + 2])
        indices_offset += face_count

    for subset in subsets:
        subset.subset.GetIndicesAttr().Set(subset.new_faces)

    mesh.GetFaceVertexIndicesAttr().Set(triangles)
    mesh.GetFaceVertexCountsAttr().Set(new_face_counts)
    return True

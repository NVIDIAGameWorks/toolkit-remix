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

__all__ = ["convert_mesh", "convert_meshes"]

from collections.abc import Callable
from typing import Any

import carb

from .cut import cut_triangles
from .data_models import CutoutParameters, MeshCutoutResult, MeshSource
from .mask import build_alpha_field, is_alpha_uniformly_opaque, load_alpha, mask_polygons_to_uv, trace_alpha_mask
from .normals import bend_normals_up, smooth_normals, up_vector
from .thicken import thicken_mesh

_PROGRESS_STEPS = 1000
_NOTHING_TO_CUT = "The texture has no transparent texels."
_NOTHING_OPAQUE = "No opaque area is left at this threshold."


def convert_mesh(
    source: MeshSource,
    parameters: CutoutParameters,
    is_cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> MeshCutoutResult | None:
    """Cut one mesh along the alpha of its diffuse texture.

    This runs on a worker thread and touches no USD object.

    Args:
        source: Mesh read on the main thread.
        parameters: Tunable conversion settings.
        is_cancelled: Optional callback that returns ``True`` to abort.
        progress: Optional callback receiving the processed and total triangle counts.

    Returns:
        The result, or ``None`` when cancelled.

    Raises:
        OSError: If the texture cannot be decoded.
    """
    if source.skip_reason:
        return MeshCutoutResult.skipped(source, source.skip_reason)
    alpha = load_alpha(source.texture_path)
    if is_alpha_uniformly_opaque(alpha):
        return MeshCutoutResult.skipped(source, _NOTHING_TO_CUT)
    mask = build_alpha_field(alpha, parameters.trace_resolution)
    polygons = trace_alpha_mask(
        mask,
        parameters.alpha_threshold,
        parameters.simplify_tolerance,
        parameters.edge_margin,
        parameters.min_island_area,
        minimal_outline=parameters.minimal_outline,
    )
    if not polygons:
        return MeshCutoutResult.skipped(source, _NOTHING_OPAQUE)
    cut_mesh, removed_percent = cut_triangles(
        source, mask_polygons_to_uv(polygons, mask.shape), progress=progress, is_cancelled=is_cancelled
    )
    if cut_mesh is None:
        return None
    if parameters.thicken:
        cut_mesh = thicken_mesh(
            cut_mesh,
            parameters.thickness,
            back_face=parameters.thicken_back_face,
            anti_stretch=parameters.thicken_anti_stretch,
            orientation=source.orientation,
        )
        if parameters.smooth_normals:
            cut_mesh = smooth_normals(cut_mesh, parameters.smoothing, source.orientation)
    if parameters.up_normals:
        cut_mesh = bend_normals_up(
            cut_mesh, up_vector(source.up_axis, source.transform), parameters.up_amount, source.orientation
        )
    return MeshCutoutResult(
        source=source,
        cut_mesh=cut_mesh,
        input_triangle_count=int(source.triangles.shape[0]),
        output_triangle_count=int(cut_mesh.triangles.shape[0]),
        removed_uv_area_percent=removed_percent,
    )


def _status_text(source: MeshSource, index: int, total: int) -> str:
    """Return a short progress status: the mesh name relative to its reference prim, never the full path.

    Args:
        source: Mesh being converted.
        index: Zero-based position in the run.
        total: Number of meshes in the run.

    Returns:
        Text for the progress popup.
    """
    name = source.prim_path
    if source.ref_prim_path and name.startswith(source.ref_prim_path):
        name = name[len(source.ref_prim_path) :].strip("/") or name
    name = name.rsplit("/", 1)[-1] if not source.ref_prim_path else name
    return f"Converting {index + 1} of {total}: {name}"


def convert_meshes(
    sources: list[MeshSource],
    parameters: CutoutParameters,
    queue_progress: Callable[[int, int | None, Any | None], None],
    is_cancelled: Callable[[], bool],
) -> list[MeshCutoutResult]:
    """Cut several meshes, reporting progress per mesh.

    This is the worker passed to ``run_worker_with_latest_progress``. A mesh whose texture cannot be decoded is
    reported through its skip reason so the other meshes still convert.

    Args:
        sources: Meshes read on the main thread.
        parameters: Tunable conversion settings.
        queue_progress: Progress queue of the worker runner.
        is_cancelled: Callback that returns ``True`` to abort.

    Returns:
        One result per source, in order; a cancelled run returns the results finished so far.
    """
    results: list[MeshCutoutResult] = []
    total = len(sources)
    for index, source in enumerate(sources):
        if is_cancelled():
            break
        queue_progress(index * _PROGRESS_STEPS, total * _PROGRESS_STEPS, _status_text(source, index, total))

        def report(current: int, triangle_count: int, mesh_index: int = index) -> None:
            fraction = current / triangle_count if triangle_count else 1.0
            queue_progress(mesh_index * _PROGRESS_STEPS + int(fraction * _PROGRESS_STEPS), None, None)

        try:
            result = convert_mesh(source, parameters, is_cancelled=is_cancelled, progress=report)
        except (OSError, ValueError, NotImplementedError) as error:
            carb.log_warn(f"[lightspeed.trex.alpha_cutout.core] {source.prim_path}: {error}")
            result = MeshCutoutResult.skipped(source, f"The texture could not be decoded: {error}")
        if result is None:
            break
        results.append(result)
    queue_progress(len(results) * _PROGRESS_STEPS, total * _PROGRESS_STEPS, None)
    return results

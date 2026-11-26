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

__all__ = ["barycentric_coordinates", "cut_triangles"]

import math
from collections.abc import Callable

import numpy as np
import shapely
from shapely import STRtree
from shapely.affinity import translate
from shapely.geometry import Polygon

from .data_models import CutMesh, MeshSource
from .triangulate import triangulate_shapely_polygon

_DEGENERATE_UV_AREA = 1e-12
_COVERED_TOLERANCE = 1e-6
_PROGRESS_STRIDE = 64


def barycentric_coordinates(points_uv: np.ndarray, triangle_uv: np.ndarray) -> np.ndarray:
    """Express points as barycentric weights of a UV triangle.

    Args:
        points_uv: ``(P, 2)`` points inside or near the triangle.
        triangle_uv: ``(3, 2)`` triangle corners.

    Returns:
        ``(P, 3)`` weights that sum to one per point.
    """
    a, b, c = triangle_uv
    v0 = b - a
    v1 = c - a
    v2 = points_uv - a
    d00 = float(np.dot(v0, v0))
    d01 = float(np.dot(v0, v1))
    d11 = float(np.dot(v1, v1))
    d20 = v2 @ v0
    d21 = v2 @ v1
    denominator = d00 * d11 - d01 * d01
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    return np.column_stack((1.0 - v - w, v, w))


class _MaskIndex:
    """Spatial index over the triangulated opaque UV region, tiled on demand for texture coordinates outside the unit square.

    The outline polygons are triangulated once. A card triangle then only meets convex pieces, and the
    intersection of two convex polygons is convex, so the per-triangle work is a fan instead of ear clipping.
    """

    def __init__(self, uv_polygons: list[Polygon]):
        self._triangles: list[Polygon] = []
        for polygon in uv_polygons:
            vertices, triangles = triangulate_shapely_polygon(polygon)
            self._triangles.extend(Polygon(vertices[triangle]) for triangle in triangles)
        self._trees: dict[tuple[int, int], tuple[STRtree, np.ndarray]] = {}

    def clip(self, triangle: Polygon) -> tuple[list[np.ndarray], bool]:
        """Intersect a UV triangle with the opaque region.

        Args:
            triangle: UV triangle.

        Returns:
            Convex kept pieces as ``(N, 2)`` counter-clockwise rings, and whether the triangle is fully covered.
        """
        bounds = triangle.bounds
        u0, v0 = math.floor(bounds[0]), math.floor(bounds[1])
        u1, v1 = max(u0 + 1, math.ceil(bounds[2])), max(v0 + 1, math.ceil(bounds[3]))
        rings: list[np.ndarray] = []
        for u in range(u0, u1):
            for v in range(v0, v1):
                tree, polygons = self._tile(u, v)
                hits = tree.query(triangle, predicate="intersects")
                if hits.size == 0:
                    continue
                candidates = polygons[hits]
                if bool(np.any(shapely.contains(candidates, triangle))):
                    return [], True
                pieces = shapely.intersection(candidates, triangle)
                pieces = pieces[shapely.get_type_id(pieces) == shapely.GeometryType.POLYGON]
                pieces = pieces[shapely.area(pieces) > _DEGENERATE_UV_AREA]
                if pieces.size == 0:
                    continue
                coords, piece_index = shapely.get_coordinates(pieces, return_index=True)
                starts = np.flatnonzero(np.r_[True, piece_index[1:] != piece_index[:-1]])
                for closed_ring in np.split(coords, starts[1:]):
                    ring = closed_ring[:-1]
                    if ring.shape[0] >= 3:
                        rings.append(ring if _signed_uv_area_ring(ring) > 0 else ring[::-1])
        return rings, False

    def _tile(self, u: int, v: int) -> tuple[STRtree, np.ndarray]:
        tile = self._trees.get((u, v))
        if tile is None:
            polygons = np.array(
                self._triangles if (u, v) == (0, 0) else [translate(p, u, v) for p in self._triangles], dtype=object
            )
            shapely.prepare(polygons)
            tile = (STRtree(polygons), polygons)
            self._trees[(u, v)] = tile
        return tile


def _fan(count: int) -> np.ndarray:
    """Return the fan triangulation of a convex ring.

    Args:
        count: Vertex count of the ring.

    Returns:
        ``(count - 2, 3)`` int32 triangles.
    """
    fan = np.arange(1, count - 1, dtype=np.int32)
    return np.stack((np.zeros_like(fan), fan, fan + 1), axis=1)


def _weld(
    points: np.ndarray, st: np.ndarray, normals: np.ndarray | None, triangles: np.ndarray, quantum: float
) -> CutMesh:
    """Merge vertices that share a quantized position and texture coordinate.

    Args:
        points: ``(V, 3)`` positions.
        st: ``(V, 2)`` texture coordinates.
        normals: ``(V, 3)`` normals, or ``None``.
        triangles: ``(T, 3)`` indices into the vertex arrays.
        quantum: Size of the welding grid.

    Returns:
        Welded mesh without degenerate triangles.
    """
    keys = np.round(np.concatenate((points, st), axis=1) / quantum).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)
    remapped = inverse[triangles]
    keep = (remapped[:, 0] != remapped[:, 1]) & (remapped[:, 1] != remapped[:, 2]) & (remapped[:, 0] != remapped[:, 2])
    return CutMesh(
        points=points[first].astype(np.float32),
        triangles=remapped[keep].astype(np.int32),
        st=st[first].astype(np.float32),
        normals=None if normals is None else normals[first].astype(np.float32),
    )


def cut_triangles(
    source: MeshSource,
    uv_polygons: list[Polygon],
    weld_quantum: float = 1e-5,
    progress: Callable[[int, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> tuple[CutMesh | None, float]:
    """Clip every triangle of a mesh against the opaque UV region and lift the pieces back to 3D.

    Triangles whose UV footprint is fully opaque pass through unchanged, fully transparent ones are dropped, and
    partial ones are replaced by the triangulated intersection. New vertices interpolate position, normal and
    texture coordinate barycentrically, which is exact because the UV mapping is affine within a triangle.

    Args:
        source: Mesh to cut.
        uv_polygons: Opaque region in UV space.
        weld_quantum: Size of the grid used to merge coincident output vertices.
        progress: Optional callback receiving the processed and total triangle counts.
        is_cancelled: Optional callback that returns ``True`` to abort.

    Returns:
        The cut mesh, or ``None`` when cancelled, and the percentage of the UV area that was removed.
    """
    mask_index = _MaskIndex(uv_polygons)
    triangle_count = int(source.triangles.shape[0])
    out_points: list[np.ndarray] = []
    out_st: list[np.ndarray] = []
    out_normals: list[np.ndarray] = []
    out_triangles: list[np.ndarray] = []
    vertex_count = 0
    total_area = 0.0
    removed_area = 0.0

    for index in range(triangle_count):
        if is_cancelled and index % _PROGRESS_STRIDE == 0 and is_cancelled():
            return None, 0.0
        if progress and index % _PROGRESS_STRIDE == 0:
            progress(index, triangle_count)
        corner_points = source.points[source.triangles[index]]
        corner_st = source.st[index].astype(np.float64)
        corner_normals = None if source.normals is None else source.normals[index]
        triangle = Polygon(corner_st)
        signed_area = _signed_uv_area(corner_st)
        area = abs(signed_area)
        pieces: list[tuple[np.ndarray, np.ndarray]]
        if area <= _DEGENERATE_UV_AREA:
            pieces = [(corner_st, np.array([[0, 1, 2]], dtype=np.int32))]
        else:
            total_area += area
            rings, covered = mask_index.clip(triangle)
            kept_area = area if covered else sum(abs(_signed_uv_area_ring(ring)) for ring in rings)
            removed_area += max(0.0, area - kept_area)
            if kept_area <= _DEGENERATE_UV_AREA:
                continue
            if covered or area - kept_area <= _COVERED_TOLERANCE * area:
                pieces = [(corner_st, np.array([[0, 1, 2]], dtype=np.int32))]
            else:
                pieces = [(ring, _fan(ring.shape[0])) for ring in rings if ring.shape[0] >= 3]
        pieces = [(piece_st, piece_triangles) for piece_st, piece_triangles in pieces if piece_triangles.shape[0]]
        if not pieces:
            continue
        if len(pieces) == 1 and pieces[0][0] is corner_st:
            piece_st, piece_triangles = corner_st, pieces[0][1]
            weights = np.eye(3)
        else:
            offsets = np.cumsum([0] + [piece_st.shape[0] for piece_st, _ in pieces[:-1]])
            piece_st = np.concatenate([piece_st for piece_st, _ in pieces], axis=0)
            piece_triangles = np.concatenate(
                [triangles + offset for (_, triangles), offset in zip(pieces, offsets)], axis=0
            )
            # The pieces are counter-clockwise in UV space; a mirrored UV triangle needs the reverse.
            if signed_area < 0:
                piece_triangles = piece_triangles[:, ::-1]
            weights = barycentric_coordinates(piece_st, corner_st)
        out_points.append(weights @ corner_points.astype(np.float64))
        out_st.append(piece_st)
        if corner_normals is not None:
            lifted = weights @ corner_normals.astype(np.float64)
            lengths = np.linalg.norm(lifted, axis=1, keepdims=True)
            out_normals.append(np.divide(lifted, lengths, out=lifted, where=lengths > 0))
        out_triangles.append(piece_triangles + vertex_count)
        vertex_count += piece_st.shape[0]

    if progress:
        progress(triangle_count, triangle_count)
    removed_percent = 100.0 * removed_area / total_area if total_area > 0 else 0.0
    if not out_triangles:
        return CutMesh(
            points=np.zeros((0, 3), dtype=np.float32),
            triangles=np.zeros((0, 3), dtype=np.int32),
            st=np.zeros((0, 2), dtype=np.float32),
            normals=None if source.normals is None else np.zeros((0, 3), dtype=np.float32),
        ), removed_percent
    mesh = _weld(
        np.concatenate(out_points, axis=0),
        np.concatenate(out_st, axis=0),
        np.concatenate(out_normals, axis=0) if out_normals else None,
        np.concatenate(out_triangles, axis=0),
        weld_quantum,
    )
    return mesh, removed_percent


def _signed_uv_area(corner_st: np.ndarray) -> float:
    """Return the signed area of a UV triangle, positive when counter-clockwise.

    Args:
        corner_st: ``(3, 2)`` triangle corners.

    Returns:
        Signed area.
    """
    a, b, c = corner_st
    return 0.5 * float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _signed_uv_area_ring(ring: np.ndarray) -> float:
    """Return the signed area of a ring, positive when counter-clockwise.

    Args:
        ring: ``(N, 2)`` ring vertices without a repeated closing vertex.

    Returns:
        Signed area.
    """
    x = ring[:, 0]
    y = ring[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

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
    "build_alpha_field",
    "explode_polygons",
    "is_alpha_uniformly_opaque",
    "load_alpha",
    "mask_polygons_to_uv",
    "trace_alpha_mask",
    "union_geometries",
]

import numpy as np
import shapely
from PIL import Image
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry, BaseMultipartGeometry

from .simplify import simplify_ring_minimal

_OPAQUE = 255
_MITRE_JOIN = "mitre"
_MITRE_LIMIT = 2.0
_POST_BUFFER_SIMPLIFY = 0.5

# Marching squares: the corner bits are a (top left) = 1, b (top right) = 2, c (bottom right) = 4 and
# d (bottom left) = 8. Edge ids are 0 top, 1 right, 2 bottom and 3 left. Cases 5 and 10 are resolved by
# the cell centre; the first entry applies when the centre is opaque.
_SEGMENTS = {
    1: [(3, 0)],
    2: [(0, 1)],
    3: [(3, 1)],
    4: [(1, 2)],
    6: [(0, 2)],
    7: [(3, 2)],
    8: [(2, 3)],
    9: [(0, 2)],
    11: [(1, 2)],
    12: [(1, 3)],
    13: [(0, 1)],
    14: [(3, 0)],
}
_SADDLE_SEGMENTS = {
    5: ([(0, 1), (2, 3)], [(3, 0), (1, 2)]),
    10: ([(3, 0), (1, 2)], [(0, 1), (2, 3)]),
}


def union_geometries(geometries: list[BaseGeometry]) -> BaseGeometry:
    """Union geometries pairwise.

    The bundled shapely build cannot create geometry collections under numpy 2, which every ``union_all``
    style call does internally, so the union is reduced through the binary ``union`` ufunc instead.

    Args:
        geometries: Non-empty list of geometries.

    Returns:
        Union of every geometry.
    """
    pending = list(geometries)
    while len(pending) > 1:
        paired = [shapely.union(pending[i], pending[i + 1]) for i in range(0, len(pending) - 1, 2)]
        if len(pending) % 2:
            paired.append(pending[-1])
        pending = paired
    return pending[0]


def load_alpha(texture_path: str) -> np.ndarray:
    """Decode the alpha channel of a texture.

    Args:
        texture_path: Absolute path of a texture Pillow can decode, DDS included.

    Returns:
        ``(H, W)`` uint8 alpha values.

    Raises:
        OSError: If the file cannot be opened or decoded.
    """
    with Image.open(texture_path) as image:
        rgba = image.convert("RGBA")
    return np.asarray(rgba)[:, :, 3].copy()


def is_alpha_uniformly_opaque(alpha: np.ndarray) -> bool:
    """Return whether no texel is transparent.

    Args:
        alpha: ``(H, W)`` uint8 alpha values.

    Returns:
        ``True`` when every texel is fully opaque or the image is empty.
    """
    return alpha.size == 0 or int(alpha.min()) == _OPAQUE


def build_alpha_field(alpha: np.ndarray, trace_resolution: int) -> np.ndarray:
    """Downscale an alpha channel into the field that is traced.

    Args:
        alpha: ``(H, W)`` uint8 alpha values.
        trace_resolution: Longest side, in texels, of the field. Larger images are box-filtered down.

    Returns:
        ``(h, w)`` float32 alpha values in the 0-255 range.
    """
    height, width = alpha.shape
    longest = max(height, width)
    if longest > trace_resolution:
        scale = trace_resolution / longest
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        alpha = np.asarray(Image.fromarray(alpha).resize(size, Image.Resampling.BOX))
    return alpha.astype(np.float32)


def _edge_fraction(start: np.ndarray, end: np.ndarray, level: float) -> np.ndarray:
    """Return where the level crosses an edge, as a fraction from its start corner.

    Args:
        start: Field values at the start corners.
        end: Field values at the end corners.
        level: Iso level.

    Returns:
        Fractions clipped to the edge.
    """
    delta = end - start
    with np.errstate(divide="ignore", invalid="ignore"):
        fraction = np.where(delta != 0, (level - start) / delta, 0.5)
    return np.clip(fraction, 0.0, 1.0)


def _iso_segments(field: np.ndarray, level: float) -> np.ndarray:
    """Trace the iso contour of a field with marching squares and linear interpolation.

    Args:
        field: ``(h, w)`` alpha values sampled at texel centres.
        level: Alpha value at which a texel counts as opaque.

    Returns:
        ``(S, 2, 2)`` segment endpoints in texel space, x to the right and y down.
    """
    outside = min(0.0, float(field.min()) - 1.0)
    padded = np.pad(field.astype(np.float64), 1, constant_values=outside)
    a, b = padded[:-1, :-1], padded[:-1, 1:]
    d, c = padded[1:, :-1], padded[1:, 1:]
    case = (a >= level) * 1 + (b >= level) * 2 + (c >= level) * 4 + (d >= level) * 8
    rows, cols = np.indices(case.shape)
    x0 = cols - 0.5
    y0 = rows - 0.5
    edge_points = (
        np.stack((x0 + _edge_fraction(a, b, level), y0), axis=-1),
        np.stack((x0 + 1.0, y0 + _edge_fraction(b, c, level)), axis=-1),
        np.stack((x0 + _edge_fraction(d, c, level), y0 + 1.0), axis=-1),
        np.stack((x0, y0 + _edge_fraction(a, d, level)), axis=-1),
    )
    centre_opaque = (a + b + c + d) * 0.25 >= level
    segments = []

    def collect(cells: np.ndarray, pairs: list[tuple[int, int]]) -> None:
        for first, second in pairs:
            segments.append(np.stack((edge_points[first][cells], edge_points[second][cells]), axis=1))

    for value, pairs in _SEGMENTS.items():
        collect(case == value, pairs)
    for value, (opaque_pairs, transparent_pairs) in _SADDLE_SEGMENTS.items():
        collect((case == value) & centre_opaque, opaque_pairs)
        collect((case == value) & ~centre_opaque, transparent_pairs)
    all_segments = np.concatenate(segments, axis=0)
    lengths = np.linalg.norm(all_segments[:, 1] - all_segments[:, 0], axis=1)
    return all_segments[lengths > 1e-9]


def _pad_field(field: np.ndarray) -> np.ndarray:
    """Surround a field with a transparent border for sampling.

    Args:
        field: ``(h, w)`` alpha values.

    Returns:
        ``(h + 2, w + 2)`` float64 field with zeros around it.
    """
    return np.pad(field.astype(np.float64), 1, constant_values=0.0)


def _sample_field(padded: np.ndarray, x: float, y: float) -> float:
    """Return the bilinear field value at a texel-space point.

    Args:
        padded: Field returned by ``_pad_field``.
        x: Horizontal texel coordinate.
        y: Vertical texel coordinate.

    Returns:
        Interpolated value, with everything outside the texture treated as fully transparent.
    """
    px = min(max(x + 0.5, 0.0), padded.shape[1] - 1.0)
    py = min(max(y + 0.5, 0.0), padded.shape[0] - 1.0)
    col, row = int(np.floor(px)), int(np.floor(py))
    col1, row1 = min(col + 1, padded.shape[1] - 1), min(row + 1, padded.shape[0] - 1)
    fx, fy = px - col, py - row
    top = padded[row, col] * (1 - fx) + padded[row, col1] * fx
    bottom = padded[row1, col] * (1 - fx) + padded[row1, col1] * fx
    return float(top * (1 - fy) + bottom * fy)


def explode_polygons(geometry) -> list[Polygon]:
    """Flatten any shapely geometry into its non-empty polygon parts.

    Args:
        geometry: Polygon, multi-polygon or collection.

    Returns:
        Polygons contained in the geometry.
    """
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, BaseMultipartGeometry):
        polygons = []
        for part in geometry.geoms:
            polygons.extend(explode_polygons(part))
        return polygons
    return []


def _simplify_polygon_minimal(polygon: Polygon, tolerance: float) -> Polygon:
    """Simplify every ring of a polygon to the fewest vertices within the tolerance.

    Args:
        polygon: Polygon to simplify.
        tolerance: Largest allowed deviation.

    Returns:
        The simplified polygon, or its Douglas-Peucker simplification when the minimal rings fold onto
        themselves.
    """
    shell = simplify_ring_minimal(np.asarray(polygon.exterior.coords)[:-1], tolerance)
    holes = [simplify_ring_minimal(np.asarray(hole.coords)[:-1], tolerance) for hole in polygon.interiors]
    if shell.shape[0] >= 3:
        simplified = Polygon(shell, [hole for hole in holes if hole.shape[0] >= 3])
        if simplified.is_valid and simplified.area > 0:
            return simplified
    return polygon.simplify(tolerance, preserve_topology=True)


def _simplify_outline(outline: BaseGeometry, tolerance: float, minimal: bool) -> BaseGeometry:
    """Simplify an outline with Douglas-Peucker or with the minimal vertex pass.

    Args:
        outline: Polygon or multi-polygon outline.
        tolerance: Largest allowed deviation.
        minimal: Whether to use the minimal vertex pass.

    Returns:
        The simplified outline.
    """
    if not minimal:
        return outline.simplify(tolerance, preserve_topology=True)
    polygons = [_simplify_polygon_minimal(polygon, tolerance) for polygon in explode_polygons(outline)]
    return union_geometries(polygons) if polygons else outline


def trace_alpha_mask(
    field: np.ndarray,
    level: float,
    simplify_tolerance: float,
    edge_margin: float,
    min_island_area: float,
    minimal_outline: bool = False,
) -> list[Polygon]:
    """Vectorize the opaque area of an alpha field into simplified polygons with holes.

    The outline is the interpolated iso contour at ``level``, so diagonal edges come out as straight lines
    instead of texel staircases.

    Args:
        field: ``(h, w)`` alpha values sampled at texel centres; a boolean mask works with ``level`` 0.5.
        level: Alpha value at which a texel counts as opaque.
        simplify_tolerance: Douglas-Peucker tolerance in texels.
        edge_margin: Distance in texels the outline grows (positive) or shrinks (negative).
        min_island_area: Polygons with a smaller area, in texels, are dropped.
        minimal_outline: Simplify to the fewest vertices within the tolerance instead of Douglas-Peucker.

    Returns:
        Polygons in texel space, x to the right and y down, sorted by their bounds.
    """
    if field.size == 0 or not (field >= level).any():
        return []
    segments = _iso_segments(field, level)
    if segments.shape[0] == 0:
        return []
    faces = shapely.polygonize(shapely.linestrings(segments))
    padded = _pad_field(field)
    opaque = []
    for face in faces.geoms:
        point = face.representative_point()
        if _sample_field(padded, point.x, point.y) >= level:
            opaque.append(face)
    if not opaque:
        return []
    outline = union_geometries(opaque)
    if simplify_tolerance > 0:
        outline = _simplify_outline(outline, simplify_tolerance, minimal_outline)
    if edge_margin:
        outline = outline.buffer(edge_margin, join_style=_MITRE_JOIN, mitre_limit=_MITRE_LIMIT)
        if simplify_tolerance > 0:
            outline = _simplify_outline(outline, simplify_tolerance * _POST_BUFFER_SIMPLIFY, minimal_outline)
    polygons = [
        polygon
        for polygon in explode_polygons(shapely.make_valid(outline))
        if polygon.area >= min_island_area and polygon.area > 0
    ]
    return sorted(polygons, key=lambda polygon: polygon.bounds)


def mask_polygons_to_uv(polygons: list[Polygon], mask_shape: tuple[int, int]) -> list[Polygon]:
    """Map texel-space polygons into the unit UV square.

    The image row 0 is the top of the texture while USD ``st`` has its origin at the bottom left, so V is flipped.

    Args:
        polygons: Polygons in texel space.
        mask_shape: ``(h, w)`` of the traced field.

    Returns:
        Polygons in UV space.
    """
    height, width = mask_shape

    def to_uv(coords: np.ndarray) -> np.ndarray:
        return np.column_stack((coords[:, 0] / width, 1.0 - coords[:, 1] / height))

    return [shapely.transform(polygon, to_uv) for polygon in polygons]

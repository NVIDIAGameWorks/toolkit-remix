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

__all__ = ["simplify_ring_minimal"]

import numpy as np
import shapely
from shapely.geometry import LinearRing

_WINDOW = 32
_EPSILON = 1e-12
_FULL_CONE = np.pi
# Share of the tolerance spent on a Douglas-Peucker pass that thins the raw contour before the optimal pass.
_PRUNE_FRACTION = 0.05


def _within_segment(relative: np.ndarray, chord: np.ndarray, tolerance: float) -> bool:
    """Test whether every vertex lies within the tolerance of a chord segment from the origin.

    Args:
        relative: ``(K, 2)`` vertices relative to the chord origin.
        chord: ``(2,)`` chord end relative to the origin.
        tolerance: Largest allowed distance.

    Returns:
        ``True`` when all vertices are within the tolerance of the segment.
    """
    length = float(chord @ chord)
    t = np.clip((relative @ chord) / max(length, _EPSILON), 0.0, 1.0)
    offsets = relative - t[:, None] * chord[None, :]
    return bool(np.all(np.einsum("ij,ij->i", offsets, offsets) <= tolerance * tolerance))


def _valid_chords(relative: np.ndarray, tolerance: float) -> tuple[np.ndarray, bool]:
    """Test which chords from the origin keep every skipped vertex within the tolerance.

    The feasible chord directions form a cone per skipped vertex; a chord is valid while its direction lies in
    the intersection of the cones of the vertices before its end. That bounds the distance to the chord line, so
    chords whose skipped vertices reach farther than the chord end are verified against the segment as well.

    Args:
        relative: ``(M, 2)`` later vertices relative to the chord origin, in polyline order.
        tolerance: Largest allowed distance of a skipped vertex to the chord segment.

    Returns:
        ``(M,)`` whether the chord to each vertex is valid, and whether no longer chord can be valid.
    """
    distances = np.hypot(relative[:, 0], relative[:, 1])
    angles = np.arctan2(relative[:, 1], relative[:, 0])
    angles = np.mod(angles - angles[0] + np.pi, 2.0 * np.pi) - np.pi + angles[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        half_width = np.where(distances <= tolerance, _FULL_CONE, np.arcsin(np.minimum(1.0, tolerance / distances)))
    low = np.maximum.accumulate(angles - half_width)
    high = np.minimum.accumulate(angles + half_width)
    valid = np.ones(relative.shape[0], dtype=bool)
    valid[1:] = (low[:-1] <= angles[1:]) & (angles[1:] <= high[:-1])
    exhausted = np.flatnonzero(low > high)
    if exhausted.size:
        valid[exhausted[0] + 1 :] = False
    farthest_before = np.empty_like(distances)
    farthest_before[0] = 0.0
    farthest_before[1:] = np.maximum.accumulate(distances)[:-1]
    for end in np.flatnonzero(valid & (farthest_before > distances)):
        valid[end] = _within_segment(relative[:end], relative[end], tolerance)
    return valid, bool(exhausted.size)


def _shortcuts(line: np.ndarray, tolerance: float) -> list[np.ndarray]:
    """Find every chord of an open polyline whose skipped vertices stay within the tolerance.

    Chords are tested in windows of growing size, so the work per vertex is bounded by the length of the run
    ahead of it that a single chord can replace.

    Args:
        line: ``(N, 2)`` polyline vertices.
        tolerance: Largest allowed distance of a skipped vertex to the chord segment.

    Returns:
        Per vertex, the indices of later vertices it may connect to directly.
    """
    count = line.shape[0]
    successors: list[np.ndarray] = []
    for index in range(count - 1):
        window = _WINDOW
        while True:
            stop = min(count, index + 1 + window)
            valid, exhausted = _valid_chords(line[index + 1 : stop] - line[index], tolerance)
            if exhausted or stop == count:
                break
            window *= 2
        successors.append(index + 1 + np.flatnonzero(valid))
    return successors


def _fewest_hops(successors: list[np.ndarray], count: int) -> list[int]:
    """Return the path with the fewest vertices from the first to the last vertex.

    Args:
        successors: Valid chord targets per vertex, all later than the vertex.
        count: Vertex count of the polyline.

    Returns:
        Vertex indices of the path, first to last.
    """
    hops = np.full(count, count + 1, dtype=np.int64)
    previous = np.full(count, -1, dtype=np.int64)
    hops[0] = 0
    for index in range(count - 1):
        targets = successors[index]
        improved = targets[hops[targets] > hops[index] + 1]
        hops[improved] = hops[index] + 1
        previous[improved] = index
    path = [count - 1]
    while path[-1] != 0:
        path.append(int(previous[path[-1]]))
    return path[::-1]


def simplify_ring_minimal(ring: np.ndarray, tolerance: float) -> np.ndarray:
    """Simplify a closed ring to the fewest vertices that keep every dropped vertex within the tolerance.

    This is the Imai-Iri optimal simplification: the greedy Douglas-Peucker pass reaches the same accuracy with
    more vertices. A small share of the tolerance goes to a Douglas-Peucker pass that thins the raw contour
    first, which keeps the optimal pass fast; the two deviations add up to at most the tolerance. The ring is
    opened at its vertex farthest from the centroid, which any simplification keeps.

    Args:
        ring: ``(N, 2)`` ring vertices without a repeated closing vertex.
        tolerance: Largest allowed distance of a dropped vertex to the simplified outline.

    Returns:
        ``(M, 2)`` simplified ring vertices without a repeated closing vertex, in the input order.
    """
    ring = np.asarray(ring, dtype=np.float64)
    if ring.shape[0] <= 3 or tolerance <= 0:
        return ring
    pruned = shapely.simplify(LinearRing(ring), tolerance * _PRUNE_FRACTION, preserve_topology=False)
    ring = np.asarray(pruned.coords)[:-1]
    if ring.shape[0] <= 3:
        return ring
    start = int(np.argmax(np.linalg.norm(ring - ring.mean(axis=0), axis=1)))
    rolled = np.roll(ring, -start, axis=0)
    line = np.concatenate((rolled, rolled[:1]), axis=0)
    path = _fewest_hops(_shortcuts(line, tolerance * (1.0 - _PRUNE_FRACTION)), line.shape[0])
    return rolled[path[:-1]]

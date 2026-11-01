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

__all__ = ["bend_normals_up", "position_ids", "smooth_normals", "unit", "up_vector", "vertex_normals_from_faces"]

import dataclasses

import numpy as np

from .data_models import CutMesh

_LEFT_HANDED = "leftHanded"
_EPSILON = 1e-12
_UP_AXES = {"Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def position_ids(points: np.ndarray, quantum: float = 1e-5) -> np.ndarray:
    """Group vertices that share a quantized position, so UV seam duplicates count as one corner.

    Args:
        points: ``(V, 3)`` positions.
        quantum: Size of the grouping grid.

    Returns:
        ``(V,)`` group id per vertex.
    """
    keys = np.round(points / quantum).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    return inverse.reshape(-1)


def unit(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normalize rows, leaving zero rows untouched.

    Args:
        vectors: ``(N, 3)`` or ``(N, 2)`` vectors.

    Returns:
        The normalized rows and the ``(N,)`` original lengths.
    """
    lengths = np.linalg.norm(vectors, axis=1)
    safe = np.where(lengths > _EPSILON, lengths, 1.0)
    return vectors / safe[:, None], lengths


def _corner_angles(corners: np.ndarray) -> np.ndarray:
    """Return the interior angle of every triangle corner.

    Args:
        corners: ``(T, 3, 3)`` triangle corner positions.

    Returns:
        ``(T, 3)`` angles in radians.
    """
    first, _ = unit((np.roll(corners, -1, axis=1) - corners).reshape(-1, 3))
    second, _ = unit((np.roll(corners, -2, axis=1) - corners).reshape(-1, 3))
    cosines = np.clip(np.einsum("ij,ij->i", first, second), -1.0, 1.0)
    return np.arccos(cosines).reshape(-1, 3)


def vertex_normals_from_faces(mesh: CutMesh, orientation: str = "rightHanded", quantum: float = 1e-5) -> np.ndarray:
    """Average the face normals around every position, weighted by the corner angle of each triangle.

    Angle weighting makes the result independent of how finely a face is tessellated, so a thin rim rounds
    as much as a thick one.

    Args:
        mesh: Mesh whose triangles define the normals.
        orientation: USD ``orientation`` of the mesh.
        quantum: Size of the grid that groups coincident positions.

    Returns:
        ``(V, 3)`` unit normals per vertex; zero where a position has no non-degenerate triangle.
    """
    points = mesh.points.astype(np.float64)
    triangles = mesh.triangles
    corners = points[triangles]
    face_normals, _ = unit(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]))
    if orientation == _LEFT_HANDED:
        face_normals = -face_normals
    weights = _corner_angles(corners).reshape(-1, 1)
    ids = position_ids(points, quantum)
    summed = np.zeros((int(ids.max()) + 1 if ids.size else 0, 3))
    np.add.at(summed, ids[triangles].ravel(), np.repeat(face_normals, 3, axis=0) * weights)
    directions, _ = unit(summed)
    return directions[ids]


def _current_normals(mesh: CutMesh, orientation: str) -> np.ndarray:
    return mesh.normals.astype(np.float64) if mesh.normals is not None else vertex_normals_from_faces(mesh, orientation)


def _blend(current: np.ndarray, target: np.ndarray, amount: float) -> np.ndarray:
    """Interpolate unit vectors and renormalize, falling back to the target where the blend collapses.

    Args:
        current: ``(V, 3)`` unit vectors.
        target: ``(V, 3)`` unit vectors.
        amount: Blend weight of the target from 0 to 1.

    Returns:
        ``(V, 3)`` unit vectors.
    """
    blended, lengths = unit((1.0 - amount) * current + amount * target)
    return np.where((lengths > _EPSILON)[:, None], blended, target)


def smooth_normals(mesh: CutMesh, amount: float, orientation: str = "rightHanded") -> CutMesh:
    """Blend every normal towards the average normal of the triangles around its position.

    Args:
        mesh: Mesh to smooth, typically a thickened one whose rim is flat shaded.
        amount: Smoothing strength from 0 (unchanged) to 1 (fully averaged).
        orientation: USD ``orientation`` of the mesh.

    Returns:
        The mesh with blended normals, or the input when the amount is zero or there are no triangles.
    """
    amount = float(np.clip(amount, 0.0, 1.0))
    if amount <= 0 or mesh.triangles.shape[0] == 0:
        return mesh
    averaged = vertex_normals_from_faces(mesh, orientation)
    blended = _blend(_current_normals(mesh, orientation), averaged, amount)
    return dataclasses.replace(mesh, normals=blended.astype(np.float32))


def up_vector(up_axis: str, transform: tuple[float, ...] | None) -> np.ndarray:
    """Express the stage up axis in the space of a mesh.

    Args:
        up_axis: Stage up axis token, ``"Y"`` or ``"Z"``.
        transform: Sixteen row-major values of the mesh transform, or ``None``.

    Returns:
        ``(3,)`` unit up direction in mesh space.
    """
    up = np.array(_UP_AXES.get(up_axis, _UP_AXES["Y"]))
    if transform is None:
        return up
    # Points transform as row vectors, so a direction maps back through the transpose of the linear part.
    linear = np.array(transform, dtype=np.float64).reshape(4, 4)[:3, :3]
    local = up @ linear.T
    direction, length = unit(local[None, :])
    return direction[0] if length[0] > _EPSILON else up


def bend_normals_up(mesh: CutMesh, up: np.ndarray, amount: float, orientation: str = "rightHanded") -> CutMesh:
    """Blend every normal towards the up direction so a canopy of cards shades like one lit volume.

    Args:
        mesh: Mesh to adjust.
        up: ``(3,)`` unit up direction in mesh space.
        amount: Blend weight from 0 (unchanged) to 1 (straight up).
        orientation: USD ``orientation`` of the mesh, used when the mesh carries no normals.

    Returns:
        The mesh with blended normals, or the input when the amount is zero or there are no triangles.
    """
    amount = float(np.clip(amount, 0.0, 1.0))
    if amount <= 0 or mesh.triangles.shape[0] == 0:
        return mesh
    current = _current_normals(mesh, orientation)
    target = np.broadcast_to(np.asarray(up, dtype=np.float64), current.shape)
    return dataclasses.replace(mesh, normals=_blend(current, target, amount).astype(np.float32))

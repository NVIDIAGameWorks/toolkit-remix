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

__all__ = ["thicken_mesh"]

import numpy as np

from .data_models import CutMesh
from .normals import position_ids, unit

_LEFT_HANDED = "leftHanded"
_EPSILON = 1e-12


def _offset_directions(
    points: np.ndarray, triangles: np.ndarray, position_ids: np.ndarray, orientation: str
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the front direction per vertex from the triangles around its position.

    Args:
        points: ``(V, 3)`` positions.
        triangles: ``(T, 3)`` indices.
        position_ids: ``(V,)`` position group per vertex.
        orientation: USD ``orientation`` of the mesh.

    Returns:
        ``(V, 3)`` unit front direction per vertex and ``(T, 3)`` unit face normals.
    """
    a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    face_normals = np.cross(b - a, c - a)
    if orientation == _LEFT_HANDED:
        face_normals = -face_normals
    unit_face_normals, _ = unit(face_normals)
    position_count = int(position_ids.max()) + 1
    corner_positions = position_ids[triangles].ravel()
    summed = np.zeros((position_count, 3))
    np.add.at(summed, corner_positions, np.repeat(face_normals, 3, axis=0))
    directions, lengths = unit(summed)
    fallback = np.zeros((position_count, 3))
    fallback[corner_positions] = np.repeat(unit_face_normals, 3, axis=0)
    directions = np.where((lengths > _EPSILON)[:, None], directions, fallback)
    return directions[position_ids], unit_face_normals


def _boundary_edges(triangles: np.ndarray, position_ids: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Find the directed edges that belong to exactly one triangle.

    Args:
        triangles: ``(T, 3)`` indices.
        position_ids: ``(V,)`` position group per vertex.

    Returns:
        Start vertex, end vertex and owning triangle per boundary edge, in the triangle's winding order.
    """
    starts = triangles[:, [0, 1, 2]].ravel()
    ends = triangles[:, [1, 2, 0]].ravel()
    position_edges = np.stack((position_ids[starts], position_ids[ends]), axis=1)
    _, inverse, counts = np.unique(np.sort(position_edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    boundary = (counts[inverse.reshape(-1)] == 1) & (position_edges[:, 0] != position_edges[:, 1])
    owners = np.repeat(np.arange(triangles.shape[0]), 3)
    return starts[boundary], ends[boundary], owners[boundary]


def _side_st(
    mesh: CutMesh, starts: np.ndarray, ends: np.ndarray, owners: np.ndarray, thickness: float, anti_stretch: bool
) -> tuple[np.ndarray, np.ndarray]:
    """Return the texture coordinates of the back corners of every side quad.

    Args:
        mesh: Front mesh.
        starts: Start vertex per boundary edge.
        ends: End vertex per boundary edge.
        owners: Owning triangle per boundary edge.
        thickness: Extrusion distance.
        anti_stretch: Whether the sides sample a texture band inside the outline instead of smearing the edge.

    Returns:
        ``(E, 2)`` texture coordinates for the back copies of the start and end vertices.
    """
    st = mesh.st.astype(np.float64)
    start_st, end_st = st[starts], st[ends]
    if not anti_stretch:
        return start_st, end_st
    uv_direction, uv_lengths = unit(end_st - start_st)
    _, edge_lengths = unit(mesh.points[ends].astype(np.float64) - mesh.points[starts].astype(np.float64))
    corner_st = st[mesh.triangles[owners]]
    first, second = corner_st[:, 1] - corner_st[:, 0], corner_st[:, 2] - corner_st[:, 0]
    uv_signed_area = first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]
    # The interior lies left of the edge in a counter-clockwise UV triangle and right of it in a mirrored one.
    inward = np.column_stack((-uv_direction[:, 1], uv_direction[:, 0])) * np.sign(uv_signed_area)[:, None]
    usable = (uv_lengths > _EPSILON) & (edge_lengths > _EPSILON)
    scale = np.where(usable, uv_lengths / np.where(usable, edge_lengths, 1.0), 0.0)
    shift = inward * (thickness * scale)[:, None]
    return start_st + shift, end_st + shift


def thicken_mesh(
    mesh: CutMesh,
    thickness: float,
    back_face: bool = True,
    anti_stretch: bool = False,
    orientation: str = "rightHanded",
    weld_quantum: float = 1e-5,
) -> CutMesh:
    """Extrude a cut mesh backwards, against its front direction, by a distance.

    Every boundary edge receives a side quad whose normal points away from the mesh. The optional back face is a
    reversed copy of the front. Side vertices are not shared with the front so each side stays flat shaded.

    Args:
        mesh: Welded front mesh.
        thickness: Extrusion distance in mesh units; zero or less returns the input.
        back_face: Whether to add the reversed back copy of the front triangles.
        anti_stretch: Whether the sides sample a texture band inside the outline instead of smearing the edge.
        orientation: USD ``orientation`` of the mesh, which decides which side is the front.
        weld_quantum: Size of the grid that groups coincident positions.

    Returns:
        The thickened mesh.
    """
    if thickness <= 0 or mesh.triangles.shape[0] == 0:
        return mesh
    points = mesh.points.astype(np.float64)
    triangles = mesh.triangles
    ids = position_ids(points, weld_quantum)
    directions, face_normals = _offset_directions(points, triangles, ids, orientation)
    back_points = points - directions * thickness
    starts, ends, owners = _boundary_edges(triangles, ids)
    edge_vectors = points[ends] - points[starts]
    side_normals, side_lengths = unit(np.cross(edge_vectors, face_normals[owners]))
    usable = side_lengths > _EPSILON
    starts, ends, owners, side_normals = starts[usable], ends[usable], owners[usable], side_normals[usable]
    back_start_st, back_end_st = _side_st(mesh, starts, ends, owners, thickness, anti_stretch)

    edge_count = starts.shape[0]
    vertex_count = points.shape[0]
    # Side quad corners are ordered start, end, back end, back start.
    side_points = np.stack((points[starts], points[ends], back_points[ends], back_points[starts]), axis=1)
    side_st = np.stack((mesh.st[starts], mesh.st[ends], back_end_st, back_start_st), axis=1)
    side_base = vertex_count + 4 * np.arange(edge_count)[:, None]
    side_triangles = np.concatenate((side_base + np.array([[0, 2, 1]]), side_base + np.array([[0, 3, 2]])), axis=0)

    out_points = [points, side_points.reshape(-1, 3)]
    out_st = [mesh.st.astype(np.float64), side_st.reshape(-1, 2)]
    out_triangles = [triangles, side_triangles]
    out_normals = None
    if mesh.normals is not None:
        out_normals = [mesh.normals.astype(np.float64), np.repeat(side_normals, 4, axis=0)]
    if back_face:
        back_base = vertex_count + 4 * edge_count
        out_points.append(back_points)
        out_st.append(mesh.st.astype(np.float64))
        out_triangles.append(triangles[:, ::-1] + back_base)
        if out_normals is not None:
            out_normals.append(-mesh.normals.astype(np.float64))
    return CutMesh(
        points=np.concatenate(out_points, axis=0).astype(np.float32),
        triangles=np.concatenate(out_triangles, axis=0).astype(np.int32),
        st=np.concatenate(out_st, axis=0).astype(np.float32),
        normals=None if out_normals is None else np.concatenate(out_normals, axis=0).astype(np.float32),
    )

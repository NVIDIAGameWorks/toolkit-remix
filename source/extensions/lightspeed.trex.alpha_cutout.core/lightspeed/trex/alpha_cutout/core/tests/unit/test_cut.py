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

__all__ = ["TestCutTriangles"]

import numpy as np
from lightspeed.trex.alpha_cutout.core.cut import barycentric_coordinates, cut_triangles
from lightspeed.trex.alpha_cutout.core.data_models import MeshSource
from omni.kit.test import AsyncTestCase
from shapely.geometry import Polygon

_QUAD_POINTS = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float32)
_QUAD_TRIANGLES = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
_QUAD_ST = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)


def _quad_source(st_points: np.ndarray = _QUAD_ST, with_normals: bool = False) -> MeshSource:
    """Build a unit quad whose positions equal its texture coordinates."""
    normals = np.tile(np.array([0, 0, 1], dtype=np.float32), (2, 3, 1)) if with_normals else None
    return MeshSource(
        prim_path="/RootNode/meshes/mesh_0000000000000000",
        mesh_hash="0000000000000000",
        points=_QUAD_POINTS,
        triangles=_QUAD_TRIANGLES,
        st=st_points[_QUAD_TRIANGLES],
        normals=normals,
        transform=None,
        double_sided=False,
        orientation="rightHanded",
        texture_path="unused.png",
        material_path="/RootNode/Looks/mat_0000000000000000",
    )


def _unit_square() -> Polygon:
    return Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])


def _surface_area(points: np.ndarray, triangles: np.ndarray) -> float:
    a = points[triangles[:, 0]]
    b = points[triangles[:, 1]]
    c = points[triangles[:, 2]]
    return float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())


class TestCutTriangles(AsyncTestCase):
    """Test the per-triangle UV cutter."""

    async def test_barycentric_coordinates_with_corners_returns_identity_weights(self):
        # Arrange
        triangle = np.array([[0, 0], [2, 0], [0, 2]], dtype=np.float64)

        # Act
        weights = barycentric_coordinates(triangle, triangle)

        # Assert
        np.testing.assert_allclose(weights, np.eye(3), atol=1e-12)

    async def test_cut_triangles_with_fully_inside_triangles_passes_geometry_through(self):
        # Arrange
        source = _quad_source()

        # Act
        mesh, removed = cut_triangles(source, [_unit_square()])

        # Assert
        self.assertEqual(mesh.triangles.shape, (2, 3))
        self.assertEqual(mesh.points.shape, (4, 3))
        self.assertAlmostEqual(removed, 0.0)

    async def test_cut_triangles_with_fully_outside_triangles_drops_them(self):
        # Arrange
        source = _quad_source()
        far_away = Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])

        # Act
        mesh, removed = cut_triangles(source, [far_away])

        # Assert
        self.assertEqual(mesh.triangles.shape, (0, 3))
        self.assertAlmostEqual(removed, 100.0)

    async def test_cut_triangles_with_partial_coverage_keeps_only_covered_area(self):
        # Arrange
        source = _quad_source()
        left_half = Polygon([(0, 0), (0.5, 0), (0.5, 1), (0, 1)])

        # Act
        mesh, removed = cut_triangles(source, [left_half])

        # Assert
        self.assertAlmostEqual(_surface_area(mesh.points, mesh.triangles), 0.5, places=5)
        self.assertAlmostEqual(removed, 50.0, places=3)
        np.testing.assert_allclose(mesh.points[:, :2], mesh.st, atol=1e-5)
        self.assertLessEqual(float(mesh.points[:, 0].max()), 0.5 + 1e-5)

    async def test_cut_triangles_with_normals_interpolates_unit_normals(self):
        # Arrange
        source = _quad_source(with_normals=True)
        left_half = Polygon([(0, 0), (0.5, 0), (0.5, 1), (0, 1)])

        # Act
        mesh, _ = cut_triangles(source, [left_half])

        # Assert
        self.assertEqual(mesh.normals.shape, mesh.points.shape)
        np.testing.assert_allclose(mesh.normals, np.tile([0, 0, 1], (mesh.points.shape[0], 1)), atol=1e-6)

    async def test_cut_triangles_with_uv_outside_unit_square_tiles_mask(self):
        # Arrange
        source = _quad_source(st_points=_QUAD_ST * 2.0 - 0.5)
        centre = Polygon([(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)])

        # Act
        mesh, removed = cut_triangles(source, [centre])

        # Assert
        self.assertAlmostEqual(removed, 75.0, places=3)
        self.assertAlmostEqual(_surface_area(mesh.points, mesh.triangles), 0.25, places=5)

    async def test_cut_triangles_with_mirrored_uv_keeps_triangle_winding(self):
        # Arrange
        source = _quad_source(st_points=_QUAD_ST[:, ::-1])
        left_half = Polygon([(0, 0), (0.5, 0), (0.5, 1), (0, 1)])

        # Act
        mesh, _ = cut_triangles(source, [left_half])

        # Assert
        a = mesh.points[mesh.triangles[:, 0]]
        b = mesh.points[mesh.triangles[:, 1]]
        c = mesh.points[mesh.triangles[:, 2]]
        self.assertTrue((np.cross(b - a, c - a)[:, 2] > 0).all())

    async def test_cut_triangles_welds_vertices_shared_by_adjacent_triangles(self):
        # Arrange
        source = _quad_source()
        left_half = Polygon([(0, 0), (0.5, 0), (0.5, 1), (0, 1)])

        # Act
        mesh, _ = cut_triangles(source, [left_half])

        # Assert
        unique = np.unique(np.round(mesh.points, 5), axis=0)
        self.assertEqual(unique.shape[0], mesh.points.shape[0])

    async def test_cut_triangles_with_degenerate_uv_triangle_passes_it_through(self):
        # Arrange
        source = _quad_source(st_points=np.zeros((4, 2), dtype=np.float32))

        # Act
        mesh, removed = cut_triangles(source, [_unit_square()])

        # Assert
        self.assertEqual(mesh.triangles.shape, (2, 3))
        self.assertAlmostEqual(removed, 0.0)

    async def test_cut_triangles_with_cancel_requested_returns_none(self):
        # Arrange
        source = _quad_source()

        # Act
        mesh, removed = cut_triangles(source, [_unit_square()], is_cancelled=lambda: True)

        # Assert
        self.assertIsNone(mesh)
        self.assertAlmostEqual(removed, 0.0)

    async def test_cut_triangles_reports_progress_with_total_at_the_end(self):
        # Arrange
        source = _quad_source()
        calls = []

        # Act
        cut_triangles(source, [_unit_square()], progress=lambda current, total: calls.append((current, total)))

        # Assert
        self.assertEqual(calls[-1], (2, 2))

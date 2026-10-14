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

__all__ = ["TestThickenMesh"]

import numpy as np
from lightspeed.trex.alpha_cutout.core.data_models import CutMesh
from lightspeed.trex.alpha_cutout.core.thicken import thicken_mesh
from omni.kit.test import AsyncTestCase

from ..unit.fixtures import quad_cut_mesh

_THICKNESS = 0.25
_SIDE_TRIANGLES = 8


def _face_normals(mesh: CutMesh) -> np.ndarray:
    a, b, c = (mesh.points[mesh.triangles[:, i]] for i in range(3))
    return np.cross(b - a, c - a)


def _centroids(mesh: CutMesh) -> np.ndarray:
    return mesh.points[mesh.triangles].mean(axis=1)


class TestThickenMesh(AsyncTestCase):
    """Test the backwards extrusion of a cut mesh."""

    async def test_thicken_mesh_with_back_face_adds_sides_and_reversed_back(self):
        # Arrange
        mesh = quad_cut_mesh()

        # Act
        result = thicken_mesh(mesh, _THICKNESS, back_face=True)

        # Assert
        self.assertEqual(result.triangles.shape[0], 2 + _SIDE_TRIANGLES + 2)
        back = result.triangles[-2:]
        self.assertTrue(np.all(_face_normals(result)[-2:][:, 2] < 0))
        np.testing.assert_allclose(result.points[back][:, :, 2], -_THICKNESS)

    async def test_thicken_mesh_without_back_face_adds_only_sides(self):
        # Arrange
        mesh = quad_cut_mesh()

        # Act
        result = thicken_mesh(mesh, _THICKNESS, back_face=False)

        # Assert
        self.assertEqual(result.triangles.shape[0], 2 + _SIDE_TRIANGLES)
        np.testing.assert_array_equal(result.triangles[:2], mesh.triangles)

    async def test_thicken_mesh_side_normals_point_away_from_the_quad(self):
        # Arrange
        mesh = quad_cut_mesh()
        centre = mesh.points.mean(axis=0)

        # Act
        result = thicken_mesh(mesh, _THICKNESS, back_face=False)

        # Assert
        sides = slice(2, 2 + _SIDE_TRIANGLES)
        outward = _centroids(result)[sides] - centre
        outward[:, 2] = 0.0
        dots = np.einsum("ij,ij->i", _face_normals(result)[sides], outward)
        self.assertTrue(np.all(dots > 0))
        side_normals = result.normals[4:]
        np.testing.assert_allclose(side_normals[:, 2], 0.0, atol=1e-6)
        np.testing.assert_allclose(np.linalg.norm(side_normals, axis=1), 1.0, atol=1e-6)

    async def test_thicken_mesh_default_side_st_copies_the_edge_st(self):
        # Arrange
        mesh = quad_cut_mesh()

        # Act
        result = thicken_mesh(mesh, _THICKNESS, back_face=False, anti_stretch=False)

        # Assert
        side_st = result.st[4:].reshape(-1, 4, 2)
        np.testing.assert_allclose(side_st[:, 2], side_st[:, 1])
        np.testing.assert_allclose(side_st[:, 3], side_st[:, 0])

    async def test_thicken_mesh_anti_stretch_shifts_side_st_inward_by_thickness(self):
        # Arrange
        mesh = quad_cut_mesh()

        # Act
        result = thicken_mesh(mesh, _THICKNESS, back_face=False, anti_stretch=True)

        # Assert
        side_st = result.st[4:].reshape(-1, 4, 2)
        shift = side_st[:, 3] - side_st[:, 0]
        np.testing.assert_allclose(np.linalg.norm(shift, axis=1), _THICKNESS, atol=1e-6)
        shifted_centre = side_st[:, 3].mean(axis=0)
        self.assertTrue(np.all(np.abs(side_st[:, 3] - 0.5) < np.abs(side_st[:, 0] - 0.5) + 1e-6))
        np.testing.assert_allclose(shifted_centre, [0.5, 0.5], atol=1e-6)

    async def test_thicken_mesh_with_uv_seam_duplicates_does_not_add_a_side_along_the_seam(self):
        # Arrange
        quad = quad_cut_mesh()
        # The diagonal is duplicated with different texture coordinates, like a UV seam.
        points = np.concatenate((quad.points, quad.points[[0, 2]]), axis=0)
        st = np.concatenate((quad.st, quad.st[[0, 2]] + 0.5), axis=0)
        normals = np.concatenate((quad.normals, quad.normals[[0, 2]]), axis=0)
        mesh = CutMesh(
            points=points, triangles=np.array([[0, 1, 2], [4, 5, 3]], dtype=np.int32), st=st, normals=normals
        )

        # Act
        result = thicken_mesh(mesh, _THICKNESS, back_face=False)

        # Assert
        self.assertEqual(result.triangles.shape[0], 2 + _SIDE_TRIANGLES)

    async def test_thicken_mesh_with_left_handed_orientation_extrudes_the_other_way(self):
        # Arrange
        mesh = quad_cut_mesh()

        # Act
        result = thicken_mesh(mesh, _THICKNESS, back_face=True, orientation="leftHanded")

        # Assert
        np.testing.assert_allclose(result.points[result.triangles[-2:]][:, :, 2], _THICKNESS)

    async def test_thicken_mesh_with_zero_thickness_returns_the_input(self):
        # Arrange
        mesh = quad_cut_mesh()

        # Act
        result = thicken_mesh(mesh, 0.0)

        # Assert
        self.assertIs(result, mesh)

    async def test_thicken_mesh_without_normals_keeps_normals_absent(self):
        # Arrange
        quad = quad_cut_mesh()
        mesh = CutMesh(points=quad.points, triangles=quad.triangles, st=quad.st, normals=None)

        # Act
        result = thicken_mesh(mesh, _THICKNESS)

        # Assert
        self.assertIsNone(result.normals)
        self.assertEqual(result.points.shape[0], 4 + 4 * 4 + 4)

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

__all__ = ["TestNormals"]

import numpy as np
from lightspeed.trex.alpha_cutout.core.data_models import CutMesh
from lightspeed.trex.alpha_cutout.core.normals import (
    bend_normals_up,
    smooth_normals,
    up_vector,
    vertex_normals_from_faces,
)
from lightspeed.trex.alpha_cutout.core.thicken import thicken_mesh
from omni.kit.test import AsyncTestCase

from ..unit.fixtures import quad_cut_mesh

_UP = np.array([0.0, 0.0, 1.0])
# Row-major USD transform that maps local +Z onto stage +Y (and local +Y onto stage -Z).
_ROTATE_Y_TO_Z = (1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1)


def _without_normals(mesh: CutMesh) -> CutMesh:
    return CutMesh(points=mesh.points, triangles=mesh.triangles, st=mesh.st, normals=None)


class TestNormals(AsyncTestCase):
    """Test the normal post-processing."""

    async def test_vertex_normals_from_faces_with_quad_returns_plus_z(self):
        # Arrange
        mesh = _without_normals(quad_cut_mesh())

        # Act
        normals = vertex_normals_from_faces(mesh)

        # Assert
        np.testing.assert_allclose(normals, np.tile(_UP, (4, 1)), atol=1e-6)

    async def test_vertex_normals_from_faces_with_left_handed_orientation_returns_minus_z(self):
        # Arrange
        mesh = _without_normals(quad_cut_mesh())

        # Act
        normals = vertex_normals_from_faces(mesh, orientation="leftHanded")

        # Assert
        np.testing.assert_allclose(normals, np.tile(-_UP, (4, 1)), atol=1e-6)

    async def test_smooth_normals_with_full_amount_rounds_the_rim_of_a_thickened_quad(self):
        # Arrange
        mesh = thicken_mesh(quad_cut_mesh(), 0.25, back_face=False)

        # Act
        result = smooth_normals(mesh, 1.0)

        # Assert
        front = result.normals[:4]
        np.testing.assert_allclose(np.linalg.norm(front, axis=1), 1.0, atol=1e-6)
        # A corner of the front meets two sides, so its normal tilts away from straight up.
        self.assertTrue(np.all(front[:, 2] < 0.95))
        self.assertTrue(np.all(front[:, 2] > 0.0))

    async def test_smooth_normals_with_zero_amount_returns_the_input(self):
        # Arrange
        mesh = thicken_mesh(quad_cut_mesh(), 0.25)

        # Act
        result = smooth_normals(mesh, 0.0)

        # Assert
        self.assertIs(result, mesh)

    async def test_bend_normals_up_with_full_amount_sets_every_normal_to_up(self):
        # Arrange
        mesh = thicken_mesh(quad_cut_mesh(), 0.25)

        # Act
        result = bend_normals_up(mesh, _UP, 1.0)

        # Assert
        np.testing.assert_allclose(result.normals, np.tile(_UP, (result.points.shape[0], 1)), atol=1e-6)

    async def test_bend_normals_up_with_half_amount_halves_the_angle(self):
        # Arrange
        quad = quad_cut_mesh()
        sideways = np.tile(np.array([1.0, 0.0, 0.0], dtype=np.float32), (4, 1))
        mesh = CutMesh(points=quad.points, triangles=quad.triangles, st=quad.st, normals=sideways)

        # Act
        result = bend_normals_up(mesh, _UP, 0.5)

        # Assert
        expected = np.tile([np.sqrt(0.5), 0.0, np.sqrt(0.5)], (4, 1))
        np.testing.assert_allclose(result.normals, expected, atol=1e-6)

    async def test_bend_normals_up_without_normals_derives_them_from_the_faces(self):
        # Arrange
        mesh = _without_normals(quad_cut_mesh())

        # Act
        result = bend_normals_up(mesh, np.array([1.0, 0.0, 0.0]), 0.5)

        # Assert
        expected = np.tile([np.sqrt(0.5), 0.0, np.sqrt(0.5)], (4, 1))
        np.testing.assert_allclose(result.normals, expected, atol=1e-6)

    async def test_up_vector_with_z_up_and_no_transform_returns_z(self):
        # Act
        result = up_vector("Z", None)

        # Assert
        np.testing.assert_allclose(result, _UP)

    async def test_up_vector_with_rotated_transform_maps_up_into_mesh_space(self):
        # Arrange: the mesh transform rotates local +Z onto stage +Y, so stage up is local +Z.

        # Act
        result = up_vector("Y", _ROTATE_Y_TO_Z)

        # Assert
        np.testing.assert_allclose(result, _UP, atol=1e-9)

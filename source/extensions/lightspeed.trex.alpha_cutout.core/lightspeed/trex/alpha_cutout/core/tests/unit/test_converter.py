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

__all__ = ["TestConvertMesh"]

import tempfile
from pathlib import Path

import numpy as np
from lightspeed.trex.alpha_cutout.core.converter import convert_mesh, parameters_from_values
from lightspeed.trex.alpha_cutout.core.data_models import CutoutParameters, MeshSource
from omni.kit.test import AsyncTestCase
from PIL import Image

_QUAD_POINTS = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float32)
_QUAD_TRIANGLES = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
_QUAD_ST = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)


def _write_texture(path: Path, alpha: np.ndarray) -> str:
    rgba = np.dstack([np.full_like(alpha, 128)] * 3 + [alpha])
    Image.fromarray(rgba, "RGBA").save(path)
    return str(path)


def _disc_alpha(size: int = 64, radius: int = 24) -> np.ndarray:
    rows, cols = np.mgrid[0:size, 0:size]
    inside = ((rows - (size - 1) / 2) ** 2 + (cols - (size - 1) / 2) ** 2) <= radius**2
    return inside.astype(np.uint8) * 255


def _quad_source(texture_path: str, prim_path: str = "/Root/mesh") -> MeshSource:
    return MeshSource(
        prim_path=prim_path,
        points=_QUAD_POINTS,
        triangles=_QUAD_TRIANGLES,
        st=_QUAD_ST[_QUAD_TRIANGLES],
        normals=None,
        transform=None,
        double_sided=False,
        orientation="rightHanded",
        texture_path=texture_path,
    )


class TestConvertMesh(AsyncTestCase):
    """Test the worker-side conversion."""

    async def test_convert_mesh_with_disc_alpha_removes_corner_area(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            texture = _write_texture(Path(temp_dir) / "disc.png", _disc_alpha())
            source = _quad_source(texture)

            # Act
            result = convert_mesh(source, CutoutParameters(edge_margin=0.0))

        # Assert
        self.assertIsNone(result.skip_reason)
        self.assertGreater(result.output_triangle_count, 2)
        self.assertEqual(result.input_triangle_count, 2)
        self.assertGreater(result.removed_uv_area_percent, 40.0)
        self.assertLess(result.removed_uv_area_percent, 60.0)

    async def test_convert_mesh_with_thicken_adds_sides_to_the_triangle_count(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            texture = _write_texture(Path(temp_dir) / "disc.png", _disc_alpha())
            source = _quad_source(texture)
            flat = convert_mesh(source, CutoutParameters(edge_margin=0.0))

            # Act
            result = convert_mesh(
                source, CutoutParameters(edge_margin=0.0, thicken=True, thickness=0.1, thicken_back_face=False)
            )

        # Assert
        self.assertGreater(result.output_triangle_count, flat.output_triangle_count)
        self.assertEqual(result.input_triangle_count, 2)

    async def test_convert_mesh_with_up_normals_points_every_normal_up(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            texture = _write_texture(Path(temp_dir) / "disc.png", _disc_alpha())
            source = _quad_source(texture)

            # Act
            result = convert_mesh(source, CutoutParameters(edge_margin=0.0, up_normals=True, up_amount=1.0))

        # Assert
        normals = result.cut_mesh.normals
        self.assertEqual(normals.shape[0], result.cut_mesh.points.shape[0])
        np.testing.assert_allclose(normals, np.tile([0.0, 1.0, 0.0], (normals.shape[0], 1)), atol=1e-6)

    async def test_convert_mesh_with_smooth_normals_keeps_unit_normals_for_every_vertex(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            texture = _write_texture(Path(temp_dir) / "disc.png", _disc_alpha())
            source = _quad_source(texture)

            # Act
            result = convert_mesh(
                source,
                CutoutParameters(edge_margin=0.0, thicken=True, thickness=0.1, smooth_normals=True, smoothing=1.0),
            )

        # Assert
        normals = result.cut_mesh.normals
        self.assertEqual(normals.shape[0], result.cut_mesh.points.shape[0])
        np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-5)

    async def test_convert_mesh_with_minimal_outline_cuts_the_disc(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            texture = _write_texture(Path(temp_dir) / "disc.png", _disc_alpha())
            source = _quad_source(texture)

            # Act
            result = convert_mesh(source, CutoutParameters(edge_margin=0.0, minimal_outline=True))

        # Assert
        self.assertIsNone(result.skip_reason)
        self.assertGreater(result.removed_uv_area_percent, 40.0)
        self.assertLess(result.removed_uv_area_percent, 60.0)

    async def test_convert_mesh_with_opaque_texture_reports_nothing_to_cut(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            texture = _write_texture(Path(temp_dir) / "opaque.png", np.full((8, 8), 255, dtype=np.uint8))
            source = _quad_source(texture)

            # Act
            result = convert_mesh(source, CutoutParameters())

        # Assert
        self.assertIsNone(result.cut_mesh)
        self.assertIn("no transparent texels", result.skip_reason)

    async def test_convert_mesh_with_transparent_texture_reports_nothing_opaque(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            texture = _write_texture(Path(temp_dir) / "clear.png", np.zeros((8, 8), dtype=np.uint8))
            source = _quad_source(texture)

            # Act
            result = convert_mesh(source, CutoutParameters())

        # Assert
        self.assertIsNone(result.cut_mesh)
        self.assertIn("No opaque area", result.skip_reason)

    async def test_convert_mesh_with_skipped_source_keeps_its_reason(self):
        # Arrange
        source = MeshSource.skipped("/Root/mesh", "no geometry")

        # Act
        result = convert_mesh(source, CutoutParameters())

        # Assert
        self.assertEqual(result.skip_reason, "no geometry")

    async def test_parameters_from_values_ignores_unknown_keys_and_keeps_defaults(self):
        # Arrange
        values = {"alpha_threshold": 64, "thicken": True, "source": "Selected Prims"}

        # Act
        parameters = parameters_from_values(values)

        # Assert
        self.assertEqual(parameters.alpha_threshold, 64)
        self.assertTrue(parameters.thicken)
        self.assertEqual(parameters.trace_resolution, CutoutParameters().trace_resolution)

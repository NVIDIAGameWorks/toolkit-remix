"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import pathlib

import numpy as np
from omni.flux.utils.octahedral_converter import OctahedralConverter
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path
from PIL import Image

__all__ = ["TestOctahedralConverter"]

_UINT8_CHANNEL_MAX = 255.0


class TestOctahedralConverter(AsyncTestCase):
    async def setUp(self):
        pass

    async def tearDown(self):
        pass

    async def test_convert_float_in_place_matches_reference_maps(self):
        """Float conversion of DirectX and OpenGL maps matches the reference octahedral maps without 8-bit rounding."""
        texture_folder_path = pathlib.Path(get_test_data_path(__name__, "textures"))
        cases = (
            ("Normal_Map_Test_DirectX.png", "Normal_Map_Test_DX_Octahedral.png", False),
            ("Normal_Map_Test_OpenGL.png", "Normal_Map_Test_OGL_Octahedral.png", True),
        )
        for source_name, reference_name, opengl in cases:
            with self.subTest(source=source_name):
                # Arrange
                with Image.open(texture_folder_path / source_name) as image_file:
                    rgb = np.array(image_file)[:, :, 0:3] / _UINT8_CHANNEL_MAX
                with Image.open(texture_folder_path / reference_name) as image_file:
                    reference = np.array(image_file)[:, :, 0:2] / _UINT8_CHANNEL_MAX
                pixels = np.dstack((rgb, np.zeros(rgb.shape[:2]))).astype("float32")

                # Act
                OctahedralConverter.convert_float_to_octahedral_in_place(pixels, opengl)

                # Assert
                np.testing.assert_allclose(pixels[:, :, 0:2], reference, atol=2.5 / _UINT8_CHANNEL_MAX)
                self.assertFalse(pixels[:, :, 2].any())
                self.assertTrue((pixels[:, :, 3] == 1.0).all())

    async def test_convert_float_in_place_maps_flat_and_inward_normals_to_the_hemisphere(self):
        """A zero-length normal becomes the surface normal, and an inward normal mirrors to point outward."""
        # Arrange
        # (0.5, 0.5, 0.5) is zero length. (0.75, 0.5, 0.25) is (0.5, 0, -0.5), which mirrors to (0.5, 0, 0.5).
        pixels = np.array([[[0.5, 0.5, 0.5, 0.0], [0.75, 0.5, 0.25, 0.0]]], dtype="float32")

        # Act
        OctahedralConverter.convert_float_to_octahedral_in_place(pixels, opengl=False)

        # Assert
        np.testing.assert_allclose(pixels, [[[0.5, 0.5, 0.0, 1.0], [0.75, 0.75, 0.0, 1.0]]], atol=1e-6)

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
import tempfile

import numpy as np
from omni.flux.utils.octahedral_converter import OctahedralConverter
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path
from PIL import Image

__all__ = ["TestOctahedralConverterE2E"]


class TestOctahedralConverterE2E(AsyncTestCase):
    """Convert normal map files on disk and compare them with the reference octahedral maps."""

    async def test_convert_file_matches_reference_maps(self):
        """DirectX and OpenGL normal map files convert to files that match the reference octahedral maps."""
        # Arrange
        texture_folder_path = pathlib.Path(get_test_data_path(__name__, "textures"))
        cases = (
            ("Normal_Map_Test_DirectX.png", "Normal_Map_Test_DX_Octahedral.png", False),
            ("Normal_Map_Test_OpenGL.png", "Normal_Map_Test_OGL_Octahedral.png", True),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            for source_name, reference_name, opengl in cases:
                with self.subTest(source=source_name):
                    out_path = pathlib.Path(temporary_directory) / reference_name

                    # Act
                    OctahedralConverter.convert_file_to_octahedral(
                        str(texture_folder_path / source_name), str(out_path), opengl
                    )

                    # Assert
                    with Image.open(out_path) as image_file:
                        converted = np.array(image_file).astype("int32")
                    with Image.open(texture_folder_path / reference_name) as image_file:
                        reference = np.array(image_file)[:, :, 0:3].astype("int32")
                    # The reference maps hold no blue. Red and green may differ by 2 for float rounding.
                    self.assertEqual(converted.shape, reference.shape)
                    self.assertLessEqual(np.abs(converted[:, :, 0:2] - reference[:, :, 0:2]).max(), 2)
                    self.assertFalse(converted[:, :, 2].any())

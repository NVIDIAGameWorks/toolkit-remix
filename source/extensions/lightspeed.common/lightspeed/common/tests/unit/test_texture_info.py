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

from omni.kit.test import AsyncTestCase
from lightspeed.common.texture_info import CompressionFormat, TextureInfo


class TestTextureInfo(AsyncTestCase):
    """Test texture conversion metadata and NVTT flag generation."""

    async def test_to_nvtt_flag_array_returns_format_gamma_and_extra_args(self):
        """NVTT flags include the compression format, gamma mode, and caller-provided args."""
        # Arrange
        texture_info = TextureInfo(CompressionFormat.BC4, False, ["--mip-filter", "max"])

        # Act
        flags = texture_info.to_nvtt_flag_array()

        # Assert
        self.assertEqual(flags, ["--format", "bc4", "--no-mip-gamma-correct", "--mip-filter", "max"])

    async def test_to_nvtt_flag_array_raises_for_unsupported_compression_format(self):
        """Invalid runtime compression values fail before building an invalid NVTT argv list."""
        # Arrange
        texture_info = TextureInfo(999, False)

        # Act
        with self.assertRaises(ValueError) as error:
            texture_info.to_nvtt_flag_array()

        # Assert
        self.assertIn("Unsupported compression format", str(error.exception))

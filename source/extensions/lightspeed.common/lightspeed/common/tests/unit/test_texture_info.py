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
from lightspeed.common.texture_info import CompressionFormat, MipFilter, TextureInfo


class TestTextureInfo(AsyncTestCase):
    """Test texture conversion metadata."""

    async def test_stores_compression_format_gamma_and_explicit_mip_filter(self):
        """Construction stores the compression format, gamma flag, and an explicit mip filter."""
        # Arrange / Act
        texture_info = TextureInfo(CompressionFormat.BC4, False, mip_filter=MipFilter.MAX)

        # Assert
        self.assertEqual(texture_info.compression_format, CompressionFormat.BC4)
        self.assertFalse(texture_info.gamma_encoded)
        self.assertEqual(texture_info.mip_filter, MipFilter.MAX)

    async def test_mip_filter_defaults_to_box(self):
        """Construction without a mip filter defaults to MipFilter.BOX."""
        # Arrange / Act
        texture_info = TextureInfo(CompressionFormat.BC7, True)

        # Assert
        self.assertEqual(texture_info.compression_format, CompressionFormat.BC7)
        self.assertTrue(texture_info.gamma_encoded)
        self.assertEqual(texture_info.mip_filter, MipFilter.BOX)

    async def test_two_instances_with_the_same_fields_compare_equal(self):
        """Frozen TextureInfo compares by value, so a DDS reuse signature can compare two instances directly."""
        # Arrange / Act
        first = TextureInfo(CompressionFormat.BC4, False, mip_filter=MipFilter.MAX)
        second = TextureInfo(CompressionFormat.BC4, False, mip_filter=MipFilter.MAX)

        # Assert
        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))

    async def test_instances_with_a_different_field_compare_unequal(self):
        """A single differing field, such as the mip filter, must break equality."""
        # Arrange / Act
        first = TextureInfo(CompressionFormat.BC4, False, mip_filter=MipFilter.MAX)
        second = TextureInfo(CompressionFormat.BC4, False, mip_filter=MipFilter.BOX)

        # Assert
        self.assertNotEqual(first, second)

    async def test_fields_cannot_be_reassigned(self):
        """TextureInfo is frozen so a cached reuse signature can never be mutated after construction."""
        # Arrange
        texture_info = TextureInfo(CompressionFormat.BC4, False)

        # Act / Assert
        with self.assertRaises(AttributeError):
            texture_info.gamma_encoded = True

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

from dataclasses import dataclass
from enum import IntEnum


class CompressionFormat(IntEnum):
    BC4 = 0  # 1 channel lossy compression format
    BC5 = 1  # 2 channel lossy compression format
    BC7 = 2  # 3 channel lossy compression format (with optional additional 4th alpha channel)


class MipFilter(IntEnum):
    """Mipmap downsampling filter to use when generating a texture's mip chain."""

    BOX = 0
    MAX = 1


@dataclass(frozen=True)
class TextureInfo:
    """A texture's desired compression format, encoding, and mip filter.

    Frozen so two textures with the same settings compare equal, which the DDS reuse-cache signature relies on.

    Args:
        compression_format (CompressionFormat): The compression format the texture should be exported to.
        gamma_encoded (bool): A boolean flag to indicate if the texture data is encoded in gamma space (True) or
        linear space (False). Note the current pipeline assumes the gamma encoding is consistent throughout, rathe
        than supporting different import/export formats for the time being.
        mip_filter (MipFilter): The mipmap downsampling filter to use when generating the texture's mip chain.
    """

    compression_format: CompressionFormat
    gamma_encoded: bool
    mip_filter: MipFilter = MipFilter.BOX

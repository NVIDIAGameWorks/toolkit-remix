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

from enum import IntEnum


class CompressionFormat(IntEnum):
    BC4 = 0  # 1 channel lossy compression format
    BC5 = 1  # 2 channel lossy compression format
    BC7 = 2  # 3 channel lossy compression format (with optional additional 4th alpha channel)


class TextureInfo:
    """Class to hold information about a texture's desired compression format, encoding and more.

    Args:
        compression_format (CompressionFormat): The compression format the texture should be exported to.
        gamma_encoded (bool): A boolean flag to indicate if the texture data is encoded in gamma space (True) or
        linear space (False). Note the current pipeline assumes the gamma encoding is consistent throughout, rathe
        than supporting different import/export formats for the time being.
    """

    def __init__(self, compression_format, gamma_encoded):
        self.compression_format = compression_format
        self.gamma_encoded = gamma_encoded

    def to_nvtt_flag_array(self):
        compression_format_string = None

        # Note: All valid compression formats handled here, no else case for a fallback as
        # it should be an error if some other value is somehow passed in.
        if self.compression_format == CompressionFormat.BC4:
            compression_format_string = "bc4"
        elif self.compression_format == CompressionFormat.BC5:
            compression_format_string = "bc5"
        elif self.compression_format == CompressionFormat.BC7:
            compression_format_string = "bc7"

        # Note: Textures encoded in gamma space should use gamma correct mip interpolation, otherwise they should not
        # for highest quality results.
        mip_gamma_correction_string = "--mip-gamma-correct" if self.gamma_encoded else "--no-mip-gamma-correct"

        return ["--format", compression_format_string, mip_gamma_correction_string]

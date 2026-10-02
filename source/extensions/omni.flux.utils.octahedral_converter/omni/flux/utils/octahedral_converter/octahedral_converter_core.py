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

from pathlib import Path

import carb
import numpy as np
from PIL import Image

# Each pass of the in-place float conversion reads about this many pixels into contiguous temporary arrays of
# 256 KiB, which stay in the CPU cache. Larger blocks run slower.
_CHUNK_PIXELS = 1 << 16


# Converts either OpenGL or DirectX style normal maps to RTX Remix compatible Hemispherical Octahedral maps.
#
# Note that normals pointing in to the surface are not physically possible, and are not supported by RTX Remix.
#   Any images with inward pointing normals will generate a warning and will be flipped to point outwards.
#
# There is a good explanation of DirectX vs OpenGL normal maps at
#   https://www.texturecan.com/post/3/DirectX-vs-OpenGL-Normal-Map/
#
# To use, call this from python as
# `OctahedralConverter.convert_file_to_octahedral("input_dx_normal_map.png", "output_octahedral_map.png", opengl=False)`
#
# To then load these into RTX Remix, you can convert it to a DDS file using
#   https://developer.nvidia.com/nvidia-texture-tools-exporter
#   Use BC5 compression, and the flag --no-mip-gamma-correct
class OctahedralConverter:
    @staticmethod
    def convert_file_to_octahedral(source_path: str, oth_path: str, opengl: bool) -> None:
        """Convert an 8-bit normal map file to an 8-bit octahedral RGB file.

        The values go through ``convert_float_to_octahedral_in_place``, and only the output rounds to 8 bits.

        Args:
            source_path: DirectX or OpenGL normal map to read.
            oth_path: Octahedral map to write.
            opengl: Whether green points up (OpenGL). False for DirectX, where green points down.
        """
        if not Path(source_path).exists():
            carb.log_warn(f"convert_file_to_octahedral called on non-existent path: {source_path}")
            return
        with Image.open(source_path) as image_file:
            rgb = np.asarray(image_file.convert("RGB"))
        pixels = np.empty((*rgb.shape[:2], 4), dtype=np.float32)
        pixels[:, :, 0:3] = rgb
        pixels[:, :, 0:3] *= 1.0 / 255.0
        OctahedralConverter.convert_float_to_octahedral_in_place(pixels, opengl)
        pixels[:, :, 0:3] *= 255.0
        pixels[:, :, 0:3] += 0.5
        Image.fromarray(pixels[:, :, 0:3].astype(np.uint8), "RGB").save(oth_path)

    @staticmethod
    def convert_float_to_octahedral_in_place(pixels: np.ndarray, opengl: bool) -> None:
        """Change a float RGBA normal map in place to octahedral values, without 8-bit rounding.

        The math is ``hemisphereDirectionToUnsignedOctahedral`` of the RTX Remix runtime. The octahedral
        projection divides by the L1 length, so a normal needs no normalization first. A zero-length normal
        becomes the surface normal. Each pass copies a block of pixels into small contiguous arrays, so memory holds
        no second copy of the image.
        After the call, red and green hold the octahedral value in [0, 1], blue is 0, and alpha is 1.

        Args:
            pixels: Float32 pixels with shape ``(height, width, 4)``. The first three channels hold the normal,
                encoded in [0, 1]. Only per-pixel changes occur, so the row order does not matter.
            opengl: Whether green points up (OpenGL). False for DirectX, where green points down.
        """
        rows_per_chunk = max(1, _CHUNK_PIXELS // pixels.shape[1])
        # DirectX green points down, as the runtime expects. OpenGL green flips: y = 1 - 2 * g.
        y_scale, y_offset = (-2.0, 1.0) if opengl else (2.0, -1.0)
        inward = 0
        for start in range(0, pixels.shape[0], rows_per_chunk):
            rows = pixels[start : start + rows_per_chunk]
            x = rows[:, :, 0] * 2.0
            x -= 1.0
            y = rows[:, :, 1] * y_scale
            y += y_offset
            z = rows[:, :, 2] * 2.0
            z -= 1.0
            # RTX Remix only supports hemispherical normals, so an inward normal mirrors to point away from the surface.
            inward += int(np.count_nonzero(z < 0.0))
            np.abs(z, out=z)
            # 0.5 / L1 length. A zero length gives 0, so the normal becomes (0.5, 0.5), the surface normal.
            scale = np.abs(x)
            scale += np.abs(y)
            scale += z
            scale[scale == 0.0] = np.inf
            np.divide(0.5, scale, out=scale)
            # The sum and the difference of the projected x and y, moved from [-1, 1] to [0, 1].
            np.subtract(x, y, out=z)
            x += y
            x *= scale
            x += 0.5
            z *= scale
            z += 0.5
            rows[:, :, 0] = x
            rows[:, :, 1] = z
            rows[:, :, 2] = 0.0
            rows[:, :, 3] = 1.0
        if inward:
            carb.log_warn(
                f"{inward} normals point inward (z < 0.0). RTX Remix only supports hemispherical normals,"
                " so they are mirrored to point away from the surface."
            )

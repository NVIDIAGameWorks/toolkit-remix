"""
* SPDX-FileCopyrightText: Copyright (c) 2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: MIT
*
* Permission is hereby granted, free of charge, to any person obtaining a
* copy of this software and associated documentation files (the "Software"),
* to deal in the Software without restriction, including without limitation
* the rights to use, copy, modify, merge, publish, distribute, sublicense,
* and/or sell copies of the Software, and to permit persons to whom the
* Software is furnished to do so, subject to the following conditions:
*
* The above copyright notice and this permission notice shall be included in
* all copies or substantial portions of the Software.
*
* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
* THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
* FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
* DEALINGS IN THE SOFTWARE.
"""
from pathlib import Path

import numpy as np
from PIL import Image


# Converts either OpenGL or DirectX style normal maps to RTX Remix compatible Hemispherical Octahedral maps.
#
# Note that normals pointing in to the surface are not physically possible, and are not supported by RTX Remix.
#   Any images with inward pointing normals will generate a warning and will be flipped to point outwards.
#
# There is a good explanation of DirectX vs OpenGL normal maps at
#   https://www.texturecan.com/post/3/DirectX-vs-OpenGL-Normal-Map/
#
# To use, call this from python as
# `LightspeedOctahedralConverter.convert_dx_file_to_octahedral("input_dx_normal_map.png", "output_octahedral_map.png")`
#
# To then load these into RTX Remix, you can convert it to a DDS file using
#   https://developer.nvidia.com/nvidia-texture-tools-exporter
#   Use BC5 compression, and the flag --no-mip-gamma-correct
class LightspeedOctahedralConverter:
    # Convert DirectX style normal maps (green is down)
    @staticmethod
    def convert_dx_file_to_octahedral(dx_path, oth_path):
        if not Path(dx_path).exists():
            print("convert_dx_to_octahedral called on non-existant path: " + dx_path)
            return
        with Image.open(dx_path) as image_file:
            img = np.array(image_file)
            LightspeedOctahedralConverter._check_for_spherical_normals(dx_path, img)
            img_int = LightspeedOctahedralConverter.convert_dx_to_octahedral(img)
            Image.fromarray(img_int, "RGB").save(oth_path)

    # Convert OpenGL style normal maps (green is up)
    @staticmethod
    def convert_ogl_file_to_octahedral(ogl_path, oth_path):
        if not Path(ogl_path).exists():
            print("convert_ogl_to_octahedral called on non-existant path: " + ogl_path)
            return
        with Image.open(ogl_path) as image_file:
            img = np.array(image_file)
            LightspeedOctahedralConverter._check_for_spherical_normals(ogl_path, img)
            img_int = LightspeedOctahedralConverter.convert_ogl_to_octahedral(img)
            Image.fromarray(img_int, "RGB").save(oth_path)

    @staticmethod
    def convert_dx_to_octahedral(image):
        normals = LightspeedOctahedralConverter._pixels_to_normals(image)
        octahedrals = LightspeedOctahedralConverter._convert_to_octahedral(normals)
        return LightspeedOctahedralConverter._octahedrals_to_pixels(octahedrals)

    @staticmethod
    def convert_ogl_to_octahedral(image):
        dx_image = LightspeedOctahedralConverter._ogl_to_dx(image)
        return LightspeedOctahedralConverter.convert_dx_to_octahedral(dx_image)

    @staticmethod
    def _check_for_spherical_normals(original_path, image):
        # Check for blue values below 128.
        mask = image[:, :, 2] < 128
        num_negative = image[mask].shape[0]
        if num_negative > 0:
            print(
                original_path
                + " contained "
                + str(num_negative)
                + " pixels with inward pointing normals (z < 0.0, or b < 128).  RTX Remix only supports hemispherical"
                + " normals, with the normal pointing away from the surface."
            )

        # Mirror the normal to point out from surface.
        image[mask, 2] = 255 - image[mask, 2]

    @staticmethod
    def _pixels_to_normals(image):
        image = image[:, :, 0:3].astype("float32") / 255
        image = image * 2.0 - 1.0
        return image / np.linalg.norm(image, axis=2)[:, :, np.newaxis]

    @staticmethod
    def _octahedrals_to_pixels(octahedrals):
        image = np.floor(octahedrals * 255 + 0.5).astype("uint8")
        return np.pad(image, ((0, 0), (0, 0), (0, 1)), mode="constant")

    @staticmethod
    def _ogl_to_dx(image):
        # flip the g channel to convert to DX style
        image[:, :, (1)] = 255 - image[:, :, (1)]
        return image

    @staticmethod
    def _convert_to_octahedral(image):
        # convert from 3 channel to 2 channel normal map
        abs_values = np.absolute(image)
        snorm_octahedrals = image[:, :, 0:2] / np.expand_dims(abs_values.sum(2), axis=2)
        # Hemisphere normal handling:
        result = snorm_octahedrals.copy()
        result[:, :, 0] = snorm_octahedrals[:, :, 0] + snorm_octahedrals[:, :, 1]
        result[:, :, 1] = snorm_octahedrals[:, :, 0] - snorm_octahedrals[:, :, 1]
        return result * 0.5 + 0.5

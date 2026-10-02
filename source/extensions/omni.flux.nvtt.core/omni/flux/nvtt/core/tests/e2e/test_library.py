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

__all__ = ["TestNvttLibraryE2E"]

import ctypes
import pathlib
import struct
import tempfile

import numpy as np
from omni.flux.nvtt.core import (
    BlockFormat,
    DxgiFormat,
    convert_to_openexr,
    encode_dds,
    read_dds_format,
    read_linear_image,
    write_openexr,
)
from omni.kit.test import AsyncTestCase
from PIL import Image

from ... import library

_DDS_FOURCC_START = 84
_DDS_FOURCC_END = 88
_DDS_MIPMAP_COUNT_OFFSET = 28
_BC6_RELATIVE_TOLERANCE = 0.05
_SRGB_MIDPOINT_LINEAR = 0.21586
_IMAGE_SIZE = 4
_RGBA_PLANES = 4


def _double_color(pixels: np.ndarray) -> None:
    """Double the color of each pixel in place.

    Args:
        pixels: Writable float RGBA pixels. The RGB channels are doubled, and alpha is kept.
    """
    pixels[:, :, 0:3] *= 2.0


def _decode_dds(native: ctypes.CDLL, source: pathlib.Path) -> np.ndarray:
    """Decode the top mip of a DDS file with NVTT.

    Args:
        native: The loaded NVTT library.
        source: DDS file to decode.

    Returns:
        A copy of the float pixels as planes of shape ``(4, height, width)``, in RGBA order.

    Raises:
        AssertionError: If NVTT cannot load the file.
    """
    native.nvttSurfaceWidth.argtypes = [ctypes.c_void_p]
    native.nvttSurfaceWidth.restype = ctypes.c_int
    native.nvttSurfaceHeight.argtypes = [ctypes.c_void_p]
    native.nvttSurfaceHeight.restype = ctypes.c_int
    surface = native.nvttCreateSurface()
    try:
        if not native.nvttSurfaceLoad(surface, str(source).encode(), None, False, None):
            raise AssertionError(f"NVTT cannot load {source}")
        width, height = native.nvttSurfaceWidth(surface), native.nvttSurfaceHeight(surface)
        pixels = native.nvttSurfaceData(surface)
        if not pixels:
            raise AssertionError(f"NVTT has no pixels for {source}")
        return (
            np.ctypeslib.as_array(pixels, shape=(_RGBA_PLANES * height * width,))
            .reshape(_RGBA_PLANES, height, width)
            .copy()
        )
    finally:
        native.nvttDestroySurface(surface)


class TestNvttLibraryE2E(AsyncTestCase):
    """Encode real HDR and SDR sources with the native library."""

    async def test_encode_bc6_hdr_exr_and_png_preserves_linear_pixels(self):
        """BC6H_UF16 retains HDR and OpenEXR radiance and converts sRGB pixels to linear values, whatever the suffix."""
        native = library._load()
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            hdr = root / "sky.hdr"
            # Radiance RGBE stores this constant image as linear RGB (4, 2, 1).
            hdr.write_bytes(b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 4 +X 4\n" + bytes((128, 64, 32, 131)) * 16)
            png = root / "sky.png"
            Image.new("RGB", (4, 4), (128, 128, 128)).save(png)
            exr = root / "sky.exr"
            write_openexr(exr, np.full((4, 4, 4), (8.0, 0.5, 2.0, 1.0), dtype="float32"))
            # The file header selects the reader and the color space, so a wrong suffix changes nothing.
            hdr_named_png, exr_named_png, png_named_exr = root / "hdr.png", root / "exr.png", root / "png.exr"
            hdr_named_png.write_bytes(hdr.read_bytes())
            exr_named_png.write_bytes(exr.read_bytes())
            png_named_exr.write_bytes(png.read_bytes())
            cases = (
                (hdr, (4.0, 2.0, 1.0)),
                (exr, (8.0, 0.5, 2.0)),
                (png, (_SRGB_MIDPOINT_LINEAR,) * 3),
                (hdr_named_png, (4.0, 2.0, 1.0)),
                (exr_named_png, (8.0, 0.5, 2.0)),
                (png_named_exr, (_SRGB_MIDPOINT_LINEAR,) * 3),
            )
            for source, expected in cases:
                with self.subTest(source=source.name):
                    # Arrange
                    destination = root / f"{source.name}.dds"

                    # Act
                    encode_dds(source, destination, block_format=BlockFormat.BC6H_UF16, gamma_encoded=False)

                    # Assert
                    data = destination.read_bytes()
                    self.assertEqual(data[:4], b"DDS ")
                    self.assertEqual(data[_DDS_FOURCC_START:_DDS_FOURCC_END], b"DX10")
                    self.assertEqual(read_dds_format(destination), DxgiFormat.BC6H_UF16)
                    self.assertEqual(struct.unpack_from("<I", data, _DDS_MIPMAP_COUNT_OFFSET)[0], 3)
                    planes = _decode_dds(native, destination)
                    self.assertEqual(planes.shape[1:], (_IMAGE_SIZE, _IMAGE_SIZE))
                    for channel, value in enumerate(expected):
                        np.testing.assert_allclose(planes[channel], value, rtol=_BC6_RELATIVE_TOLERANCE)

    async def test_encode_bc6_from_bc6_dds_keeps_linear_pixels(self):
        """A BC6H DDS source holds linear values, so a second BC6H_UF16 encode keeps the radiance below and above 1."""
        # Arrange
        native = library._load()
        expected = (0.5, 4.0, 2.0)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            exr, first, second = root / "sky.exr", root / "first.dds", root / "second.dds"
            write_openexr(exr, np.full((_IMAGE_SIZE, _IMAGE_SIZE, 4), (*expected, 1.0), dtype="float32"))
            encode_dds(exr, first, block_format=BlockFormat.BC6H_UF16, gamma_encoded=False)

            # Act
            encode_dds(first, second, block_format=BlockFormat.BC6H_UF16, gamma_encoded=False)

            # Assert
            self.assertEqual(read_dds_format(first), DxgiFormat.BC6H_UF16)
            self.assertEqual(read_dds_format(second), DxgiFormat.BC6H_UF16)
            planes = _decode_dds(native, second)
            for channel, value in enumerate(expected):
                np.testing.assert_allclose(planes[channel], value, rtol=_BC6_RELATIVE_TOLERANCE)

    async def test_openexr_round_trip_keeps_exact_float_pixels(self):
        """write_openexr and read_linear_image keep every float value and the row order. Other formats read None."""
        pixels = np.arange(2 * 3 * 4, dtype="float32").reshape(2, 3, 4) * -0.37 + 1.0e4
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            exr, png = root / "image.exr", root / "image.png"
            write_openexr(exr, pixels)
            Image.new("RGB", (2, 2)).save(png)

            np.testing.assert_array_equal(read_linear_image(exr), pixels)
            self.assertIsNone(read_linear_image(png))

    async def test_convert_to_openexr_raises_for_an_unknown_format(self):
        """A file that FreeImage cannot identify raises and writes nothing, so no caller checks a result."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source, destination = root / "image.png", root / "image.exr"
            source.write_bytes(b"not an image")

            with self.assertRaises(RuntimeError):
                convert_to_openexr(source, destination, lambda pixels: None)
            self.assertFalse(destination.exists())

    async def test_convert_to_openexr_saves_the_edited_pixels_in_source_order(self):
        """The edit reaches the output file, and 8 and 16 bit sources keep their channel, row, and value precision."""
        rgba8 = np.arange(2 * 3 * 4, dtype="uint8").reshape(2, 3, 4) * 10 + 5
        gray16 = np.array([[1, 257, 4097], [32769, 65534, 65535]], dtype="uint16")
        cases = (
            ("rgba8.png", Image.fromarray(rgba8, "RGBA"), rgba8 / 255.0),
            ("gray16.png", Image.fromarray(gray16), np.dstack([gray16 / 65535.0] * 3 + [np.ones(gray16.shape)])),
        )
        with tempfile.TemporaryDirectory() as directory:
            for name, image, source_values in cases:
                with self.subTest(source=name):
                    source, destination = pathlib.Path(directory, name), pathlib.Path(directory, f"{name}.exr")
                    image.save(source)
                    expected = source_values.astype("float32")
                    expected[:, :, 0:3] *= 2.0

                    convert_to_openexr(source, destination, _double_color)

                    np.testing.assert_allclose(read_linear_image(destination), expected, rtol=1e-6)

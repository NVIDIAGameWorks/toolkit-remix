"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import asyncio
import contextlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import carb
import carb.tokens

# import numpy as np
import omni.usd
from lightspeed.common import constants
from PIL import Image, ImageOps


class ColorToRoughnessCore:
    @staticmethod
    def perform_conversion(texture, output_texture, overwrite=False):
        # Get the paths to the nvtt process for format conversion and pix2pix for access to the nueral net driver
        if os.path.exists(output_texture) and not overwrite:
            carb.log_info("Skipping " + texture + " since " + output_texture + " already exists.")
            return
        if not output_texture.lower().endswith(".dds") and not output_texture.lower().endswith(".png"):
            carb.log_info("Output texture " + output_texture + "must be either png or dds format.")
            return
        if os.path.exists(output_texture) and overwrite:
            # delete
            os.remove(output_texture)
        nvtt_path = constants.NVTT_PATH
        converter_path = Path(constants.PIX2PIX_TEST_SCRIPT_PATH)
        converter_dir = Path(constants.PIX2PIX_ROOT_PATH)
        # Copy the neural net data files over to the driver if they don't already exist
        neural_net_data_path = Path(constants.PIX2PIX_CHECKPOINTS_PATH).joinpath("Color_Roughness")
        if not neural_net_data_path.exists():
            shutil.copytree(str(Path(__file__).parent.joinpath("tools", "Color_Roughness")), neural_net_data_path)
        # Set up the path to where the neural net driver leaves the results of the conversion
        result_path = Path(constants.PIX2PIX_RESULTS_PATH).joinpath(
            "Color_Roughness", "test_latest", "images", "texture_fake_B.png"
        )
        # Create temp dir and set up texture name/path
        original_texture_name = Path(texture).stem
        temp_dir = tempfile.TemporaryDirectory().name  # noqa PLR1732
        test_path = Path(temp_dir).joinpath("test", "texture", "texture.png")
        test_path.parent.mkdir(parents=True, exist_ok=True)
        carb.log_info("Converting: " + texture)
        # Convert the input image to a PNG if it already isn't
        if not texture.lower().endswith(".png"):
            png_texture_path = Path(temp_dir).joinpath(original_texture_name + ".png")
            with subprocess.Popen(
                [str(nvtt_path), texture, "--output", str(png_texture_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            ) as convert_png_process:
                convert_png_process.wait()
            # use PILLOW as a fallback if nvtt fails
            if png_texture_path.exists():
                with contextlib.suppress(NotImplementedError):
                    with Image.open(texture) as im:  # noqa
                        im.save(png_texture_path, "PNG")
        else:
            png_texture_path = texture
        # Double the width of the input image so that the neural net driver thinks there's a known result for comparison
        # This can be just empty since it's not used in any way, but is the required input format
        try:
            with Image.open(png_texture_path) as im:  # noqa
                width, height = im.size
                im = im.crop((0, 0, width * 2, height))  # noqa
                im.save(test_path, "PNG")
        except NotImplementedError:
            return
        # Create the dirtectory for the output and delete the results directory if it exists
        Path(output_texture).parent.mkdir(parents=True, exist_ok=True)
        if result_path.exists():
            result_path.unlink()
        # Configure environment to find kit's python.pipapi libraries
        python_path = carb.tokens.get_tokens_interface().resolve("${python}")
        separator = ";" if platform.system() == "Windows" else ":"
        pythonpath_env = separator.join(sys.path)[1:]  # strip leading colon
        new_env = os.environ.copy()
        new_env["PYTHONPATH"] = pythonpath_env
        # Perform the conversion
        with subprocess.Popen(
            [
                python_path,
                str(converter_path),
                "--dataroot",
                temp_dir,
                "--name",
                "Color_Roughness",
                "--model",
                "pix2pix",
                "--num_test",
                "1",
                "--gpu_ids",
                "-1",
                "--preprocess",
                "scale_width",
                "--load_size",
                "1024",
            ],
            cwd=str(converter_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            env=new_env,
        ) as conversion_process:
            conversion_process.wait()
        # Reduce the 3 channel output to a single channgel image
        try:
            with Image.open(str(result_path)) as im:  # noqa
                grey_im = ImageOps.grayscale(im)
                # Convert Smoothness to roughness
                grey_im = ImageOps.invert(grey_im)
                grey_im.save(str(result_path))
                grey_im.close()
        except NotImplementedError:
            return
        # Convert to DDS if necessary, and generate mips (note dont use the temp dir for this)
        if output_texture.lower().endswith(".dds"):
            with subprocess.Popen(
                [
                    str(nvtt_path),
                    str(result_path),
                    "--format",
                    constants.TEXTURE_COMPRESSION_LEVELS[constants.MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE],
                    "--output",
                    output_texture,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            ) as compress_mip_process:
                compress_mip_process.wait()
        else:
            shutil.copy(str(result_path), output_texture)

    @staticmethod
    @omni.usd.handle_exception
    async def async_perform_upscale(texture, output_texture):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, ColorToRoughnessCore.perform_conversion, texture, output_texture)

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
import omni.usd
from lightspeed.common import constants
from PIL import Image


class ColorToNormalCore:
    @staticmethod
    def perform_conversion(texture, output_texture):
        # setup script paths'
        if os.path.exists(output_texture):
            carb.log_info("Skipping " + texture + " since " + output_texture + " already exists.")
            return
        if not output_texture.lower().endswith(".dds") and not output_texture.lower().endswith(".png"):
            carb.log_info("Output texture " + output_texture + "must be either png or dds format.")
            return
        nvtt_path = constants.NVTT_PATH
        converter_path = Path(constants.PIX2PIX_TEST_SCRIPT_PATH)
        converter_dir = Path(constants.PIX2PIX_ROOT_PATH)
        result_path = Path(constants.PIX2PIX_RESULTS_PATH).joinpath(
            "Color_NormalDX", "test_latest", "images", "texture_fake_B.png"
        )
        neural_net_data_path = Path(constants.PIX2PIX_CHECKPOINTS_PATH).joinpath("Color_NormalDX")
        if not neural_net_data_path.exists():
            shutil.copytree(str(Path(__file__).parent.joinpath("tools", "Color_NormalDX")), neural_net_data_path)
        # create temp dir and get texture name/path
        original_texture_name = Path(texture).stem
        temp_dir = tempfile.TemporaryDirectory().name
        test_path = Path(temp_dir).joinpath("test", "texture", "texture.png")
        test_path.parent.mkdir(parents=True, exist_ok=True)
        # begin real work
        carb.log_info("Converting: " + texture)
        # convert to png
        if not texture.lower().endswith(".png"):
            png_texture_path = Path(temp_dir).joinpath(original_texture_name + ".png")
            convert_png_process = subprocess.Popen(
                [str(nvtt_path), texture, "--output", str(png_texture_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            convert_png_process.wait()
            # use PILLOW as a fallback if nvtt fails
            if png_texture_path.exists():
                with contextlib.suppress(NotImplementedError):
                    with Image.open(texture) as im:
                        im.save(png_texture_path, "PNG")
        else:
            png_texture_path = texture
        # prepare the image for conversion
        with Image.open(texture) as im:
            width, height = im.size
            im = im.crop((0, 0, width * 2, height))
            im.save(test_path, "PNG")
        # perform conversion
        Path(output_texture).parent.mkdir(parents=True, exist_ok=True)
        if result_path.exists():
            result_path.unlink()
        # configure environment to find kit's python.pipapi libraries
        python_path = carb.tokens.get_tokens_interface().resolve("${python}")
        separator = ";" if platform.system() == "Windows" else ":"
        pythonpath_env = separator.join(sys.path)[1:]  # strip leading colon
        new_env = os.environ.copy()
        new_env["PYTHONPATH"] = pythonpath_env
        conversion_process = subprocess.Popen(
            [
                python_path,
                str(converter_path),
                "--dataroot",
                temp_dir,
                "--name",
                "Color_NormalDX",
                "--model",
                "pix2pix",
                "--num_test",
                "1",
                "--gpu_ids",
                "-1",
            ],
            cwd=str(converter_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            env=new_env,
        )
        conversion_process.wait()
        # convert to DDS, and generate mips (note dont use the temp dir for this)
        if output_texture.lower().endswith(".dds"):
            compress_mip_process = subprocess.Popen(
                [str(nvtt_path), str(result_path), "--format", "bc7", "--output", output_texture],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            compress_mip_process.wait()
        else:
            shutil.copy(str(result_path), output_texture)

    @staticmethod
    @omni.usd.handle_exception
    async def async_perform_upscale(texture, output_texture):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, ColorToNormalCore.perform_upscale, texture, output_texture)

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
import subprocess
import tempfile
from pathlib import Path

import carb
import omni.usd
from lightspeed.common import constants
from PIL import Image


class UpscalerCore:
    @staticmethod
    def perform_upscale(texture, output_texture, keep_png=False, overwrite=False):
        # setup script paths'
        if Path(output_texture).exists() and not overwrite:
            carb.log_info("Skipping " + texture + " since " + output_texture + " already exists.")
            return
        if not output_texture.lower().endswith(".dds") and not output_texture.lower().endswith(".png"):
            carb.log_info("Output texture " + output_texture + "must be either png or dds format.")
            return
        if os.path.exists(output_texture) and overwrite:
            # delete
            os.remove(output_texture)
        script_path = str(Path(__file__).absolute().parent)
        nvtt_path = constants.NVTT_PATH
        esrgan_tool_path = str(
            Path(script_path).joinpath("tools", "realesrgan-ncnn-vulkan-20210901-windows", "realesrgan-ncnn-vulkan.exe")
        )
        # create temp dir and get texture name/path
        original_texture_name = str(Path(texture).stem)
        output_texture_name = str(Path(output_texture).stem)
        output_texture_path = str(Path(output_texture).absolute().parent)
        temp_dir = tempfile.TemporaryDirectory()  # noqa PLR1732
        # begin real work
        carb.log_info("Upscaling: " + texture)
        # convert to png
        if not texture.lower().endswith(".png"):
            png_texture_path = str(Path(temp_dir.name).joinpath(original_texture_name + ".png"))
            with subprocess.Popen(
                [nvtt_path, texture, "--output", png_texture_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
            ) as convert_png_process:
                convert_png_process.wait()
            # use PILLOW as a fallback if nvtt fails
            if not Path(png_texture_path).exists():
                with contextlib.suppress(NotImplementedError):
                    with Image.open(texture) as im:  # noqa
                        im.save(png_texture_path, "PNG")
        else:
            png_texture_path = texture
        # perform upscale
        Path(output_texture).parent.mkdir(parents=True, exist_ok=True)
        upscaled_texture_path = str(Path(output_texture_path).joinpath(output_texture_name + ".png"))
        with subprocess.Popen(
            [esrgan_tool_path, "-i", png_texture_path, "-o", upscaled_texture_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        ) as upscale_process:
            upscale_process.wait()
        # check for alpha channel and upscale it if it exists
        try:
            with Image.open(png_texture_path) as memory_image:
                if memory_image.mode == "RGBA":
                    alpha_path = str(Path(temp_dir.name).joinpath(original_texture_name + "_alpha.png"))
                    upscaled_alpha_path = str(
                        Path(temp_dir.name).joinpath(original_texture_name + "_upscaled4x_alpha.png")
                    )
                    memory_image.split()[-1].save(alpha_path)
                    with subprocess.Popen(
                        [esrgan_tool_path, "-i", alpha_path, "-o", upscaled_alpha_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT,
                    ) as upscale_process:
                        upscale_process.wait()
                    with Image.open(upscaled_alpha_path).convert("L") as upscaled_alpha_image:
                        with Image.open(upscaled_texture_path) as upscaled_memory_image:
                            upscaled_memory_image.putalpha(upscaled_alpha_image)
                            upscaled_memory_image.save(upscaled_texture_path, "PNG")
        except FileNotFoundError:
            carb.log_info("File not found error! :" + png_texture_path)
            pass
        # convert to DDS, and generate mips (note dont use the temp dir for this)
        if output_texture.lower().endswith(".dds"):
            with subprocess.Popen(
                [
                    nvtt_path,
                    upscaled_texture_path,
                    "--format",
                    constants.TEXTURE_COMPRESSION_LEVELS[constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE],
                    "--output",
                    output_texture,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            ) as compress_mip_process:
                compress_mip_process.wait()
        if (
            not keep_png
            and output_texture.replace("\\", "/") != upscaled_texture_path.replace("\\", "/")
            and os.path.exists(upscaled_texture_path)
        ):
            os.remove(upscaled_texture_path)
        temp_dir.cleanup()

    @staticmethod
    @omni.usd.handle_exception
    async def async_perform_upscale(texture, output_texture, keep_png=False):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, UpscalerCore.perform_upscale, texture, output_texture, keep_png)

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
import os.path
import subprocess
import tempfile

import carb
from PIL import Image


class UpscalerCore:
    @staticmethod
    def perform_upscale(texture, output_texture, keep_png=False):
        # setup script paths'
        if os.path.exists(output_texture):
            carb.log_info("Skipping " + texture + " since " + output_texture + " already exists.")
            return
        if not output_texture.lower().endswith(".dds") and not output_texture.lower().endswith(".png"):
            carb.log_info("Output texture " + output_texture + "must be either png or dds format.")
            return
        script_path = os.path.dirname(os.path.abspath(__file__))
        nvtt_path = script_path + ".\\tools\\nvtt\\nvtt_export.exe"
        esrgan_tool_path = script_path + ".\\tools\\realesrgan-ncnn-vulkan-20210901-windows\\realesrgan-ncnn-vulkan.exe"
        # create temp dir and get texture name/path
        original_texture_name = os.path.splitext(os.path.basename(texture))[0]
        output_texture_name = os.path.splitext(os.path.basename(output_texture))[0]
        output_texture_path = os.path.dirname(os.path.abspath(output_texture))
        temp_dir = tempfile.TemporaryDirectory()
        # begin real work
        carb.log_info("Upscaling: " + texture)
        # convert to png
        if not texture.lower().endswith(".png"):
            png_texture_path = os.path.join(temp_dir.name, original_texture_name + ".png")
            convert_png_process = subprocess.Popen(
                [nvtt_path, texture, "--output", png_texture_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
            )
            convert_png_process.wait()
            # use PILLOW as a fallback if nvtt fails
            if not os.path.exists(png_texture_path):
                with contextlib.suppress(NotImplementedError):
                    with Image.open(texture) as im:
                        im.save(png_texture_path, "PNG")
        else:
            png_texture_path = texture
        # perform upscale
        os.makedirs(os.path.dirname(output_texture), exist_ok=True)
        upscaled_texture_path = os.path.join(output_texture_path, output_texture_name + ".png")
        upscale_process = subprocess.Popen(
            [esrgan_tool_path, "-i", png_texture_path, "-o", upscaled_texture_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        upscale_process.wait()
        # check for alpha channel and upscale it if it exists
        try:
            with Image.open(png_texture_path) as memory_image:
                if memory_image.mode == "RGBA":
                    alpha_path = os.path.join(temp_dir.name, original_texture_name + "_alpha.png")
                    upscaled_alpha_path = os.path.join(temp_dir.name, original_texture_name + "_upscaled4x_alpha.png")
                    memory_image.split()[-1].save(alpha_path)
                    upscale_process = subprocess.Popen(
                        [esrgan_tool_path, "-i", alpha_path, "-o", upscaled_alpha_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT,
                    )
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
            compress_mip_process = subprocess.Popen(
                [nvtt_path, upscaled_texture_path, "--format", "bc7", "--output", output_texture],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            compress_mip_process.wait()
        if not keep_png and output_texture.replace("\\", "/") != upscaled_texture_path.replace("\\", "/"):
            os.remove(upscaled_texture_path)
        temp_dir.cleanup()

    async def async_perform_upscale(texture, output_texture, keep_png=False):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, UpscalerCore.perform_upscale, texture, output_texture, keep_png)

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
from typing import TYPE_CHECKING, Callable, Union

import carb
import omni.usd
from lightspeed.common import constants
from PIL import Image

if TYPE_CHECKING:
    from lightspeed.upscale.core.items import BaseUpscaleModel


class UpscalerCore:
    @staticmethod
    def __validate_path(input_texture: Path, output_texture: Path, overwrite: bool) -> bool:
        """Make sure the provided paths are valid and cleanup output if overwriting"""

        if output_texture.exists() and not overwrite:
            carb.log_info(f"Skipping '{input_texture}' since '{output_texture}' already exists.")
            return False

        accepted_extensions = [".dds", ".png"]
        if output_texture.suffix.lower() not in accepted_extensions:
            carb.log_info(
                f"Output texture {output_texture} must be have on of the following file extensions: "
                f"{', '.join(accepted_extensions)}"
            )
            return False

        if os.path.exists(output_texture) and overwrite:
            # Cleanup the existing Output
            os.remove(output_texture)

        return True

    @staticmethod
    def __convert_input_texture_to_png(input_texture: Path, temp_path: Path):
        """Make sure the input texture is a PNG file and convert it if it's not"""
        if input_texture.suffix.lower() == ".png":
            return input_texture

        output_path = (temp_path / input_texture.stem).with_suffix(".png")
        with subprocess.Popen(
            [constants.NVTT_PATH, str(input_texture), "--output", str(output_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        ) as convert_png_process:
            convert_png_process.wait()

        # use PILLOW as a fallback if NVTT fails
        if not output_path.exists():
            with contextlib.suppress(NotImplementedError):
                with Image.open(input_texture) as img:
                    img.save(output_path, "PNG")

        return output_path

    @staticmethod
    def __convert_output_texture_to_png(output_texture: Path):
        """Make sure the output texture uses a PNG extension and its parent directory exists"""
        output_texture.parent.mkdir(parents=True, exist_ok=True)
        return Path(output_texture).with_suffix(".png")

    @staticmethod
    def __upscale_alpha_channel(
        perform_upscale: Callable[[Path, Path], None], input_texture: Path, output_texture: Path, temp_path: Path
    ):
        """Check for alpha channel and upscale it if it exists"""
        try:
            with Image.open(input_texture) as img:
                if img.mode == "RGBA":
                    alpha_path = temp_path / (input_texture.stem + "_alpha.png")
                    upscaled_alpha_path = temp_path / (input_texture.stem + "_upscaled4x_alpha.png")

                    img.split()[-1].save(alpha_path)
                    perform_upscale(alpha_path, upscaled_alpha_path)

                    with Image.open(upscaled_alpha_path).convert("L") as upscaled_alpha_img:
                        with Image.open(output_texture) as upscaled_output_img:
                            upscaled_output_img.putalpha(upscaled_alpha_img)
                            upscaled_output_img.save(output_texture, "PNG")

        except FileNotFoundError:
            carb.log_info(f"Unable to upscale texture alpha channel: {input_texture}")

    @staticmethod
    def __convert_to_dds(converted_output_texture: Path, output_texture: Path):
        """Convert to DDS, and generate mips (Note: don't use the temp dir for this)"""
        if output_texture.suffix.lower() != ".dds":
            return

        with subprocess.Popen(
            [
                constants.NVTT_PATH,
                str(converted_output_texture),
                "--output",
                str(output_texture),
                *constants.TEXTURE_INFO[constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE].to_nvtt_flag_array(),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        ) as convert_process:
            convert_process.wait()

    @staticmethod
    def __cleanup_temporary_pngs(converted_output_texture: Path, output_texture: Path, keep_png: bool):
        """Cleanup the leftover temporary PNGs"""
        if keep_png or output_texture == converted_output_texture or not converted_output_texture.exists():
            return

        os.remove(converted_output_texture)

    @staticmethod
    def perform_upscale(
        upscale_model: "BaseUpscaleModel",
        input_texture: Union[Path, str],
        output_texture: Union[Path, str],
        keep_png: bool = False,
        overwrite: bool = False,
    ):
        carb.log_info(f"Upscaling using {upscale_model.name}: {input_texture}")

        # Make sure paths are of type Pathlib.Path
        input_texture = Path(input_texture)
        output_texture = Path(output_texture)

        if not UpscalerCore.__validate_path(input_texture, output_texture, overwrite):
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            converted_input_texture = UpscalerCore.__convert_input_texture_to_png(input_texture, temp_path)
            converted_output_texture = UpscalerCore.__convert_output_texture_to_png(output_texture)

            upscale_model.perform(converted_input_texture, converted_output_texture)

            UpscalerCore.__upscale_alpha_channel(
                upscale_model.perform, converted_input_texture, converted_output_texture, temp_path
            )
            UpscalerCore.__convert_to_dds(converted_output_texture, output_texture)
            UpscalerCore.__cleanup_temporary_pngs(converted_output_texture, output_texture, keep_png)

    @staticmethod
    @omni.usd.handle_exception
    async def async_perform_upscale(
        upscale_model: "BaseUpscaleModel",
        input_texture: Union[Path, str],
        output_texture: Union[Path, str],
        keep_png: bool = False,
        overwrite: bool = False,
    ):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, UpscalerCore.perform_upscale, upscale_model, input_texture, output_texture, keep_png, overwrite
        )

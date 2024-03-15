"""
* Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb.tokens
import omni.kit.app
import traceback
import carb
import os
from pathlib import Path


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def go():
    """
    This function will grab the Lightspeed Mass Ingestion shortcut and format it to link the Flux Mass Core CLI
    """
    try:
        ext_id = omni.kit.app.get_app().get_extension_manager().get_enabled_extension_id("omni.flux.validator.mass.core")
        ext_root = Path(omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id))
        shell_ext = carb.tokens.get_tokens_interface().resolve("${shell_ext}")
        apps = Path(carb.tokens.get_tokens_interface().resolve("${app}"))
        file_name = f"lightspeed.app.trex.ingestcraft.cli{shell_ext}"
        file_path = apps.parent.joinpath(file_name)
        relative_path_cli = os.path.relpath(ext_root, file_path.parent)
        relative_path_experience = os.path.relpath(apps.joinpath("lightspeed.app.trex.validation_cli.kit"), file_path.parent)
        if not file_path.exists():
            raise FileNotFoundError(f"Could not find {file_name} to generate the Mass Ingestion CLI")
        with open(file_path, "r", encoding="utf8") as inp:
            new_file_lines = []
            for line in inp:
                line = line.format_map(
                    _SafeDict(
                        omni_flux_validator_mass_core=relative_path_cli,
                        experience=relative_path_experience
                    )
                )
                new_file_lines.append(line)

        with open(file_path, "w", encoding="utf8") as outfile:
            outfile.writelines(new_file_lines)
    except Exception:
        carb.log_error(f"Traceback:\n{traceback.format_exc()}")
        omni.kit.app.get_app().post_quit(1)


if __name__ == "__main__":
    go()

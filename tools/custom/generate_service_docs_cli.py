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
import carb.tokens
import omni.kit.app
import traceback
import carb
import os
import stat
from pathlib import Path


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def go():
    """
    This function will grab the Lightspeed Mass Ingestion shortcut and format it to link the Flux Mass Core CLI
    """
    try:
        ext_id = omni.kit.app.get_app().get_extension_manager().get_enabled_extension_id("omni.flux.service.documentation")
        ext_root = Path(omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id))
        shell_ext = carb.tokens.get_tokens_interface().resolve("${shell_ext}")
        apps = Path(carb.tokens.get_tokens_interface().resolve("${app}"))
        file_name = f"omni.flux.app.service.documentation.cli{shell_ext}"
        file_path = apps.parent.joinpath(file_name)
        relative_path_cli = os.path.relpath(ext_root, file_path.parent)
        if not file_path.exists():
            raise FileNotFoundError(f"Could not find {file_name} to generate the Service Documentation Generation CLI")

        with open(file_path, "r", encoding="utf8") as inp:
            new_file_lines = []
            for line in inp:
                line = line.format_map(
                    _SafeDict(
                        omni_flux_service_documentation=relative_path_cli
                    )
                )
                new_file_lines.append(line)

        with open(file_path, "w", encoding="utf8") as outfile:
            outfile.writelines(new_file_lines)

        st = os.stat(file_path)
        os.chmod(file_path, st.st_mode | stat.S_IEXEC)
    except Exception:
        carb.log_error(f"Traceback:\n{traceback.format_exc()}")
        omni.kit.app.get_app().post_quit(1)


if __name__ == "__main__":
    go()

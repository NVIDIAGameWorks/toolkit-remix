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
import argparse
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


def go(ext_name: str, app_name: str):
    """
    This function will grab the Stage Manager shortcut and format it to link the Stage Manager Core CLI
    """
    try:
        ext_id = omni.kit.app.get_app().get_extension_manager().get_enabled_extension_id(ext_name)
        if ext_id is None:
            raise RuntimeError(f"Could not find the extension: {ext_name}")

        ext_root = Path(omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id))
        apps = Path(carb.tokens.get_tokens_interface().resolve("${app}"))

        shell_ext = carb.tokens.get_tokens_interface().resolve("${shell_ext}")
        file_name = Path(app_name)
        if file_name.suffix.lower() in [".bat", ".sh"]:
            # Make sure the app has the right extension
            file_name = file_name.with_suffix(shell_ext)
        else:
            # Add the right extension
            file_name = f"{file_name}{shell_ext}"

        file_path = apps.parent.joinpath(file_name)
        if not file_path.exists():
            raise FileNotFoundError(f"Could not find the file: {file_name}")

        relative_path_cli = os.path.relpath(ext_root, file_path.parent)

        with open(file_path, "r", encoding="utf8") as inp:
            new_file_lines = []
            for line in inp:
                line = line.format_map(
                    _SafeDict(
                        extension_path=relative_path_cli,
                    )
                )
                new_file_lines.append(line)

        with open(file_path, "w", encoding="utf8") as outfile:
            outfile.writelines(new_file_lines)

        st = os.stat(file_path)
        os.chmod(file_path, st.st_mode | stat.S_IEXEC)
    except Exception:  # noqa
        carb.log_error(f"Traceback:\n{traceback.format_exc()}")
        omni.kit.app.get_app().post_quit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Application Generator Script",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-id", "--extension-id", type=str, help="The ID for the extension to generate the application for", required=True)
    parser.add_argument("-n", "--app-name", type=str, help="The name of the app to generate", required=True)

    args = parser.parse_args()

    go(args.extension_id, args.app_name)

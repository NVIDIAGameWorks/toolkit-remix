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
import pathlib
import platform
import subprocess


def main():
    example = r"""
    Example:

        cli.bat -s my_schema.json \
        -e \
        omni.flux.stage_manager.plugin.column \
        omni.flux.stage_manager.plugin.context.usd \
        omni.flux.stage_manager.plugin.filter.usd \
        omni.flux.stage_manager.plugin.interaction.usd \
        omni.flux.stage_manager.plugin.widget.usd
    """  # noqa

    parser = argparse.ArgumentParser(
        description="Run the stage manager in a standalone app.",
        epilog=example,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-s", "--schema", type=str, help="Your schema file (.json)", required=True)
    parser.add_argument(
        "-e",
        "--enable",
        help="Name(s) of the Kit extension(s) plugin we want to use",
        nargs="+",
        type=str,
        required=True,
    )
    parser.add_argument(
        "-x", "--extra-args", help="Any extra arguments to pass to Kit", action="append", type=str, required=False
    )
    args = parser.parse_args()

    root_dir = pathlib.Path(__file__).parent.parent.parent.parent

    cmd = [
        str(root_dir.joinpath("kit", "kit.exe" if platform.system() == "Windows" else "kit")),
        str(pathlib.Path(__file__).parent.parent.joinpath("apps", "omni.flux.app.stage_manager.kit")),
    ]
    for ext in args.enable:
        cmd.extend(["--enable", ext])

    for arg in args.extra_args or []:
        cmd.extend([arg])

    exec_cmd = f"{pathlib.Path(__file__).parent.parent.joinpath('omni', 'flux', 'stage_manager', 'core', 'cli.py')}"  # noqa E501
    exec_cmd += f" -s {args.schema}"
    cmd.extend(["--exec", exec_cmd])

    print(" ".join(cmd))
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end="")  # process line here

    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args)


if __name__ == "__main__":
    main()

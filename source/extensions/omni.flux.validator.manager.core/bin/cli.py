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
    example = """
    Example:

        cli.bat -s my_schema.json -e omni.flux.validator.plugin.check.usd omni.flux.validator.plugin.context.usd_stage omni.flux.validator.plugin.selector.usd -p
    """  # noqa

    parser = argparse.ArgumentParser(
        description="Run the validation in command line.", epilog=example, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-s", "--schema", type=str, help="Your schema file (.json)", required=True)
    parser.add_argument("-q", "--queue-id", type=str, help="Queue ID to update", required=False)
    parser.add_argument(
        "-p", "--print-result", help="Print the result in the stdout", default=False, action="store_true"
    )
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
        str(pathlib.Path(__file__).parent.parent.joinpath("apps", "omni.flux.app.validator_cli.kit")),
    ]
    for ext in args.enable:
        cmd.extend(["--enable", ext])

    for arg in args.extra_args:
        cmd.extend([arg])

    cmd.append("--no-window")
    exec_cmd = f"{pathlib.Path(__file__).parent.parent.joinpath('omni', 'flux', 'validator', 'manager', 'core', 'cli.py')}"  # noqa E501
    exec_cmd += f" -s {args.schema}"
    if args.print_result:
        exec_cmd += " -p"
    if args.queue_id:
        exec_cmd += f" -q {args.queue_id}"
    cmd.extend(["--exec", exec_cmd])

    print(" ".join(cmd))
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end="")  # process line here

    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args)


if __name__ == "__main__":
    main()

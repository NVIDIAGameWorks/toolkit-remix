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

        cli.bat -s my_schema1.json -s my_schema2.json -e omni.flux.validator.plugin.check.usd omni.flux.validator.plugin.context.usd_stage omni.flux.validator.plugin.selector.usd -p -x--merge-config="file.kit"
    """  # noqa

    parser = argparse.ArgumentParser(
        description="Run the validation in command line.", epilog=example, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-s", "--schema", type=str, help="Your schema file (.json)", required=True, action="append")
    parser.add_argument(
        "-k", "--kit-exe", type=str, help="If you want to use a specific Kit executable", required=False
    )
    parser.add_argument(
        "-p", "--print-result", help="Print the result in the stdout", default=False, action="store_true"
    )
    parser.add_argument(
        "-ex", "--executor", help="Executor to use: 0=async, 1=process", nargs="?", const=1, type=int, default=0
    )
    parser.add_argument(
        "-t", "--timeout", help="Timeout for the validation. Default 600sc.", nargs="?", const=1, type=int
    )
    parser.add_argument("-si", "--silent", help="Silent the stdout", default=False, action="store_true")
    parser.add_argument(
        "-e",
        "--enable",
        help="Name(s) of the Kit extension(s) plugin we want to use",
        nargs="+",
        type=str,
    )
    parser.add_argument(
        "-x", "--extra-args", help="Any extra arguments to pass to Kit", action="append", type=str, required=False
    )
    args = parser.parse_args()

    if args.kit_exe:
        kit_exe = args.kit_exe
    else:
        root_dir = pathlib.Path(__file__).parent.parent.parent.parent
        kit_exe = str(root_dir.joinpath("kit", "kit.exe" if platform.system() == "Windows" else "kit"))

    cmd = [
        kit_exe,
        str(pathlib.Path(__file__).parent.parent.joinpath("apps", "omni.flux.app.validator.mass_cli.kit")),
    ]
    for ext in args.enable or []:
        cmd.extend(["--enable", ext])
    for arg in args.extra_args or []:
        cmd.extend([arg])

    # Every args between "--start-future-args-remove" and "--end-future-args-remove" will be deleted if the CLI
    # run another process from the CLI (see process_executor.py)
    cmd.append("--start-future-args-remove")
    cmd.append("--no-window")

    exec_cmd = f"{pathlib.Path(__file__).parent.parent.joinpath('omni', 'flux', 'validator', 'mass', 'core', 'cli.py')}"  # noqa E501
    for schema in args.schema:
        exec_cmd += f" -s {schema}"
    if args.print_result:
        exec_cmd += " -p"
    if args.silent:
        exec_cmd += " -si"
    if args.executor:
        exec_cmd += f" --executor {args.executor}"
    if args.timeout is not None:
        exec_cmd += f" --timeout {args.timeout}"

    cmd.extend(["--exec", f'"{exec_cmd}"'])

    cmd.append("--end-future-args-remove")

    print(" ".join(cmd))

    with subprocess.Popen(" ".join(cmd), stdout=subprocess.PIPE, shell=True, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end="")  # process line here

    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args)


if __name__ == "__main__":
    main()

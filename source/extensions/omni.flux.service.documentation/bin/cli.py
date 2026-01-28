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

        cli.bat -o "{kit}\..\..\..\docs\flux\latest\service-documentation.html" -e omni.flux.service.factory
    """  # noqa

    parser = argparse.ArgumentParser(
        description="Run the service documentation generation in command line.",
        epilog=example,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-o", "--output", type=str, help="The output HTML file path", required=True)
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

    if pathlib.Path(args.output).suffix.lower() != ".html":
        raise ValueError("The output file must be an HTML file. (.html)")

    root_dir = pathlib.Path(__file__).parent.parent.parent.parent

    cmd = [
        str(root_dir.joinpath("kit", "kit.exe" if platform.system() == "Windows" else "kit")),
        str(pathlib.Path(__file__).parent.parent.joinpath("apps", "omni.flux.app.service.documentation_cli.kit")),
    ]
    for ext in args.enable:
        cmd.extend(["--enable", ext])

    for arg in args.extra_args or []:
        cmd.extend([arg])

    cmd.append("--no-window")
    exec_cmd = f"{pathlib.Path(__file__).parent.parent.joinpath('omni', 'flux', 'service', 'documentation', 'cli.py')}"
    exec_cmd += f' -o "{args.output}"'
    cmd.extend(["--exec", exec_cmd])

    print(" ".join(cmd))
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end="")  # process line here

    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args)


if __name__ == "__main__":
    main()

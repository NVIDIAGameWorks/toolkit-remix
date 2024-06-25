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

import re


def delete_change_log_text(file_name, start_line, end_line):
    """
    Delete the changelog from the specific header
    """
    with open(file_name, "r", encoding="utf8") as f:
        txts = f.readlines()

    result = []
    started = False
    for txt in txts:
        if started and re.match(end_line, txt):
            started = False
        if started:
            continue
        if re.match(start_line, txt):
            started = True
            continue
        result.append(txt)

    with open(file_name, "w", encoding="utf8") as f:
        f.writelines(result)


def setup_repo_tool(parser, config):
    parser.prog = "delete_changelog"
    parser.description = "Remove lines from the CHANGELOG"
    parser.add_argument(
        "-f",
        "--file-name",
        dest="file_name",
        required=False,
        help=(
            "The file name to process. This flag override the one from the config file."
        )
    )
    parser.add_argument(
        "-s",
        "--start-line",
        dest="start_line",
        required=False,
        help="Regex of the starting line you want to use. This flag override the one from the config file.",
    )
    parser.add_argument(
        "-e",
        "--end-line",
        dest="end_line",
        required=False,
        help=(
            "Regex of the ending line you want to use. Ending line will not be included. This flag override the one "
            "from the config file."
        )
    )

    def run_repo_tool(options, config):
        settings = config["repo_delete_changelog"]
        file_name = options.file_name if options.file_name else settings["file_name"]
        start_line = options.start_line if options.start_line else settings["start_line"]
        end_line = options.end_line if options.end_line else settings["end_line"]

        delete_change_log_text(file_name, start_line, end_line)
        print("Success!")

    return run_repo_tool

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

import sys
from pathlib import Path


def setup_repo_tool(parser, config):
    parser.prog = "check_forbidden_words"
    parser.description = (
        "Check that a word is not present in the file(s). Can be useful to check if a dep that should not be used was "
        "used."
    )

    def _multi_glob(start_path, paths):
        """Combine the results of multiple globs into a single list of Paths"""
        if not isinstance(paths, (list, tuple)):
            paths = [paths]
        retval = []
        for path in paths:
            retval += [pth for pth in start_path.glob(path)]
        return retval

    def run_repo_tool(options, config):
        settings = config.get("repo_check_forbidden_words", {})
        file_settings = settings.get("files")
        word_settings = settings.get("words")
        include_files = file_settings.get("include", [])
        forbidden_words = word_settings.get("exclude", [])
        start_path = Path(".")
        all_files = _multi_glob(start_path, include_files)

        bad_files = []
        to_print = ""

        for all_file in all_files:
            with open(all_file, "r", encoding="utf8") as _file:
                for i, line in enumerate(_file.readlines()):
                    for forbidden_word in forbidden_words:
                        if forbidden_word in line:
                            to_print += (
                                f"File \"file:///{Path(all_file).absolute().as_posix()}\", line {i+1} contains "
                                f"forbidden word: {forbidden_word}. Please remove it.\n"
                            )
                            bad_files.append(all_file)

        if bad_files:
            sys.exit(to_print)

    return run_repo_tool

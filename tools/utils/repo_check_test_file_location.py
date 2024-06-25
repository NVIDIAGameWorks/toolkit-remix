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
    parser.prog = "check_test_file_location"
    parser.description = "Verify all `test_*.py` files are in directories specified in the config's `required_paths`"

    def _multi_glob(start_path, paths):
        """Combine the results of multiple globs into a single list of Paths"""
        if not isinstance(paths, (list, tuple)):
            paths = [paths]
        retval = []
        for path in paths:
            retval += [pth for pth in start_path.glob(path)]
        return retval

    def run_repo_tool(options, config):
        settings = config.get("repo_check_test_file_location", {})
        file_settings = settings.get("files")
        rule_settings = settings.get("rule")
        include_dirs = file_settings.get("include", ["**/source/**/tests/*.py"])
        exclude_dirs = file_settings.get("exclude", ["**/lightspeed.common/lightspeed/common/tools/**/*"])
        allowed_paths = rule_settings.get("allow_paths", ["**/source/**/tests/__init__.py"])
        start_path = Path(".")
        all_files = _multi_glob(start_path, include_dirs)
        excluded_files = _multi_glob(start_path, exclude_dirs)
        allowed_files = _multi_glob(start_path, allowed_paths)

        # First remove all excluded files
        non_excluded = [pth for pth in all_files if pth not in excluded_files]
        bad_locations = [pth for pth in non_excluded if pth not in allowed_files]
        if bad_locations:
            msg = "\n".join([loc.as_posix() for loc in bad_locations])
            sys.exit(f"Test files must be in the directories specified in `rule.allow_paths`. Found:\n{msg}")

    return run_repo_tool

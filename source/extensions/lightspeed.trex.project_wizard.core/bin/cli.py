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
import asyncio

import omni.kit.app
from lightspeed.trex.project_wizard.core import ProjectWizardCore
from omni.flux.utils.common.path_utils import read_json_file


def main():
    example = """
    Example:

        cli.bat -s my_schema.json
    """
    parser = argparse.ArgumentParser(
        description="Remix project wizard CLI tool.",
        epilog=example,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-s", "--schema", type=str, help="Your schema file (.json)", required=True)
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="The tool will perform a dry run (log operations only).",
    )
    parsed_args = parser.parse_args()
    asyncio.ensure_future(run(parsed_args))


def print_message(message: str, category: str = "INFO"):
    print(f"[{category}] {message}")


async def run(parsed_args):
    exit_code = 1
    try:
        core = ProjectWizardCore()

        _log_sub = core.subscribe_log_info(lambda v: print_message(v))
        _progress_sub = core.subscribe_run_progress(lambda v: print_message(f"Progress: {v}%"))
        _completed_sub = core.subscribe_run_finished(
            lambda v, *_: print_message(f"Project Setup Finished: {'Success' if v else 'Failed'}")
        )

        success = await core.setup_project(read_json_file(parsed_args.schema), parsed_args.dry_run)
        if success:
            exit_code = 0
    finally:
        omni.kit.app.get_app().post_quit(exit_code)


if __name__ == "__main__":
    main()

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
import omni.usd
from lightspeed.trex.packaging.core import PackagingCore
from omni.flux.utils.common.path_utils import read_json_file


def main():
    example = """
    Example:

        cli.bat -s my_schema.json
    """
    parser = argparse.ArgumentParser(
        description="Remix Project Packaging CLI tool.",
        epilog=example,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-s", "--schema", type=str, help="Your schema file (.json)", required=True)
    parsed_args = parser.parse_args()
    asyncio.ensure_future(run(parsed_args))


@omni.usd.handle_exception
async def run(parsed_args):
    exit_code = 1
    try:
        core = PackagingCore()

        def print_completed(errors, failed_assets, cancelled):
            message = "Project Packaging Finished:\n"
            if errors or failed_assets:
                if errors:
                    message += f"Errors occurred: {errors}\n"
                if failed_assets:
                    message += f"Failed to collect assets: {failed_assets}\n"
            else:
                message += "Packaging was cancelled." if cancelled else "The project was successfully packaged."

        _progress_sub = core.subscribe_packaging_progress(  # noqa F841
            lambda c, t, s: print(f"Progress: {s} ({c} / {t})")
        )
        _completed_sub = core.subscribe_packaging_completed(print_completed)  # noqa F841

        success = await core.package(read_json_file(parsed_args.schema))
        if success:
            exit_code = 0
    finally:
        omni.kit.app.get_app().post_quit(exit_code)


if __name__ == "__main__":
    main()

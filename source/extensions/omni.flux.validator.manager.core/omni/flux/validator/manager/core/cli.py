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

import omni.client
import omni.kit.app
import omni.usd
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore


def main():
    example = """
    Example:

        cli.bat -s my_schema.json -p omni.flux.validator.plugin.check.usd omni.flux.validator.plugin.context.usd_stage
    """

    parser = argparse.ArgumentParser(
        description="Run the validation in command line.", epilog=example, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-s", "--schema", type=str, help="Your schema file (.json)", required=True)
    parser.add_argument("-q", "--queue-id", type=str, help="Queue ID to update", required=False)
    parser.add_argument(
        "-p", "--print-result", help="Print the result in the stdout", default=False, action="store_true"
    )
    args = parser.parse_args()

    result, entry = omni.client.stat(args.schema)
    if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
        raise ValueError(f"Can't read the schema file {args.schema}")

    asyncio.ensure_future(run(args.schema, args.print_result, args.queue_id))


@omni.usd.handle_exception
async def run(json_path: str, print_result: bool, queue_id: str | None):
    exit_code = 1
    try:
        data = _path_utils.read_json_file(json_path)
        core = _ManagerCore(data)
        await core.deferred_run(print_result=print_result, queue_id=queue_id)
        exit_code = 0
    finally:
        omni.kit.app.get_app().post_quit(exit_code)


if __name__ == "__main__":
    main()

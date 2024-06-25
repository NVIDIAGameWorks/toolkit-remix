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
from omni.flux.asset_importer.core import AssetItemImporterModel, ImporterCore


def main():
    example = """
    Example:

        cli.py -c config.json -d default/output/folder/
    """
    parser = argparse.ArgumentParser(
        description="Batch convert assets to usd.", epilog=example, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-c", "--config", type=str, help="Your config file (.json)", required=True)
    parser.add_argument("-d", "--default-output", help="A default folder to output results to.", default=None)
    parser.add_argument(
        "-pk", "--print-keys", help="Print all of the valid fields that can be put into the json.", default=None
    )
    try:
        parsed_args = parser.parse_args()
    except SystemExit as e:
        omni.kit.app.get_app().post_quit(e.code)
        return

    if parsed_args.print_keys:
        print(f"Valid keys for asset import: {AssetItemImporterModel.__fields__.keys()}")
    asyncio.ensure_future(run(parsed_args))


def sub_progress_count_fn(value):
    print(f"Progress: {value}%")


async def run(parsed_args):
    exit_code = 1
    try:
        importer = ImporterCore()
        _sub = importer.subscribe_batch_progress(sub_progress_count_fn)  # noqa
        success = await importer.import_batch_async(parsed_args.config, parsed_args.default_output)
        if success:
            exit_code = 0
    finally:
        omni.kit.app.get_app().post_quit(exit_code)


if __name__ == "__main__":
    main()

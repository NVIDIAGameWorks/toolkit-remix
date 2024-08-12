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

import carb
import omni.kit.app
from omni.flux.stage_manager.core import StageManagerCore as _StageManagerCore
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.common.path_utils import read_json_file as _read_json_file


def main():
    example = """
    Example:

        cli.py -s my_schema.json
    """

    parser = argparse.ArgumentParser(
        description="Run the stage manager in a standalone app.",
        epilog=example,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-s", "--schema", type=str, help="Your schema file (.json)", required=True)
    args = parser.parse_args()

    schema_url = _OmniUrl(carb.tokens.get_tokens_interface().resolve(args.schema))
    if not schema_url.is_file:
        raise ValueError(f"Can't read the schema file: {schema_url}")

    asyncio.ensure_future(run(schema_url))


async def run(schema_url: _OmniUrl):
    exit_code = 1
    try:
        schema = _read_json_file(str(schema_url))

        core = _StageManagerCore()
        core.test(schema)
        exit_code = 0
    finally:
        omni.kit.app.get_app().post_quit(exit_code)


if __name__ == "__main__":
    main()

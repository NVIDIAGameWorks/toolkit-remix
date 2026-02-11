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
import os
import pathlib
import traceback

import carb
import omni.client
import omni.kit.app
from omni.flux.utils.common.path_utils import write_file as _write_file
from omni.flux.validator.manager.core import validation_schema_json_encoder as _validation_schema_json_encoder
from omni.flux.validator.mass.core import ManagerMassCore as _ManagerMassCore
from pydantic import ValidationError


def main():
    example = """
    Example:

        cli.bat -s my_schema1.json -s my_schema2.json -p --enable omni.flux.validator.plugin.check.usd
            --enable omni.flux.validator.plugin.context.usd_stage
    """

    parser = argparse.ArgumentParser(
        description="Run the validation in command line.", epilog=example, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-s", "--schema", type=str, help="Your schema file (.json)", required=True, action="append")
    parser.add_argument(
        "-ex", "--executor", help="Executor to use: 0=async, 1=process", nargs="?", const=1, type=int, default=0
    )
    parser.add_argument(
        "-p", "--print-result", help="Print the result in the stdout", default=False, action="store_true"
    )
    parser.add_argument(
        "-t", "--timeout", help="Timeout for the validation. Default 600sc.", nargs="?", const=1, type=int
    )
    parser.add_argument("-si", "--silent", help="Silent the stdout", default=False, action="store_true")
    parser.add_argument("-sfar", "--start-future-args-remove", help=argparse.SUPPRESS)
    parser.add_argument("-efar", "--end-future-args-remove", help=argparse.SUPPRESS)
    args = parser.parse_args()

    for schema in args.schema:
        result, entry = omni.client.stat(schema)
        if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
            raise ValueError(f"Can't read the schema file {schema}")

    asyncio.ensure_future(
        run(
            args.schema,
            args.executor,
            args.print_result,
            args.silent,
            args.timeout,
        )
    )


async def run(
    json_paths: list[str],
    executor: int,
    print_result: bool,
    silent: bool,
    timeout: int | None = None,
):
    exit_code = 0

    def _on_run_finished(validation_core, i_progress, size_progress, _result, message: str | None = None):
        print(f"Progress {i_progress + 1}/{size_progress}")
        if not _result:
            nonlocal exit_code
            exit_code = 1
            current_dir = os.getcwd()
            json_path = str(pathlib.Path(current_dir).joinpath(f"{validation_core.model.name}_failed_schema.json"))
            _write_file(
                json_path,
                validation_core.model.json(indent=4, encoder=_validation_schema_json_encoder).encode("utf-8"),
                raise_if_error=False,
            )
            message_path = str(pathlib.Path(current_dir).joinpath(f"{validation_core.model.name}_failed_message.txt"))
            _write_file(message_path, message.encode("utf-8"), raise_if_error=False)

    message = "Some inputs are not valid. Please delete/fix them before continuing"
    sub_run_finisheds = []
    try:
        core = _ManagerMassCore(standalone=True, schema_paths=json_paths)
        sub_run_finisheds.append(core.subscribe_run_finished(_on_run_finished))
        items = core.schema_model.get_item_children(None)
        size_items = len(items)
        for i, item in enumerate(items):
            if not all(item.model.is_ready_to_run().values()):
                carb.log_error(message)
                return
            try:
                result = await item.cook_template_no_exception()
            except ValidationError as e:
                carb.log_error("Exception when async cook_template_no_exception()")
                carb.log_error(f"{e}")
                carb.log_error(f"{traceback.format_exc()}")
                carb.log_error(message)
                return
            await core.create_tasks(
                executor,
                result,
                print_result=print_result,
                silent=silent,
                timeout=timeout,
                standalone=True,
            )
            print(f"Global progress {i + 1}/{size_items}")
    finally:
        omni.kit.app.get_app().post_quit(exit_code)


if __name__ == "__main__":
    main()

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
import json
import platform
import subprocess
import sys
import tempfile
from enum import Enum
from pathlib import Path

try:
    from .constants import USD_FILE_SUFFIXES, USD_FILE_SUFFIXES_DISPLAY
    from .usdlux_light_inputs import iter_usd_files, migrate_usdlux_light_inputs_paths
except ImportError:
    from constants import USD_FILE_SUFFIXES, USD_FILE_SUFFIXES_DISPLAY
    from usdlux_light_inputs import iter_usd_files, migrate_usdlux_light_inputs_paths


class Migrations(Enum):
    DistantLightsZDirection = "distant-lights-z-direction"
    UsdLuxLightInputs = "usdlux-light-inputs"


RECURSIVE_HELP = "Recursively search for USD files in the given directory. Will be ignored if `--file` is given."


def setup_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run various compatibility migrations in a command line tool.")

    subparsers = parser.add_subparsers(dest="migrations", help="Available migrations")
    subparsers.required = True

    lights_parser = subparsers.add_parser(
        Migrations.DistantLightsZDirection.value,
        description=(
            "Migrate distant lights pointing in the wrong direction (Z towards the sun) to point in the correct "
            "direction (Z away from the sun)."
        ),
    )

    __add_target_args(
        lights_parser,
        "Path to the USD file to migrate to the updated standard",
        "Path to the directory of USD files to migrate to the updated standard",
    )

    lights_parser.add_argument(
        "--force",
        "-F",
        action="store_true",
        help="Force execute the migration, regardless of if it was already executed or not.",
    )

    usdlux_inputs_parser = subparsers.add_parser(
        Migrations.UsdLuxLightInputs.value,
        description="Migrate legacy UsdLux light attributes to the USD 25.11 `inputs:` attribute names.",
    )
    __add_target_args(
        usdlux_inputs_parser,
        "Path to the USD file to migrate to the updated UsdLux standard",
        "Path to the directory of USD files to migrate to the updated UsdLux standard",
    )

    return parser.parse_args()


def __add_target_args(parser: argparse.ArgumentParser, file_help: str, directory_help: str):
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--file", "-f", type=Path, help=file_help)
    input_group.add_argument("--directory", "-d", type=Path, help=directory_help)
    parser.add_argument("--recursive", "-r", action="store_true", help=RECURSIVE_HELP)


def validate_args(args: argparse.Namespace):
    if args.file:
        if args.recursive:
            print("Warning: --recursive flag is ignored when processing a file")
        file = Path(args.file)
        if not file.exists() or not file.is_file():
            raise FileNotFoundError("The selected file does not exist.")
        if file.suffix.lower() not in USD_FILE_SUFFIXES:
            raise ValueError(f"The selected file is not a USD file. Valid file types are: {USD_FILE_SUFFIXES_DISPLAY}")
    elif args.directory:
        directory = Path(args.directory)
        if not directory.exists() or not directory.is_dir():
            raise FileNotFoundError("The selected directory does not exist.")


def execute(args: argparse.Namespace):
    match args.migrations:
        case Migrations.DistantLightsZDirection.value:
            __run_distant_lights_migrations(args)
        case Migrations.UsdLuxLightInputs.value:
            __run_usdlux_light_inputs_migration(args)
        case _:
            return


def __run_distant_lights_migrations(args: argparse.Namespace):
    __confirm_migration(args)

    schema_path = "./distant_lights_migration_file.json" if args.file else "./distant_lights_migration_directory.json"
    schema_path = (Path(__file__).parent / schema_path).resolve()

    with open(schema_path) as schema_file:
        schema = json.load(schema_file)

    if args.file:
        schema["context_plugin"]["data"]["file"] = str(args.file)
        schema["context_plugin"]["data"]["skip_validated_files"] = not args.force
    else:
        schema["context_plugin"]["data"]["directory"] = str(args.directory)
        schema["context_plugin"]["data"]["recursive"] = args.recursive
        schema["context_plugin"]["data"]["skip_validated_files"] = not args.force

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as schema_file:
        json.dump(schema, schema_file, indent=4)
        schema_file_path = schema_file.name

    try:
        extension = ".bat" if platform.system().lower() == "windows" else ".sh"
        exec_path = str(Path(__file__).parent.parent.parent / "lightspeed.app.trex.ingestcraft.cli") + extension

        cmd = [exec_path, "--schema", schema_file_path]
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
            for line in process.stdout:
                print(line.decode(errors="replace"), end="")
    finally:
        Path(schema_file_path).unlink(missing_ok=True)


def __run_usdlux_light_inputs_migration(args: argparse.Namespace):
    __confirm_migration(args)

    paths = [args.file] if args.file else iter_usd_files(args.directory, args.recursive)
    if not paths:
        print("No USD files were found.")
        return

    for result in migrate_usdlux_light_inputs_paths(paths):
        if result.changed:
            status = "MIGRATED"
        elif result.skipped:
            status = "SKIPPED"
        else:
            status = "UNCHANGED"
        print(f"[{status}] {result.path}: {result.message}")


def __confirm_migration(args: argparse.Namespace):
    if args.file:
        target_files = f"the following USD file: {args.file}"
        additional_info = ["If you wish to process the entire directory instead, use the `--directory` (or `-d`) flag"]
    elif args.recursive:
        target_files = (
            f"all the USD files in the following directory and in all the included sub-directories: {args.directory}"
        )
        additional_info = [
            "If you wish to process a single file instead, use the `--file` (or `-f`) flag",
            "If you wish to process the files immediately in the directory instead, remove the `--recursive` (or `-r`) flag",
        ]
    else:
        target_files = f"all the USD files immediately in the following directory only: {args.directory}"
        additional_info = [
            "If you wish to process a single file instead, use the `--file` (or `-f`) flag",
            "If you wish to process all the files in the directory as well as all the included sub-directories, add the `--recursive` (or `-r`) flag",
        ]

    continue_token = "continue"
    quit_token = "q"
    separator_length = 96

    print("*" * separator_length)
    print(
        f"You are about to process {target_files}.",
        "",
        "This migration updates files in place. Save your project first or run it on a copy.",
        "",
        *additional_info,
        "",
        f'If you wish to proceed, please input "{continue_token}".',
        f'If you wish to quit, please input "{quit_token}"',
        "",
        sep="\n",
    )
    val = ""
    while val.lower() not in [continue_token, quit_token]:
        val = input()
        if val.lower() not in [continue_token, quit_token]:
            print(f'Invalid value entered. Please input "{continue_token}" to continue or "{quit_token}" to quit.')
    if val.lower() != continue_token:
        print("\nAborting the process")
        sys.exit(0)
    print("\nExecuting the migration")
    print("*" * separator_length)


if __name__ == "__main__":
    _args = setup_cli()
    validate_args(_args)
    execute(_args)

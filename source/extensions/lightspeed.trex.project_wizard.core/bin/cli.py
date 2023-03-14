"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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

        _log_sub = core.subscribe_log_info(lambda v: print_message(v))  # noqa F841
        _progress_sub = core.subscribe_run_progress(lambda v: print_message(f"Progress: {v}%"))  # noqa F841
        _completed_sub = core.subscribe_run_finished(  # noqa F841
            lambda v, *_: print_message(f"Project Setup Finished: {'Success' if v else 'Failed'}")
        )

        success = await core.setup_project(read_json_file(parsed_args.schema), parsed_args.dry_run)
        if success:
            exit_code = 0
    finally:
        omni.kit.app.get_app().post_quit(exit_code)


if __name__ == "__main__":
    main()

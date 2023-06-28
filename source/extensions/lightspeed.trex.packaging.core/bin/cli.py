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

        _progress_sub = core.subscribe_packaging_progress(  # noqa F841
            lambda c, t, s: print(f"Progress: {s} ({c} / {t})")
        )
        _completed_sub = core.subscribe_packaging_completed(  # noqa F841
            lambda e, c: print(
                f"Project Packaging Finished: {f'Errors occurred: {e}' if e else 'Cancelled' if c else 'Success'}"
            )
        )

        success = await core.package(read_json_file(parsed_args.schema))
        if success:
            exit_code = 0
    finally:
        omni.kit.app.get_app().post_quit(exit_code)


if __name__ == "__main__":
    main()

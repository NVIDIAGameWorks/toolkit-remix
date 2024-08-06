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
import json
from pathlib import Path

import carb
import omni.kit.app
import omni.usd
from omni.services.core import main as main_service


def main():
    example = r"""
    Example:

        cli.bat -o "{kit}\..\..\..\docs\flux\latest\service-documentation.html"
    """

    parser = argparse.ArgumentParser(
        description="Run the service documentation generation in command line.",
        epilog=example,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-o", "--output", type=str, help="The output HTML file path", required=True)
    args = parser.parse_args()

    asyncio.ensure_future(run(args.output))


@omni.usd.handle_exception
async def run(output: str):
    exit_code = 1
    try:
        html_template = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta http-equiv="content-type" content="text/html; charset=UTF-8">
                <title>RTX Remix REST API Documentation</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
                <style>
                    body {
                        margin: 0;
                        padding: 0;
                    }
                </style>
                <style data-styled="" data-styled-version="4.4.1"></style>
            </head>
            <body>
                <div id="redoc-container"></div>
                <script src="https://cdn.jsdelivr.net/npm/redoc/bundles/redoc.standalone.js"> </script>
                <script>
                    var spec = %s;
                    Redoc.init(spec, {}, document.getElementById("redoc-container"));
                </script>
            </body>
            </html>
        """

        output = Path(carb.tokens.get_tokens_interface().resolve(output))
        output.parent.mkdir(parents=True, exist_ok=True)

        app = main_service.get_app()
        with open(output, "w", encoding="utf-8") as fd:
            print(html_template % json.dumps(app.openapi()), file=fd)  # noqa S001

        exit_code = 0
    finally:
        omni.kit.app.get_app().post_quit(exit_code)


if __name__ == "__main__":
    main()

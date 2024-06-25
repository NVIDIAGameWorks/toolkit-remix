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

import typing
from pathlib import Path
from typing import List, Optional

import carb
import carb.tokens
import omni.client
from lightspeed.common.constants import CAPTURE_FOLDER, LSS_FOLDER, USD_EXTENSIONS

if typing.TYPE_CHECKING:
    from lightspeed.widget.content_viewer.scripts.core import ContentData


def get_captures(data: "ContentData") -> List[str]:
    return sorted(
        [
            str(file)
            for file in Path(data.path).iterdir()
            if file.is_file() and file.suffix in USD_EXTENSIONS and str(file.stem).startswith(f"{CAPTURE_FOLDER}_")
        ],
        reverse=True,
    )


def get_capture_image(usd_path: str) -> Optional[str]:
    image_path = Path(usd_path).parent.joinpath(".thumbs", f"{Path(usd_path).name}.dds")
    return str(image_path) if image_path.exists() else None


def get_captures_directory(data: "ContentData") -> str:
    return str(Path(data.path).parent.joinpath(LSS_FOLDER, CAPTURE_FOLDER))


def read_file(file_path) -> Optional[bytes]:
    """Read a file on the disk"""
    result, _, content = omni.client.read_file(file_path)
    if result == omni.client.Result.OK:
        data = memoryview(content).tobytes()
    else:
        try:  # try local
            with open(file_path, "rb") as in_file:
                data = in_file.read()
        except IOError:
            carb.log_error(f"Cannot read {file_path}, error code: {result}.")
            return None
    return data  # noqa R504

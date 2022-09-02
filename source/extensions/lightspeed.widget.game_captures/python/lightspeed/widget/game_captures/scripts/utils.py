"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import typing
from pathlib import Path
from typing import List, Optional

import carb
import carb.tokens
import omni.client
from lightspeed.common.constants import CAPTURE_FOLDER, LSS_FOLDER

if typing.TYPE_CHECKING:
    from lightspeed.widget.content_viewer.scripts.core import ContentData


def get_captures(data: "ContentData") -> List[str]:
    return sorted(
        [
            str(file)
            for file in Path(data.path).iterdir()
            if file.is_file()
            and file.suffix in [".usd", ".usda", ".usdc"]
            and str(file.stem).startswith(f"{CAPTURE_FOLDER}_")
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

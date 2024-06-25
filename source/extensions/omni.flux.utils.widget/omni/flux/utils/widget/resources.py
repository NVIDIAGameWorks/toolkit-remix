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

from pathlib import Path
from typing import Dict, List, Optional

import carb.settings
import omni.kit.app


def __get_default_resources_ext():
    return carb.settings.get_settings().get("/exts/omni.flux.utils.widget/default_resources_ext")


def __get_extension_root(name: str) -> Path:
    """
    Get the extension root folder

    Args:
        name: the name of the extension

    Returns:
        The root folder of the given extension
    """
    ext_id = omni.kit.app.get_app().get_extension_manager().get_enabled_extension_id(name)
    return Path(omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id))


def get_icons(name: str, ext_name: Optional[str] = None) -> Optional[str]:
    """
    Get icon from a resource extension

    Args:
        name: the name of the icon to get (without the extension)
        ext_name: the name of the resource extension. If not specify,
            /exts/omni.flux.utils.widget/default_resources_ext setting will be used.

    Returns:
        Path of the icon
    """
    if ext_name is None:
        ext_name = __get_default_resources_ext()
    if ext_name is None:
        carb.log_warn("No resource extension found!")
        return None
    for icon in __get_extension_root(ext_name).joinpath("data", "icons").iterdir():
        if icon.stem == name:
            return str(icon)
    return None


def get_image(name: str, ext_name: Optional[str] = None) -> Optional[str]:
    """
    Get image from a resource extension

    Args:
        name: the name of the image to get (without the extension)
        ext_name: the name of the resource extension. If not specify,
            /exts/omni.flux.utils.widget/default_resources_ext setting will be used.

    Returns:
        Path of the image
    """
    if ext_name is None:
        ext_name = __get_default_resources_ext()
    if ext_name is None:
        carb.log_warn("No resource extension found!")
        return None
    for image in __get_extension_root(ext_name).joinpath("data", "images").iterdir():
        if image.stem == name:
            return str(image)
    return None


def get_background_images(ext_name: Optional[str] = None) -> List[str]:
    """
    Get background image from a resource extension

    Args:
        name: the name of the background image to get (without the extension)
        ext_name: the name of the resource extension. If not specify,
            /exts/omni.flux.utils.widget/default_resources_ext setting will be used.

    Returns:
        Path of the background image
    """
    if ext_name is None:
        ext_name = __get_default_resources_ext()
    if ext_name is None:
        carb.log_warn("No resource extension found!")
        return []
    return [
        str(image)
        for image in __get_extension_root(ext_name).joinpath("data", "images", "background_images").iterdir()
        if not image.is_dir()
    ]


def get_fonts(name: str, ext_name: Optional[str] = None) -> Optional[str]:
    """
    Get font from a resource extension

    Args:
        name: the name of the font to get (without the extension)
        ext_name: the name of the resource extension. If not specify,
            /exts/omni.flux.utils.widget/default_resources_ext setting will be used.

    Returns:
        Path of the font
    """
    if ext_name is None:
        ext_name = __get_default_resources_ext()
    if ext_name is None:
        carb.log_warn("No resource extension found!")
        return None
    for font in __get_extension_root(ext_name).joinpath("data", "fonts").iterdir():
        if font.stem == name:
            return str(font)
    return None


def get_test_data(name: str, ext_name: Optional[str] = None) -> Optional[str]:
    """
    Get test data from a resource extension

    Args:
        name: the name of the data to get (without the extension). Can be "hello.usd" or "hello/hello.usd"
        ext_name: the name of the resource extension. If not specify,
            /exts/omni.flux.utils.widget/default_resources_ext setting will be used.

    Returns:
        Path of test data
    """
    if ext_name is None:
        ext_name = __get_default_resources_ext()
    if ext_name is None:
        carb.log_warn("No resource extension found!")
        return None
    root_path = __get_extension_root(ext_name).joinpath("data", "tests")
    for data in root_path.rglob("*"):
        if data == root_path.joinpath(name):
            return str(data)
    return None


def get_font_list(ext_name: Optional[str] = None) -> Dict[str, str]:
    """
    Get font list from a resource extension

    Args:
        ext_name: the name of the resource extension. If not specify,
            /exts/omni.flux.utils.widget/default_resources_ext setting will be used.

    Returns:
        Dictionary with the name of the font and the font path
    """
    if ext_name is None:
        ext_name = __get_default_resources_ext()
    if ext_name is None:
        carb.log_warn("No resource extension found!")
        return {}
    return {font.stem: str(font) for font in __get_extension_root(ext_name).joinpath("data", "fonts").iterdir()}

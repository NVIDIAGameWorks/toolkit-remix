"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from enum import Enum
from lightspeed.common.constants import SAVE_USD_FILE_EXTENSIONS_OPTIONS as _SAVE_USD_FILE_EXTENSIONS_OPTIONS
from omni.flux.asset_importer.core.data_models import UsdExtensions as _UsdExtensions


class ModPackagingMode(str, Enum):
    REDIRECT = (
        "redirect",
        "Redirect dependencies",
        "Creates the smallest package, but dependency mods must also be installed.",
    )
    IMPORT = (
        "import",
        "Import dependencies",
        "Creates a standalone package and keeps the layered USD structure.",
    )
    FLATTEN = (
        "flatten",
        "Flatten into one layer",
        "Creates a standalone package, collapses the packaged result into one authored layer, and only keeps assets still referenced by the flattened output.",
    )

    def __new__(cls, value: str, label: str, description: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        obj.description = description
        return obj


_PRESERVE_OUTPUT_FORMAT_DESCRIPTION = "Keeps the packaged root layer on the same extension as the source mod layer."
_PACKAGING_OUTPUT_FORMAT_DESCRIPTIONS = {
    None: _PRESERVE_OUTPUT_FORMAT_DESCRIPTION,
    **{
        _UsdExtensions(pattern.removeprefix("*.").lower()): description
        for pattern, description in _SAVE_USD_FILE_EXTENSIONS_OPTIONS
    },
}


MOD_PACKAGING_MODE_UI_OPTIONS = tuple((mode, mode.label) for mode in ModPackagingMode)
MOD_PACKAGING_OUTPUT_FORMAT_UI_OPTIONS = (
    (None, "Preserve Extensions"),
    *((output_format, output_format.value) for output_format in _UsdExtensions),
)


def get_packaged_root_output_suffix(output_format: _UsdExtensions | None) -> str | None:
    return None if output_format is None else f".{output_format.value}"


def get_packaged_root_export_args(output_format: _UsdExtensions | None) -> dict[str, str] | None:
    return None if output_format in (None, _UsdExtensions.USD) else {"format": output_format.value}


def get_packaging_mode_description(mode: ModPackagingMode) -> str:
    return mode.description


def get_packaging_output_format_description(output_format: _UsdExtensions | None) -> str:
    return _PACKAGING_OUTPUT_FORMAT_DESCRIPTIONS[output_format]

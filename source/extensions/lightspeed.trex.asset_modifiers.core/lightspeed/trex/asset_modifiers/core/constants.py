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

__all__ = ["FILE_INPUT", "SETTINGS_ROOT", "SOURCE_INPUT"]

from pathlib import Path

from lightspeed.trex.asset_modifiers.factory import ModifierInput

from .enums import SourceGetter

SETTINGS_ROOT = "/persistent/exts/lightspeed.trex.asset_modifiers.core"

# Every modifier shows these Source inputs before its own inputs.
SOURCE_INPUT = ModifierInput(
    "source",
    "Prims",
    SourceGetter,
    SourceGetter.SELECTED,
    group="Source",
    tooltip="Select the prims to modify. Only prims that the modifier accepts are used.",
)
FILE_INPUT = ModifierInput("file", "File", Path, Path(), group="Source", tooltip="Select the model file to modify.")

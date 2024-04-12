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
import re
from pathlib import Path
from typing import List, Optional

from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCore
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from pydantic import BaseModel, Field, validator


class ModPackagingSchema(BaseModel):
    context_name: str = Field(
        ..., description="The context name to use for the packaging stage. Should be a unique context name."
    )
    mod_layer_paths: List[Path] = Field(
        ...,
        description="The mod layer paths should be ordered by opinion strength where the strongest layer is first. "
        "All mod layers found in a given project should be in found in the list, including external mod dependencies",
    )
    selected_layer_paths: List[Path] = Field(
        ...,
        description="A list of layers to package. Must at least contain the strongest mod layer found in "
        "`mod_layer_paths` or the packaging process will quick return.",
    )
    output_directory: Path = Field(
        ...,
        description="The directory where the packaged mod should be stored.\n\n"
        "WARNING: The directory will be emptied prior to packaging the mod.",
    )
    redirect_external_dependencies: Optional[bool] = Field(
        True,
        description="Whether the reference dependencies taken from external mods should be redirected or copied in "
        "this mod's package during the packaging process.\n\n"
        "- Redirecting will allow the mod to use the installed mod's dependencies so updating a dependency will be as "
        "simple as to install the updated dependency.\n"
        "- Copying will make sure the mod is completely standalone so no other mods need to be installed for this mod "
        "to be loaded successfully.",
    )
    mod_name: str = Field(..., description="The display name used for the mod in the RTX Remix Runtime.")
    mod_version: str = Field(..., description="The mod version. Used when building dependency lists.")
    mod_details: Optional[str] = Field(None, description="Optional text used to describe the mod in more details.")

    @validator("mod_layer_paths", allow_reuse=True)
    def at_least_one(cls, v):  # noqa
        """Check that at least 1 mod file was selected"""
        if len(v) < 1:
            raise ValueError("At least 1 mod file should exist in the stage")
        return v

    @validator("mod_layer_paths", each_item=True, allow_reuse=True)
    def is_mod_file_valid(cls, v):  # noqa
        """Check that the file is a valid mod file"""
        if not _ReplacementCore.is_mod_file(str(v)):
            raise ValueError(f"The path is not a valid mod file: {v}")
        return v

    @validator("selected_layer_paths", each_item=True, allow_reuse=True)
    def layer_exists(cls, v):  # noqa
        """Check that every selected layer file exists"""
        layer_url = _OmniUrl(v)
        if not layer_url.exists:
            raise ValueError(f"The selected layer does not exist: {v}")
        return v

    @validator("mod_name", "output_directory", allow_reuse=True)
    def is_not_empty(cls, v):  # noqa
        """Check that the mod name is not empty"""
        if not v or not str(v).strip():
            raise ValueError("The value cannot be empty")
        return v

    @validator("mod_version", allow_reuse=True)
    def is_valid_version(cls, v):  # noqa
        """Check that the mod version has a valid format"""
        if not re.search("^(\\d+\\.\\d+(?:\\.\\d+)?)$", v):
            raise ValueError('The version must use the following format: "{MAJOR}.{MINOR}.{PATCH}". Example: 1.0.1')
        return v

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

import carb
import omni.usd
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from pydantic import Field, field_validator

from .current_stage import CurrentStageContextPlugin as _CurrentStageContextPlugin


class UsdFileContextPlugin(_CurrentStageContextPlugin):
    display_name: str = Field(default="USD File", exclude=True)
    context_name: str = Field(default="", exclude=True)

    file_path: str = Field(description="The file path to the USD File to load")

    @field_validator("file_path", mode="before")
    @classmethod
    def file_path_is_valid(cls, v):
        resolved_url = _OmniUrl(carb.tokens.get_tokens_interface().resolve(v))
        if not resolved_url.is_file:
            raise ValueError("The file path is not a valid file")
        return str(resolved_url)

    def setup(self):
        context = omni.usd.get_context(self.context_name)
        context.open_stage(self.file_path)

        stage = context.get_stage()
        if not stage:
            raise RuntimeError(f'An error occurred while opening the USD file -> "{self.file_path}"')

        super().setup()

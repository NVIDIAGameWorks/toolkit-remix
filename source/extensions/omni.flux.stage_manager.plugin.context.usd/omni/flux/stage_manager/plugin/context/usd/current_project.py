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

import omni.usd
from pydantic import Field, validator

from .base import StageManagerUSDContextPlugin as _StageManagerUSDContextPlugin


class CurrentProjectPlugin(_StageManagerUSDContextPlugin):
    context_name: str = Field(...)

    display_name: str = "Current Project"

    @validator("context_name", allow_reuse=True)
    def context_name_is_valid(cls, v):  # noqa N805
        if not omni.usd.get_context(v):
            raise ValueError("The context does not exist")
        return v

    def setup(self):
        #  TODO Implement the actual context setup
        pass

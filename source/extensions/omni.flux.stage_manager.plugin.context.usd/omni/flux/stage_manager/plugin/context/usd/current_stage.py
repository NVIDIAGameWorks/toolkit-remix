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


class CurrentStageContextPlugin(_StageManagerUSDContextPlugin):
    context_name: str = Field(..., description="The name of the context from which to get the stage")

    recursive_traversal: bool = Field(
        False, description="Whether to get all the prims in the stage or just the root prims"
    )

    display_name: str = "Current Stage"

    @validator("context_name", allow_reuse=True)
    def context_name_is_valid(cls, v):  # noqa N805
        if not omni.usd.get_context(v):
            raise ValueError("The context does not exist")
        return v

    def setup(self):
        context = omni.usd.get_context(self.context_name)
        stage = context.get_stage()

        if not stage:
            raise RuntimeError(f'The context does not have a stage -> "{self.context_name}"')

        if self.recursive_traversal:
            return [prim for prim in stage.TraverseAll() if not omni.usd.is_hidden_type(prim)]

        return stage.GetPseudoRoot().GetChildren()

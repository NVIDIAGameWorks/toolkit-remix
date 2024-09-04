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
from pxr import Usd
from pydantic import Field, PrivateAttr, validator

from .base import StageManagerUSDContextPlugin as _StageManagerUSDContextPlugin


class CurrentStageContextPlugin(_StageManagerUSDContextPlugin):
    context_name: str = Field(..., description="The name of the context from which to get the stage")

    display_name: str = "Current Stage"

    _stage: Usd.Stage | None = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._stage = None

    @validator("context_name", allow_reuse=True)
    def context_name_is_valid(cls, v):  # noqa N805
        if not omni.usd.get_context(v):
            raise ValueError("The context does not exist")
        return v

    def setup(self):
        """
        Set up the context. This will be called once by the core.

        Raises:
            ValueError: If no stage exists for the given context
        """
        context = omni.usd.get_context(self.context_name)
        self._stage = context.get_stage()

        if not self._stage:
            raise ValueError(f'The context does not have a stage -> "{self.context_name}"')

    def get_items(self):
        """
        Fetch the list of prims other plugins should use

        Raises:
            ValueError: If the context was not setup

        Returns:
            List of USD prims
        """
        if not self._stage:
            raise ValueError("The context was not setup")

        return self._stage.GetPseudoRoot().GetChildren()

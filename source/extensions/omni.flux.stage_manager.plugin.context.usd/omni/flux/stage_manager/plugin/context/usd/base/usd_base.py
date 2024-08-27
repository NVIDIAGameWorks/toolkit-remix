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

import abc
from typing import TYPE_CHECKING

from omni.flux.stage_manager.factory import StageManagerDataTypes as _StageManagerDataTypes
from omni.flux.stage_manager.factory.plugins import StageManagerContextPlugin as _StageManagerContextPlugin

if TYPE_CHECKING:
    from pxr import Usd


class StageManagerUSDContextPlugin(_StageManagerContextPlugin, abc.ABC):
    @classmethod
    @property
    @abc.abstractmethod
    def context_name(cls):
        pass

    @classmethod
    @property
    def data_type(cls):
        return _StageManagerDataTypes.USD

    def setup(self) -> list["Usd.Prim"]:
        """
        Fetch the list of prims other plugins should use

        Returns:
            List of USD prims
        """
        pass

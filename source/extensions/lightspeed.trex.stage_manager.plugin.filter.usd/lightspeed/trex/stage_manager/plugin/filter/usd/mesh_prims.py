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

from typing import TYPE_CHECKING

from lightspeed.trex.utils.common.prim_utils import is_instance as _is_instance
from lightspeed.trex.utils.common.prim_utils import is_model as _is_model
from omni.flux.stage_manager.plugin.filter.usd.base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin
from pydantic import Field

if TYPE_CHECKING:
    from pxr import Usd


class MeshPrimsFilterPlugin(_ToggleableUSDFilterPlugin):
    display_name: str = "Mesh Prims"
    tooltip: str = "Filter out mesh prims"

    include_instances: bool = Field(
        True, description="Whether the filter should also include instances with the meshes or not."
    )

    def _filter_predicate(self, prim: "Usd.Prim") -> bool:
        return _is_model(prim) or (self.include_instances and _is_instance(prim))

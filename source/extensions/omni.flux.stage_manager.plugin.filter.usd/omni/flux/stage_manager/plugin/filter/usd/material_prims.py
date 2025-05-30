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

from pxr import Usd, UsdGeom, UsdShade
from pydantic import Field

from .base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin


class MaterialPrimsFilterPlugin(_ToggleableUSDFilterPlugin):
    display_name: str = Field(default="Material Prims", exclude=True)
    tooltip: str = Field(default="Filter out material prims", exclude=True)

    include_meshes: bool = Field(
        True, description="Whether the filter should also include child meshes with the materials or not."
    )

    def _filter_predicate(self, prim: "Usd.Prim") -> bool:
        return prim.IsA(UsdShade.Material) or (self.include_meshes and prim.IsA(UsdGeom.Mesh))

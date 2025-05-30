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

from omni.flux.utils.common import get_omni_prims as _get_omni_prims
from pydantic import Field

from .base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin

if TYPE_CHECKING:
    from pxr import Usd


class OmniPrimsFilterPlugin(_ToggleableUSDFilterPlugin):
    display_name: str = Field(default="Omniverse Prims", exclude=True)
    tooltip: str = Field(default="Filter out Omniverse prims", exclude=True)

    def _filter_predicate(self, prim: "Usd.Prim") -> bool:
        return prim.GetPath() in _get_omni_prims()

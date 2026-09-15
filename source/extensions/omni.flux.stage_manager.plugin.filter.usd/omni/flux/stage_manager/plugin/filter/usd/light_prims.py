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

__all__ = ["LightPrimsFilterPlugin"]

import threading
from collections.abc import Callable

from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.utils.common.lights import get_light_type
from pxr import UsdLux
from pydantic import Field

from .base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin


class LightPrimsFilterPlugin(_ToggleableUSDFilterPlugin):
    display_name: str = Field(default="Light Prims", exclude=True)
    tooltip: str = Field(default="Filter for light prims", exclude=True)

    def build_filter_predicate(self, cancel_event: threading.Event | None = None) -> Callable[[StageManagerItem], bool]:
        """Build an active user predicate or inactive intrinsic light classifier.

        Args:
            cancel_event: Optional event accepted by the shared builder contract.

        Returns:
            Predicate that evaluates one Stage Manager item.
        """
        if self.filter_active:
            return self.filter_predicate

        def predicate(item: StageManagerItem) -> bool:
            """Prepare one supported light for the context refresh."""
            is_supported_light = self._evaluate_item(item)
            if is_supported_light:
                item.mark_display_name_candidate()
            return is_supported_light

        return predicate

    def _evaluate_item(self, item: StageManagerItem) -> bool:
        """Evaluate whether an item contains a supported light.

        Args:
            item: Stage Manager item containing the prim to evaluate.

        Returns:
            Whether the item contains a supported light.
        """
        prim = item.data
        is_light = prim.HasAPI(UsdLux.LightAPI) if hasattr(UsdLux, "LightAPI") else prim.IsA(UsdLux.Light)
        return is_light and get_light_type(prim.GetTypeName()) is not None

"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from __future__ import annotations

from lightspeed.common.constants import PARTICLE_SCHEMA_NAME as _PARTICLE_SCHEMA_NAME
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin
from pydantic import Field


class ParticleSystemsFilterPlugin(_ToggleableUSDFilterPlugin):
    display_name: str = Field(default="Particle System Prims", exclude=True)
    tooltip: str = Field(default="Filter for particle systems", exclude=True)

    def _evaluate_item(self, item: _StageManagerItem) -> bool:
        """Evaluate whether an item contains a particle system.

        Args:
            item: Stage Manager item containing the prim to evaluate.

        Returns:
            Whether the prim has the particle-system schema.
        """
        return item.data.HasAPI(_PARTICLE_SCHEMA_NAME)

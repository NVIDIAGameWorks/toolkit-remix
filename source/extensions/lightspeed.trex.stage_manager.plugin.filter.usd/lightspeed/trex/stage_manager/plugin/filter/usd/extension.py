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

__all__ = ["LightspeedStageManagerUSDFilterPluginsExtension"]

import carb
import omni.ext
from omni.flux.stage_manager.factory import get_instance

from .geometry_prims import GeometryPrimsFilterPlugin
from .instance_group import InstanceGroupFilterPlugin
from .is_capture import IsCaptureFilterPlugin
from .is_category import IsCategoryFilterPlugin
from .is_logic_graph import RemixLogicPrimsFilterPlugin
from .mesh_group import MeshGroupFilterPlugin
from .mesh_prims import MeshPrimsFilterPlugin
from .particle_prims import ParticleSystemsFilterPlugin


class LightspeedStageManagerUSDFilterPluginsExtension(omni.ext.IExt):
    _PLUGINS = [
        IsCaptureFilterPlugin,
        IsCategoryFilterPlugin,
        InstanceGroupFilterPlugin,
        GeometryPrimsFilterPlugin,
        MeshGroupFilterPlugin,
        MeshPrimsFilterPlugin,
        ParticleSystemsFilterPlugin,
        RemixLogicPrimsFilterPlugin,
    ]

    def on_startup(self, _):
        carb.log_info("[lightspeed.trex.stage_manager.plugin.filter.usd] Startup")

        get_instance().register_plugins(self._PLUGINS)

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.stage_manager.plugin.filter.usd] Shutdown")

        get_instance().unregister_plugins(self._PLUGINS)

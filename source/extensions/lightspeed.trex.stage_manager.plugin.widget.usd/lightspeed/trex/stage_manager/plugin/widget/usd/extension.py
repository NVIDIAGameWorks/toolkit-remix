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

import carb
import omni.ext
from omni.flux.stage_manager.factory import get_instance as _get_factory_instance

from .action_assign_category import AssignCategoryActionWidgetPlugin as _AssignCategoryActionWidgetPlugin
from .action_delete_restore import DeleteRestoreActionWidgetPlugin as _DeleteRestoreActionWidgetPlugin
from .action_logic_graph import LogicGraphWidgetPlugin as _LogicGraphWidgetPlugin
from .action_nickname_toggle import NicknameToggleActionWidgetPlugin as _NicknameToggleActionWidgetPlugin
from .action_particle_systems import ParticleSystemsActionWidgetPlugin as _ParticleSystemsActionWidgetPlugin
from .action_remap_skeleton import RemapSkeletonActionWidgetPlugin as _RemapSkeletonActionWidgetPlugin
from .action_rename_prim import PrimRenameNameActionWidgetPlugin as _PrimRenameNameActionWidgetPlugin
from .focus_in_viewport import FocusInViewportActionWidgetPlugin as _FocusInViewportActionWidgetPlugin
from .info_remap_skeleton import RemapSkeletonInfoWidgetPlugin as _RemapSkeletonInfoWidgetPlugin
from .state_hidden_category import IsCategoryHiddenStateWidgetPlugin as _IsCategoryHiddenStateWidgetPlugin
from .state_is_capture import IsCaptureStateWidgetPlugin as _IsCaptureStateWidgetPlugin


class LightspeedStageManagerUSDWidgetPluginsExtension(omni.ext.IExt):
    _PLUGINS = [
        _AssignCategoryActionWidgetPlugin,
        _DeleteRestoreActionWidgetPlugin,
        _FocusInViewportActionWidgetPlugin,
        _IsCaptureStateWidgetPlugin,
        _IsCategoryHiddenStateWidgetPlugin,
        _LogicGraphWidgetPlugin,
        _NicknameToggleActionWidgetPlugin,
        _ParticleSystemsActionWidgetPlugin,
        _PrimRenameNameActionWidgetPlugin,
        _RemapSkeletonActionWidgetPlugin,
        _RemapSkeletonInfoWidgetPlugin,
    ]

    def on_startup(self, _):
        carb.log_info("[lightspeed.trex.stage_manager.plugin.widget.usd] Startup")

        _get_factory_instance().register_plugins(self._PLUGINS)

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.stage_manager.plugin.widget.usd] Shutdown")

        _get_factory_instance().unregister_plugins(self._PLUGINS)

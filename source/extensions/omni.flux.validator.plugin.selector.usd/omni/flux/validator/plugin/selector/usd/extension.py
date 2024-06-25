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
import carb.settings
import omni.ext
from omni.flux.validator.factory import get_instance as _get_factory_instance

from .all_materials import AllMaterials as _AllMaterials
from .all_meshes import AllMeshes as _AllMeshes
from .all_prims import AllPrims as _AllPrims
from .all_shaders import AllShaders as _AllShaders
from .all_textures import AllTextures as _AllTextures
from .nothing import Nothing as _Nothing
from .root_prims import RootPrims as _RootPrims


class FluxValidatorPluginSelectorUSDExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        carb.log_info("[omni.flux.validator.plugin.selector.usd] Startup")
        _get_factory_instance().register_plugins(
            [_AllPrims, _AllMeshes, _AllMaterials, _AllShaders, _AllTextures, _Nothing, _RootPrims]
        )

    def on_shutdown(self):
        carb.log_info("[omni.flux.validator.plugin.selector.usd] Shutdown")
        _get_factory_instance().unregister_plugins(
            [_AllPrims, _AllMeshes, _AllMaterials, _AllShaders, _AllTextures, _Nothing, _RootPrims]
        )

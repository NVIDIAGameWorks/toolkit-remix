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
from omni.flux.factory.base import FactoryBase as _FactoryBase

from .plugins.base import StageManagerPluginBase as _StageManagerPluginBase

_instance: _FactoryBase | None = None


def get_instance() -> _FactoryBase:
    """
    Returns:
        The Stage Manager Factory instance
    """
    return _instance


class StageManagerFactoryExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, _):
        global _instance
        carb.log_info("[omni.flux.stage_manager.factory] Startup")

        _instance = _FactoryBase[_StageManagerPluginBase]()

    def on_shutdown(self):
        global _instance
        carb.log_info("[omni.flux.stage_manager.factory] Shutdown")

        if _instance:
            _instance.destroy()
        _instance = None

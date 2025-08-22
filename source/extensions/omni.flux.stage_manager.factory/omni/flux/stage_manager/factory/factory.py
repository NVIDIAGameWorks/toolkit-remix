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

__all__ = ["StageManagerFactory"]

from omni.flux.factory.base import FactoryBase

from .plugins.base import StageManagerPluginBase
from .plugins.mixins import StageManagerMenuMixin


class StageManagerFactory(FactoryBase[StageManagerPluginBase]):
    def register_plugins(self, plugins):
        super().register_plugins(plugins)

        for plugin in plugins:
            if issubclass(plugin, StageManagerMenuMixin):
                plugin.register_menu()

    def unregister_plugins(self, plugins):
        super().unregister_plugins(plugins)

        for plugin in plugins:
            if issubclass(plugin, StageManagerMenuMixin):
                plugin.unregister_menu()

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

from omni.flux.factory.base import FactoryBase as _FactoryBase

from .plugins.plugin_base import Base as _PluginBase


class ValidatorFactory(_FactoryBase[_PluginBase]):
    def is_plugin_registered(self, name: str) -> bool:
        """
        Check is the plugin is registered into the factory

        Args:
            name: the name of the plugin to check

        Raises:
            ValueError: if the plugin is not registered

        Returns:
            True if registered, else raise a Value Error
        """
        if not super().is_plugin_registered(name):
            raise ValueError(f"Plugin {name} is not registered/not found! Stopped.")
        return True

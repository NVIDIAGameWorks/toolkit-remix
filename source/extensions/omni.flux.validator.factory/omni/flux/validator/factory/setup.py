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

import typing
from typing import List, Optional, Type

if typing.TYPE_CHECKING:
    from .plugins.base import Base as _Base


class Setup:
    def __init__(self):
        self.__plugins = {}

    def is_plugin_registered(self, name: str) -> bool:
        """
        Check is the plugin is registered into the factory

        Args:
            name: the name of the plugin to check

        Returns:
            True if registered, else False
        """
        if name not in self.__plugins:
            raise ValueError(f"Plugin {name} is not registered/not found! Stopped.")
        return True

    def get_plugins_from_name(self, plugin_name: str) -> Optional[Type["_Base"]]:
        """
        Get the plugin from a name

        Args:
            plugin_name: the name of the plugin to get

        Returns:
            The plugin
        """
        for name, plugin in self.__plugins.items():
            if name == plugin_name:
                return plugin
        return None

    def get_all_plugins(self):
        """Return all registered plugins"""
        return self.__plugins

    def register_plugins(self, plugins: List[Type["_Base"]]):
        """
        Register a plugin into the factory

        Args:
            plugins: the list of plugins to register
        """
        for plugin in plugins:
            self.__plugins[plugin.name] = plugin

    def unregister_plugins(self, plugins: List[Type["_Base"]]):
        """
        Unregister a plugin into the factory

        Args:
            plugins: the list of plugins to unregister
        """
        for plugin in plugins:
            if plugin.name in self.__plugins:
                del self.__plugins[plugin.name]

    def destroy(self):
        self.__plugins = {}

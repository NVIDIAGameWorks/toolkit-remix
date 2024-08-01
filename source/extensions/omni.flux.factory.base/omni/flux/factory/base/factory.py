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

from typing import Generic, TypeVar

from .plugins.base import PluginBase

T = TypeVar("T", bound=PluginBase)


class FactoryBase(Generic[T]):
    def __init__(self):
        self._plugins: dict[str, type[T]] = {}

    def is_plugin_registered(self, name: str) -> bool:
        """
        Check is the plugin is registered into the factory

        Args:
            name: the name of the plugin to check

        Returns:
            True if registered, else False
        """
        return name in self._plugins

    def get_plugin_from_name(self, plugin_name: str) -> type[T] | None:
        """
        Get the plugin from a name

        Args:
            plugin_name: the name of the plugin to get

        Returns:
            The plugin
        """
        return self._plugins.get(plugin_name)

    def get_all_plugins(self) -> dict[str, type[T]]:
        """Return all registered plugins"""
        return self._plugins

    def register_plugins(self, plugins: list[type[T]]):
        """
        Register a plugin into the factory

        Args:
            plugins: the list of plugins to register
        """
        for plugin in plugins:
            self._plugins[plugin.name] = plugin

    def unregister_plugins(self, plugins: list[type[T]]):
        """
        Unregister a plugin into the factory

        Args:
            plugins: the list of plugins to unregister
        """
        for plugin in plugins:
            if self.is_plugin_registered(plugin.name):
                del self._plugins[plugin.name]

    def destroy(self):
        self._plugins = {}

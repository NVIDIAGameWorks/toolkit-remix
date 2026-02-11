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

from collections.abc import Iterable
from typing import TYPE_CHECKING

from omni.flux.stage_manager.factory import StageManagerPluginBase as _StageManagerPluginBase
from omni.flux.stage_manager.factory import get_instance as _get_stage_manager_factory_instance
from omni.flux.stage_manager.factory.plugins import StageManagerContextPlugin as _StageManagerContextPlugin
from omni.flux.stage_manager.factory.plugins import StageManagerInteractionPlugin as _StageManagerInteractionPlugin
from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory import StageManagerFactory as _StageManagerFactory


class StageManagerSchema(BaseModel):
    """
    A Pydantic BaseModel class used to define the internal structure of the StageManager data.

    This model will use the StageManager factory to resolve all the plugins and transform the JSON dict used to
    initialize this base model to a completely initialized data structure.
    """

    context: _StageManagerContextPlugin = Field(description="The context plugin to use to provide data")
    interactions: list[_StageManagerInteractionPlugin] = Field(description="List of interactions to display in the UI")

    @field_validator("interactions", mode="before")
    @classmethod
    def check_unique_interactions(cls, v):
        # Use a list + validator to keep the list order
        return list(dict.fromkeys(v))

    def __init__(self, **data: dict):
        # Resolve all the plugins to their expected class
        data = self._resolve_plugins_recursive(_get_stage_manager_factory_instance(), data)

        super().__init__(**data)

    def _resolve_plugins_recursive(
        self, factory: "_StageManagerFactory", data: dict | Iterable | _StageManagerPluginBase
    ) -> dict | Iterable | _StageManagerPluginBase:
        if isinstance(data, dict):
            if "name" in data:
                plugin_class = factory.get_plugin_from_name(data["name"])
                if not plugin_class:
                    raise ValueError(f"An unregistered plugin was detected -> {data['name']}")
                # Resolve the plugin's attributes recursively
                resolved_data = {k: self._resolve_plugins_recursive(factory, v) for k, v in data.items()}
                # Create the plugin instance with resolved data first
                plugin_instance = plugin_class(**resolved_data)

                # Now populate additional_filters on the instance based on compatible_filters
                if hasattr(plugin_instance, "compatible_filters") and hasattr(plugin_instance, "additional_filters"):
                    additional_filter_types = set()
                    for filter_name in plugin_instance.compatible_filters:
                        filter_plugin_class = factory.get_plugin_from_name(filter_name)
                        if not filter_plugin_class:
                            continue
                        filter_plugin_obj = filter_plugin_class()
                        if filter_plugin_obj and type(filter_plugin_obj) not in additional_filter_types:
                            plugin_instance.additional_filters.append(filter_plugin_obj)
                            additional_filter_types.add(type(filter_plugin_obj))
                return self.__resolve_plugin_attributes(factory, plugin_instance)
            # Recursively resolve each item in the dict
            return {k: self._resolve_plugins_recursive(factory, v) for k, v in data.items()}

        if isinstance(data, Iterable) and not isinstance(data, (str, bytes, BaseModel)):
            # Recursively resolve each item in the list
            return [self._resolve_plugins_recursive(factory, item) for item in data]

        if isinstance(data, _StageManagerPluginBase):
            # Resolve attributes of an existing plugin instance
            return self.__resolve_plugin_attributes(factory, data)

        return data

    def __resolve_plugin_attributes(
        self, factory: "_StageManagerFactory", plugin: _StageManagerPluginBase
    ) -> _StageManagerPluginBase:
        # Use __dict__ to get all fields, including excluded ones
        fields = plugin.__dict__
        for field_name, field_value in fields.items():
            resolved_value = self._resolve_plugins_recursive(factory, field_value)
            if resolved_value != field_value:
                # Use Pydantic's __setattr__ to update the field
                setattr(plugin, field_name, resolved_value)
        return plugin

# noqa PLC0302
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
from pydantic import BaseModel as _BaseModel
from pydantic import validator

if TYPE_CHECKING:
    from omni.flux.factory.base import FactoryBase as _FactoryBase


class StageManagerSchema(_BaseModel):
    """
    A Pydantic BaseModel class used to define the internal structure of the StageManager data.

    This model will use the StageManager factory to resolve all the plugins and transform the JSON dict used to
    initialize this base model to a completely initialized data structure.
    """

    context: _StageManagerContextPlugin
    interactions: list[_StageManagerInteractionPlugin]

    @validator("interactions", allow_reuse=True)
    def check_unique_interactions(cls, v):  # noqa N805
        # Use a list + validator to keep the list order
        return list(dict.fromkeys(v))

    def __init__(self, **data: dict):
        # Resolve all the plugins to their expected class
        data = self._resolve_plugins_recursive(_get_stage_manager_factory_instance(), data)

        super().__init__(**data)

    def _resolve_plugins_recursive(
        self, factory: "_FactoryBase", data: dict | Iterable | _StageManagerPluginBase
    ) -> dict | Iterable | _StageManagerPluginBase:
        if isinstance(data, dict):
            # The dict is not a plugin definition but a dict of plugins
            if "name" not in data:
                return {k: self._resolve_plugins_recursive(factory, v) for k, v in data.items()}
            # The dict is a plugin definition, resolve
            plugin_class = factory.get_plugin_from_name(data["name"])
            if not plugin_class:
                raise ValueError(f"An unregistered plugin was detected -> {data['name']}")
            resolved_plugin = plugin_class(**{k: self._resolve_plugins_recursive(factory, v) for k, v in data.items()})
            # Resolve the plugin's attributes
            fields = resolved_plugin.dict()
            for field_name, field_value in fields.items():
                resolved_value = self._resolve_plugins_recursive(factory, field_value)
                if resolved_value != field_value:
                    # Use Pydantic's __setattr__ to update the field
                    setattr(resolved_plugin, field_name, resolved_value)
            return resolved_plugin

        # The value is a list, resolve every item in the list
        if isinstance(data, Iterable) and not isinstance(data, (str, bytes)):
            return [self._resolve_plugins_recursive(factory, item) for item in data]

        return data

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

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr, field_validator, model_validator

from ..extension import get_instance as _get_factory_instance
from .interface_base import IBase as _IBase
from .interface_base import IBaseSchema as _IBaseSchema


class BaseSchema(_IBaseSchema):
    name: str
    enabled: bool = True
    data: _IBase.Data

    _instance: Any = PrivateAttr(default=None)  # instance before data because data need the instance

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    @model_validator(mode="before")
    @classmethod
    def _parse_plugin_data(cls, values: dict[str, Any]) -> dict[str, Any]:
        plugin_name = values.get("name")
        if not plugin_name or not isinstance(plugin_name, str):
            raise KeyError(f"The key 'name' is missing from the plugin data for {cls.__name__}")

        raw_plugin_data = values.get("data")
        if raw_plugin_data is None:
            raise ValueError(f"'data' key is missing for the plugin {plugin_name}")

        plugin_cls = _get_factory_instance().get_plugin_from_name(plugin_name)
        if not plugin_cls:
            raise ValueError(
                f"Plugin {plugin_name} was not registered! Please enable the extension that has the plugin"
            )

        temp_plugin_instance = plugin_cls()
        # Check if data_type is a Pydantic model or at least a callable that can parse
        if (
            not hasattr(temp_plugin_instance, "data_type")
            or not callable(getattr(temp_plugin_instance, "data_type", None))
        ) and (
            not (
                isinstance(temp_plugin_instance.data_type, type)
                and issubclass(temp_plugin_instance.data_type, BaseModel)
            )
        ):
            raise TypeError(f"Plugin {plugin_name} data_type is not a Pydantic model: {temp_plugin_instance.data_type}")

        try:
            # Parse the raw_plugin_data using the plugin's specific data_type model
            # This ensures values["data"] will be an instance of that model.
            values["data"] = temp_plugin_instance.data_type(**raw_plugin_data)
        except Exception as e:
            raise ValueError(
                f"Failed to parse 'data' for plugin {plugin_name} using {temp_plugin_instance.data_type.__name__}: {e}"
            ) from e

        # The __check_data_flow can now be called in an 'after' validator, once self.data is populated.
        return values

    @model_validator(mode="after")
    def _initialize_plugin_instance_and_check_flow(self) -> "BaseSchema":
        # This validator runs after the model fields (name, data) are validated and assigned.
        # self.data is now an instance of the plugin's specific Data model.

        plugin_cls = _get_factory_instance().get_plugin_from_name(self.name)
        if not plugin_cls:
            # This should have been caught by the 'name' field_validator, but defensive check.
            raise ValueError(f"Plugin {self.name} is not registered (in after validator).")

        self._instance = plugin_cls()  # Create the actual plugin instance
        self._instance.set_parent_schema(self)

        # Now that self.data is the parsed model, we can check data flow
        BaseSchema.__check_data_flow(self.name, self.data)
        return self

    @property
    def instance(self) -> "BaseSchema" | None:
        return self._instance

    @staticmethod
    def __check_data_flow(plugin_name: str, plugin_data_model: Any):
        data_flow_compatible_names = plugin_data_model.data_flow_compatible_name or []
        for data_flow in plugin_data_model.data_flows or []:
            if data_flow.name not in data_flow_compatible_names:
                raise ValueError(
                    f"'{data_flow.name}' DataFlow is not compatible with the plugin {plugin_name}. Compatible data "
                    f"flows are {data_flow_compatible_names}"
                )

    @field_validator("name", mode="before")
    @classmethod
    def is_registered(cls, v: str) -> str:
        # This runs before _parse_plugin_data if field validators run before model validators for 'before' mode.
        # Pydantic execution order: field validators -> model_validator(mode='before') -> model_validator(mode='after')
        plugin_cls = _get_factory_instance().get_plugin_from_name(v)
        if not plugin_cls:
            raise ValueError(f"Plugin {v} is not registered")
        return v

    def destroy(self):
        if self._instance:
            self._instance.destroy()
        self._instance = None

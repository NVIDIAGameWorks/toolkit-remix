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

import abc
from enum import Enum as _Enum
from typing import Any
from collections.abc import Callable, Iterable

import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.validator.factory import DataFlow as _DataFlow
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from pydantic_core.core_schema import ValidationInfo

from .interface_base import IBase as _IBase
from .interface_base import IBaseSchema as _IBaseSchema


class ValidatorRunMode(_Enum):
    BASE_ALL = "base_all"  # re-run all plugins
    BASE_SELF_TO_END = "base_self_to_end"  # re-run from itself to the end
    BASE_ONLY_SELECTED = "base_only_selected"  # re-run only the passed list of plugins


class Base(_IBase, abc.ABC):
    display_name: str | None = None

    class Data(_IBase.Data):
        on_progress_callback: Callable[[float, str, bool], None] | None = Field(default=None, exclude=True)
        on_global_progress_callback: Callable[[float], None] | None = Field(default=None, exclude=True)

        # Write data that plugins can use downstream for example.
        # Useful to do a post-process at the end of the validation
        data_flows: list[_DataFlow] | None = Field(default=None)
        channel: str = Field(default="Default")
        expose_mass_ui: bool = Field(default=False)
        expose_mass_queue_action_ui: bool = Field(default=False)

        cook_mass_template: bool = Field(
            default=False,
            description="Set this to true if you want the mass validator to use the plugin to cook the template",
        )
        display_name_mass_template: str | None = Field(
            default=None, description="Name to show when we process a cooked template from mass processing"
        )
        display_name_mass_template_tooltip: str | None = Field(
            default=None, description="Tooltip to show when we process a cooked template from mass processing"
        )
        uuid: str | None = Field(default=None, description="UUID of the plugin")
        progress: tuple[float, str, bool] | None = Field(
            default=(0.0, "Initializing", True), description="Progress of the plugin"
        )
        global_progress_value: float | None = Field(default=0.0, description="Global progress value of the plugin")

        model_config = ConfigDict(extra="forbid", validate_assignment=True, arbitrary_types_allowed=True)

        _compatible_data_flow_names: list[str] | None = PrivateAttr(default=None)

        @property
        def data_flow_compatible_name(self):
            return self._compatible_data_flow_names

        @field_validator("uuid", mode="before")
        @classmethod
        def sanitize_uuid(cls, v: str | None) -> str | None:
            if v is not None:
                v = str(v).replace("-", "")
            return v

        @field_validator("progress", mode="before")
        @classmethod
        def _fire_progress_callback(cls, v: tuple[float, str, bool] | None, info: ValidationInfo):
            callback = info.data.get("on_progress_callback")
            if callback and v is not None:
                callback(*v)
            return v

        @field_validator("global_progress_value", mode="before")
        @classmethod
        def _fire_global_progress_value_callback(cls, v: float | None, info: ValidationInfo):
            callback = info.data.get("on_global_progress_callback")
            if callback and v is not None:
                callback(v)
            return v

    def __init__(self):
        self._schema: _IBaseSchema | None = None

        self.__on_build_ui = _Event()
        self.__on_mass_build_ui = _Event()
        self.__on_mass_build_queue_action_ui = _Event()
        self.__on_mass_cook_template = _Event()
        self.__on_progress = _Event()
        self.__on_global_progress = _Event()
        self.__on_validator_run = _Event()
        self.__on_enable_validation = _Event()
        self.__on_validation_is_ready_to_run = _Event()

    def _set_schema_attribute(self, attr: str, value: Any):
        """Call the event object that has the list of functions"""
        setattr(self._schema, attr, value)

    def _get_schema_attribute(self, attr: str) -> Any:
        """Call the event object that has the list of functions"""
        return getattr(self._schema, attr)

    @abc.abstractmethod
    def _callback_to_set(self) -> None:
        """
        Implementation of the callback to set up the event when data are changed
        Warnings: super() should be called before
        """
        self._schema.data.on_progress_callback = self.__on_progress
        self._schema.data.on_global_progress_callback = self.__on_global_progress

    def set_parent_schema(self, schema: _IBaseSchema):
        self._schema: _IBaseSchema = schema
        self._callback_to_set()

    def _on_validator_run(self, items: list[Base], run_mode: ValidatorRunMode, catch_exception: bool = True):
        self.__on_validator_run(items, run_mode, catch_exception)

    def _on_validator_enable(self, value: bool):
        self.__on_enable_validation(value)

    def _on_validation_is_ready_to_run(self, value: bool):
        self.__on_validation_is_ready_to_run(id(self), value)

    def subscribe_validator_run(self, callback: Callable[[list[Base], ValidatorRunMode, bool | None], Any]):
        return _EventSubscription(self.__on_validator_run, callback)

    def subscribe_enable_validation(self, callback: Callable[[bool], Any]):
        return _EventSubscription(self.__on_enable_validation, callback)

    def subscribe_on_validation_is_ready_to_run(self, callback: Callable[[int, bool], Any]):
        return _EventSubscription(self.__on_validation_is_ready_to_run, callback)

    def subscribe_build_ui(self, callback: Callable[[Any], Any]):
        return _EventSubscription(self.__on_build_ui, callback)

    def subscribe_mass_build_ui(self, callback: Callable[[Any], Any]):
        return _EventSubscription(self.__on_mass_build_ui, callback)

    def subscribe_mass_build_queue_action_ui(self, callback: Callable[[Any], Any]):
        return _EventSubscription(self.__on_mass_build_queue_action_ui, callback)

    def on_mass_cook_template(self, success, message, data):
        self.__on_mass_cook_template(success, message, data)

    def subscribe_mass_cook_template(self, callback: Callable[[tuple[bool, str | None, Any]], Any]):
        return _EventSubscription(self.__on_mass_cook_template, callback)

    def get_progress(self) -> tuple[float, str, bool]:
        return self._schema.data.progress

    def on_progress(self, progress: float, message: str, result: bool):
        self._schema.data.progress = (progress, message, result)

    def subscribe_progress(self, callback: Callable[[float, str, bool], Any]):
        return _EventSubscription(self.__on_progress, callback)

    def subscribe_global_progress(self, callback: Callable[[float], Any]):
        return _EventSubscription(self.__on_global_progress, callback)

    def get_global_progress(self) -> float:
        return self._schema.data.global_progress_value

    def set_global_progress(self, value: float):
        self._schema.data.global_progress_value = value

    @omni.usd.handle_exception
    async def on_crash(self, schema_data: Any, data: Any) -> None:
        await self._on_crash(schema_data, data)

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _on_crash(self, schema_data: Any, data: Any) -> None:
        pass

    @omni.usd.handle_exception
    async def build_ui(self, schema_data: Any) -> Any:
        result = await self._build_ui(schema_data)
        self.__on_build_ui(result)
        return result

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _build_ui(self, schema_data: Any) -> Any:
        pass

    @omni.usd.handle_exception
    async def mass_build_ui(self, schema_data: Any) -> Any:
        result = await self._mass_build_ui(schema_data)
        self.__on_mass_build_ui(result)
        return result

    @omni.usd.handle_exception
    async def _mass_build_ui(self, schema_data: Any) -> Any:
        pass

    def mass_build_queue_action_ui(
        self, schema_data: Any, default_actions: list[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> Any:
        result = self._mass_build_queue_action_ui(schema_data, default_actions, callback)
        self.__on_mass_build_queue_action_ui(result)
        return result

    def _mass_build_queue_action_ui(
        self, schema_data: Any, default_actions: list[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> Any:
        pass

    @omni.usd.handle_exception
    async def mass_cook_template(self, schema_data_template: Any) -> tuple[bool, str | None, list[Data]]:
        success, message, data = await self._mass_cook_template(schema_data_template)
        self.on_mass_cook_template(success, message, data)
        return success, message, data

    @omni.usd.handle_exception
    async def _mass_cook_template(self, schema_data_template: Any) -> tuple[bool, str | None, Any]:
        pass

    def _get_schema_data_flows(self, schema_data: Data, schema: BaseModel) -> list[_DataFlow]:
        all_data_flows = []
        schema_dict = schema.model_dump(serialize_as_any=True)
        for attr in schema_dict:
            next_plugin = getattr(schema, attr)
            next_plugins = []
            if isinstance(next_plugin, _IBaseSchema):
                next_plugins = [next_plugin]
            elif isinstance(next_plugin, Iterable):
                next_plugins = [plugin for plugin in next_plugin if isinstance(plugin, _IBaseSchema)]

            for plugin in next_plugins:
                data_flows: list[_DataFlow] | None = plugin.data.data_flows
                if data_flows:
                    for data_flow in data_flows:
                        if data_flow.channel != schema_data.channel:
                            continue
                        all_data_flows.append(data_flow)
                all_data_flows.extend(self._get_schema_data_flows(schema_data, plugin))
        return all_data_flows

    def show(self, value: bool, schema_data: Any):
        pass

    def destroy(self):
        self._schema = None
        self.__on_build_ui = None
        self.__on_progress = None
        self.__on_validator_run = None

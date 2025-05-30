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

import abc
import time
from typing import Any, Callable

import carb
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from .context_base import Schema as _ContextSchema
from .context_base import SetupDataTypeVar as _SetupDataTypeVar
from .plugin_base import Base as _Base
from .resultor_base import Schema as _ResultorSchema
from .schema_base import BaseSchema as _BaseSchema
from .selector_base import Schema as _SelectorSchema


class CheckBase(_Base, abc.ABC):
    class Data(_Base.Data):
        on_check_callback: Callable[[bool, str, Any], Any] | None = Field(default=None, exclude=True)
        on_fix_callback: Callable[[bool, str, Any], Any] | None = Field(default=None, exclude=True)

        last_check_message: str | None = Field(default=None)
        last_check_data: Any | None = Field(
            default=None, exclude=True, description="This is tmp we don't keep it in the schema"
        )
        last_check_timing: float | None = Field(default=None)
        last_check_result: bool | None = Field(default=None)

        last_fix_message: str | None = Field(default=None)
        last_fix_data: Any | None = Field(
            default=None, exclude=True, description="This is tmp we don't keep it in the schema"
        )
        last_fix_timing: float | None = Field(default=None)
        last_fix_result: bool | None = Field(default=None)

        @field_validator("last_check_result", mode="before")
        @classmethod
        def _fire_last_check_result_callback(cls, v: bool | None, info: ValidationInfo):
            """When the check result is set, the message and data is also set"""
            callback = info.data.get("on_check_callback")
            if callback and v is not None:
                callback(v, info.data.get("last_check_message"), info.data.get("last_check_data"))
            return v

        @field_validator("last_fix_result", mode="before")
        @classmethod
        def _fire_last_fix_result_callback(cls, v: bool | None, info: ValidationInfo):
            """When the fix result is set, the message and data is also set"""
            callback = info.data.get("on_fix_callback")
            if callback and v is not None:
                callback(v, info.data.get("last_fix_message"), info.data.get("last_fix_data"))
            return v

    def __init__(self):
        super().__init__()
        self.__on_check = _Event()
        self.__on_fix = _Event()

    def _callback_to_set(self) -> None:
        """
        Implementation of the callback to set up the event when data are changed
        Warnings: super() should be called before
        """
        super()._callback_to_set()
        self._schema.data.on_check_callback = self.__on_check
        self._schema.data.on_fix_callback = self.__on_fix

    def subscribe_check(self, callback: Callable[[Any, str, Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_check, callback)

    def subscribe_fix(self, callback: Callable[[Any, str, Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_fix, callback)

    @omni.usd.handle_exception
    async def check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be called to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        carb.log_info(f"Try to run check plugin check {self.name} ...")
        st = time.time()
        result, message, data = await self._check(schema_data, context_plugin_data, selector_plugin_data)
        schema_data.last_check_message = message
        schema_data.last_check_data = data
        schema_data.last_check_timing = time.time() - st
        schema_data.last_check_result = result
        self.on_progress(1, "Finished", result)
        carb.log_info(f"\tResult: {result}: {message}")
        return result, message, data

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        return False, "Not implemented", None

    @omni.usd.handle_exception
    async def fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be called to fix the data if the fix function return False

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the fix passed, False if not.
            str: the message you want to show, like "Succeeded to fix this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        carb.log_info(f"Try to run check plugin fix {self.name} ...")
        st = time.time()
        result, message, data = await self._fix(schema_data, context_plugin_data, selector_plugin_data)
        schema_data.last_fix_message = message
        schema_data.last_fix_data = data
        schema_data.last_fix_timing = time.time() - st
        schema_data.last_fix_result = result
        self.on_progress(1, "Finished", result)
        carb.log_info(f"\tResult: {result}: {message}")
        if not result:
            return False, message, data
        messages = f"{message}\n"
        result, message, data = await self.check(schema_data, context_plugin_data, selector_plugin_data)
        messages += message
        return result, messages, data

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data if the fix function return False

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the fix passed, False if not.
            str: the message you want to show, like "Succeeded to fix this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        return False, "Not implemented", None


class Schema(_BaseSchema):
    context_plugin: _ContextSchema
    selector_plugins: list[_SelectorSchema]
    resultor_plugins: list[_ResultorSchema] | None = Field(default=None)
    stop_if_fix_failed: bool = Field(default=False)
    pause_if_fix_failed: bool = Field(default=True)

    @field_validator("selector_plugins", mode="before")
    @classmethod
    def at_least_one(cls, v: list[_SelectorSchema]) -> list[_SelectorSchema]:
        if not v:
            raise ValueError("We should have at least 1 selector plugin")
        return v

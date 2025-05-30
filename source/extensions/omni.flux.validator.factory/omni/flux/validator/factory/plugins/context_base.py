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
from functools import partial
from typing import Any, Awaitable, Callable, TypeVar

import carb
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from .plugin_base import Base as _Base
from .resultor_base import Schema as _ResultorSchema
from .schema_base import BaseSchema as _BaseSchema

SetupDataTypeVar = TypeVar("SetupDataTypeVar")


class ContextBase(_Base, abc.ABC):
    class Data(_Base.Data):
        on_check_callback: Callable[[bool, str], Any] | None = Field(default=None, exclude=True)
        on_set_callback: Callable[[bool, str, SetupDataTypeVar], Any] | None = Field(default=None, exclude=True)
        on_exit_callback: Callable[[bool, str], Any] | None = Field(default=None, exclude=True)

        last_check_message: str | None = Field(default=None)
        last_check_timing: float | None = Field(default=None)
        last_check_result: bool | None = Field(default=None)

        last_set_message: str | None = Field(default=None)
        last_set_data: SetupDataTypeVar | None = Field(
            default=None, exclude=True, description="This is tmp we don't keep it in the schema"
        )
        last_set_timing: float | None = Field(default=None)
        last_set_result: bool | None = Field(default=None)

        last_on_exit_message: str | None = Field(default=None)
        last_on_exit_timing: float | None = Field(default=None)
        last_on_exit_result: bool | None = Field(default=None)

        hide_context_ui: bool = Field(default=False)

        @field_validator("last_check_result", mode="before")
        @classmethod
        def _fire_last_check_result_callback(cls, v: bool | None, info: ValidationInfo):
            """When the check result is set, the message and data is also set"""
            callback = info.data.get("on_check_callback")
            if callback and v is not None:
                callback(v, info.data.get("last_check_message"))
            return v

        @field_validator("last_set_result", mode="before")
        @classmethod
        def _fire_last_set_result_callback(cls, v: bool | None, info: ValidationInfo):
            """When the set result is set, the message and data is also set"""
            callback = info.data.get("on_set_callback")
            if callback and v is not None:
                callback(v, info.data.get("last_set_message"), info.data.get("last_set_data"))
            return v

        @field_validator("last_on_exit_result", mode="before")
        @classmethod
        def _fire_last_exit_result_callback(cls, v: bool | None, info: ValidationInfo):
            """When the exit result is set, the message is also set"""
            callback = info.data.get("on_exit_callback")
            if callback and v is not None:
                callback(v, info.data.get("last_on_exit_message"))
            return v

    def __init__(self):
        super().__init__()
        self.__on_check = _Event()
        self.__on_set = _Event()
        self.__on_exit = _Event()
        self.__run_callback_called = False

    def _callback_to_set(self) -> None:
        """
        Implementation of the callback to set up the event when data are changed
        Warnings: super() should be called before
        """
        super()._callback_to_set()
        self._schema.data.on_check_callback = self.__on_check
        self._schema.data.on_set_callback = self.__on_set
        self._schema.data.on_exit_callback = self.__on_exit

    async def __run_callback(
        self, run_callback: Callable[[SetupDataTypeVar], Awaitable[None]], context_plugin_data: SetupDataTypeVar
    ):
        self.__run_callback_called = True
        await run_callback(context_plugin_data)

    def subscribe_check(self, callback: Callable[[bool, str], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_check, callback)

    def subscribe_set(self, callback: Callable[[bool, str, SetupDataTypeVar], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_set, callback)

    def subscribe_on_exit(self, callback: Callable[[bool, str], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_exit, callback)

    @omni.usd.handle_exception
    async def check(self, schema_data: Data, parent_context: SetupDataTypeVar) -> tuple[bool, str]:
        """
        Function that will be called to check the data. For example, check that a USD stage is open, or a USD file path
        exist

        Args:
            schema_data: the data that should be checked
            parent_context: context data from the parent context

        Returns:
            bool: True if the check passed, False if not.
            str: the message you want to show, like "Succeeded to check this context"
        """
        carb.log_info(f"Try to run context plugin check {self.name} ...")
        st = time.time()
        result, message = await self._check(schema_data, parent_context)
        schema_data.last_check_message = message
        schema_data.last_check_timing = time.time() - st
        schema_data.last_check_result = result
        self.on_progress(1, "Finished", result)
        carb.log_info(f"\tResult: {result}: {message}")
        return result, message

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _check(self, schema_data: Data, parent_context: SetupDataTypeVar) -> tuple[bool, str]:
        """
        Function that will be called to execute the data. For example, check that a USD stage is open, or a USD file
        path exist

        Args:
            schema_data: the data that should be checked
            parent_context: context data from the parent context

        Returns:
            bool: True if the check passed, False if not.
            str: the message you want to show, like "Succeeded to check this context"
        """
        return False, "Not implemented"

    async def setup(
        self,
        schema_data: Data,
        run_callback: Callable[[SetupDataTypeVar], Awaitable[None]],
        parent_context: SetupDataTypeVar,
    ) -> tuple[bool, str, SetupDataTypeVar]:
        """
        Function that will be called to set the data. For a context plugin, it will grab the data that we want to pass
        them to check plugin. From example, open a USD file and grab the prims. Or grab prims from an opened stage.

        Args:
            schema_data: the data that should set. Same data than check()
            run_callback: the validation that will be run in the context of this setup
            parent_context: context data from the parent context

        Returns:
            bool: True if the setup passed, False if not.
            str: the message you want to show, like "Succeeded to setup this"
            any: data that you want to pass. Those data will be passed and used by the selector(s) and check(s) plugins.
            Like a USD stage.
        """
        carb.log_info(f"Try to run context plugin set {self.name} ...")
        st = time.time()
        result_context = await self._setup(schema_data, partial(self.__run_callback, run_callback), parent_context)
        if result_context is None:
            raise ValueError(f"Plugin {self.name} crashed.")
        result, message, data = result_context
        schema_data.last_set_message = message
        schema_data.last_set_timing = time.time() - st
        schema_data.last_set_data = data
        schema_data.last_set_result = result
        self.on_progress(1, "Finished", result)
        carb.log_info(f"\tResult: {result}: {message}")
        if not result:
            return result, message, data
        if not self.__run_callback_called:
            return False, f"Plugin implementation of {self.name} is wrong, 'run_callback()' was not called!", None
        return result, message, data

    @abc.abstractmethod
    async def _setup(
        self,
        schema_data: Data,
        run_callback: Callable[[SetupDataTypeVar], Awaitable[None]],
        parent_context: SetupDataTypeVar,
    ) -> tuple[bool, str, SetupDataTypeVar]:
        """
        Function that will be executed to set the data. For a context plugin, it will grab the data that we want to pass
        them to check plugin. From example, open a USD file and grab the prims. Or grab prims from an opened stage.

        Args:
            schema_data: the data that we should set. Same data than check()
            run_callback: the validation that will be run in the context of this setup
            parent_context: context data from the parent context

        Returns:
            bool: True if the setup passed, False if not.
            str: the message you want to show, like "Succeeded to setup this"
            any: data that you want to pass. Those data will be passed and used by the selector(s) and check(s) plugins.
                Like a USD stage.
        """
        return False, "Not implemented", None

    @omni.usd.handle_exception
    async def on_exit(self, schema_data: Data, parent_context: SetupDataTypeVar) -> tuple[bool, str]:
        """
        Function that will be called to after the check of the data. For example, save the input USD stage

        Args:
            schema_data: the data that should be checked
            parent_context: context data from the parent context

        Returns:
            bool: True if the on exit passed, False if not.
            str: the message you want to show, like "Succeeded to exit this context"
        """
        carb.log_info(f"Try to run context plugin on exit {self.name} ...")
        st = time.time()
        result, message = await self._on_exit(schema_data, parent_context)
        schema_data.last_on_exit_message = message
        schema_data.last_on_exit_timing = time.time() - st
        schema_data.last_on_exit_result = result
        self.on_progress(1, "Finished", result)
        carb.log_info(f"\tResult: {result}: {message}")
        return result, message

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _on_exit(self, schema_data: Data, parent_context: SetupDataTypeVar) -> tuple[bool, str]:
        """
        Function that will be called to after the check of the data. For example, save the input USD stage

        Args:
            schema_data: the data that should be checked
            parent_context: context data from the parent context

        Returns:
            bool: True if the on exit passed, False if not.
            str: the message you want to show, like "Succeeded to exit this context"
        """
        return False, "Not implemented"


class Schema(_BaseSchema):
    resultor_plugins: list[_ResultorSchema] | None = Field(default=None)

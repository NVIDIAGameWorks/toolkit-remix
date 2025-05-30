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

from .context_base import SetupDataTypeVar as _SetupDataTypeVar
from .plugin_base import Base as _Base
from .schema_base import BaseSchema as _BaseSchema


class SelectorBase(_Base, abc.ABC):
    class Data(_Base.Data):
        on_select_callback: Callable[[bool, str, Any], Any] | None = Field(default=None, exclude=True)

        last_select_message: str | None = Field(default=None)
        last_select_data: Any | None = Field(
            default=None, exclude=True, description="This is tmp we don't keep it in the schema"
        )
        last_select_timing: float | None = Field(default=None)
        last_select_result: bool | None = Field(default=None)

        @field_validator("last_select_result", mode="before")
        @classmethod
        def _fire_last_select_result_callback(cls, v: bool | None, info: ValidationInfo):
            callback = info.data.get("on_select_callback")
            if callback and v is not None:
                callback(v, info.data.get("last_select_message"), info.data.get("last_select_data"))
            return v

    def __init__(self):
        super().__init__()
        self.__on_select = _Event()

    def _callback_to_set(self) -> None:
        """
        Implementation of the callback to set up the event when data are changed
        Warnings: super() should be called before
        """
        super()._callback_to_set()
        self._schema.data.on_select_callback = self.__on_select

    def subscribe_select(self, callback: Callable[[bool, str, Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_select, callback)

    @omni.usd.handle_exception
    async def select(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be called to select the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the previous selector plugin

        Returns:
            bool: True if the selector passed, False if not.
            str: the message you want to show, like "Succeeded to select this"
            any: data that you want to pass. Those data will be passed and used by the check(s) plugins.
            Like a list of USD prims.
        """
        carb.log_info(f"Try to run select plugin select {self.name} ...")
        st = time.time()
        result, message, data = await self._select(schema_data, context_plugin_data, selector_plugin_data)
        schema_data.last_select_message = message
        schema_data.last_select_timing = time.time() - st
        schema_data.last_select_data = data
        schema_data.last_select_result = result
        self.on_progress(1, "Finished", result)
        carb.log_info(f"\tResult: {result}: {message}")
        return result, message, data

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _select(
        self, schema_data: Any, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to select the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the previous selector plugin

        Returns:
            bool: True if the selector passed, False if not.
            str: the message you want to show, like "Succeeded to select this"
            any: data that you want to pass. Those data will be passed and used by the check(s) plugins.
                Like a list of USD prims.
        """
        return False, "Not implemented", schema_data


class Schema(_BaseSchema):
    pass

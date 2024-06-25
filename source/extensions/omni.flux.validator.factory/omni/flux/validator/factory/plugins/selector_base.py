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
from typing import Any, Callable, Optional, Tuple

import carb
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, validator

from .base import Base as _Base
from .base import BaseSchema as _BaseSchema
from .context_base import SetupDataTypeVar as _SetupDataTypeVar


class SelectorBase(_Base):
    class Data(_Base.Data):
        on_select_callback: Optional[Callable[[bool, str, Any], Any]] = Field(default=None, exclude=True)

        last_select_message: Optional[str] = None
        last_select_data: Optional[Any] = Field(
            default=None, exclude=True
        )  # this is tmp we don't keep it in the schema
        last_select_timing: Optional[float] = None
        last_select_result: Optional[bool] = None

        @validator("last_select_result", allow_reuse=True)
        def _fire_last_select_result_callback(cls, v, values):  # noqa N805
            """When the check result is set, the message and data is also set"""
            callback = values.get("on_select_callback")
            if callback:
                callback(v, values["last_select_message"], values["last_select_data"])
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
    ) -> Tuple[bool, str, Any]:
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
    ) -> Tuple[bool, str, Any]:
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
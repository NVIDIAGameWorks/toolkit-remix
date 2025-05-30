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
from pydantic import BaseModel, Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from .plugin_base import Base as _Base
from .schema_base import BaseSchema as _BaseSchema


class ResultorBase(_Base, abc.ABC):
    class Data(_Base.Data):
        on_resultor_callback: Callable[[bool, str], Any] | None = Field(default=None, exclude=True)

        last_resultor_message: str | None = Field(default=None)
        last_resultor_timing: float | None = Field(default=None)
        last_resultor_result: bool | None = Field(default=None)

        @field_validator("last_resultor_result", mode="before")
        @classmethod
        def _fire_last_resultor_result_callback(cls, v: bool | None, info: ValidationInfo):
            """When the check result is set, the message and data is also set"""
            callback = info.data.get("on_resultor_callback")
            if callback and v is not None:
                callback(v, info.data.get("last_resultor_message"))
            return v

    def __init__(self):
        super().__init__()
        self.__on_result = _Event()

    def _callback_to_set(self) -> None:
        """
        Implementation of the callback to set up the event when data are changed
        Warnings: super() should be called before
        """
        super()._callback_to_set()
        self._schema.data.on_resultor_callback = self.__on_result

    def subscribe_result(self, callback: Callable[[bool, str], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_result, callback)

    @omni.usd.handle_exception
    async def result(self, schema_data: Data, schema: BaseModel) -> tuple[bool, str]:
        """
        Function that will be called to work on the result

        Args:
            schema_data: the data from the schema.
            schema: the whole schema ran by the manager

        Returns:
            bool: True if the result passed, False if not.
            str: the message you want to show, like "Succeeded to write the result here"
        """
        carb.log_info(f"Try to run selector plugin select {self.name} ...")
        st = time.time()
        result, message = await self._result(schema_data, schema)
        schema_data.last_resultor_message = message
        schema_data.last_resultor_timing = time.time() - st
        schema_data.last_resultor_result = result
        self.on_progress(1, "Finished", result)
        carb.log_info(f"\tResult: {result}: {message}")
        return result, message

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _result(self, schema_data: Data, schema: BaseModel) -> tuple[bool, str]:
        """
        Function that will be called to work on the result

        Args:
            schema_data: the data from the schema.
            schema: the whole schema ran by the manager

        Returns:
            bool: True if the result passed, False if not.
            str: the message you want to show, like "Succeeded to write the result here"
        """
        return False, "Not implemented"


class Schema(_BaseSchema):
    pass

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
from typing import Any, Optional

import omni.client
import omni.kit.app
import omni.usd
from omni.flux.validator.factory import ContextBase as _ContextBase
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from pxr import Sdf
from pydantic import Field


class ContextBaseUSD(_ContextBase, abc.ABC):
    class Data(_ContextBase.Data):
        context_name: Optional[str] = None
        create_context_if_not_exist: bool = False

        # tmp data
        computed_context: Optional[str] = Field(default=None, repr=False)  # the resulting context

    async def _set_current_context(
        self, schema_data: "ContextBaseUSD.Data", parent_context: _SetupDataTypeVar
    ) -> Optional[omni.usd.UsdContext]:
        schema_data.computed_context = ""
        if parent_context is not None:
            schema_data.computed_context = parent_context
        if schema_data.context_name is not None:
            schema_data.computed_context = schema_data.context_name  # overridden by the schema
        context = omni.usd.get_context(schema_data.computed_context)
        if not context and schema_data.create_context_if_not_exist:
            context = omni.usd.create_context(schema_data.computed_context)
        if not context:
            return None

        return context

    async def _close_stage(self, usd_context_name: str):
        """
        Function that will be called to after the check of the data. For example, save the input USD stage

        Args:
            usd_context_name: the USD context name
        """
        context = omni.usd.get_context(usd_context_name)
        stage = context.get_stage()
        # The stage was already closed
        if not stage:
            return
        root_layer = stage.GetRootLayer()
        # ugly work around to un-hold layers
        Sdf._TestTakeOwnership(root_layer)  # noqa
        await context.close_stage_async()

    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, context_plugin_data: _SetupDataTypeVar) -> None:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data of the plugin from the schema
        """
        if schema_data.computed_context is None:
            schema_data.computed_context = ""
        context = omni.usd.get_context(schema_data.computed_context)
        if context and context.can_close_stage():
            await self._close_stage(schema_data.computed_context)

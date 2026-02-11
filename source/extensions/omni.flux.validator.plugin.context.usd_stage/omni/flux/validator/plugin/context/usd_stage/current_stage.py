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

from typing import Any
from collections.abc import Awaitable, Callable

import omni.client
import omni.ui as ui
import omni.usd
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar

from .base.context_base_usd import ContextBaseUSD as _ContextBaseUSD


class CurrentStage(_ContextBaseUSD):
    class Data(_ContextBaseUSD.Data):
        save_on_exit: bool = False
        close_stage_on_exit: bool = False

    name = "CurrentStage"
    display_name = "Current Stage"
    tooltip = "This plugin will use the current opened stage"
    data_type = Data

    @omni.usd.handle_exception
    async def _check(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> tuple[bool, str]:
        """
        Function that will be called to execute the data.

        Args:
            schema_data: the USD file path to check
            parent_context: context data from the parent context

        Returns: True if the check passed, False if not
        """
        context = await self._set_current_context(schema_data, parent_context)
        if not context:
            return False, f"The context {context} doesn't exist!"
        return bool(context.get_stage()), str(omni.client.normalize_url(context.get_stage_url()))

    async def _setup(
        self,
        schema_data: Data,
        run_callback: Callable[[_SetupDataTypeVar], Awaitable[None]],
        parent_context: _SetupDataTypeVar,
    ) -> tuple[bool, str, _SetupDataTypeVar]:
        """
        Function that will be executed to set the data. Here we will open the file path and give the stage

        Args:
            schema_data: the data that we should set. Same data than check()
            run_callback: the validation that will be run in the context of this setup
            parent_context: context data from the parent context

        Returns: True if ok + message + data that need to be passed into another plugin
        """
        context = await self._set_current_context(schema_data, parent_context)
        if not context:
            return False, f"The context {schema_data.computed_context} doesn't exist!", None
        result_data = context.get_stage()
        await run_callback(schema_data.computed_context)
        return (
            True,
            str(omni.client.normalize_url(context.get_stage_url())),
            result_data,
        )

    async def _on_exit(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> tuple[bool, str]:
        """
        Function that will be called to after the check of the data. For example, save the input USD stage

        Args:
            schema_data: the data that should be checked
            parent_context: context data from the parent context

        Returns:
            bool: True if the on exit passed, False if not.
            str: the message you want to show, like "Succeeded to exit this context"
        """
        context = omni.usd.get_context(schema_data.computed_context)
        if schema_data.save_on_exit:
            layer_stack = context.get_stage().GetLayerStack(includeSessionLayers=False)

            for layer in layer_stack:
                # Only save a layer if it exists on disk
                if layer.realPath:
                    layer.Save()

        if schema_data.close_stage_on_exit:
            await self._close_stage(schema_data.computed_context)

        return True, "Exit ok"

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Any) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("Current opened stage is used", alignment=ui.Alignment.CENTER)

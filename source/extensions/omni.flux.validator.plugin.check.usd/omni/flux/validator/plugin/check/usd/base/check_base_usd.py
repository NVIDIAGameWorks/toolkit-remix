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

from typing import Any, Optional, Tuple

import carb
import omni.usd
from omni.flux.validator.factory import CheckBase as _CheckBase
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from pxr import Sdf


class CheckBaseUSD(_CheckBase):
    class Data(_CheckBase.Data):
        save_on_fix_failure: bool = True
        context_name: Optional[str] = None

    data_type = Data

    @omni.usd.handle_exception
    async def check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check if asset paths on the selected prims in the attributes listed in schema
        data's `conversion_args` are dds encoded

        Note: This is intended to be run on Shader prims.

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        schema_data.context_name = context_plugin_data
        return await super().check(schema_data, context_plugin_data, selector_plugin_data)

    @omni.usd.handle_exception
    async def fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
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

        def __save_stage():
            if schema_data.save_on_fix_failure and not result:
                context = omni.usd.get_context(context_plugin_data)
                context.save_stage()
                carb.log_info(f"\tStage saved: {context.get_stage_url()}")

        result, message, data = await super().fix(schema_data, context_plugin_data, selector_plugin_data)
        __save_stage()
        return result, message, data

    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, context_plugin_data: _SetupDataTypeVar) -> None:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data of the plugin from the schema
        """
        context = omni.usd.get_context(context_plugin_data or "")
        if context and context.can_close_stage():
            stage = context.get_stage()
            root_layer = stage.GetRootLayer()
            # ugly work around to un-hold layers
            Sdf._TestTakeOwnership(root_layer)  # noqa
            await context.close_stage_async()

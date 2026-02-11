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

import asyncio
from typing import Any

import omni.ui as ui
import omni.usd
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD


class PrintPrims(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        slow_down: bool = False
        slow_down_value: float = 0.03

    name = "PrintPrims"
    tooltip = "This plugin will print prims from the selector plugin"
    data_type = Data

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        message = "Check:\n"
        data = []
        progress = 0
        self.on_progress(progress, "Start", True)
        if selector_plugin_data:
            to_add = 100 / len(selector_plugin_data) / 100
            for prim in sorted(selector_plugin_data, key=lambda x: str(x.GetPath())):
                message += f"- {str(prim.GetPath())}\n"
                progress += to_add
                if schema_data.slow_down:
                    await asyncio.sleep(schema_data.slow_down_value)
                self.on_progress(progress, f"Add {prim.GetPath()}", True)
                data.append(prim)
        print(message)
        return True, message, data

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        message = "Fix:\n"
        data = []
        progress = 0
        self.on_progress(progress, "Start", False)
        if selector_plugin_data:
            to_add = 100 / len(selector_plugin_data) / 100
            for prim in sorted(selector_plugin_data, key=lambda x: str(x.GetPath())):
                message += f"- {str(prim.GetPath())}\n"
                progress += to_add
                if schema_data.slow_down:
                    await asyncio.sleep(schema_data.slow_down_value)
                self.on_progress(progress, f"Add {prim.GetPath()}", False)
                data.append(prim)
        print(message)
        return True, message, data

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")

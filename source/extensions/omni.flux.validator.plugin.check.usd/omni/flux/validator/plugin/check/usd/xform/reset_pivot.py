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

from numbers import Number
from typing import Any, Tuple

import omni.ui as ui
import omni.usd
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from pxr import Sdf
from pydantic import validator

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


class ResetPivot(_CheckBaseUSD):
    _ATTRIBUTE_NAME = "xformOp:translate:pivot"

    class Data(_CheckBaseUSD.Data):
        pivot_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)

        @validator("pivot_position", allow_reuse=True)
        def translate_format_valid(cls, v):  # noqa N805
            if len(v) != 3 or not all(isinstance(val, Number) for val in v):
                raise ValueError("The pivot position must be represented by a tuple of 3 float in the format (X,Y,Z).")
            return v

    name = "ResetPivot"
    tooltip = "This plugin will reset the selected prim's pivot to the desired position."
    data_type = Data
    display_name = "Reset Prim Pivot"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
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
        message = "Check:\n"
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        if selector_plugin_data:
            progress_delta = 1 / len(selector_plugin_data)
            for prim in selector_plugin_data:
                pivot = prim.GetAttribute(self._ATTRIBUTE_NAME)
                if not pivot and schema_data.pivot_position == (0.0, 0.0, 0.0):
                    is_valid = True
                    progress_message = "- SKIPPED: Prim has no pivot attribute. Default pivot transform is valid."
                else:
                    is_valid = pivot and pivot.Get() == schema_data.pivot_position
                    progress_message = (
                        "- OK: Prim has the proper pivot transform"
                        if is_valid
                        else "- INVALID: Prim has an invalid pivot transform"
                    )

                progress += progress_delta
                message += f"{progress_message}\n"
                success &= is_valid

                self.on_progress(progress, progress_message, success)

        return success, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        message = "Fix:\n"
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        if selector_plugin_data:
            progress_delta = 1 / len(selector_plugin_data)
            for prim in selector_plugin_data:
                pivot = prim.GetAttribute(self._ATTRIBUTE_NAME)
                if not pivot and schema_data.pivot_position == (0.0, 0.0, 0.0):
                    is_valid = True
                    progress_message = "- SKIPPED: Prim has no pivot attribute. Default pivot is valid."
                elif pivot.Get() == schema_data.pivot_position:
                    is_valid = True
                    progress_message = "- SKIPPED: Prim has the proper pivot transform"
                else:
                    omni.kit.commands.execute(
                        "ChangePropertyCommand",
                        prop_path=str(prim.GetPath().AppendProperty(self._ATTRIBUTE_NAME)),
                        value=schema_data.pivot_position,
                        prev=None,
                        type_to_create_if_not_exist=Sdf.ValueTypeNames.Vector3d,
                        usd_context_name=context_plugin_data,
                    )
                    is_valid = True
                    progress_message = f"- FIXED: Prim pivot set to {schema_data.pivot_position}"

                progress += progress_delta
                message += f"{progress_message}\n"
                success &= is_valid

                self.on_progress(progress, progress_message, success)

        return success, message, None

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")

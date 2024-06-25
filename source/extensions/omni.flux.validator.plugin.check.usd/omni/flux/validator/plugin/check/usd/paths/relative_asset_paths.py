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

from typing import Any, Tuple

import omni.ui as ui
import omni.usd
from omni.flux.utils.common import path_utils as _path_utils
from pxr import Sdf

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


class RelativeAssetPaths(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        pass

    name = "RelativeAssetPaths"
    tooltip = "This plugin will replace absolute asset paths with relative paths."
    data_type = Data
    display_name = "Make Asset Paths Relative"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check if the input prims have absolute paths in their asset paths

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        message = "Check:\n"
        all_pass = True
        for prim in selector_plugin_data:
            abs_paths = []
            for attr in prim.GetAttributes():
                if attr.GetTypeName() == Sdf.ValueTypeNames.Asset and attr.Get():
                    attr_path = str(attr.Get().path)
                    if _path_utils.is_absolute_path(attr_path):
                        abs_paths.append(attr_path)
                        break

            if len(abs_paths) > 0:
                message += f"- FAIL: {str(prim.GetPath())} references: {abs_paths}\n"
                all_pass = False
            else:
                message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to change all asset paths to relative.

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        message = "Fix:\n"
        all_pass = True
        stage = omni.usd.get_context(context_plugin_data).get_stage()
        base_path = stage.GetRootLayer().identifier
        with Sdf.ChangeBlock():
            for prim in selector_plugin_data:
                failing_paths = []
                for attr in prim.GetAttributes():
                    if attr.GetTypeName() == Sdf.ValueTypeNames.Asset and attr.Get():
                        attr_path = str(attr.Get().path)
                        if _path_utils.is_absolute_path(attr_path):
                            abs_path = attr.Get().resolvedPath
                            rel_path = omni.client.make_relative_url(base_path, abs_path)
                            if rel_path == abs_path:
                                # making the path relative failed
                                failing_paths.append(attr_path)
                            else:
                                attr.Set(rel_path)

                if len(failing_paths) > 0:
                    message += f"- FAIL: {str(prim.GetPath())} failed to make path relative: {failing_paths}\n"
                    all_pass = False
                else:
                    message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")

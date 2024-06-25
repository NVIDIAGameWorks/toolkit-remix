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

import re
from typing import Any, List, Tuple

import omni.ui as ui
import omni.usd
from pxr import Sdf

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


class StripExtraAttributes(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        # This list accepts regex patterns, but the pattern must match the entire property name
        keep_list: List[str] = [
            # First, keep all the attributes accessed by the Remix runtime:
            "doubleSided",
            "invertedUvs",
            "material:binding",
            "normals",
            "orientation",
            "points",
            "xformOp.*",
            "primvars:skel:jointIndices",
            "primvars:skel:jointWeights",
            # Second, keep values required for kit compatibility
            "faceVertexCounts",
            "faceVertexIndices",
            "primvars:st",
            "primvars:st:indices",
            "primvars:skel:geomBindTransform",
            "skel:skeleton",
            "skel:joints",
            "subdivisionScheme",  # needed for smooth normals when using vertex interpolation
        ]

    name = "StripExtraAttributes"
    tooltip = "This plugin will remove any non-essential properties from a mesh prim"
    data_type = Data
    display_name = "Strip Extra USD Attributes"

    def get_regex_str(self, schema_data: Data):
        return f"^(?:{'|'.join(schema_data.keep_list)})$"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check if the input prims have up to date geom subsets

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        message = "Check:\n"
        all_pass = True
        # Regex to match an entire string against a list of options.
        keep_regex = re.compile(self.get_regex_str(schema_data))
        for prim in selector_plugin_data:
            bad_props = []
            for attr in prim.GetAttributes():
                if attr.HasAuthoredValue() and not keep_regex.match(attr.GetName()):
                    bad_props.append(attr.GetName())

            if len(bad_props) > 0:
                message += f"- FAIL: {str(prim.GetPath())}, {bad_props}\n"
                all_pass = False
            else:
                message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to triangulate the mesh prims (including geom subsets)

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        message = "Fix:\n"
        all_pass = True
        # Regex to match an entire string against a list of options.
        keep_regex = re.compile(self.get_regex_str(schema_data))
        with Sdf.ChangeBlock():
            for prim in selector_plugin_data:
                attr_to_remove = []
                for attr in prim.GetAttributes():
                    if attr.HasAuthoredValue() and not keep_regex.match(attr.GetName()):
                        attr_to_remove.append(attr.GetName())

                for attr in attr_to_remove:
                    prim.RemoveProperty(attr)

                message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")

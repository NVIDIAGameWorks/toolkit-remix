"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import carb.settings
import omni.graph.core as og
from omni.graph.window.core import OmniGraphModel
from pxr import Sdf


class RemixLogicGraphModel(OmniGraphModel):
    def cull_legacy_prims(self):
        """Return True if the OgnPrim nodes should not be created in the graph"""
        return not carb.settings.get_settings().get("/persistent/omnigraph/createPrimNodes")

    def get_port_type(self, path: Sdf.Path) -> str | None:
        """Returns the description of the port's attribute type, or None if there is a problem"""
        # Get the parent's result first
        result = super().get_port_type(path)

        # If it's an unresolved union, provide more details
        attr: og.Attribute | None = self.get_attribute_from_path(path)
        if attr is not None:
            extended_type = attr.get_extended_type()
            if extended_type == og.ExtendedAttributeType.EXTENDED_ATTR_TYPE_UNION:
                union_types: list[str] = attr.get_union_types()  # type: ignore
                # A little bit sneaky here but we use the opening/closing parenthesis from port_tooltip_text
                if union_types:
                    return (
                        f"Flexible type)\n\t"
                        f"Connect a port to specify type.\n\t(Valid types: {', '.join(union_types)}"
                    )  # fmt: skip
                return (
                    "Flexible type)\n\t"
                    "Connect a port to specify type. \n\t(Could not determine valid types."
                )  # fmt: skip

            if extended_type == og.ExtendedAttributeType.EXTENDED_ATTR_TYPE_ANY:
                return (
                    "Flexible type)\n\t"
                    "Connect a port to specify type.\n\t(Valid types: Any"
                )  # fmt: skip

        return result

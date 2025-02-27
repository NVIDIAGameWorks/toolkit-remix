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

import carb
from omni.flux.material_api.placeholder_attribute import PlaceholderAttribute
from pxr import UsdShade

from .utils import get_sdr_shader_node_for_prim, get_sdr_shader_property_default_value


class UsdShadeInputPlaceholderAttribute(PlaceholderAttribute):
    def Get(self, time_code=0):  # noqa: N802
        """
        Override to get the default value of the property this class acts as a stand in for from the
        default value metadata.
        """

        sdr_shader_node = get_sdr_shader_node_for_prim(self._prim)
        if not sdr_shader_node:  # pragma: no cover
            carb.log_error(f"Cannot get Sdr.ShaderNode for prim at: '{self._prim.GetPath()}'")
            return None

        input_name = self._name.replace(UsdShade.Tokens.inputs, "")
        sdr_shader_property = sdr_shader_node.GetInput(input_name)
        if not sdr_shader_property:  # pragma: no cover
            carb.log_error(f"Cannot get Sdr.ShaderProperty input: '{input_name}' for prim at: '{self._prim.GetPath()}'")
            return None

        return get_sdr_shader_property_default_value(sdr_shader_property, self._metadata)

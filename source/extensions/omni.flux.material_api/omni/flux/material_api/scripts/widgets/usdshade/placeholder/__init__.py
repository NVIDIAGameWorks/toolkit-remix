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

__doc__ = """This module provides functionality to retrieve UsdShadePropertyPlaceholder objects for USD prims to
drive UI components."""

__all__ = ["get_placeholder_properties_for_prim"]

from typing import List, Optional

import carb
from pxr import Usd, UsdShade

from .placeholder import UsdShadePropertyPlaceholder


def get_placeholder_properties_for_prim(
    prim: Usd.Prim, args: Optional[dict] = None
) -> List[UsdShadePropertyPlaceholder]:
    """Retrieves a list of UsdShadePropertyPlaceholder objects for a given USD prim.

    This function builds placeholders used for driving the UI by examining the
    type of USD prim provided. Depending on whether the prim is a Shader, Material,
    or NodeGraph, it delegates to the corresponding builder class to construct
    the placeholders.

    Args:
        prim (Usd.Prim): The USD primitive for which to retrieve property placeholders.
        args (dict): A dictionary of arguments that are passed to the builder classes.

    Returns:
        List[:obj:`UsdShadePropertyPlaceholder`]: A list of UsdShadePropertyPlaceholder objects
        that represent the properties of the given prim within the UI.

    Raises:
        A warning is logged if the provided prim is not of type Shader, Material, or NodeGraph.
    """

    from .material_builder import MaterialPropertiesBuilder
    from .nodegraph_builder import NodeGraphPropertiesBuilder
    from .shader_builder import ShaderPropertiesBuilder

    if args is None:
        args = {}

    if prim.IsA(UsdShade.Shader):
        return ShaderPropertiesBuilder(prim, args).build()

    if prim.IsA(UsdShade.Material):
        return MaterialPropertiesBuilder(prim, args).build()

    if prim.IsA(UsdShade.NodeGraph):
        return NodeGraphPropertiesBuilder(prim, args).build()

    carb.log_warn(f"Expected UsdShade prim at: '{prim.GetPath()}'")  # pragma: no cover
    return []  # pragma: no cover

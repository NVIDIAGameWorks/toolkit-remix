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

import omni.usd
from pxr import Usd, UsdGeom, UsdShade


def get_materials_from_prim_paths(
    prim_paths: list[str], context_name: str = ""
) -> list[UsdShade.Material | UsdShade.MaterialBindingAPI | None]:
    """
    For each str prim path, get the materials that are used by the prim.

    Args:
        prim_paths: list of str
        context_name: str

    Returns:
        list of UsdShade.Material, UsdShade.MaterialBindingAPI, or None
    """

    def get_mat_from_geo(_prim):
        if _prim.IsA(UsdGeom.Subset) or _prim.IsA(UsdGeom.Mesh):
            _material, _ = UsdShade.MaterialBindingAPI(_prim).ComputeBoundMaterial()
            if _material:
                return _material
        return None

    usd_context = omni.usd.get_context(context_name)
    stage = usd_context.get_stage()

    material_prims = []
    for prim_path in prim_paths:
        prim = stage.GetPrimAtPath(prim_path)
        if prim.IsValid():
            if prim.IsA(UsdShade.Material):
                material_prims.append(UsdShade.Material(prim))
            elif prim.IsA(UsdShade.Shader):
                material_prims.append(UsdShade.Material(prim.GetParent()))
            else:
                display_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
                children_iterator = iter(Usd.PrimRange(prim, display_predicate))
                for child_prim in children_iterator:
                    mat_mesh = get_mat_from_geo(child_prim)
                    if mat_mesh:
                        material_prims.append(mat_mesh)
    return material_prims

"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import typing

import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Usd, UsdGeom, UsdShade

if typing.TYPE_CHECKING:
    from pxr import Sdf


class Setup:
    def __init__(self, context_name: str):
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context = omni.usd.get_context(context_name)

    def get_material_layer_stack(self, path: "Sdf.Path"):
        stage = self._context.get_stage()
        prim = stage.GetPrimAtPath(path)
        stacks = prim.GetPrimStack()
        return [stack.layer for stack in stacks]

    def get_materials_from_prim(self, prim, from_reference_layer_path: str = None):  # noqa PLR1710
        def traverse_instanced_children(_prim):  # noqa R503
            for child in _prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate):
                if from_reference_layer_path is not None:
                    stacks = child.GetPrimStack()
                    if from_reference_layer_path not in [stack.layer.realPath for stack in stacks]:
                        yield from traverse_instanced_children(child)
                        continue
                yield child
                yield from traverse_instanced_children(child)

        def get_mat_from_geo(_prim):
            _material, _ = UsdShade.MaterialBindingAPI(_prim).ComputeBoundMaterial()
            if _material:
                return _material.GetPath()
            return None

        result = []
        if prim.IsValid() and (prim.IsA(UsdGeom.Subset) or prim.IsA(UsdGeom.Mesh)):
            mat_prim = get_mat_from_geo(prim)
            if mat_prim:
                result.append(mat_prim)
        return result

    def destroy(self):
        _reset_default_attrs(self)

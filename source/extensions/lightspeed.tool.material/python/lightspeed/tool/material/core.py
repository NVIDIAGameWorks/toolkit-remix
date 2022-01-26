"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import os
from typing import List

import omni.usd
from lightspeed.common import constants
from pxr import Sdf, Usd, UsdShade


class ToolMaterialCore:
    @staticmethod
    def _get_shader_from_material(material: Usd.Prim):
        shader, _, _ = material.ComputeSurfaceSource()
        if not shader:
            # Although the schema is new, there can still be old parameter overrides if the MDL is referenced into the
            # stage. Need to convert those old overrides.
            shader, _, _ = material.ComputeSurfaceSource("mdl")
        return shader if shader else None

    @staticmethod
    def get_materials_from_prim_paths(prim_paths: List[str]):
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        material_prims = []
        for prim_path in prim_paths:
            prim = stage.GetPrimAtPath(prim_path)
            if prim.IsValid():
                if str(prim_path).startswith(constants.INSTANCE_PATH):
                    refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
                    for (ref, _) in refs_and_layers:
                        if not ref.assetPath:
                            material, relationship = UsdShade.MaterialBindingAPI(
                                stage.GetPrimAtPath(ref.primPath)
                            ).ComputeBoundMaterial()
                            if material:
                                material_prims.append(material)
                elif str(prim_path).startswith(constants.MESH_PATH):
                    material, relationship = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                    if material:
                        material_prims.append(material)
                elif prim.IsA(UsdShade.Material):
                    material_prims.append(prim)
        return material_prims

    @staticmethod
    def set_new_mdl_to_shaders(shaders, mdl_path):
        for shader in shaders:
            shader.SetSourceAsset(Sdf.AssetPath(mdl_path), "mdl")
            _mtl_name = os.path.basename(mdl_path if not mdl_path.endswith(".mdl") else mdl_path.rpartition(".")[0])
            shader.SetSourceAssetSubIdentifier(_mtl_name, "mdl")

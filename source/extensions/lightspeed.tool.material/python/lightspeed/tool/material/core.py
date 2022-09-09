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
import shutil
from pathlib import Path
from typing import List, Optional

import carb
import omni.client
import omni.kit.commands
import omni.usd
from lightspeed.common import constants
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from pxr import Sdf, Usd, UsdGeom, UsdShade


class ToolMaterialCore:
    @staticmethod
    def copy_default_mat_reference() -> List[str]:
        material_files = []
        current_path = Path(__file__).parent
        for _ in range(3):
            current_path = current_path.parent
        material_usd_dir = current_path.joinpath("data", "material_usd")

        layer_manager = LayerManagerCore()
        replacement_layer = layer_manager.get_layer(LayerType.replacement)
        if not replacement_layer:
            return []
        dst_dir = Path(replacement_layer.identifier).parent.joinpath(constants.MATERIALS_FOLDER)
        for usd_file in os.listdir(str(material_usd_dir)):
            material_files.append(str(dst_dir.joinpath(usd_file)))
            if dst_dir.joinpath(usd_file).exists():
                continue
            if not dst_dir.exists():
                dst_dir.mkdir()
            shutil.copy(str(material_usd_dir.joinpath(usd_file)), str(dst_dir))
            carb.log_info(f"Copy {str(material_usd_dir.joinpath(usd_file))} in {dst_dir}")
        return material_files

    @staticmethod
    def get_shader_from_material(material: Usd.Prim):
        shader, _, _ = material.ComputeSurfaceSource()
        if not shader:
            # Although the schema is new, there can still be old parameter overrides if the MDL is referenced into the
            # stage. Need to convert those old overrides.
            shader, _, _ = material.ComputeSurfaceSource("mdl")
        return shader if shader else None

    @staticmethod
    def get_materials_from_prim_paths(prim_paths: List[str]):
        def get_mat_from_geo(_prim):
            if _prim.IsA(UsdGeom.Subset) or _prim.IsA(UsdGeom.Mesh):
                _material, _ = UsdShade.MaterialBindingAPI(_prim).ComputeBoundMaterial()
                if _material:
                    return _material
            return None

        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        material_prims = []
        for prim_path in prim_paths:  # noqa PLR1702
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

    @staticmethod
    def get_corresponding_usd_mat_from_mdl_path(material_files, mdl_path) -> Optional[str]:
        # grab the good reference material
        sub_id = os.path.basename(mdl_path).rpartition(".")[0]
        for material_file in material_files:
            stage = Usd.Stage.Open(material_file)
            iterator = iter(stage.TraverseAll())
            for prim in iterator:
                if prim.IsValid() and prim.IsA(UsdShade.Shader):
                    shader = UsdShade.Shader(prim)
                    if sub_id == shader.GetSourceAssetSubIdentifier("mdl"):
                        return material_file
        return None

    @staticmethod
    def get_mat_prim_from_usd(material_file) -> Optional[Usd.Prim]:
        # grab the good reference material
        stage = Usd.Stage.Open(material_file)
        iterator = iter(stage.TraverseAll())
        for prim in iterator:
            if prim.IsValid() and prim.IsA(UsdShade.Material):
                return prim
        return None

    @staticmethod
    def anchor_reference_asset_path_to_layer(ref: Sdf.Reference, intro_layer: Sdf.Layer, anchor_layer: Sdf.Layer):
        asset_path = ref.assetPath
        if asset_path:
            asset_path = intro_layer.ComputeAbsolutePath(asset_path)
            if not anchor_layer.anonymous:
                asset_path = omni.client.normalize_url(
                    omni.client.make_relative_url(anchor_layer.identifier, asset_path)
                )

            # make a copy as Reference is immutable
            ref = Sdf.Reference(
                assetPath=asset_path.replace("\\", "/"),
                primPath=ref.primPath,
                layerOffset=ref.layerOffset,
                customData=ref.customData,
            )
        return ref

    @staticmethod
    def set_new_mdl_to_shaders(shaders, material_prims, stage, mdl_path):
        material_files = ToolMaterialCore.copy_default_mat_reference()
        new_mat_ref_path = ToolMaterialCore.get_corresponding_usd_mat_from_mdl_path(material_files, mdl_path)
        if not new_mat_ref_path:
            carb.log_error(f"Can't find corresponding material reference for mdl {mdl_path}")
            return
        # group material with shaders
        material_dict = {}
        for mat in material_prims:
            for shader in shaders:
                if mat.GetPath().pathString in shader.GetPath().pathString:
                    material_dict[mat] = shader
                    break

        edit_layer = stage.GetEditTarget().GetLayer()
        default_ref_prim = ToolMaterialCore.get_mat_prim_from_usd(new_mat_ref_path)
        final_path = new_mat_ref_path
        # make the path relative to current edit target layer
        if not edit_layer.anonymous:
            final_path = omni.client.make_relative_url(edit_layer.realPath, new_mat_ref_path)
        for mat, _ in material_dict.items():
            refs_and_layers = omni.usd.get_composed_references_from_prim(mat.GetPrim())
            for (ref, layer) in refs_and_layers:
                new_ref = Sdf.Reference(assetPath=final_path, primPath=default_ref_prim.GetPath())
                ref_remove = ToolMaterialCore.anchor_reference_asset_path_to_layer(ref, layer, edit_layer)

                omni.kit.commands.execute(
                    "ReplaceReference",
                    stage=stage,
                    prim_path=mat.GetPath(),
                    old_reference=ref_remove,
                    new_reference=new_ref,
                )
                # normally we only have 1 material reference.
                break

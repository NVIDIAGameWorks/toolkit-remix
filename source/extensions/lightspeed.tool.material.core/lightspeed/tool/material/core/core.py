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

import os
import shutil
from pathlib import Path
from typing import List, Optional

import carb
import omni.client
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from omni.flux.utils.common.materials import get_materials_from_prim_paths as _get_materials_from_prim_paths
from pxr import Sdf, Usd, UsdShade


class ToolMaterialCore:
    @staticmethod
    def copy_default_mat_reference() -> List[str]:
        material_files = []
        current_path = Path(__file__)
        for _ in range(5):
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
    async def get_shader_subidentifier(shader: UsdShade.Shader):
        subid_list = await omni.kit.material.library.get_subidentifier_from_material(
            shader, lambda x: x, use_functions=False
        )
        return str(subid_list[0]) if subid_list else None

    @staticmethod
    def get_shader_from_material(material: Usd.Prim):
        shader, _, _ = material.ComputeSurfaceSource()
        if not shader:
            # Although the schema is new, there can still be old parameter overrides if the MDL is referenced into the
            # stage. Need to convert those old overrides.
            shader, _, _ = material.ComputeSurfaceSource("mdl")
        return shader if shader else None

    @staticmethod
    def get_materials_from_prim_paths(prim_paths: List[str], context_name: str = ""):
        return _get_materials_from_prim_paths(prim_paths, context_name)

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
        with omni.kit.undo.group():
            for mat, _ in material_dict.items():
                refs_and_layers = omni.usd.get_composed_references_from_prim(mat.GetPrim())
                for ref, layer in refs_and_layers:
                    new_ref = Sdf.Reference(assetPath=final_path, primPath=default_ref_prim.GetPath())
                    ref_remove = ToolMaterialCore.anchor_reference_asset_path_to_layer(ref, layer, edit_layer)

                    omni.kit.commands.execute(
                        "SetExplicitReferencesCommand",
                        stage=stage,
                        prim_path=str(mat.GetPath()),
                        reference=ref_remove,
                        to_set=[new_ref],
                    )
                    # normally we only have 1 material reference.

    @staticmethod
    def remove_material_override(context_name: str, prim: Usd.Prim) -> bool:
        mat_prim = ToolMaterialCore.get_materials_from_prim_paths([prim.GetPath()], context_name=context_name)[0]
        if mat_prim:
            omni.kit.commands.execute(
                "RemoveProperty",
                prop_path=prim.GetRelationship(constants.MATERIAL_RELATIONSHIP).GetPath(),
                usd_context_name=context_name,
            )
            omni.kit.commands.execute("DeletePrims", paths=[mat_prim.GetPath()], context_name=context_name)
            return True
        return False

    @staticmethod
    def create_new_material_override(
        context_name: str,
        desired_prim_path: str,
        default_material_mdl_url: str,
        default_material_mdl_name: str,
        prim: Usd.Prim,
    ) -> bool:
        stage = omni.usd.get_context(context_name).get_stage()

        # create a unique valid prim path based on the filename
        mtl_path = omni.usd.get_stage_next_free_path(stage, desired_prim_path, False)

        # create a new OmniPBR node
        omni.kit.commands.execute(
            "CreateMdlMaterialPrim",
            mtl_url=default_material_mdl_url,
            mtl_name=default_material_mdl_name,
            mtl_path=mtl_path,
            stage=stage,
            context_name=context_name,
        )

        # validate the new material was created
        output_material_prim = stage.GetPrimAtPath(mtl_path)
        if not omni.usd.get_shader_from_material(output_material_prim, get_prim=True):
            return False

        # bind newly created material to desired prim
        omni.kit.commands.execute(
            "BindMaterial",
            prim_path=prim.GetPath(),
            material_path=output_material_prim.GetPath(),
            strength=UsdShade.Tokens.strongerThanDescendants,
            context_name=context_name,
        )

        return True

    @staticmethod
    def convert_materials(prims: List[Usd.Prim], mdl_file_name: str, context_name: str = ""):
        usd_context = omni.usd.get_context(context_name)
        stage = usd_context.get_stage()

        prim_paths = [p.GetPath() for p in prims]
        material_prims = ToolMaterialCore.get_materials_from_prim_paths(prim_paths, context_name=context_name)
        shaders = [ToolMaterialCore.get_shader_from_material(material_prim) for material_prim in material_prims]

        for prim in prims:
            if prim.IsValid() and prim.IsA(UsdShade.Shader):
                shaders.append(UsdShade.Shader(prim))

        carb.log_info(f"Convert selection Materials to use: {mdl_file_name}")
        carb.log_verbose(str(shaders))
        ToolMaterialCore.set_new_mdl_to_shaders(shaders, material_prims, stage, mdl_file_name)

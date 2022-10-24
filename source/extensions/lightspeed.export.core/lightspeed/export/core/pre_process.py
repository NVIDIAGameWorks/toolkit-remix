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

import carb
import omni.client
import omni.ext
import omni.usd
from lightspeed.common import constants
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from pxr import Sdf, Usd


def preprocess(layer_manager: LayerManagerCore, context_name: str = ""):
    """
    Pre process to fully resolve reference stacks for tweaked materials and meshes
    """
    capture_layer = layer_manager.get_layer(LayerType.capture)
    autoupscale_layer = layer_manager.get_layer(LayerType.autoupscale)
    replacements_layer = layer_manager.get_layer(LayerType.replacement)
    stage = omni.usd.get_context(context_name).get_stage()
    with Usd.EditContext(stage, replacements_layer):
        with Sdf.ChangeBlock():
            mat_prim = stage.GetPrimAtPath(constants.ROOTNODE_LOOKS)
            all_capture_mats = mat_prim.GetAllChildren()
            for prim in all_capture_mats:
                # if Prim has any properties in the replacements layer
                if replacements_layer.GetPrimAtPath(prim.GetPath()) or (
                    autoupscale_layer is not None and autoupscale_layer.GetPrimAtPath(prim.GetPath())
                ):
                    _cleanup_capture_refs(
                        prim, capture_layer, constants.MATERIALS_FOLDER + "/", constants.CAPTURED_MAT_PATH_PREFIX
                    )

            mesh_prim = stage.GetPrimAtPath(constants.ROOTNODE_MESHES)
            all_capture_meshes = mesh_prim.GetAllChildren()
            for prim in all_capture_meshes:
                # if Prim has any properties in the replacements layer
                if replacements_layer.GetPrimAtPath(prim.GetPath()) or (
                    autoupscale_layer is not None and autoupscale_layer.GetPrimAtPath(prim.GetPath())
                ):
                    _cleanup_capture_refs(
                        prim, capture_layer, constants.MESHES_FOLDER + "/", constants.CAPTURED_MESH_PATH_PREFIX
                    )
                _maybe_preserve_original_draw(prim, capture_layer)

            light_prim = stage.GetPrimAtPath(constants.ROOTNODE_LIGHTS)
            all_capture_lights = light_prim.GetAllChildren()
            for prim in all_capture_lights:
                # if Prim has any properties in the replacements layer
                if replacements_layer.GetPrimAtPath(prim.GetPath()) or (
                    autoupscale_layer is not None and autoupscale_layer.GetPrimAtPath(prim.GetPath())
                ):
                    _cleanup_capture_refs(
                        prim, capture_layer, constants.LIGHTS_FOLDER + "/", constants.CAPTURED_LIGHT_PATH_PREFIX
                    )


def _cleanup_capture_refs(prim, capture_layer: Sdf.Layer, capture_folder, ref_path_prefix):
    """
    Promote all references to replacements layer
    """
    refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
    refs = []
    for ref, ref_layer in refs_and_layers:
        # Need to convert references to absolute paths.
        refs.append(
            Sdf.Reference(
                assetPath=Sdf.ComputeAssetPathRelativeToLayer(ref_layer, ref.assetPath),
                primPath=ref.primPath,
                customData=ref.customData,
            )
        )

    # Check if the prim isn't present in the current capture layer.
    if len(refs) == 0 and not capture_layer.GetPrimAtPath(prim.GetPath()):
        rel_path = capture_folder + prim.GetName() + ".usd"

        # base reference may have been left out accidentally, so check if ref was intentionally deleted
        intentionally_deleted = False
        stack = prim.GetPrimStack()
        for prim_spec in stack:
            if prim_spec.HasInfo(Sdf.PrimSpec.ReferencesKey):
                op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
                if op.isExplicit:
                    intentionally_deleted = True
                    break
                desired_abs_path = Sdf.ComputeAssetPathRelativeToLayer(prim_spec.layer, rel_path)
                for ref in op.deletedItems:
                    if ref.assetPath == desired_abs_path:
                        intentionally_deleted = True
                        break

        # Not intentionally deleted, so restore the ref to the capture asset
        if not intentionally_deleted:
            abs_path = Sdf.ComputeAssetPathRelativeToLayer(capture_layer, rel_path)
            if not os.path.exists(abs_path):
                carb.log_error("Missing base USD for prim " + prim.GetName())
            refs = [Sdf.Reference(assetPath=abs_path, primPath=ref_path_prefix + prim.GetName())]

    prim.GetReferences().SetReferences(refs)


def _file_in_folder(file_path, folder_path):
    abs_file_path = os.path.abspath(file_path)
    abs_folder_path = os.path.abspath(folder_path)
    return abs_file_path.startswith(abs_folder_path)


def _maybe_preserve_original_draw(prim, capture_layer):
    original_mesh = prim.GetChild("mesh")
    if original_mesh and len(prim.GetAllChildren()) > 1:
        # Original mesh is still present, but new children are as well. Check for changes to the original
        stack = original_mesh.GetPrimStack()
        if len(stack) == 1:
            ref_path = stack[0].layer.realPath
            capture_folder = os.path.dirname(capture_layer.realPath)
            if _file_in_folder(ref_path, capture_folder) and ref_path.endswith(prim.GetName() + ".usd"):
                # mesh is unaltered capture.  Need to exclude it and flag the runtime to preserve the original
                # draw call.
                attr = prim.CreateAttribute(constants.PRESERVE_ORIGINAL_ATTRIBUTE, Sdf.ValueTypeNames.Int)
                attr.Set(1)
                # delete the reference to the original captured mesh.
                refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
                refs = []
                for ref, _layer in refs_and_layers:
                    # Need to convert references to absolute paths.
                    if not _file_in_folder(ref.assetPath, capture_folder):
                        refs.append(ref)
                prim.GetReferences().SetReferences(refs)

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
from lightspeed.layer_manager.scripts.core import LayerManagerCore, LayerType
from pxr import Sdf, Usd


def preprocess(layer_manager: LayerManagerCore):
    """
    Pre process to fully resolve reference stacks for tweaked materials and meshes
    """
    capture_layer = layer_manager.get_layer(LayerType.capture)
    autoupscale_layer = layer_manager.get_layer(LayerType.autoupscale)
    replacements_layer = layer_manager.get_layer(LayerType.replacement)
    stage = omni.usd.get_context().get_stage()
    with Usd.EditContext(stage, replacements_layer):
        with Sdf.ChangeBlock():
            mat_prim = stage.GetPrimAtPath(constants.ROOTNODE_LOOKS)
            all_capture_mats = mat_prim.GetAllChildren()
            for prim in all_capture_mats:
                # if Prim has any properties in the replacements layer
                if (
                    replacements_layer.GetPrimAtPath(prim.GetPath())
                    or autoupscale_layer is not None
                    and autoupscale_layer.GetPrimAtPath(prim.GetPath())
                ):
                    _cleanup_capture_refs(prim, capture_layer, constants.MATERIALS_FOLDER + "/")

            mesh_prim = stage.GetPrimAtPath(constants.ROOTNODE_MESHES)
            all_capture_meshes = mesh_prim.GetAllChildren()
            for prim in all_capture_meshes:
                # if Prim has any properties in the replacements layer
                if (
                    replacements_layer.GetPrimAtPath(prim.GetPath())
                    or autoupscale_layer is not None
                    and autoupscale_layer.GetPrimAtPath(prim.GetPath())
                ):
                    _cleanup_capture_refs(prim, capture_layer, constants.MESHES_FOLDER + "/")


def _cleanup_capture_refs(prim, capture_layer: Sdf.Layer, capture_folder):
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
            refs = [Sdf.Reference(assetPath=abs_path, primPath=prim.GetPath())]

    prim.GetReferences().SetReferences(refs)

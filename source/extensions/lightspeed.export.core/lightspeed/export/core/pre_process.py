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
    # TODO TREX-2111: We should be merging the replacements layers before running the pre processor, and only
    # supporting a single replacements layer here.
    override_layers = [replacements_layer]
    if autoupscale_layer:
        override_layers.append(autoupscale_layer)
    stage = omni.usd.get_context(context_name).get_stage()
    with Usd.EditContext(stage, replacements_layer):
        with Sdf.ChangeBlock():
            mat_prim = stage.GetPrimAtPath(constants.ROOTNODE_LOOKS)
            all_capture_mats = mat_prim.GetAllChildren()
            for prim in all_capture_mats:
                # if Prim has any properties in the replacements layer
                if _is_prim_overridden(prim.GetPath(), override_layers):
                    capture_abs_path = _get_capture_asset_path(prim, capture_layer, constants.MATERIALS_FOLDER + "/")
                    capture_prim_path = constants.CAPTURED_MAT_PATH_PREFIX + prim.GetName()
                    _cleanup_capture_refs(
                        stage,
                        prim,
                        capture_layer,
                        override_layers,
                        capture_abs_path,
                        capture_prim_path,
                        None,
                    )

            mesh_prim = stage.GetPrimAtPath(constants.ROOTNODE_MESHES)
            all_capture_meshes = mesh_prim.GetAllChildren()
            for prim in all_capture_meshes:
                # if Prim has any properties in the replacements layer
                if _is_prim_overridden(prim.GetPath(), override_layers):
                    capture_abs_path = _get_capture_asset_path(prim, capture_layer, constants.MESHES_FOLDER + "/")
                    capture_prim_path = constants.CAPTURED_MESH_PATH_PREFIX + prim.GetName()
                    _cleanup_capture_refs(
                        stage, prim, capture_layer, override_layers, capture_abs_path, capture_prim_path, "mesh"
                    )

            light_prim = stage.GetPrimAtPath(constants.ROOTNODE_LIGHTS)
            all_capture_lights = light_prim.GetAllChildren()
            for prim in all_capture_lights:
                # if Prim has any properties in the replacements layer
                if _is_prim_overridden(prim.GetPath(), override_layers):
                    capture_abs_path = _get_capture_asset_path(prim, capture_layer, constants.LIGHTS_FOLDER + "/")
                    capture_prim_path = constants.CAPTURED_LIGHT_PATH_PREFIX + prim.GetName()
                    _cleanup_capture_refs(
                        stage, prim, capture_layer, override_layers, capture_abs_path, capture_prim_path, None
                    )


def _cleanup_capture_refs(
    stage, prim, capture_layer: Sdf.Layer, override_layers, capture_abs_path, capture_prim_path, preserve_original_child
):
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
    if not capture_layer.GetPrimAtPath(prim.GetPath()):
        # base reference may have been left out accidentally, so check if ref was intentionally deleted
        intentionally_deleted = False
        stack = prim.GetPrimStack()
        for prim_spec in stack:
            if prim_spec.HasInfo(Sdf.PrimSpec.ReferencesKey):
                op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
                if op.isExplicit:
                    intentionally_deleted = True
                    break
                for ref in op.deletedItems:
                    if prim_spec.layer.ComputeAbsolutePath(ref.assetPath) == capture_abs_path:
                        intentionally_deleted = True
                        break

        # Not intentionally deleted, so restore the ref to the capture asset
        if not intentionally_deleted:
            if not os.path.exists(capture_abs_path):
                carb.log_error("Missing base USD for prim " + prim.GetName())

            if preserve_original_child is not None and not _is_prim_overridden(
                prim.GetPath().AppendChild(preserve_original_child), override_layers
            ):
                if not refs and not prim.GetChildren():
                    # no references and no children means that this was an ignorable override
                    #   (This is usually caused by a change to the visibility property.)
                    carb.log_warn("Preprocessing removed meaningless override on prim " + str(prim.GetPath()))
                    stage.RemovePrim(prim.GetPath())
                else:
                    # No mesh alterations in replacements, need to preserve original call
                    attr = prim.CreateAttribute(constants.PRESERVE_ORIGINAL_ATTRIBUTE, Sdf.ValueTypeNames.Int)
                    attr.Set(1)
            else:
                # Need to restore the original capture reference.
                refs.insert(0, Sdf.Reference(assetPath=capture_abs_path, primPath=capture_prim_path))
    prim.GetReferences().SetReferences(refs)


def _file_in_folder(file_path, folder_path):
    abs_file_path = os.path.abspath(file_path)
    abs_folder_path = os.path.abspath(folder_path)
    return abs_file_path.startswith(abs_folder_path)


def _is_prim_overridden(prim_path, override_layers):
    return any(layer.GetPrimAtPath(prim_path) for layer in override_layers)


def _get_capture_asset_path(prim, capture_layer, capture_folder):
    return Sdf.ComputeAssetPathRelativeToLayer(capture_layer, capture_folder + prim.GetName() + ".usd")

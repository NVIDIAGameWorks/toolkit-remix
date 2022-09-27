"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb
import omni.client
import omni.usd
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Usd

_DEFAULT_PRIM_TAG = "<Default Prim>"


class Setup:
    def __init__(self, context_name: str):
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context = omni.usd.get_context(context_name)

    @staticmethod
    def switch_ref_abs_to_rel_path(stage, path):
        edit_layer = stage.GetEditTarget().GetLayer()
        # make the path relative to current edit target layer
        if not edit_layer.anonymous:
            return omni.client.make_relative_url(edit_layer.realPath, path)
        return path

    @staticmethod
    def get_reference_prim_path_from_asset_path(
        new_asset_path: str, layer: Sdf.Layer, edit_target_layer: Sdf.Layer, ref: Sdf.Reference, can_return_default=True
    ) -> str:
        abs_new_asset_path = omni.client.normalize_url(edit_target_layer.ComputeAbsolutePath(new_asset_path))
        abs_asset_path = omni.client.normalize_url(layer.ComputeAbsolutePath(ref.assetPath))
        # if the new path is the same that the old one, and there is a prim path, we return the current prim path
        if abs_new_asset_path == abs_asset_path and ref.primPath:
            return str(ref.primPath)
        if abs_new_asset_path == abs_asset_path and not ref.primPath and can_return_default:
            return _DEFAULT_PRIM_TAG

        # Try to see if there is a default prim on the new path
        if can_return_default:
            ref_stage = Usd.Stage.Open(abs_new_asset_path)
            ref_root_prim = ref_stage.GetDefaultPrim()
            if ref_root_prim and ref_root_prim.IsValid():
                return _DEFAULT_PRIM_TAG

        # If there is not a default prim, return the previous one (the UI will check if the mesh exist)
        return str(ref.primPath)

    @staticmethod
    def ref_prim_path_is_default_prim(prim_path: str):
        return prim_path == _DEFAULT_PRIM_TAG

    @staticmethod
    def get_ref_default_prim_tag():
        return _DEFAULT_PRIM_TAG

    @staticmethod
    def is_ref_prim_path_valid(asset_path: str, prim_path: str, layer: Sdf.Layer, log_error=True):
        abs_new_asset_path = omni.client.normalize_url(layer.ComputeAbsolutePath(asset_path))
        _, entry = omni.client.stat(abs_new_asset_path)
        if not entry.flags & omni.client.ItemFlags.READABLE_FILE:
            return False
        ref_stage = Usd.Stage.Open(abs_new_asset_path)
        if prim_path == _DEFAULT_PRIM_TAG:
            ref_root_prim = ref_stage.GetDefaultPrim()
            if ref_root_prim and ref_root_prim.IsValid():
                return True
            if log_error:
                carb.log_error(f"No default prim find in {abs_new_asset_path}")
            return False
        iterator = iter(ref_stage.TraverseAll())
        for prim in iterator:
            if str(prim.GetPath()) == prim_path:
                return True
        if log_error:
            carb.log_error(f"{prim_path} can't be find in {abs_new_asset_path}")
        return False

    def add_new_reference(
        self, stage: Usd.Stage, prim_path: Sdf.Path, asset_path: str, layer: Sdf.Layer
    ) -> Sdf.Reference:
        asset_path = omni.client.normalize_url(omni.client.make_relative_url(layer.identifier, asset_path))
        new_ref = Sdf.Reference(assetPath=asset_path.replace("\\", "/"), primPath=Sdf.Path())
        omni.kit.commands.execute(
            "AddReference",
            stage=stage,
            prim_path=prim_path,
            reference=new_ref,
        )
        return new_ref

    def __anchor_reference_asset_path_to_layer(
        self, ref: Sdf.Reference, intro_layer: Sdf.Layer, anchor_layer: Sdf.Layer
    ):
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

    def remove_reference(
        self, stage: Usd.Stage, prim_path: Sdf.Path, ref: Sdf.Reference, intro_layer: Sdf.Layer
    ) -> Sdf.Reference:
        edit_target_layer = stage.GetEditTarget().GetLayer()
        # When removing a reference on a different layer, the deleted assetPath should be relative to edit target layer,
        # not introducing layer
        if intro_layer and intro_layer != edit_target_layer:
            ref = self.__anchor_reference_asset_path_to_layer(ref, intro_layer, edit_target_layer)
        omni.kit.commands.execute(
            "RemoveReference",
            stage=stage,
            prim_path=str(prim_path),
            reference=ref,
        )

    def on_reference_edited(
        self,
        stage: Usd.Stage,
        prim_path: Sdf.Path,
        ref: Sdf.Reference,
        new_ref_asset_path: str,
        new_ref_prim_path: str,
        intro_layer: Sdf.Layer,
    ) -> Sdf.Reference:
        new_ref_prim_path = Sdf.Path() if new_ref_prim_path == _DEFAULT_PRIM_TAG else Sdf.Path(new_ref_prim_path)
        new_ref = Sdf.Reference(assetPath=new_ref_asset_path.replace("\\", "/"), primPath=new_ref_prim_path)

        edit_target_layer = stage.GetEditTarget().GetLayer()
        # When replacing a reference on a different layer, the replaced assetPath should be relative to
        # edit target layer, not introducing layer
        if intro_layer != edit_target_layer:
            ref = self.__anchor_reference_asset_path_to_layer(ref, intro_layer, edit_target_layer)

        if ref == new_ref:
            carb.log_info(f"Reference {ref.assetPath} was not replaced")
            return None

        omni.kit.commands.execute(
            "ReplaceReference",
            stage=stage,
            prim_path=prim_path,
            old_reference=ref,
            new_reference=new_ref,
        )
        carb.log_info(f"Reference {new_ref_asset_path} was replaced")
        return new_ref

    @staticmethod
    def is_absolute_path(path: str) -> bool:
        return _path_utils.is_absolute_path(path)

    @staticmethod
    def is_file_path_valid(path: str, layer: Sdf.Layer, log_error: bool = True) -> bool:
        return _path_utils.is_file_path_valid(path, layer=layer, log_error=log_error)

    def destroy(self):
        _reset_default_attrs(self)

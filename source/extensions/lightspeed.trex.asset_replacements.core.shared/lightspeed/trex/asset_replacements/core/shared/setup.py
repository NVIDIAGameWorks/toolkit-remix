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
from pathlib import Path
from typing import List, Union

import carb
import omni.client
import omni.usd
from lightspeed.common import constants
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Usd, UsdGeom

if typing.TYPE_CHECKING:
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemInstanceMesh as _ItemInstanceMesh
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
        ItemReferenceFileMesh as _ItemReferenceFileMesh,
    )

_DEFAULT_PRIM_TAG = "<Default Prim>"


class Setup:
    def __init__(self, context_name: str):
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context = omni.usd.get_context(context_name)

    def get_children_from_prim(self, prim, from_reference_layer_path: str = None):  # noqa PLR1710
        def traverse_instanced_children(_prim):  # noqa R503
            for child in _prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate):
                if from_reference_layer_path is not None:
                    stacks = child.GetPrimStack()
                    if from_reference_layer_path not in [stack.layer.realPath for stack in stacks]:
                        yield from traverse_instanced_children(child)
                        continue
                yield child
                yield from traverse_instanced_children(child)

        return list(traverse_instanced_children(prim))

    @staticmethod
    def prim_is_from_a_capture_reference(prim) -> bool:
        stacks = prim.GetPrimStack()
        if stacks:
            for stack in stacks:
                layer_path = Path(stack.layer.realPath)
                if constants.CAPTURE_FOLDER in layer_path.parts and constants.MESHES_FOLDER in layer_path.parts:
                    # this is a mesh from the capture folder
                    return True
        return False

    def filter_xformable_prims(self, prims: List[Usd.Prim]):
        return [prim for prim in prims if UsdGeom.Xformable(prim)]

    def get_corresponding_prototype_prims(self, prims) -> List[str]:
        """Give a list of instance prims (inst_/*), and get the corresponding prims inside the prototypes (mesh_/*)"""
        paths = []
        for prim in prims:
            root_node = prim.GetPrimIndex().rootNode
            if not root_node:
                continue
            children = root_node.children
            if not children:
                continue
            paths.append(str(children[0].path))
        return paths

    def get_xformable_prim_from_ref_items(
        self,
        ref_items: List["_ItemReferenceFileMesh"],
        parent_items: List[Union["_ItemInstanceMesh", "_ItemReferenceFileMesh"]],
    ) -> List[Usd.Prim]:
        """
        Get xformables prim that comes from the reference item and are children of the parent items.
        """
        if not ref_items:
            return []
        selected_prims = [item.prim for item in parent_items]
        if not selected_prims:
            return []
        # TODO: select only the first selection for now, and select the material that match the selected usd ref
        # path
        selected_refs = [item.ref for item in ref_items]
        selected_layers = [item.layer for item in ref_items]
        reference_path = omni.client.normalize_url(selected_layers[0].ComputeAbsolutePath(selected_refs[0].assetPath))
        children_prims = self.get_children_from_prim(selected_prims[0], from_reference_layer_path=reference_path)
        if not children_prims:
            return []
        # get the first xformable from the list
        xformable_prims = self.filter_xformable_prims(children_prims)
        if xformable_prims:
            xformable_prims = [xformable_prims[0]]
        return xformable_prims

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

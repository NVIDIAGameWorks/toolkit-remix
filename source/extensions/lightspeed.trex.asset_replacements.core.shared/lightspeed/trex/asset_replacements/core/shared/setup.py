"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import re
import typing
import uuid
from pathlib import Path
from typing import List, Optional, Union

import carb
import omni.client
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.error_popup.window import ErrorPopup
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.layer_types import LayerType as _LayerType
from lightspeed.tool.material.core import ToolMaterialCore as _ToolMaterialCore
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.validator.factory import BASE_HASH_KEY as _BASE_HASH_KEY
from omni.flux.validator.factory import VALIDATION_PASSED as _VALIDATION_PASSED
from omni.usd.commands import remove_prim_spec as _remove_prim_spec
from pxr import Sdf, Usd, UsdGeom, UsdSkel

if typing.TYPE_CHECKING:
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemInstanceMesh as _ItemInstanceMesh
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
        ItemReferenceFileMesh as _ItemReferenceFileMesh,
    )

_DEFAULT_PRIM_TAG = "<Default Prim>"


class Setup:
    def __init__(self, context_name: str):
        self._default_attr = {
            "_context_name": None,
            "_context": None,
            "_layer_manager": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._layer_manager = _LayerManagerCore()

    def get_children_from_prim(
        self,
        prim,
        from_reference_layer_path: str = None,
        level: Optional[int] = None,
        skip_remix_ref: bool = False,
        only_prim_not_from_ref: bool = False,
    ):  # noqa PLR1710

        _level = 0

        def get_parent_ref_layers(_prim):
            refs_and_layers = omni.usd.get_composed_references_from_prim(_prim)
            result = []
            if refs_and_layers:
                for (ref, layer) in refs_and_layers:
                    if not ref.assetPath:
                        continue
                    result.append(omni.client.normalize_url(layer.ComputeAbsolutePath(ref.assetPath)))
            parent = _prim.GetParent()
            if parent and parent.IsValid():
                result.extend(get_parent_ref_layers(parent))
            return result

        def traverse_instanced_children(_prim, _level, _skip_remix_ref=False):  # noqa R503
            if level is not None and _level == level:
                return
            _level += 1
            for child in _prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate):
                # it can happen that we added the same reference multiple time. But USD can't do that.
                # As a workaround, we had to create a xform child and add the reference to it.
                # Check the children and find the attribute that define that
                is_remix_ref = False
                if _skip_remix_ref:
                    is_remix_ref = child.GetAttribute(constants.IS_REMIX_REF_ATTR)
                    if is_remix_ref.IsValid():
                        _level -= 1

                layer_stack = [omni.client.normalize_url(stack.layer.realPath) for stack in child.GetPrimStack()]
                if only_prim_not_from_ref and set(layer_stack).intersection(set(get_parent_ref_layers(_prim))):
                    yield from traverse_instanced_children(child, _level, _skip_remix_ref=_skip_remix_ref)
                    continue

                if (
                    from_reference_layer_path is not None
                    and not only_prim_not_from_ref
                    and from_reference_layer_path not in layer_stack
                ):
                    yield from traverse_instanced_children(child, _level, _skip_remix_ref=_skip_remix_ref)
                    continue
                if not is_remix_ref:
                    yield child
                yield from traverse_instanced_children(child, _level, _skip_remix_ref=_skip_remix_ref)

        return list(traverse_instanced_children(prim, _level, _skip_remix_ref=skip_remix_ref))

    def select_child_from_instance_item_and_ref(
        self,
        stage,
        from_prim,
        from_reference_layer_path,
        instance_items: List["_ItemInstanceMesh"],
        only_xformable: bool = False,
        only_imageable: bool = False,
        filter_scope_prim_without_imageable: bool = False,
    ):
        """
        Select the first prim of a ref corresponding to the selected instance items
        """
        selection = []
        for item in instance_items:
            prim = stage.GetPrimAtPath(item.path)
            if not prim.IsValid():
                continue

            # it can happen that we added the same reference multiple time. But USD can't do that.
            # As a workaround, we had to create a xform child and add the reference to it.
            # Check the children and find the attribute that define that
            to_break = False
            for child in prim.GetChildren():
                is_remix_ref = child.GetAttribute(constants.IS_REMIX_REF_ATTR)
                if is_remix_ref.IsValid():
                    proto_children = self.get_corresponding_prototype_prims([child])
                    for proto_child in proto_children:
                        if proto_child == str(from_prim.GetPath()):
                            prim = child
                            to_break = True
                            break
                if to_break:
                    break

            children = self.get_children_from_prim(
                prim, from_reference_layer_path=self.switch_ref_rel_to_abs_path(stage, from_reference_layer_path)
            )
            if only_xformable:
                # get the first xformable from the list
                children = self.filter_xformable_prims(children)
            if only_imageable:
                # get the first xformable from the list
                children = self.filter_imageable_prims(children)
            if filter_scope_prim_without_imageable:
                scope_without = self.get_scope_prims_without_imageable_children(children)
                children = [child for child in children if child not in scope_without]
            # select the first children
            if children:
                selection.append(str(children[0].GetPath()))

        if selection:
            self.select_prim_paths(selection)

    def get_next_xform_children(self, prim, from_reference_layer_path: str = None) -> List[Usd.Prim]:
        children_prims = prim.GetChildren()
        if not children_prims:
            return []
        if from_reference_layer_path is not None:
            children_prims2 = []
            for child in children_prims:
                stacks = child.GetPrimStack()
                if from_reference_layer_path in [stack.layer.realPath for stack in stacks]:
                    children_prims2.append(child)
        else:
            children_prims2 = list(children_prims)
        if not children_prims2:
            return []
        xformable_prims = self.filter_xformable_prims(children_prims2)
        if xformable_prims:
            return xformable_prims
        # if not children, check if the sub children is a xform
        result = []
        for children_prim in children_prims2:
            result.extend(self.get_next_xform_children(children_prim))
        return result

    @staticmethod
    def prim_is_from_a_capture_reference(prim) -> bool:
        stacks = prim.GetPrimStack()
        if stacks:
            for stack in stacks:
                if Setup.ref_path_is_from_capture(stack.layer.realPath):
                    # this is a mesh from the capture folder
                    return True
        return False

    def filter_xformable_prims(self, prims: List[Usd.Prim]):
        return [prim for prim in prims if UsdGeom.Xformable(prim)]

    def filter_scope_prims(self, prims: List[Usd.Prim]):
        return [prim for prim in prims if UsdGeom.Scope(prim)]

    def filter_imageable_prims(self, prims: List[Usd.Prim]):
        return [prim for prim in prims if UsdGeom.Imageable(prim) or prim.IsA(UsdGeom.Subset)]

    def get_corresponding_prototype_prims(self, prims) -> List[str]:
        """Give a list of instance prims (inst_123456789/*), and get the corresponding prims inside the prototypes
        (mesh_123456789/*)"""
        paths = []
        for prim in prims:
            if not prim.IsValid():
                continue

            stage = prim.GetStage()
            path = re.sub(constants.REGEX_INSTANCE_TO_MESH_SUB, rf"{constants.MESH_PATH}\2", str(prim.GetPath()))
            if not stage.GetPrimAtPath(path).IsValid():
                continue
            paths.append(path)
        return paths

    def get_corresponding_prototype_prims_from_path(self, paths) -> List[str]:
        """Give a list of instance prims (inst_123456789/*), and get the corresponding prims inside the prototypes
        (mesh_123456789/*)"""
        stage = self._context.get_stage()
        prims = [stage.GetPrimAtPath(path) for path in paths]
        return self.get_corresponding_prototype_prims(prims)

    def remove_prim_overrides(self, prim_path: Union[Sdf.Path, str]):
        # Recursively remove prim specs from given layer and all its sublayers
        def remove_prim_specs_recursive(layer, prim_spec_paths):
            for prim_spec_path in prim_spec_paths:
                if layer.GetPrimAtPath(prim_spec_path):
                    omni.kit.commands.execute(
                        "RemovePrimSpecCommand",
                        layer_identifier=layer.identifier,
                        prim_spec_path=prim_spec_path,
                        usd_context=self._context_name,
                    )
            for sublayer_path in layer.subLayerPaths:
                sublayer = Sdf.Layer.FindOrOpen(layer.ComputeAbsolutePath(sublayer_path))
                if sublayer:
                    remove_prim_specs_recursive(sublayer, prim_spec_paths)

        # Get the root-level replacement layer
        replacement_layer = self._layer_manager.get_layer(_LayerType.replacement)
        if not replacement_layer:
            return

        # Since we're expecting a mesh prim, make sure to grab the related material prims
        material_prims = _ToolMaterialCore.get_materials_from_prim_paths([prim_path], self._context_name) or []
        material_prim_paths = [m.GetPath() for m in material_prims]

        with omni.kit.undo.group():
            remove_prim_specs_recursive(replacement_layer, [prim_path, *material_prim_paths])

    def get_selected_prim_paths(self) -> List[Union[str]]:
        return self._context.get_selection().get_selected_prim_paths()

    def select_prim_paths(self, paths: List[Union[str]], current_selection: List[Union[str]] = None):
        if current_selection is None:
            current_selection = self.get_selected_prim_paths()
        if sorted(paths) != sorted(current_selection):
            omni.kit.commands.execute(
                "SelectPrims", old_selected_paths=current_selection, new_selected_paths=paths, expand_in_stage=True
            )

    def get_prim_from_ref_items(
        self,
        ref_items: List["_ItemReferenceFileMesh"],
        parent_items: List[Union["_ItemInstanceMesh", "_ItemReferenceFileMesh"]],
        only_xformable: bool = False,
        only_imageable: bool = False,
        level: Optional[int] = None,
        skip_remix_ref: bool = False,
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
        children_prims = self.get_children_from_prim(
            selected_prims[0], from_reference_layer_path=reference_path, level=level, skip_remix_ref=skip_remix_ref
        )
        if not children_prims:
            return []
        if only_xformable:
            # get the first xformable from the list
            children_prims = self.filter_xformable_prims(children_prims)
        if only_imageable:
            # get the first xformable from the list
            children_prims = self.filter_imageable_prims(children_prims)
        return children_prims

    def get_scope_prims_without_imageable_children(self, prims):
        result = []
        scoped_children = self.filter_scope_prims(prims)
        for scope in scoped_children:
            scope_children = self.get_children_from_prim(scope)
            imageable_children = self.filter_imageable_prims(scope_children)
            # if this is a scope prim, and this scope prim doesn't have any imageable prim, we keep it
            if not imageable_children:
                result.append(scope)
        return result

    def texture_path_is_from_capture(self, path: str):
        path_p = Path(path)
        return (
            bool(constants.CAPTURE_FOLDER in path_p.parts or constants.REMIX_CAPTURE_FOLDER in path_p.parts)
            and constants.TEXTURES_FOLDER in path_p.parts
        )

    @staticmethod
    def ref_path_is_from_capture(path: str):
        path_p = Path(path)
        return (
            bool(constants.CAPTURE_FOLDER in path_p.parts or constants.REMIX_CAPTURE_FOLDER in path_p.parts)
            and constants.MESHES_FOLDER in path_p.parts
        )

    def was_the_asset_ingested(self, path: str) -> bool:
        # invalid paths are ignored
        if not _path_utils.is_file_path_valid(path, log_error=False):
            return True
        # ignore assets from captures
        if Setup.ref_path_is_from_capture(path) or self.texture_path_is_from_capture(path):
            return True
        return bool(
            _path_utils.hash_match_metadata(path, key=_BASE_HASH_KEY)
            and _path_utils.read_metadata(path, _VALIDATION_PASSED)
        )

    @staticmethod
    def switch_ref_abs_to_rel_path(stage, path):
        edit_layer = stage.GetEditTarget().GetLayer()
        # make the path relative to current edit target layer
        if not edit_layer.anonymous:
            return omni.client.make_relative_url(edit_layer.realPath, path)
        return path

    @staticmethod
    def switch_ref_rel_to_abs_path(stage, path):
        edit_layer = stage.GetEditTarget().GetLayer()
        # make the path relative to current edit target layer
        if not edit_layer.anonymous:
            return omni.client.normalize_url(edit_layer.ComputeAbsolutePath(path))
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
        self,
        stage: Usd.Stage,
        prim_path: Sdf.Path,
        asset_path: str,
        new_ref_prim_path: str,
        layer: Sdf.Layer,
        create_if_remix_ref: bool = True,
    ) -> Sdf.Reference:

        detail_message = ""

        # it can happen that we added the same reference multiple time. But USD can't do that.
        # As a workaround, we had to create a xform child and add the reference to it.
        prim = stage.GetPrimAtPath(prim_path)
        child_prim_path = self.__create_child_ref_prim(stage, prim, create_if_remix_ref=create_if_remix_ref)

        asset_path = omni.client.normalize_url(omni.client.make_relative_url(layer.identifier, asset_path))
        new_ref_prim_path = (
            Sdf.Path() if new_ref_prim_path.strip() == _DEFAULT_PRIM_TAG else Sdf.Path(new_ref_prim_path.strip())
        )
        new_ref = Sdf.Reference(assetPath=asset_path.replace("\\", "/"), primPath=new_ref_prim_path)
        omni.kit.commands.execute(
            "AddReference",
            stage=stage,
            prim_path=child_prim_path,
            reference=new_ref,
        )

        if UsdSkel.Root(prim):
            child_prim = prim.GetStage().GetPrimAtPath(child_prim_path)
            skeleton_prim = prim.GetStage().GetPrimAtPath(prim_path.AppendPath("skel"))
            skeleton = UsdSkel.Skeleton(skeleton_prim)

            # The Joints Attr contains full paths to each bone, we only care about the actual bone's name.
            skel_joints = [joint.split("/")[-1] for joint in skeleton.GetJointsAttr().Get()]

            for ref_prim in Usd.PrimRange(child_prim):
                # Nested SkelRoot prims cause problems, so override their type to XForm
                root_api = UsdSkel.Root(ref_prim)
                if root_api:
                    omni.kit.commands.execute(
                        "SetPrimTypeName",
                        prim=ref_prim,
                        type_name="Xform",
                    )
                    continue

                binding_api = UsdSkel.BindingAPI(ref_prim)
                if not binding_api:
                    continue

                indices_primvar = binding_api.GetJointIndicesPrimvar()
                indices = indices_primvar.Get()
                original_joints = binding_api.GetJointsAttr().Get()
                if not indices or not original_joints:
                    continue

                # Force the mesh to bind to the captured skeleton
                omni.kit.commands.execute(
                    "SetRelationshipTargetsCommand",
                    relationship=binding_api.GetSkeletonRel(),
                    targets=[skeleton_prim.GetPath()],
                )

                original_joints = binding_api.GetJointsAttr().Get()
                mesh_joints = [joint.split("/")[-1] for joint in original_joints]
                if not mesh_joints:
                    continue

                # First, check if the joint arrays match
                needs_remapping = not all(m == s for m, s in zip(mesh_joints, skel_joints))
                if needs_remapping:
                    carb.log_info(
                        f"Replacement mesh {ref_prim.GetPath()} joint names don't match skeleton.  Attempting to"
                        " automatically remap the joint indices."
                    )
                    joint_map = [-1] * len(mesh_joints)
                    try:
                        for (index, joint_name) in enumerate(mesh_joints):
                            joint_map[index] = skel_joints.index(joint_name)
                    except ValueError:
                        # mesh contains a joint name not in the skeleton, auto remapping by name isn't safe.
                        # TODO (REMIX-1811) this should prompt the user to launch a remapping utility.
                        joint_map = None
                        carb.log_error(
                            f"Replacement mesh at {ref_prim.GetPath()} contains joint names that are not in the"
                            " captured skeleton and could not be remapped."
                            f" - Skeleton: {skel_joints}\n"
                            f" - Mesh: {mesh_joints}\n"
                        )
                        detail_message += (
                            f"{ref_prim.GetPath()}\n"
                            f" - Contains joint names that are not in the captured skeleton.  The joints will"
                            f" need to be manually remapped.\n"
                            f" - Skeleton: {skel_joints}\n"
                            f" - Mesh: {mesh_joints}\n"
                        )

                    if joint_map and indices:
                        remapped_indices = [joint_map[index] for index in indices]
                        omni.kit.commands.execute(
                            "ChangePropertyCommand",
                            usd_context_name=stage,
                            prop_path=binding_api.GetJointIndicesAttr().GetPath(),
                            value=remapped_indices,
                            prev=indices,
                        )
                        carb.log_info(f"joint indices successfully remapped for {ref_prim.GetPath()}")

                # Set skel:joints property to None.
                omni.kit.commands.execute(
                    "ChangePropertyCommand",
                    usd_context_name=stage,
                    prop_path=binding_api.GetJointsAttr().GetPath(),
                    value=Sdf.ValueBlock(),
                    prev=original_joints,
                )

        if detail_message:
            popup = ErrorPopup(
                "Add Reference Errors",
                "Content problem(s) when adding a reference.",
                detail_message,
                window_size=(900, 300),
            )
            popup.show()
        return new_ref, child_prim_path

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
        self,
        stage: Usd.Stage,
        prim_path: Sdf.Path,
        ref: Sdf.Reference,
        intro_layer: Sdf.Layer,
        remove_if_remix_ref: bool = True,
    ) -> Sdf.Reference:
        edit_target_layer = stage.GetEditTarget().GetLayer()
        # When removing a reference on a different layer, the deleted assetPath should be relative to edit target layer,
        # not introducing layer
        if intro_layer and intro_layer != edit_target_layer:
            ref = self.__anchor_reference_asset_path_to_layer(ref, intro_layer, edit_target_layer)
        # get prim
        prim = stage.GetPrimAtPath(prim_path)
        is_remix_ref = prim.GetAttribute(constants.IS_REMIX_REF_ATTR)
        # if prim_path is mesh_*, we want to get his children and remove overrides later
        # if not, we just remove the ref xform added for duplicated refs
        if is_remix_ref and not remove_if_remix_ref:
            prims = []
            parent_prim = prim.GetParent()
        else:
            prims = [prim]
            if is_remix_ref:
                parent_prim = prim.GetParent()
            else:
                parent_prim = None

        regex_is_mesh = re.compile(constants.REGEX_MESH_PATH)
        if regex_is_mesh.match(str(prim_path)):
            # we grab the children, but we skip remix ref
            prims = [
                _prim for _prim in prim.GetChildren() if not _prim.GetAttribute(constants.IS_REMIX_REF_ATTR).IsValid()
            ]

        omni.kit.commands.execute(
            "SetExplicitReferencesCommand",
            stage=stage,
            prim_path=str(prim_path),
            reference=ref,
            to_set=[],
        )

        # we should never delete /mesh_* or /light_* or /inst_*
        regex_mesh_inst_light = re.compile(constants.REGEX_MESH_INST_LIGHT_PATH)
        prims = [
            str(_prim.GetPath())
            for _prim in prims
            if _prim.IsValid() and not regex_mesh_inst_light.match(str(_prim.GetPath()))
        ]
        if prims:
            self.delete_prim(prims)

        # but if the prim is empty with no override, nothing, we should delete the override
        if parent_prim:
            prim_spec = edit_target_layer.GetPrimAtPath(parent_prim.GetPath())
            if prim_spec and not prim_spec.hasReferences and not prim_spec.nameChildren:
                _remove_prim_spec(edit_target_layer, prim_spec.path)

    def delete_prim(self, paths: List[str]):
        omni.kit.commands.execute(
            "DeletePrims",
            paths=paths,
            context_name=self._context_name,
        )

    def __create_child_ref_prim(self, stage: Usd.Stage, prim: Usd.Prim, create_if_remix_ref: bool = True) -> str:
        prim_path = prim.GetPath()
        is_remix_ref = prim.GetAttribute(constants.IS_REMIX_REF_ATTR)
        if is_remix_ref and not create_if_remix_ref:
            return str(prim_path)
        if is_remix_ref:
            prim_path = prim_path.GetParentPath()
        prim_path = omni.usd.get_stage_next_free_path(
            stage, str(prim_path.AppendPath(f"ref_{str(uuid.uuid4()).replace('-', '')}")), False
        )
        omni.kit.commands.execute(
            "CreatePrimCommand",
            prim_path=prim_path,
            prim_type="Xform",
            select_new_prim=False,
            context_name=self._context_name,
        )
        child_prim = prim.GetStage().GetPrimAtPath(prim_path)

        omni.kit.commands.execute(
            "CreateUsdAttributeOnPath",
            attr_path=child_prim.GetPath().AppendProperty(constants.IS_REMIX_REF_ATTR),
            attr_type=Sdf.ValueTypeNames.Bool,
            attr_value=True,
            usd_context_name=self._context_name,
        )

        return prim_path

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

    def filter_transformable_prims(self, paths: Optional[List[Sdf.Path]]):
        transformable = []
        regex_in_instance = re.compile(constants.REGEX_IN_INSTANCE_PATH)
        regex_light_pattern = re.compile(constants.REGEX_LIGHT_PATH)
        for path in paths:
            prim = self._context.get_stage().GetPrimAtPath(path)
            if not self.filter_xformable_prims([prim]):
                continue
            if regex_light_pattern.match(prim.GetName()):
                # if this is a light instance, we add it. We can move light instance directly
                transformable.append(str(path))
                continue
            if regex_in_instance.match(str(prim.GetPath())):
                # enable the transform manip only for lights and prim in instances (and light instance)
                # we don't allow moving prim in mesh directly, a prim in an instance has to be selected
                # we don't allow moving an instance directly
                # enable also for live light in mesh
                if self.prim_is_from_a_capture_reference(prim):
                    # prim from capture can't be moved
                    continue
                corresponding_paths = self.get_corresponding_prototype_prims([prim])
                if corresponding_paths:
                    transformable.extend(corresponding_paths)
        return transformable

    @staticmethod
    def get_prim_hash(prim_path):
        return re.match(constants.REGEX_HASH, prim_path).group(3)

    @staticmethod
    def get_instance_from_mesh(mesh_paths: List[str], instance_paths: List[str]) -> List[str]:
        instances = set()
        for mesh_path in mesh_paths:
            for instance_path in instance_paths:
                if Setup.get_prim_hash(instance_path) != Setup.get_prim_hash(mesh_path):
                    continue
                instances.add(constants.COMPILED_REGEX_MESH_TO_INSTANCE_SUB.sub(instance_path, mesh_path))
        return list(instances)

    def destroy(self):
        _reset_default_attrs(self)

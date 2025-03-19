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

import re
import typing
import uuid
from typing import Optional, Union

import carb
import omni.client
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.error_popup.window import ErrorPopup
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core.data_models import LayerType as _LayerType
from lightspeed.tool.material.core import ToolMaterialCore as _ToolMaterialCore
from lightspeed.trex.utils.common.asset_utils import get_texture_type_input_name as _get_texture_type_attribute
from lightspeed.trex.utils.common.asset_utils import is_asset_ingested as _is_asset_ingested
from lightspeed.trex.utils.common.asset_utils import is_layer_from_capture as _is_layer_from_capture
from lightspeed.trex.utils.common.asset_utils import is_mesh_from_capture as _is_mesh_from_capture
from lightspeed.trex.utils.common.asset_utils import is_texture_from_capture as _is_texture_from_capture
from lightspeed.trex.utils.common.prim_utils import filter_prims_paths as _filter_prims_paths
from lightspeed.trex.utils.common.prim_utils import get_children_prims
from lightspeed.trex.utils.common.prim_utils import get_extended_selection as _get_extended_selection
from lightspeed.trex.utils.common.prim_utils import get_prim_paths as _get_prim_paths
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.usd.commands import remove_prim_spec as _remove_prim_spec
from pxr import Sdf, Usd, UsdGeom, UsdShade, UsdSkel

if typing.TYPE_CHECKING:
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemInstance as _ItemInstance
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
        ItemReferenceFile as _ItemReferenceFile,
    )

from .data_models import (
    AppendReferenceRequestModel,
    AssetPathResponseModel,
    AssetReplacementsValidators,
    DefaultAssetDirectory,
    GetPrimsQueryModel,
    GetTexturesQueryModel,
    PrimInstancesPathParamModel,
    PrimReferencePathParamModel,
    PrimsResponseModel,
    PrimTexturesPathParamModel,
    ReferenceResponseModel,
    ReplaceReferenceRequestModel,
    SetSelectionPathParamModel,
    TexturesResponseModel,
)
from .skeleton import (
    SkeletonAutoRemappingError,
    SkeletonDefinitionError,
    SkeletonReplacementBinding,
    author_binding_to_skel,
    clear_skel_root_type,
    path_names_only,
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
        self._layer_manager = _LayerManagerCore(context_name=context_name)

    # DATA MODEL FUNCTIONS

    def get_selected_prim_paths_with_data_model(self) -> PrimsResponseModel:
        return PrimsResponseModel(asset_paths=self.get_selected_prim_paths())

    def select_prim_paths_with_data_model(self, body: SetSelectionPathParamModel):
        self.select_prim_paths(body.asset_paths)

    def get_prim_paths_with_data_model(self, query: GetPrimsQueryModel) -> PrimsResponseModel:
        prim_paths = []

        selection = None
        if query.return_selection:
            selection = _get_extended_selection(context_name=self._context_name)

        for prim_type in query.asset_types if query.asset_types is not None else [None]:
            prim_paths += _get_prim_paths(
                asset_hashes=query.asset_hashes,
                prim_type=prim_type,
                selection=selection,
                filter_session_prims=query.filter_session_prims,
                layer_id=query.layer_identifier,
                exists=query.exists,
                context_name=self._context_name,
            )

        return PrimsResponseModel(asset_paths=prim_paths)

    def get_instances_with_data_model(self, params: PrimInstancesPathParamModel) -> PrimsResponseModel:
        return PrimsResponseModel(asset_paths=list(self.get_instances_from_mesh_path(params.asset_path)))

    def get_textures_with_data_model(
        self, params: PrimTexturesPathParamModel, query: GetTexturesQueryModel
    ) -> TexturesResponseModel:
        return TexturesResponseModel(
            textures=self.get_textures_from_material_path(
                params.asset_path,
                texture_types=(
                    {_TextureTypes[texture_type.value] for texture_type in query.texture_types}
                    if query.texture_types
                    else None
                ),
            )
        )

    def get_reference_with_data_model(self, params: PrimReferencePathParamModel) -> ReferenceResponseModel:
        introducing_prim, references = AssetReplacementsValidators.get_prim_references(
            params.asset_path, self._context_name
        )
        return ReferenceResponseModel(
            reference_paths=[
                (str(introducing_prim.GetPath()), (str(ref.assetPath), layer.identifier)) for ref, layer in references
            ]
        )

    def replace_reference_with_data_model(
        self, params: PrimReferencePathParamModel, body: ReplaceReferenceRequestModel
    ) -> ReferenceResponseModel:
        with omni.kit.undo.group():
            stage = self._context.get_stage()
            edit_target_layer = stage.GetEditTarget().GetLayer()

            introducing_prim, references = AssetReplacementsValidators.get_prim_references(
                params.asset_path, self._context_name
            )
            prim_path = introducing_prim.GetPath()

            if body.existing_asset_layer_id and body.existing_asset_file_path:
                current_layer = Sdf.Layer.FindOrOpen(str(body.existing_asset_layer_id))
                current_ref = Sdf.Reference(
                    assetPath=_OmniUrl(body.existing_asset_file_path).path, primPath=str(params.asset_path)
                )
            else:
                current_ref, current_layer = references[0]

            # Remove the existing reference
            self.remove_reference(stage, prim_path, current_ref, current_layer, remove_if_remix_ref=False)

            # Get the new reference prim path
            ref_prim_path = self.get_reference_prim_path_from_asset_path(
                str(body.asset_file_path), current_layer, edit_target_layer, current_ref
            )

            # Add the new reference prim path
            reference, child_prim_path = self.add_new_reference(
                stage,
                prim_path,
                self.switch_ref_abs_to_rel_path(stage, str(body.asset_file_path)),
                ref_prim_path,
                edit_target_layer,
                create_if_remix_ref=False,
            )

        return ReferenceResponseModel(
            reference_paths=[(str(child_prim_path), (str(reference.assetPath), edit_target_layer.identifier))]
        )

    def append_reference_with_data_model(
        self, params: PrimReferencePathParamModel, body: AppendReferenceRequestModel
    ) -> ReferenceResponseModel:
        with omni.kit.undo.group():
            stage = self._context.get_stage()
            edit_target_layer = stage.GetEditTarget().GetLayer()
            introducing_prim, _ = AssetReplacementsValidators.get_prim_references(params.asset_path, self._context_name)

            reference, child_prim_path = self.add_new_reference(
                stage,
                introducing_prim.GetPath(),
                self.switch_ref_abs_to_rel_path(stage, str(body.asset_file_path)),
                self.get_ref_default_prim_tag(),
                edit_target_layer,
            )

        return ReferenceResponseModel(
            reference_paths=[(str(child_prim_path), (str(reference.assetPath), edit_target_layer.identifier))]
        )

    def get_default_output_directory_with_data_model(
        self, directory: DefaultAssetDirectory = DefaultAssetDirectory.INGESTED
    ) -> AssetPathResponseModel:
        stage = self._context.get_stage()
        if not stage:
            raise ValueError("No stage is currently loaded.")
        root_layer = stage.GetRootLayer()
        if root_layer.anonymous:
            raise ValueError("No project is currently loaded.")

        project_url = _OmniUrl(root_layer.realPath)
        output_directory = _OmniUrl(project_url.parent_url) / directory.value

        return AssetPathResponseModel(asset_path=str(output_directory))

    # TRADITIONAL FUNCTIONS

    def get_children_from_prim(
        self,
        prim,
        from_reference_layer_path: str = None,
        level: Optional[int] = None,
        skip_remix_ref: bool = False,
        only_prim_not_from_ref: bool = False,
    ):
        return get_children_prims(
            prim,
            from_reference_layer_path=from_reference_layer_path,
            level=level,
            skip_remix_ref=skip_remix_ref,
            only_prim_not_from_ref=only_prim_not_from_ref,
        )

    def get_instances_from_mesh_path(self, prim_path: str) -> set[str]:
        instances = set()
        instance_pattern = re.compile(constants.REGEX_INSTANCE_PATH)
        for instance_path in _filter_prims_paths(lambda prim: bool(instance_pattern.match(str(prim.GetPath())))):
            if Setup.get_prim_hash(instance_path) != Setup.get_prim_hash(prim_path):
                continue
            instances.add(constants.COMPILED_REGEX_MESH_TO_INSTANCE_SUB.sub(instance_path, prim_path))
        return instances

    def get_textures_from_material_path(
        self, prim_path: str, texture_types: Optional[set[_TextureTypes]]
    ) -> list[tuple[str, str]]:
        textures = []

        asset_prim = self._context.get_stage().GetPrimAtPath(prim_path)
        if not asset_prim:
            return textures

        shader_prim = omni.usd.get_shader_from_material(asset_prim, get_prim=True)
        if not shader_prim:
            return textures

        shader = UsdShade.Shader(shader_prim)
        if not shader:
            return textures

        texture_type_names = None
        if texture_types is not None:
            texture_type_names = [_get_texture_type_attribute(texture_type) for texture_type in texture_types]

        for shader_input in shader.GetInputs():
            # Make sure the input matches the filter if set
            if texture_type_names is not None and shader_input.GetFullName() not in texture_type_names:
                continue
            # Make sure the input expects an asset
            if shader_input.GetTypeName() != Sdf.ValueTypeNames.Asset:
                continue
            # Make sure the asset is a supported texture
            texture_asset_path = shader_input.Get().resolvedPath
            if _OmniUrl(texture_asset_path).suffix.lower() not in _SUPPORTED_TEXTURE_EXTENSIONS:
                continue
            # Store the texture property and the asset path
            textures.append((str(shader_input.GetAttr().GetPath()), str(texture_asset_path)))

        return textures

    def select_child_from_instance_item_and_ref(
        self,
        stage,
        from_prim,
        from_reference_layer_path,
        instance_items: list["_ItemInstance"],
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

    def get_next_xform_children(self, prim, from_reference_layer_path: str = None) -> list[Usd.Prim]:
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
                if _is_layer_from_capture(stack.layer.realPath):
                    # The layer is a capture layer
                    return True
        return False

    def filter_xformable_prims(self, prims: list[Usd.Prim]) -> list[Usd.Prim]:
        return [prim for prim in prims if UsdGeom.Xformable(prim)]

    def filter_scope_prims(self, prims: list[Usd.Prim]) -> list[Usd.Prim]:
        return [prim for prim in prims if UsdGeom.Scope(prim)]

    def filter_imageable_prims(self, prims: list[Usd.Prim]) -> list[Usd.Prim]:
        return [prim for prim in prims if UsdGeom.Imageable(prim) or prim.IsA(UsdGeom.Subset)]

    @staticmethod
    def get_corresponding_prototype_prims(prims) -> list[str]:
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

    def get_corresponding_prototype_prims_from_path(self, paths) -> list[str]:
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

    def get_selected_prim_paths(self) -> list[str]:
        return self._context.get_selection().get_selected_prim_paths()

    def select_prim_paths(self, paths: list[str], current_selection: list[str] = None):
        if current_selection is None:
            current_selection = self.get_selected_prim_paths()
        if set(paths) != set(current_selection):
            omni.kit.commands.execute(
                "SelectPrims", old_selected_paths=current_selection, new_selected_paths=paths, expand_in_stage=True
            )

    def get_prim_from_ref_items(
        self,
        ref_items: list["_ItemReferenceFile"],
        parent_items: list[Union["_ItemInstance", "_ItemReferenceFile"]],
        only_xformable: bool = False,
        only_imageable: bool = False,
        level: Optional[int] = None,
        skip_remix_ref: bool = False,
    ) -> list[Usd.Prim]:
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

    def get_scope_prims_without_imageable_children(self, prims) -> list[Usd.Prim]:
        result = []
        scoped_children = self.filter_scope_prims(prims)
        for scope in scoped_children:
            scope_children = self.get_children_from_prim(scope)
            imageable_children = self.filter_imageable_prims(scope_children)
            # if this is a scope prim, and this scope prim doesn't have any imageable prim, we keep it
            if not imageable_children:
                result.append(scope)
        return result

    @staticmethod
    def texture_path_is_from_capture(path: str) -> bool:
        return _is_texture_from_capture(path)

    @staticmethod
    def ref_path_is_from_capture(path: str) -> bool:
        return _is_mesh_from_capture(path)

    @staticmethod
    def was_the_asset_ingested(path: str, ignore_invalid_paths: bool = True) -> bool:
        return _is_asset_ingested(path, ignore_invalid_paths)

    def asset_is_in_project_dir(self, path: str, layer: "Sdf.Layer", include_deps_dir: bool = False) -> bool:
        # get asset, root, and deps urls
        asset_path = layer.ComputeAbsolutePath(path)
        asset_path_url = omni.client.normalize_url(asset_path)
        asset_path_str = asset_path_url.lower()

        root_path_url = _OmniUrl(_OmniUrl(self._context.get_stage_url()).parent_url)
        root_path_str = omni.client.normalize_url(str(root_path_url))
        root_path_str = root_path_str.lower()

        deps_path_url = root_path_url / constants.REMIX_DEPENDENCIES_FOLDER
        deps_path_url = omni.client.normalize_url(str(deps_path_url))
        deps_path_str = deps_path_url.lower()

        # return true if the asset is in proj dir and not in /deps
        result = root_path_str in asset_path_str
        if not include_deps_dir and deps_path_str in asset_path_str:
            result = False
        return result

    @staticmethod
    def switch_ref_abs_to_rel_path(stage: Usd.Stage, path: str) -> str:
        edit_layer = stage.GetEditTarget().GetLayer()
        # make the path relative to current edit target layer
        if not edit_layer.anonymous:
            return omni.client.make_relative_url(edit_layer.realPath, path)
        return path

    @staticmethod
    def switch_ref_rel_to_abs_path(stage: Usd.Stage, path: str) -> str:
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
    def ref_prim_path_is_default_prim(prim_path: str) -> bool:
        return prim_path == _DEFAULT_PRIM_TAG

    @staticmethod
    def get_ref_default_prim_tag() -> str:
        return _DEFAULT_PRIM_TAG

    @staticmethod
    def is_ref_prim_path_valid(asset_path: str, prim_path: str, layer: Sdf.Layer, log_error=True) -> bool:
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
    ) -> tuple[Sdf.Reference, str]:

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

        child_prim = prim.GetStage().GetPrimAtPath(child_prim_path)

        # Handle Skeleton Replacements
        skeleton_prim = prim.GetStage().GetPrimAtPath(prim_path.AppendPath("skel"))
        skeleton = UsdSkel.Skeleton(skeleton_prim)
        if UsdSkel.Root(prim) and bool(skeleton):
            captured_joints = skeleton.GetJointsAttr().Get()
            # The Joints Attr contains full paths to each bone, we only care about the actual bone's name.
            skel_joint_names = path_names_only(captured_joints)

            for ref_prim in Usd.PrimRange(child_prim):
                # Nested SkelRoot prims cause problems, so override their type to XForm
                root_api = UsdSkel.Root(ref_prim)
                if root_api:
                    clear_skel_root_type(ref_prim)
                    continue

                binding_api = UsdSkel.BindingAPI(ref_prim)
                if not binding_api:
                    continue

                indices_primvar = binding_api.GetJointIndicesPrimvar()
                indices = indices_primvar.Get()
                if not indices:
                    carb.log_warn(
                        f"{ref_prim.GetPath()} contained a skeleton binding API, but is missing "
                        f"`primvars:skel:jointIndices`."
                    )
                    detail_message += (
                        f"{ref_prim.GetPath()}\n"
                        f" - Contains a binding API but no `primvars:skel:jointIndices`.\n"
                        f"   The joints will need to be manually remapped."
                    )
                    continue
                mesh_joints = binding_api.GetJointsAttr().Get()
                if not mesh_joints:
                    carb.log_warn(
                        f"{ref_prim.GetPath()} contained a skeleton binding API, but is missing `skel:joints`."
                    )
                    detail_message += (
                        f"{ref_prim.GetPath()}\n"
                        f" - Contains a binding API but no `skel:joints`.\n"
                        f"   The joints will need to be manually remapped."
                    )
                    continue

                # Force the mesh to bind to the captured skeleton
                author_binding_to_skel(binding_api, skeleton_prim)

                # Check if the joint arrays match
                mesh_joint_names = path_names_only(mesh_joints)
                needs_remapping = not all(m == s for m, s in zip(mesh_joint_names, skel_joint_names))
                if not needs_remapping:
                    continue

                # Now that the new reference is bound, we can try to remap the joints
                carb.log_info(
                    f"Replacement mesh {ref_prim.GetPath()} joint names don't match skeleton.  Attempting to"
                    " automatically remap the joint indices."
                )
                try:
                    skel_replacement = SkeletonReplacementBinding(prim, ref_prim)
                except SkeletonDefinitionError as err:
                    detail_message += f"Could not remap skeleton for bound mesh:{err}\n"
                    continue

                try:
                    joint_map = skel_replacement.generate_joint_map(mesh_joints, captured_joints, fallback=True)
                except SkeletonAutoRemappingError as err:
                    detail_message += f"Could not generate a joint map and remap skeleton for bound mesh:{err}\n"
                    continue

                carb.log_info(f"Automatically remapping joints for {ref_prim.GetPath()} with {joint_map}.")
                skel_replacement.apply(joint_map)

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
    ) -> Sdf.Reference:
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
    ):
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

    def delete_prim(self, paths: list[str]):
        stage = self._context.get_stage()

        parent_prims = []
        for path in paths:
            prim = stage.GetPrimAtPath(path)
            parent_prims.append(prim.GetParent())

        with omni.kit.undo.group():
            omni.kit.commands.execute(
                "DeletePrims",
                paths=paths,
                context_name=self._context_name,
            )

            # Remove any parent prim's overrides if they are empty
            replacement_layer = stage.GetEditTarget().GetLayer()
            for prim in parent_prims:
                omni.kit.commands.execute(
                    "RemoveOverride",
                    prim_path=prim.GetPath(),
                    layer=replacement_layer,
                    context_name=self._context_name,
                    check_up_to_prim=constants.ROOTNODE,
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

    def filter_transformable_prims(self, paths: Optional[list[Sdf.Path]]) -> list[str]:
        """
        Filter a list of prim paths to those that can be transformed.

        Instanced mesh prim paths will be replaced with their corresponding prototype
        prim paths so that transformations will act on all instances.
        """
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
                    # in a case we duplicated a captured prim
                    parent = prim.GetParent()
                    if parent and parent.GetAttribute(constants.IS_REMIX_REF_ATTR):
                        pass
                    else:
                        # prim from capture can't be moved
                        continue
                corresponding_paths = self.get_corresponding_prototype_prims([prim])
                if corresponding_paths:
                    transformable.extend(corresponding_paths)
        return transformable

    @staticmethod
    def get_prim_hash(prim_path) -> str:
        return re.match(constants.REGEX_HASH, prim_path).group(3)

    @staticmethod
    def get_instance_from_mesh(mesh_paths: list[str], instance_paths: list[str]) -> list[str]:
        instances = set()
        for mesh_path in mesh_paths:
            for instance_path in instance_paths:
                if Setup.get_prim_hash(instance_path) != Setup.get_prim_hash(mesh_path):
                    continue
                instances.add(constants.COMPILED_REGEX_MESH_TO_INSTANCE_SUB.sub(instance_path, mesh_path))
        return list(instances)

    def add_attribute(self, paths: list[str], attribute_name: str, value=None, prev_val=None, val_type=None):
        stage = self._context.get_stage()
        for path in paths:
            attr_path = Sdf.Path(path).AppendProperty(attribute_name)
            prop = stage.GetPropertyAtPath(attr_path)
            prim = stage.GetPrimAtPath(path)

            if prop:
                omni.kit.commands.execute("ChangeProperty", prop_path=prop.GetPath(), value=value, prev=prev_val)
            else:
                omni.kit.commands.execute(
                    "CreateUsdAttribute", prim=prim, attr_name=attribute_name, attr_value=value, attr_type=val_type
                )

    def destroy(self):
        _reset_default_attrs(self)

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

import carb
import carb.settings
import omni.client
import omni.kit.undo
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.common import constants as _constants
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.kit.usd.layers import LayerUtils as _LayerUtils
from omni.usd.commands import remove_prim_spec as _remove_prim_spec
from pxr import Sdf, Usd

_CONTEXT = "/exts/lightspeed.event.copy_ref_to_override/context"


class CopyRefToPrimCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_subscription_layer": None,
            "_layer_manager": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        settings = carb.settings.get_settings()
        self._context_name = settings.get(_CONTEXT) or ""
        self._context = omni.usd.get_context(self._context_name)
        self._layer_manager = _LayerManagerCore(self._context_name)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "Bake Reference from prim override"

    def _install(self):
        """Function that will create the behavior"""
        self._install_layer_listener()

    def _install_layer_listener(self):
        self._uninstall_layer_listener()
        layers = _layers.get_layers()
        self._subscription_layer = layers.get_event_stream().create_subscription_to_pop(
            self.__on_layer_event, name="LayerChange"
        )

    def __create_capture_package_layer(self):
        replacement_layer = self._layer_manager.get_layer(_LayerType.replacement)
        if not replacement_layer:
            carb.log_verbose("CopyRefToPrimCore: Mod layer doesn't exist!")
            return None
        partition_replacement_layer = replacement_layer.realPath.rpartition(".")
        layer_path = (
            f"{partition_replacement_layer[0]}_{_constants.REMIX_CAPTURE_BAKER_SUFFIX}"
            f".{partition_replacement_layer[-1]}"
        )
        find_capture_package_layer = Sdf.Layer.FindOrOpen(layer_path)

        # check if the layer is in the current stage, or it is but doesn't exist (user error?)
        capture_baker_layer = self._layer_manager.get_layer(_LayerType.capture_baker)
        if not capture_baker_layer or (capture_baker_layer and not find_capture_package_layer):
            if find_capture_package_layer:
                capture_baker_layer = self._layer_manager.insert_sublayer(
                    layer_path,
                    _LayerType.capture_baker,
                    set_as_edit_target=False,
                    parent_layer=replacement_layer,
                    do_undo=False,
                )
                carb.log_info(f"CopyRefToPrimCore: inserted layer {layer_path}")
            else:
                capture_baker_layer = self._layer_manager.create_new_sublayer(
                    _LayerType.capture_baker,
                    path=layer_path,
                    set_as_edit_target=False,
                    parent_layer=replacement_layer,
                    replace_existing=False,
                    do_undo=False,
                )
                carb.log_info(f"CopyRefToPrimCore: created layer {layer_path}")
            self._layer_manager.mute_layer(_LayerType.capture_baker, do_undo=False)
            self._layer_manager.lock_layer(_LayerType.capture_baker, do_undo=False)

            # Update custom data for the Capture Baker
            custom_layer_data = capture_baker_layer.customLayerData
            custom_layer_data_instance = self._layer_manager.get_layer_instance(
                _LayerType.capture_baker
            ).get_custom_layer_data()
            if custom_layer_data_instance:
                custom_layer_data.update(custom_layer_data_instance)
            capture_baker_layer.customLayerData = custom_layer_data
            capture_baker_layer.Save()  # because of new customLayerData
        else:
            # be sure to re-open the layer
            capture_baker_layer = find_capture_package_layer
            capture_baker_layer.Reload()
        # be sure to mute
        self._layer_manager.mute_layer(_LayerType.capture_baker, do_undo=False)
        self.__move_capture_baker_at_bottom()
        return capture_baker_layer

    def __move_capture_baker_at_bottom(self):
        replacement_layer = self._layer_manager.get_layer(_LayerType.replacement)
        if not replacement_layer:
            carb.log_verbose("CopyRefToPrimCore: Mod layer doesn't exist!")
            return
        capture_baker_layer = self._layer_manager.get_layer(_LayerType.capture_baker)
        if not capture_baker_layer:
            carb.log_verbose("CopyRefToPrimCore: Capture baker layer doesn't exist!")
            return
        # be sure to move the layer at the end of the stack
        source_parent_layer_identifier = replacement_layer.identifier
        source_layer_position = _LayerUtils.get_sublayer_position_in_parent(
            source_parent_layer_identifier, capture_baker_layer.identifier
        )

        if source_layer_position != len(replacement_layer.subLayerPaths) - 1:
            # we move it at the bottom of the stack
            omni.kit.commands.execute(
                "MoveSublayer",
                from_parent_layer_identifier=source_parent_layer_identifier,
                from_sublayer_position=source_layer_position,
                to_parent_layer_identifier=source_parent_layer_identifier,
                to_sublayer_position=-1,
                remove_source=False,
                usd_context=self._context_name,
            )

    def __get_all_replacement_layers(self, replacements_layer):
        # We grab all the sublayers of the replacements_layer
        layers = []
        for sublayerpath in replacements_layer.subLayerPaths:
            sublayer = Sdf.Layer.FindOrOpen(replacements_layer.ComputeAbsolutePath(sublayerpath))
            if not sublayer:
                continue
            # if there is a layer type value, it means that this is not a layer created by the user but by the tool
            layer_type = self._layer_manager.get_custom_data_layer_type(sublayer)
            if layer_type in [
                _LayerType.replacement.value,
                _LayerType.capture.value,
                _LayerType.capture_baker.value,
                _LayerType.workfile.value,
            ]:
                continue
            layers.append(sublayer)
            layers.extend(self.__get_all_replacement_layers(sublayer))
        return layers

    @staticmethod
    def _make_refs_relative(src_layer, dst_layer, refs):
        def __do_make_path_relative(_path):
            return omni.client.make_relative_url(dst_layer.identifier, str(_path))

        ret_refs = []
        for ref in refs:
            if _path_utils.is_absolute_path(str(ref.assetPath)):
                rel_path = __do_make_path_relative(ref.assetPath)
            else:
                # we compute the absolute path and make it relative
                abs_path = src_layer.ComputeAbsolutePath(str(ref.assetPath))
                rel_path = __do_make_path_relative(abs_path)
            ref_new = Sdf.Reference(
                assetPath=rel_path,
                primPath=ref.primPath,
                layerOffset=ref.layerOffset,
                customData=ref.customData,
            )
            ret_refs.append(ref_new)
        return ret_refs

    @staticmethod
    def _is_prim_overridden(prim_path, override_layers):
        return any(layer.GetPrimAtPath(prim_path) for layer in override_layers)

    @staticmethod
    def _anchor_ref_spec_to_layer(op, src_layer, dst_layer):
        if op.isExplicit:
            op.explicitItems = CopyRefToPrimCore._make_refs_relative(src_layer, dst_layer, op.explicitItems)
        else:
            op.addedItems = CopyRefToPrimCore._make_refs_relative(src_layer, dst_layer, op.addedItems)
            op.prependedItems = CopyRefToPrimCore._make_refs_relative(src_layer, dst_layer, op.prependedItems)
            op.appendedItems = CopyRefToPrimCore._make_refs_relative(src_layer, dst_layer, op.appendedItems)
            op.deletedItems = CopyRefToPrimCore._make_refs_relative(src_layer, dst_layer, op.deletedItems)
            op.orderedItems = CopyRefToPrimCore._make_refs_relative(src_layer, dst_layer, op.orderedItems)
        return op

    def __create_default_stage_nodes(self, stage, source_layer, output_layer, all_replacements_layers):

        regex_to_update = re.compile(_constants.REGEX_MAT_MESH_LIGHT_PATH)

        def should_copy_value(
            spec_type, field, src_layer, src_path, field_in_src, dst_layer, dst_path, field_in_dst, *args, **kwargs
        ):
            # if there is a reference, we re-path the ref to be relative to the capture_baker layer
            match = regex_to_update.match(str(src_path))
            if match and field == Sdf.PrimSpec.ReferencesKey:
                mat_spec = src_layer.GetPrimAtPath(src_path)
                if mat_spec.HasInfo(Sdf.PrimSpec.ReferencesKey):
                    op = mat_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
                    op_result = CopyRefToPrimCore._anchor_ref_spec_to_layer(op, src_layer, dst_layer)
                    return True, op_result
            return True

        def should_copy_children(children_field, src_layer, src_path, field_in_src, dst_layer, dst_path, field_in_dst):
            value = False
            # we copy all children of the root node and the camera
            if str(src_path) in [_constants.ROOTNODE, _constants.ROOTNODE_CAMERA]:
                value = True
            # if this is a material, we copy everything from it
            if regex_to_update.match(str(src_path)):
                value = True
            return value

        # we copy the children of the root node
        # we can use the current capture layer because all captures have the same root nodes
        if source_layer.GetPrimAtPath(_constants.ROOTNODE):
            Sdf.CopySpec(
                source_layer,
                _constants.ROOTNODE,
                output_layer,
                _constants.ROOTNODE,
                should_copy_value,
                should_copy_children,
            )

        # we copy the children (mat_*) of the looks node
        looks_prim = (
            stage.GetPrimAtPath(_constants.ROOTNODE_LOOKS),
            _constants.MATERIALS_FOLDER,
            _constants.CAPTURED_MAT_PATH_PREFIX,
        )
        # we copy the children (mesh_*) of the mesh node
        meshes_prim = (
            stage.GetPrimAtPath(_constants.ROOTNODE_MESHES),
            _constants.MESHES_FOLDER,
            _constants.CAPTURED_MESH_PATH_PREFIX,
        )
        # we copy the children (light_*) of the lights node
        lights_prim = (
            stage.GetPrimAtPath(_constants.ROOTNODE_LIGHTS),
            _constants.LIGHTS_FOLDER,
            _constants.CAPTURED_LIGHT_PATH_PREFIX,
        )
        prims = [lights_prim, looks_prim, meshes_prim]

        for prim, folder, capture_prefix in prims:  # noqa PLR1702
            if not prim or not prim.IsValid():  # noqa PLE1101
                continue
            # loop over /RootNode/lights, /RootNode/Looks, /RootNode/meshes
            for prim_child in prim.GetAllChildren():  # noqa PLE1101
                # if the prim has any override(s)
                is_override = CopyRefToPrimCore._is_prim_overridden(prim_child.GetPath(), all_replacements_layers)
                if not is_override:
                    # if there is no override, we don't need to back the ref into the output layer
                    # check if the ref was previously backed. If yes, clean up!
                    if output_layer.GetPrimAtPath(prim_child.GetPath()):
                        _remove_prim_spec(output_layer, str(prim_child.GetPath()))
                    continue

                capture_asset_abs_path = CopyRefToPrimCore._get_capture_asset_path(
                    prim_child, source_layer, output_layer, folder
                )

                # check if the ref was intentionally deleted
                intentionally_deleted = False
                stack = prim_child.GetPrimStack()
                # by default, we set the primPath of the ref in the output layer
                copy_ref_prim_path = capture_prefix + prim_child.GetName()
                for prim_spec in stack:
                    if prim_spec.HasInfo(Sdf.PrimSpec.ReferencesKey):
                        op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
                        if op.isExplicit:
                            for ref in op.explicitItems:
                                if prim_spec.layer.ComputeAbsolutePath(ref.assetPath) == capture_asset_abs_path:
                                    copy_ref_prim_path = ref.primPath
                                    break
                            intentionally_deleted = True
                            break
                        # Will happen if we delete the initial original reference
                        for ref in op.deletedItems:
                            if prim_spec.layer.ComputeAbsolutePath(ref.assetPath) == capture_asset_abs_path:
                                intentionally_deleted = True
                                # if a ref was deleted, be sure that the ref on the output layer uses the same primPath
                                # than the deleted one. Or the delete will not work.
                                copy_ref_prim_path = ref.primPath
                                break

                # special case for mesh. If the ref was not intentionally deleted
                add_preserve_original_attribute = False
                has_ref_children = False
                is_mesh_override = True
                sub_mesh_path = prim_child.GetPath().AppendChild(_constants.MESH_SUB_MESH_NAME)  # mesh_*/mesh
                if folder == _constants.MESHES_FOLDER and not intentionally_deleted:
                    # if there is not an override on mesh_*/mesh but there is child like mesh_*/custom_cube or
                    # mesh_*/ref we need to set the PRESERVE_ORIGINAL_ATTRIBUTE attribute.
                    # In a case where we want to set a child to the original ref. For example a light that
                    # follow a character. So we need to preserve the original call of the asset.
                    # In the app, this is when we don't touch the original ref, but "append" some ref(s) to it
                    is_mesh_override = CopyRefToPrimCore._is_prim_overridden(sub_mesh_path, all_replacements_layers)
                # we grab the children. We will have mesh_*/mesh, but check if we have other children
                # that are not part of the ref
                # grab the original ref
                sub_children = prim_child.GetChildren()
                # if we have at least 1 child that is not mesh_*/mesh, it means we need to add
                # PRESERVE_ORIGINAL_ATTRIBUTE
                for sub_child in sub_children:
                    if sub_child.GetPath() == sub_mesh_path:
                        continue
                    has_ref_children = True
                    if not is_mesh_override:
                        add_preserve_original_attribute = True
                    break

                if intentionally_deleted:
                    # if the ref is deleted, and not child ref was added, we need to tell that we should not draw
                    # anything for meshes and add PRESERVE_ORIGINAL_ATTRIBUTE
                    if not has_ref_children and folder == _constants.MESHES_FOLDER:
                        prim_spec = Sdf.CreatePrimInLayer(output_layer, prim_child.GetPath())
                        prim_spec.specifier = Sdf.SpecifierDef

                        attr = prim_spec.properties.get(_constants.PRESERVE_ORIGINAL_ATTRIBUTE) or Sdf.AttributeSpec(
                            prim_spec, _constants.PRESERVE_ORIGINAL_ATTRIBUTE, Sdf.ValueTypeNames.Int
                        )
                        attr.default = 0
                        # delete reference if the previous capture_baker layer has some
                        prim_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, Sdf.ReferenceListOp())
                    # Case where we replace a ref.
                    # Because the replacement/mod layer set an explicit ref, we don't need to copy anything
                    # So we delete the prim spec if it exists in the output layer
                    # But for things that are not meshes, if we delete completely this thing, because we don't need
                    # PRESERVE_ORIGINAL_ATTRIBUTE, we don't need any prim spec
                    elif (
                        has_ref_children and output_layer.GetPrimAtPath(prim_child.GetPath())
                    ) or not has_ref_children:
                        _remove_prim_spec(output_layer, str(prim_child.GetPath()))
                else:
                    capture_asset_rel_path = omni.client.make_relative_url(
                        output_layer.identifier, str(capture_asset_abs_path)
                    )
                    prim_spec = Sdf.CreatePrimInLayer(output_layer, prim_child.GetPath())
                    prim_spec.specifier = Sdf.SpecifierDef
                    if (
                        add_preserve_original_attribute
                        and _constants.PRESERVE_ORIGINAL_ATTRIBUTE not in prim_spec.properties
                    ):
                        attr = Sdf.AttributeSpec(
                            prim_spec, _constants.PRESERVE_ORIGINAL_ATTRIBUTE, Sdf.ValueTypeNames.Int
                        )
                        attr.default = 1
                    elif (
                        not add_preserve_original_attribute
                        and _constants.PRESERVE_ORIGINAL_ATTRIBUTE in prim_spec.properties
                    ):
                        prim_spec.RemoveProperty(prim_spec.properties[_constants.PRESERVE_ORIGINAL_ATTRIBUTE])

                    # because we preserve the original call, we dont need to add the reference
                    expected_refs = Sdf.ReferenceListOp()
                    if not add_preserve_original_attribute:
                        expected_refs.explicitItems = [
                            Sdf.Reference(assetPath=capture_asset_rel_path, primPath=copy_ref_prim_path)
                        ]
                    prim_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, expected_refs)

    @staticmethod
    def _get_capture_asset_path(prim, capture_layer, output_layer, capture_folder):
        return Sdf.ComputeAssetPathRelativeToLayer(capture_layer, capture_folder + "/" + prim.GetName() + ".usd")

    # @omni.usd.handle_exception
    # async def __do_process_layer(self, stage):
    def __do_process_layer(self, stage):
        if not stage:
            return
        # if there is no replacement layer, there is nothing to do
        replacements_layer = self._layer_manager.get_layer(_LayerType.replacement)
        if not replacements_layer:
            return
        # if there is no capture layer, there is nothing to do
        current_capture_layer = self._layer_manager.get_layer(_LayerType.capture)
        if not current_capture_layer:
            return
        # get all replacement layers that the user works on.
        # we grab the replacement layer + all sublayers (but exclude sublayer/replacement layers from others mods)
        all_replacements_layers = self.__get_all_replacement_layers(replacements_layer)
        all_replacements_layers.insert(0, replacements_layer)
        # we create/insert the capture_baker layer.
        capture_package_layer = self.__create_capture_package_layer()
        with Sdf.ChangeBlock():
            self.__create_default_stage_nodes(
                stage, current_capture_layer, capture_package_layer, all_replacements_layers
            )

        # we save the layer
        carb.log_info(f"Bake references into {capture_package_layer.realPath}")
        self._layer_manager.save_layer(_LayerType.capture_baker, show_checkpoint_error=False)

    def __process_layer(self, stage: Usd.Stage = None):
        if stage is None:
            stage = self._context.get_stage()
        # each time we save a layer part of the replacement layer, we process the whole
        # replacement layer + capture_baker. We do that as a whole process because we want to be sure that if an user
        # edit the capture_baker layer externally, we are still cleaning up and processing the whole thing nicely
        self.__do_process_layer(stage)

    @_ignore_function_decorator(attrs=["_ignore_on_event"])
    def __on_layer_event(self, event):
        payload = _layers.get_layer_event_payload(event)
        if not payload:
            return
        if payload.event_type == _layers.LayerEventType.DIRTY_STATE_CHANGED:
            dirty_sublayers = _layers.get_layers_state().get_dirty_layer_identifiers()

            replacements_layer = self._layer_manager.get_layer(_LayerType.replacement)
            if not replacements_layer:
                return
            # get all replacement layers that the user works on.
            all_replacements_layers = self.__get_all_replacement_layers(replacements_layer)
            all_replacements_layers.insert(0, replacements_layer)
            # check if the dirty layer is one of the replacement layer
            intersection = set(payload.identifiers_or_spec_paths).intersection(
                [layer.identifier for layer in all_replacements_layers]
            )
            if not intersection:
                return
            # now check is the dirty layer is still dirty. If no, it means it was just saved
            intersection = set(dirty_sublayers).intersection(payload.identifiers_or_spec_paths)
            if not intersection:
                with omni.kit.undo.group():
                    self.__process_layer()

        if payload.event_type == _layers.LayerEventType.SUBLAYERS_CHANGED:
            self.__move_capture_baker_at_bottom()

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._uninstall_layer_listener()

    def _uninstall_layer_listener(self):
        self._subscription_layer = None

    def destroy(self):
        self._uninstall()
        _reset_default_attrs(self)

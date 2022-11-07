"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import glob
import os
import re
import stat
import uuid
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

import carb
import carb.tokens
import omni.client
import omni.ext
import omni.usd
from lightspeed.common import constants
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.kit.tool.collect.collector import Collector
from pxr import Sdf, Usd, UsdGeom, UsdUtils

from .post_process import LightspeedPostProcessExporter
from .pre_process import preprocess


class DependencyErrorTypes(Enum):
    MDL_ABSOLUTE_PATH = "Mdl absolute path"
    MDL_BACKSLASH_PATH = "Mdl backslash in path"
    TEXTURE_ABSOLUTE_PATH = "Texture absolute path"
    TEXTURE_PATH_NOT_EXIST = "Texture path does not exist"
    TEXTURE_IS_DDS = "Texture is a dds texture"
    REFERENCE_ABSOLUTE_PATH = "Reference absolute path"
    REFERENCE_PATH_NOT_EXIST = "Reference path does not exist"
    REFERENCE_HASH_NOT_EXIST = "Reference hash/delta does not exist anymore"
    HAS_SUBDIVISIONS = "Mesh uses subdivisions"
    THIS_IS_A_PAYLOAD = (
        "There are payload(s) in your stage. Open the layer at the first line of each error "
        "and switch the payload into a reference."
    )


class LightspeedExporterCore:

    EXPORT_START_MARKER = "*********************** Export Start ***********************"
    EXPORT_END_MARKER = "*********************** Export End ***********************"

    def __init__(self, export_button_fn=None, cancel_button_fn=None, context_name: str = ""):
        self.__default_attr = {
            "_layer_manager": None,
            "_post_exporter": None,
            "_collector": None,
            "_context_name": None,
        }
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self.__on_progress_changed = _Event()
        self.__on_progress_text_changed = _Event()
        self.__on_finish_export = _Event()
        self.__on_export_readonly_error = _Event()
        self.__on_dependency_errors = _Event()

        self._context_name = context_name
        self._export_button_fn = export_button_fn
        self._cancel_button_fn = cancel_button_fn
        self._layer_manager = LayerManagerCore(self._context_name)
        self._post_exporter = LightspeedPostProcessExporter(self._context_name)

    def _dependency_errors(self, dependency_errors: Dict[DependencyErrorTypes, Dict[str, str]]):
        """Call the event object that has the list of functions"""
        self.__on_dependency_errors(dependency_errors)

    def subscribe_dependency_errors(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_dependency_errors, func)

    def _progress_changed(self, progress: float = None):
        """Call the event object that has the list of functions"""
        self.__on_progress_changed(progress)

    def subscribe_progress_changed(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_progress_changed, func)

    def _progress_text_changed(self, text: str = None):
        """Call the event object that has the list of functions"""
        self.__on_progress_text_changed(text)

    def subscribe_progress_text_changed(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_progress_text_changed, func)

    def _export_readonly_error(self, read_only_paths):
        """Call the event object that has the list of functions"""
        self.__on_export_readonly_error(read_only_paths)

    def subscribe_export_readonly_error(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_export_readonly_error, func)

    def _finish_export(self):
        """Call the event object that has the list of functions"""
        self.__on_finish_export()

    def subscribe_finish_export(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_finish_export, func)

    def set_export_fn(self, export_fn):
        self._export_button_fn = export_fn

    def set_cancel_fn(self, cancel_fn):
        self._cancel_button_fn = cancel_fn

    def __get_log_file(self) -> str:
        log_folder = carb.tokens.get_tokens_interface().resolve("${logs}")
        list_of_files = glob.glob(os.path.join(log_folder, "*.log"))
        return omni.client.normalize_url(max(list_of_files, key=os.path.getctime))

    def __copy_log_file_to_output(self, output_folder):
        log_path = self.__get_log_file()
        lines = []
        with open(log_path, encoding="utf8") as infile:
            copy = False
            for line in reversed(infile.readlines()):
                if self.EXPORT_END_MARKER in line.strip():
                    copy = True
                    continue
                if self.EXPORT_START_MARKER in line.strip():
                    break
                if copy:
                    lines.append(line)

        with open(os.path.join(output_folder, os.path.basename(log_path)), "w", encoding="utf8") as outfile:
            for line in reversed(lines):
                outfile.write(line)

    def export(self, export_dir, validate_dependencies=True):
        carb.log_info(self.EXPORT_START_MARKER)
        if self._export_button_fn:
            self._export_button_fn(export_dir)
        else:
            self._start_exporting(export_dir, validate_dependencies=validate_dependencies)

    def cancel(self):
        if self._cancel_button_fn:
            self._cancel_button_fn()
        carb.log_info("Cancel export...")

        if self._collector:
            self._collector.cancel()

        # reopen original stage
        omni.usd.get_context(self._context_name).open_stage(self._workspace_stage_path_norm)

        # Delete the temporary pre-processed replacement layer.
        os.remove(self._temp_stage_path)
        os.remove(self._temp_replacements_path)

    def get_default_export_path(self, create_if_not_exist: bool = False) -> Optional[str]:
        game_name, capture_folder = self._layer_manager.game_current_game_capture_folder()
        if not game_name:
            return None
        path = str(Path(capture_folder).parent.joinpath(constants.GAME_READY_ASSETS_FOLDER)) + os.sep
        if create_if_not_exist:
            Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def check_export_path(self, path) -> bool:
        stage = omni.usd.get_context(self._context_name).get_stage()
        if stage.GetRootLayer().anonymous:
            carb.log_error("Please save your stage first")
            return False
        if not path:
            carb.log_error("Please set a folder for the export")
            return False
        result, entry = omni.client.stat(path)
        if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
            carb.log_error("The export path should be an existing folder")
            return False
        # detect when a user tries to export into gameReadyAssets while using gameReadyAsset/replacements.usda
        replacement_layer = self._layer_manager.get_layer(LayerType.replacement)
        replacement_layer_dir_path = Path(replacement_layer.realPath).parent.resolve()
        if str(replacement_layer_dir_path) == str(Path(path).resolve()):
            carb.log_error(
                "Cannot export to the same folder in which the source replacements layer resides: "
                + str(replacement_layer_dir_path)
            )
            return False
        return True

    def _start_exporting(self, export_folder, validate_dependencies=True):
        # Make sure there are no readonly files or directories in the export folder
        if not self._validate_write_permissions(export_folder):
            return

        context = omni.usd.get_context(self._context_name)
        stage = context.get_stage()
        export_status = constants.EXPORT_STATUS_INCOMPLETE_EXPORT
        try:
            result_errors = self._validate_dependencies_exist(stage)
            if result_errors:
                export_status = constants.EXPORT_STATUS_PRECHECK_ERRORS
                carb.log_error(constants.BAD_EXPORT_LOG_PREFIX + str(result_errors))
                if validate_dependencies:
                    self._dependency_errors(result_errors)
                    return
        except MemoryError:
            # TODO we don't have a fix for this yet, so it shouldn't be a blocker.
            # when the USD memory error is fixed, this should set an export_status.
            # export_status = constants.EXPORT_STATUS_PRECHECK_MEMORY_ERRORS
            carb.log_error("Memory error: can't run dependencies validator")

        # Save the current stage
        context.save_stage()
        # cache workspace stage path, which is currently open
        workspace_stage_path = context.get_stage_url()
        self._workspace_stage_path_norm = omni.client.normalize_url(workspace_stage_path)

        # Create temporary copy of stage for preprocessing
        self._temp_stage_path = os.path.join(
            os.path.dirname(workspace_stage_path), f"pre_processed_combined_{str(uuid.uuid4())}.usda"
        )
        context.save_as_stage(self._temp_stage_path)

        stage = context.get_stage()  # be sure to reload
        root_layer = stage.GetRootLayer()
        layer = self._layer_manager.get_layer(LayerType.replacement)
        if layer is None:
            message = "Export Failed: Can't find the replacement layer"
            carb.log_error(message)
            self._progress_text_changed(message)
            return
        usd_path = Sdf.ComputeAssetPathRelativeToLayer(root_layer, layer.realPath)

        layer_ind = 0
        for index, sublayer_path in enumerate(root_layer.subLayerPaths):
            if Sdf.ComputeAssetPathRelativeToLayer(root_layer, sublayer_path) == usd_path:
                layer_ind = index
                break

        # Create temporary copy of replacements layer for preprocessing.  This is needed for the exporter to pick up
        # any changed dependencies.  This is done before preprocessing to prevent accidentally overwriting the original.
        self._temp_replacements_path = os.path.join(
            os.path.dirname(usd_path), f"pre_processed_replacement_{str(uuid.uuid4())}.usda"
        )
        self._layer_manager.save_layer_as(LayerType.replacement, self._temp_replacements_path)

        self._layer_manager.remove_layer(LayerType.replacement)
        self._layer_manager.insert_sublayer(
            self._temp_replacements_path,
            LayerType.replacement,
            sublayer_insert_position=layer_ind,
            set_as_edit_target=True,
            add_custom_layer_data=False,
        )
        context.save_as_stage(self._temp_stage_path)

        layer = self._layer_manager.get_layer(LayerType.replacement)
        omni.kit.commands.execute("FlattenSubLayers", usd_context=context, layer_to_flatten=layer)

        if not self._layer_manager.save_layer_as(LayerType.replacement, self._temp_replacements_path):
            message = "Export Failed: failed to save flattened replacement layer."
            carb.log_error(message)
            self._progress_text_changed(message)
            return

        preprocess(self._layer_manager, self._context_name)
        preprocessed_replacements = self._layer_manager.get_layer(LayerType.replacement)
        preprocessed_custom_layer_data = preprocessed_replacements.customLayerData
        preprocessed_custom_layer_data[constants.EXPORT_STATUS_NAME] = export_status
        preprocessed_replacements.customLayerData = preprocessed_custom_layer_data

        if not self._layer_manager.save_layer_as(LayerType.replacement, self._temp_replacements_path):
            message = "Export Failed: failed to save pre-processed replacement layer."
            carb.log_error(message)
            self._progress_text_changed(message)
            return

        self._progress_text_changed(f"Analyzing USD {os.path.basename(usd_path)}...")
        self._collector = Collector(self._temp_replacements_path, export_folder, False, True, False)

        def progress_callback(step, total):
            self._progress_text_changed(f"Collecting USD {os.path.basename(usd_path)}...")
            if total != 0:
                self._progress_changed(float(step) / total)
            else:
                self._progress_changed(0.0)

        async def _deferred_finish_callback():
            export_file_path = export_folder
            if not export_file_path.endswith("/"):
                export_file_path += "/"
            # The collector makes a copy of the temporary replacement layer, so rename that to the intended destination.
            export_file_path_norm = omni.client.normalize_url(
                export_file_path + os.path.basename(self._temp_replacements_path)
            )
            dest_file_path_norm = omni.client.normalize_url(export_file_path + constants.GAME_READY_REPLACEMENTS_FILE)
            os.replace(export_file_path_norm, dest_file_path_norm)

            self._progress_text_changed(f"Post Processing USD {os.path.basename(usd_path)}...")
            # now process/optimize geo for game
            await self._post_exporter.process(dest_file_path_norm, self._progress_text_changed, self._progress_changed)

            # reopen original stage
            # TODO: Crash, use async function instead, waiting OM-42168
            # omni.usd.get_context().open_stage(workspace_stage_path)
            await context.open_stage_async(self._workspace_stage_path_norm)

            # Delete the temporary pre-processed replacement layer.
            os.remove(self._temp_stage_path)
            os.remove(self._temp_replacements_path)

            carb.log_info(self.EXPORT_END_MARKER)

            self.__copy_log_file_to_output(export_folder)
            self._finish_export()

        def finish_callback():
            loop = asyncio.get_event_loop()
            asyncio.ensure_future(_deferred_finish_callback(), loop=loop)

        asyncio.ensure_future(self._collector.collect(progress_callback, finish_callback))

    def destroy(self):
        for attr, value in self.__default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)

    def _validate_dependencies_exist(self, stage):  # noqa C901
        def traverse_instanced_children(prim):
            for child in prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate):
                yield child
                yield from traverse_instanced_children(child)

        (all_layers, _, _) = UsdUtils.ComputeAllDependencies(stage.GetRootLayer().identifier)
        if not all_layers:
            all_layers = stage.GetLayerStack()

        result_errors = {}

        # filter stale meshes references. We want to remove overrides of references on meshes hashes that don't
        # exist anymore
        # we use the capture layer file to find the meshes folder
        layer = self._layer_manager.get_layer(LayerType.capture)
        mesh_hashes = []
        material_hashes = []
        light_hashes = []
        if layer:
            # we generate a list of hashes from the list of mesh usd files
            meshes_folder = os.path.join(os.path.dirname(layer.identifier), constants.MESHES_FOLDER)
            for usd_mesh in glob.glob(os.path.join(meshes_folder, "*.usd")):
                match = re.match(f"^{constants.MESHES_FILE_PREFIX}([A-Z0-9]{{16}}).usd$", os.path.basename(usd_mesh))
                if match:
                    mesh_hashes.append(match.groups()[0])
                    # now when we check reference paths, we check if the hash of the reference prim is in this list
            # we generate a list of hashes from the list of material usd files
            materiales_folder = os.path.join(os.path.dirname(layer.identifier), constants.MATERIALS_FOLDER)
            for usd_material in glob.glob(os.path.join(materiales_folder, "*.usd")):
                match = re.match(
                    f"^{constants.MATERIAL_FILE_PREFIX}([A-Z0-9]{{16}}).usd$", os.path.basename(usd_material)
                )
                if match:
                    material_hashes.append(match.groups()[0])
            # we generate a list of hashes from the list of light usd files
            lights_folder = os.path.join(os.path.dirname(layer.identifier), constants.LIGHTS_FOLDER)
            for usd_light in glob.glob(os.path.join(lights_folder, "*.usd")):
                match = re.match(f"^{constants.LIGHT_FILE_PREFIX}([A-Z0-9]{{16}}).usd$", os.path.basename(usd_light))
                if match:
                    light_hashes.append(match.groups()[0])
        else:
            carb.log_error("Can't find the capture layer")

        for layer in all_layers:  # noqa PLR1702
            chk = layer.identifier
            chk_path = Path(chk)

            # we ignore data from capture, because the user didn't generate that
            last_chk_parent = chk_path
            to_continue = False
            for parent in last_chk_parent.parents:
                if parent.stem == constants.CAPTURE_FOLDER:
                    to_continue = True
                    break

            if to_continue:
                continue

            sub_stage = Usd.Stage.Open(chk)
            all_prims = list(traverse_instanced_children(sub_stage.GetPseudoRoot()))
            for prim in all_prims:
                # check overrides also
                # if the prim specifier is an override and his name is "Shader", we check the overrides
                if prim.GetTypeName() in ["Shader"] or (
                    prim.GetSpecifier() == Sdf.SpecifierOver and prim.GetName() == "Shader"
                ):
                    for attr in prim.GetAttributes():
                        layers = [
                            x.layer.identifier
                            for x in attr.GetPropertyStack(Usd.TimeCode.Default())
                            if x.layer.identifier.strip()
                        ]
                        if chk not in layers:
                            # ignore things that are not overridden in the current layer or part of the current layer
                            continue

                        if attr.GetName() == "info:mdl:sourceAsset":
                            if ":/" in str(attr.Get()):
                                # Not relative path
                                key = f"{chk}\n             {prim.GetPath().pathString}::{attr.GetName()}"
                                if not result_errors.get(DependencyErrorTypes.MDL_ABSOLUTE_PATH.value):
                                    result_errors[DependencyErrorTypes.MDL_ABSOLUTE_PATH.value] = {}
                                result_errors[DependencyErrorTypes.MDL_ABSOLUTE_PATH.value][
                                    key
                                ] = f"ERROR: {attr.GetName()} has absolute MDL path: {attr.Get()}"
                            if "\\" in str(attr.Get()):
                                # Incorrect slash direction
                                key = f"{chk}\n             {prim.GetPath().pathString}::{attr.GetName()}"
                                if not result_errors.get(DependencyErrorTypes.MDL_BACKSLASH_PATH.value):
                                    result_errors[DependencyErrorTypes.MDL_BACKSLASH_PATH.value] = {}
                                result_errors[DependencyErrorTypes.MDL_BACKSLASH_PATH.value][key] = (
                                    f"ERROR: {attr.GetName()} has incorrect slash(es). "
                                    f"Needs to be forward slash ----------> {attr.Get()}"
                                )
                        else:
                            value = attr.Get()
                            if attr.GetTypeName() == "asset" and value:
                                str_value = str(value)
                                if ":/" in str_value:
                                    key = f"{chk}\n             {prim.GetPath().pathString}::{attr.GetName()}"
                                    if not result_errors.get(DependencyErrorTypes.TEXTURE_ABSOLUTE_PATH.value):
                                        result_errors[DependencyErrorTypes.TEXTURE_ABSOLUTE_PATH.value] = {}
                                    result_errors[DependencyErrorTypes.TEXTURE_ABSOLUTE_PATH.value][
                                        key
                                    ] = f"ERROR: {attr.GetName()} has absolute asset path ----------> {str_value}"
                                if str_value.startswith("@"):
                                    str_value = str_value[1:]
                                if str_value.endswith("@"):
                                    str_value = str_value[:-1]

                                # disable .dds check
                                # # we ignore dds that come from the capture folder
                                # p_value = Path(str_value)
                                # last_p_value = p_value
                                # to_ignore = False
                                # for parent in last_p_value.parents:
                                #     if parent.stem == constants.CAPTURE_FOLDER:
                                #         to_ignore = True
                                #         break
                                #
                                # if str_value.lower().endswith(".dds") and not to_ignore:
                                #     key = f"{chk}\n             {prim.GetPath().pathString}::{attr.GetName()}"
                                #     if not result_errors.get(DependencyErrorTypes.TEXTURE_IS_DDS.value):
                                #         result_errors[DependencyErrorTypes.TEXTURE_IS_DDS.value] = {}
                                #     result_errors[DependencyErrorTypes.TEXTURE_IS_DDS.value][
                                #         key
                                #     ] = f"ERROR: {attr.GetName()} is a .dds path ----------> {str_value}"

                                full_path = omni.client.normalize_url(layer.ComputeAbsolutePath(str_value))
                                result, entry = omni.client.stat(full_path)
                                if (
                                    result != omni.client.Result.OK
                                    or not entry.flags & omni.client.ItemFlags.READABLE_FILE
                                ):
                                    key = f"{chk}\n             {prim.GetPath().pathString}::{attr.GetName()}"
                                    if not result_errors.get(DependencyErrorTypes.TEXTURE_PATH_NOT_EXIST.value):
                                        result_errors[DependencyErrorTypes.TEXTURE_PATH_NOT_EXIST.value] = {}
                                    result_errors[DependencyErrorTypes.TEXTURE_PATH_NOT_EXIST.value][key] = (
                                        f"ERROR: {attr.GetName()} has path that doesn't exist ----------> "
                                        f"{str(attr.Get())}"
                                    )

                def check_prim_hash_exist(_prim):
                    """
                    Check that the prim hash is still needed. It can happen that some overrides are still here but
                    the captured mesh is not here anymore
                    """
                    to_return = True
                    for _primspec in _prim.GetPrimStack():
                        if not _primspec:
                            continue
                        if _primspec.layer and _primspec.layer.identifier != chk:  # noqa PLW0640
                            # ignore things that are not overridden in the current layer or part of the current layer
                            continue
                        to_return = False
                        break
                    if to_return:
                        return
                    if mesh_hashes:
                        _match = re.match(
                            f"^{constants.MESHES_FILE_PREFIX}([A-Z0-9]{{16}})$",
                            os.path.basename(_prim.GetPath().pathString),
                        )
                        if _match and _match.groups()[0] not in mesh_hashes:
                            if not result_errors.get(DependencyErrorTypes.REFERENCE_HASH_NOT_EXIST.value):
                                result_errors[DependencyErrorTypes.REFERENCE_HASH_NOT_EXIST.value] = {}
                            _key = f"{chk}\n             {_prim.GetPath().pathString}"  # noqa PLW0640
                            result_errors[DependencyErrorTypes.REFERENCE_HASH_NOT_EXIST.value][
                                _key
                            ] = "ERROR: This is an old override. Please remove it"
                    if material_hashes:
                        _match = re.match(
                            f"^{constants.MATERIAL_FILE_PREFIX}([A-Z0-9]{{16}})$",
                            os.path.basename(_prim.GetPath().pathString),
                        )
                        if _match and _match.groups()[0] not in material_hashes:
                            if not result_errors.get(DependencyErrorTypes.REFERENCE_HASH_NOT_EXIST.value):
                                result_errors[DependencyErrorTypes.REFERENCE_HASH_NOT_EXIST.value] = {}
                            _key = f"{chk}\n             {_prim.GetPath().pathString}"  # noqa PLW0640
                            result_errors[DependencyErrorTypes.REFERENCE_HASH_NOT_EXIST.value][
                                _key
                            ] = "ERROR: This is an old override. Please remove it"
                    if light_hashes:
                        _match = re.match(
                            f"^{constants.LIGHT_FILE_PREFIX}([A-Z0-9]{{16}})$",
                            os.path.basename(_prim.GetPath().pathString),
                        )
                        if _match and _match.groups()[0] not in light_hashes:
                            if not result_errors.get(DependencyErrorTypes.REFERENCE_HASH_NOT_EXIST.value):
                                result_errors[DependencyErrorTypes.REFERENCE_HASH_NOT_EXIST.value] = {}
                            _key = f"{chk}\n             {_prim.GetPath().pathString}"  # noqa PLW0640
                            result_errors[DependencyErrorTypes.REFERENCE_HASH_NOT_EXIST.value][
                                _key
                            ] = "ERROR: This is an old override. Please remove it"

                check_prim_hash_exist(prim)

                for primspec in prim.GetPrimStack():
                    # check if there are payloads
                    if (
                        constants.INSTANCE_PATH not in str(prim.GetPath())
                        and primspec.layer
                        and primspec.layer.identifier == chk
                    ):
                        items = []
                        for item in primspec.payloadList.addedItems:
                            if item.assetPath:
                                items.append(item)
                        for item in primspec.payloadList.prependedItems:
                            if item.assetPath:
                                items.append(item)
                        for item in primspec.payloadList.explicitItems:
                            if item.assetPath:
                                items.append(item)
                        for item in items:
                            if item is None:
                                continue
                            str_value = str(item.assetPath)
                            if str_value.strip():
                                if str_value.startswith("@"):
                                    str_value = str_value[1:]
                                if str_value.endswith("@"):
                                    str_value = str_value[:-1]
                                full_path = omni.client.normalize_url(layer.ComputeAbsolutePath(str_value))
                                key = f"{chk}\n             {prim.GetPath().pathString}"
                                if not result_errors.get(DependencyErrorTypes.THIS_IS_A_PAYLOAD.value):
                                    result_errors[DependencyErrorTypes.THIS_IS_A_PAYLOAD.value] = {}
                                result_errors[DependencyErrorTypes.THIS_IS_A_PAYLOAD.value][
                                    key
                                ] = f"ERROR: {prim.GetName()} is a payload ----------> {full_path}"

                    if not primspec:
                        continue
                    if not primspec.referenceList:
                        continue
                    if primspec.layer and primspec.layer.identifier != chk:
                        # ignore things that are not overridden in the current layer or part of the current layer
                        continue
                    # Checking USDA
                    items = primspec.referenceList.explicitItems
                    for item in items:
                        if item is not None and ":/" in item.assetPath:
                            key = f"{chk}\n             {prim.GetPath().pathString}"
                            if not result_errors.get(DependencyErrorTypes.REFERENCE_ABSOLUTE_PATH.value):
                                result_errors[DependencyErrorTypes.REFERENCE_ABSOLUTE_PATH.value] = {}
                            result_errors[DependencyErrorTypes.REFERENCE_ABSOLUTE_PATH.value][
                                key
                            ] = f"ERROR: {prim.GetName()} has absolute reference path ----------> {item.assetPath}"

                        str_value = str(item.assetPath)
                        if str_value.strip():
                            if str_value.startswith("@"):
                                str_value = str_value[1:]
                            if str_value.endswith("@"):
                                str_value = str_value[:-1]
                            full_path = omni.client.normalize_url(layer.ComputeAbsolutePath(str_value))
                            result, entry = omni.client.stat(full_path)
                            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
                                key = f"{chk}\n             {prim.GetPath().pathString}"
                                if not result_errors.get(DependencyErrorTypes.REFERENCE_PATH_NOT_EXIST.value):
                                    result_errors[DependencyErrorTypes.REFERENCE_PATH_NOT_EXIST.value] = {}
                                result_errors[DependencyErrorTypes.REFERENCE_PATH_NOT_EXIST.value][key] = (
                                    f"ERROR: {prim.GetName()} has reference path that doesn't exist ----------> "
                                    f"{item.assetPath}"
                                )

                    # Checking USD
                    items = primspec.referenceList.prependedItems
                    for item in items:
                        if item is not None and ":/" in item.assetPath:
                            key = f"{chk}\n             {prim.GetPath().pathString}"
                            if not result_errors.get(DependencyErrorTypes.REFERENCE_ABSOLUTE_PATH.value):
                                result_errors[DependencyErrorTypes.REFERENCE_ABSOLUTE_PATH.value] = {}
                            result_errors[DependencyErrorTypes.REFERENCE_ABSOLUTE_PATH.value][
                                key
                            ] = f"ERROR: {prim.GetName()} has absolute reference path ----------> {item.assetPath}"

                        str_value = str(item.assetPath)
                        if str_value.strip():
                            if str_value.startswith("@"):
                                str_value = str_value[1:]
                            if str_value.endswith("@"):
                                str_value = str_value[:-1]
                            full_path = omni.client.normalize_url(layer.ComputeAbsolutePath(str_value))
                            result, entry = omni.client.stat(full_path)
                            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
                                key = f"{chk}\n             {prim.GetPath().pathString}"
                                if not result_errors.get(DependencyErrorTypes.REFERENCE_PATH_NOT_EXIST.value):
                                    result_errors[DependencyErrorTypes.REFERENCE_PATH_NOT_EXIST.value] = {}
                                result_errors[DependencyErrorTypes.REFERENCE_PATH_NOT_EXIST.value][key] = (
                                    f"ERROR: {prim.GetName()} has reference path that doesn't exist ----------> "
                                    f"{item.assetPath}"
                                )

                # if the prim is a mesh, check that it has normals
                mesh_schema = UsdGeom.Mesh(prim)
                if mesh_schema:
                    subdiv_scheme = mesh_schema.GetSubdivisionSchemeAttr().Get()
                    if subdiv_scheme != "none":
                        key = f"{chk}\n             {prim.GetPath().pathString}"
                        if not result_errors.get(DependencyErrorTypes.HAS_SUBDIVISIONS.value):
                            result_errors[DependencyErrorTypes.HAS_SUBDIVISIONS.value] = {}
                        result_errors[DependencyErrorTypes.HAS_SUBDIVISIONS.value][key] = (
                            f"ERROR: subdivision setting other than `none` was found on the mesh {prim.GetName()}."
                            f"\n               "
                            f" Please re-export the geometry with normals. If this is an export from Maya, in the"
                            f"\n               "
                            f" export options, please set the `subdivision method` to `None` (under `Geometry`)."
                        )

        return result_errors

    def _validate_write_permissions(self, export_folder):
        read_only = []
        for root, _, files in os.walk(export_folder, followlinks=True):
            root_path = Path(root)
            file_paths = list(map(lambda f: root_path / f, files))  # noqa PLW0640

            if stat.FILE_ATTRIBUTE_READONLY & root_path.stat().st_file_attributes:
                read_only.append(str(root_path))

            for file_path in file_paths:
                if stat.FILE_ATTRIBUTE_READONLY & file_path.stat().st_file_attributes:
                    read_only.append(str(file_path))

        if len(read_only) > 0:
            self._export_readonly_error(read_only)
            return False

        return True

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
from pxr import Sdf, Usd, UsdUtils

from .post_process import LightspeedPosProcessExporter
from .pre_process import preprocess


class DependencyErrorTypes(Enum):
    MDL_ABSOLUTE_PATH = "Mdl absolute path"
    MDL_BACKSLASH_PATH = "Mdl backslash in path"
    TEXTURE_ABSOLUTE_PATH = "Texture absolute path"
    TEXTURE_PATH_NOT_EXIST = "Texture path does not exist"
    TEXTURE_IS_DDS = "Texture is a dds texture"
    REFERENCE_ABSOLUTE_PATH = "Reference absolute path"
    REFERENCE_PATH_NOT_EXIST = "Reference path does not exist"


class LightspeedExporterCore:

    EXPORT_START_MARKER = "*********************** Export Start ***********************"
    EXPORT_END_MARKER = "*********************** Export End ***********************"

    def __init__(self, export_button_fn=None, cancel_button_fn=None):
        self.__default_attr = {"_layer_manager": None, "_post_exporter": None, "_collector": None}
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self.__on_progress_changed = _Event()
        self.__on_progress_text_changed = _Event()
        self.__on_finish_export = _Event()
        self.__on_export_readonly_error = _Event()
        self.__on_dependency_errors = _Event()

        self.__collector_weakref = None
        self._export_button_fn = export_button_fn
        self._cancel_button_fn = cancel_button_fn
        self._layer_manager = LayerManagerCore()
        self._post_exporter = LightspeedPosProcessExporter()

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
        omni.usd.get_context().open_stage(self._workspace_stage_path_norm)

        # Delete the temporary pre-processed replacement layer.
        os.remove(self._temp_stage_path)
        os.remove(self._temp_replacements_path)

    def get_default_export_path(self, create_if_not_exist: bool = False) -> Optional[str]:
        current_game_capture_folder = self._layer_manager.game_current_game_capture_folder()
        if not current_game_capture_folder:
            return None
        path = str(Path(current_game_capture_folder.path).parent.joinpath(constants.GAME_READY_ASSETS_FOLDER)) + os.sep
        if create_if_not_exist:
            Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def check_export_path(self, path) -> bool:
        stage = omni.usd.get_context().get_stage()
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

        context = omni.usd.get_context()
        stage = context.get_stage()

        if validate_dependencies:
            result_errors = self._validate_dependencies_exist(stage)
            if result_errors:
                self._dependency_errors(result_errors)
                return
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

        root_layer = stage.GetRootLayer()
        layer = self._layer_manager.get_layer(LayerType.replacement)
        if layer is None:
            carb.log_error("Can't find the replacement layer")
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

        preprocess(self._layer_manager)

        self._layer_manager.save_layer_as(LayerType.replacement, self._temp_replacements_path)

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
        self.__collector_weakref = None
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
                if prim.GetTypeName() in ["Shader"]:
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
                                if str_value.lower().endswith(".dds"):
                                    key = f"{chk}\n             {prim.GetPath().pathString}::{attr.GetName()}"
                                    if not result_errors.get(DependencyErrorTypes.TEXTURE_IS_DDS.value):
                                        result_errors[DependencyErrorTypes.TEXTURE_IS_DDS.value] = {}
                                    result_errors[DependencyErrorTypes.TEXTURE_IS_DDS.value][
                                        key
                                    ] = f"ERROR: {attr.GetName()} is a .dds path ----------> {str_value}"

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

                for primspec in prim.GetPrimStack():
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

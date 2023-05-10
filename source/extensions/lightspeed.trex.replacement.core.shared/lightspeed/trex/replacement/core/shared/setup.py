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
from pathlib import Path
from typing import Dict, Optional, Union

import carb
import omni.client
import omni.usd
from lightspeed.common import constants
from lightspeed.layer_manager.constants import LSS_LAYER_GAME_NAME, LSS_LAYER_MOD_NOTES
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.layer_types import LayerType, LayerTypeKeys
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Tf, Usd


class Setup:
    def __init__(self, context_name: str):
        self._default_attr = {"_layer_manager": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context = omni.usd.get_context(context_name)
        self._layer_manager = _LayerManagerCore(context_name=context_name)

    def get_layer(self):
        return self._layer_manager.get_layer(LayerType.replacement)

    @staticmethod
    def is_path_valid(path: str, existing_file: bool = True) -> bool:
        if not path or not path.strip():
            carb.log_error(f"'{path}' is not valid")
            return False
        if path.rpartition(".")[-1] not in ["usd", "usda", "usdc"]:
            carb.log_error(f"The path '{path}' is not a USD path")
            return False
        if existing_file:
            _, entry = omni.client.stat(path)
            if not (entry.flags & omni.client.ItemFlags.WRITEABLE_FILE):  # noqa PLC0325
                if entry.flags & omni.client.ItemFlags.READABLE_FILE:
                    carb.log_error(f"'{path}' is not writeable")
                return False
        else:
            result, entry = omni.client.stat(os.path.dirname(path))
            if result != omni.client.Result.OK or not (
                entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN
            ):  # noqa PLC0325
                return False
        if constants.CAPTURE_FOLDER in Path(path).parts or constants.REMIX_CAPTURE_FOLDER in Path(path).parts:
            carb.log_error(f"'{path}' is in the {constants.REMIX_CAPTURE_FOLDER} directory")
            return False
        if constants.GAME_READY_ASSETS_FOLDER in Path(path).parts:
            carb.log_error(f"'{path}' is in a {constants.GAME_READY_ASSETS_FOLDER} directory")
            return False
        return True

    def import_replacement_layer(
        self,
        path: str,
        use_existing_layer: bool = True,
        set_edit_target: bool = False,
        replace_existing: bool = True,
        sublayer_position: int = -1,
    ):
        capture_layer = self._layer_manager.get_layer(LayerType.capture)
        if not capture_layer:
            carb.log_error("A capture layer must be imported in the stage before a replacement layer can be imported.")
            return

        if replace_existing:
            self._layer_manager.remove_layer(LayerType.replacement)

        if use_existing_layer:
            carb.log_info(f"Importing mod layer {path}")
            layer = self._layer_manager.insert_sublayer(
                path,
                LayerType.replacement,
                set_as_edit_target=set_edit_target,
                sublayer_insert_position=sublayer_position,
            )
            carb.log_info("Ok")
        else:
            carb.log_info(f"Creating a new mod layer {path}")
            existing_layer = Sdf.Layer.Find(path)
            if existing_layer:
                existing_layer.Clear()
            layer = self._layer_manager.create_new_sublayer(
                LayerType.replacement,
                path=path,
                set_as_edit_target=set_edit_target,
                replace_existing=replace_existing,
                sublayer_create_position=sublayer_position,
            )
            carb.log_info("Ok")

        # replacement layer needs to have the same TimeCodesPerSecond as the capture layer
        # for reference deletion to work. See OM-42663 for more info.
        capture_stage = Usd.Stage.Open(capture_layer.realPath)
        time_codes = capture_stage.GetTimeCodesPerSecond()
        replacement_stage = Usd.Stage.Open(layer.realPath)
        replacement_stage.SetTimeCodesPerSecond(time_codes)

        layer_instance = self._layer_manager.get_layer_instance(LayerType.replacement)
        if layer_instance is None:
            carb.log_error(f"Can't find a layer schema type {LayerType.replacement.value}")
            return

        layer_instance.set_custom_layer_data(
            {LSS_LAYER_GAME_NAME: self._layer_manager.get_game_name_from_path(capture_layer.realPath)}
        )
        custom_layer_data = layer.customLayerData
        custom_data_layer_inst = layer_instance.get_custom_layer_data()
        if custom_data_layer_inst:
            custom_layer_data.update(custom_data_layer_inst)
        layer.customLayerData = custom_layer_data

        layer.Save()

    @staticmethod
    def is_mod_file(path: str) -> bool:
        try:
            layer = Sdf.Layer.FindOrOpen(path)
        except Tf.ErrorException as e:
            carb.log_verbose(e)
            return False
        if not layer:
            return False
        if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == LayerType.replacement.value:
            return True
        return False

    def get_existing_mod_file(self, dirname: Union[str, Path]) -> Optional[str]:
        """
        Args:
            dirname: The path to search for mod files

        Returns:
            The full path of the mod file if it's found. None otherwise
        """
        if not dirname:
            return None

        result, entries = omni.client.list(str(dirname))
        if result != omni.client.Result.OK:
            return None

        for entry in entries:
            mod_file = omni.client.combine_urls(str(dirname), entry.relative_path)
            if Path(mod_file).name.lower() == constants.GAME_READY_REPLACEMENTS_FILE.lower() and self.is_mod_file(
                mod_file
            ):
                return mod_file

        return None

    def get_layer_notes(self, mod_file_path: Union[str, Path]) -> Optional[str]:
        """
        Args:
            mod_file_path: The full path to an existing mod file

        Returns:
            The notes saved in the file if present. None otherwise
        """
        if not mod_file_path:
            return None

        existing_mod_layer = Sdf.Layer.FindOrOpen(str(mod_file_path))
        custom_layer_data = existing_mod_layer.customLayerData
        return custom_layer_data[LSS_LAYER_MOD_NOTES] if LSS_LAYER_MOD_NOTES in custom_layer_data else None

    def get_replaced_hashes(self, path: Optional[Union[str, Path]] = None) -> Dict[Sdf.Layer, Dict[str, Sdf.Path]]:
        def get_sublayers_recursive(path: Sdf.Path):
            layer = Sdf.Layer.FindOrOpen(path)
            if not layer:
                return []
            sublayers = [layer]
            for sub in [layer.ComputeAbsolutePath(s) for s in layer.subLayerPaths]:
                sublayers.extend(get_sublayers_recursive(sub))
            return sublayers

        hashes = {}
        if path and self.is_path_valid(str(path)):
            replacements = path
        else:
            replacement_layer = self.get_layer()
            if not replacement_layer:
                return hashes
            replacements = replacement_layer.identifier
        for sublayer in get_sublayers_recursive(replacements):
            hashes[sublayer] = self._layer_manager.get_layer_hashes_no_comp_arcs(sublayer)
        return hashes

    def destroy(self):
        _reset_default_attrs(self)

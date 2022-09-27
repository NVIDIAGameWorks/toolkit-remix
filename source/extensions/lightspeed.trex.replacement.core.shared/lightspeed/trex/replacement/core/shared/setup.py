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
import omni.usd
from lightspeed.layer_manager.constants import LSS_LAYER_GAME_NAME
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.layer_types import LayerType, LayerTypeKeys
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Usd


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
            carb.log_error(f"{path} is not valid")
            return False
        if path.rpartition(".")[-1] not in ["usd", "usda", "usdc"]:
            carb.log_error(f"The path {path} is not an USD path")
            return False
        if existing_file:
            _, entry = omni.client.stat(path)
            if not (entry.flags & omni.client.ItemFlags.WRITEABLE_FILE):  # noqa PLC0325
                if entry.flags & omni.client.ItemFlags.READABLE_FILE:
                    carb.log_error(f"{path} is not writeable")
                return False
        else:
            result, entry = omni.client.stat(os.path.dirname(path))
            if result != omni.client.Result.OK or not (
                entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN
            ):  # noqa PLC0325
                return False
        return True

    def import_replacement_layer(self, path: str, use_existing_layer: bool = True):

        capture_layer = self._layer_manager.get_layer(LayerType.capture)
        if not capture_layer:
            carb.log_error(
                "A capture layer has to be in the stage before to create a replacement layer.\n"
                "Please import a capture layer."
            )
            return

        self._layer_manager.remove_layer(LayerType.replacement)
        if use_existing_layer:
            carb.log_info(f"Importing mod layer {path}")
            layer = self._layer_manager.insert_sublayer(path, LayerType.replacement, sublayer_insert_position=0)
            carb.log_info("Ok")
        else:
            carb.log_info(f"Creating a new mod layer {path}")
            existing_layer = Sdf.Layer.Find(path)
            if existing_layer:
                existing_layer.Clear()
            layer = self._layer_manager.create_new_sublayer(
                LayerType.replacement, path=path, sublayer_create_position=0
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

    def is_mod_file(self, path: str) -> bool:
        layer = Sdf.Layer.FindOrOpen(path)
        if not layer:
            return False
        if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == LayerType.replacement.value:
            return True
        return False

    def destroy(self):
        _reset_default_attrs(self)

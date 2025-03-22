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

import functools
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import carb
import omni.client
import omni.usd
from lightspeed.common import constants
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core.data_models import LayerType, LayerTypeKeys
from omni.flux.utils.common import async_wrap as _async_wrap
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from PIL import Image
from pxr import Sdf, Usd, UsdGeom


class Setup:
    def __init__(self, context_name: str):
        self._default_attr = {
            "_layer_manager": None,
            "_subscription_stage_event": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.__directory = None
        self._context = omni.usd.get_context(context_name)
        self._layer_manager = _LayerManagerCore(context_name=context_name)

        self._subscription_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_load_event, name="Recent file loaded"
        )

        _get_event_manager_instance().register_global_custom_event(
            constants.GlobalEventNames.IMPORT_CAPTURE_LAYER.value
        )

    def get_layer(self):
        return self._layer_manager.get_layer(LayerType.capture)

    def __copy_metadata_from_stage_to_stage(self, stage_source, stage_destination):
        # copy over layer-meta-data from capture layer
        with Usd.EditContext(stage_destination, stage_destination.GetRootLayer()):
            UsdGeom.SetStageUpAxis(stage_destination, UsdGeom.GetStageUpAxis(stage_source))
            UsdGeom.SetStageMetersPerUnit(stage_destination, UsdGeom.GetStageMetersPerUnit(stage_source))
            time_codes = stage_source.GetTimeCodesPerSecond()
            stage_destination.SetTimeCodesPerSecond(time_codes)

    @staticmethod
    def is_path_valid(path: str, error_callback: Optional[Callable[[str, str], None]] = None) -> bool:
        error_title = "Wrong capture directory"
        if not path or not path.strip():
            if error_callback is not None:
                error_callback(error_title, f"{path} is not valid")
            return False
        _, entry = omni.client.stat(path)
        if not (entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN):  # noqa PLC0325
            if error_callback is not None:
                error_callback(error_title, f"{path} is not a directory")
            return False
        if str(Path(path).stem) not in [constants.CAPTURE_FOLDER, constants.REMIX_CAPTURE_FOLDER]:
            if error_callback is not None:
                error_callback(error_title, f"{path} is not a 'capture' folder")
            return False
        return True

    @staticmethod
    def get_game_icon_from_folder(folder_path: str) -> Optional[str]:
        icons = list(Path(folder_path).glob("*_icon.bmp"))
        return str(icons[0]) if icons else None

    @staticmethod
    def get_upscaled_game_icon_from_folder(folder_path: str) -> Optional[str]:
        default_icon = Setup.get_game_icon_from_folder(folder_path)
        if not default_icon:
            return None
        # first we convert the bmp to png without alpha
        png_file = default_icon.replace("_icon.bmp", "_icon.png")
        with Image.open(default_icon) as im1:
            im1 = im1.convert("RGB")
            im1.save(png_file)
        return str(png_file)

    @omni.usd.handle_exception
    async def deferred_get_upscaled_game_icon_from_folder(self, folder_path: str, callback):  # noqa PLW0238
        wrapped_fn = _async_wrap(functools.partial(self.get_upscaled_game_icon_from_folder, folder_path))
        result = await wrapped_fn()
        callback(result)

    def __on_load_event(self, event):
        if event.type in [int(omni.usd.StageEventType.OPENED)]:
            capture_layer = self._layer_manager.get_layer(LayerType.capture)
            if not capture_layer:
                return
            root_layer = self._context.get_stage().GetRootLayer()
            if not root_layer:
                return
            if root_layer.customLayerData.get("cameraSettings", {}).get("Perspective", {}).get("position", {}):
                return
            _get_event_manager_instance().call_global_custom_event(
                constants.GlobalEventNames.IMPORT_CAPTURE_LAYER.value
            )

    def import_capture_layer(self, path: str):
        carb.log_info(f"Import capture layer {path}")
        # copy over layer-meta-data from capture layer
        stage = self._context.get_stage()
        capture_stage = Usd.Stage.Open(path)
        self.__copy_metadata_from_stage_to_stage(capture_stage, stage)

        # delete existing one if exists
        self._layer_manager.remove_layer(LayerType.capture)
        # add the capture layer
        self._layer_manager.insert_sublayer(
            path, LayerType.capture, add_custom_layer_data=False, set_as_edit_target=False
        )
        self._layer_manager.lock_layer(LayerType.capture)
        _get_event_manager_instance().call_global_custom_event(constants.GlobalEventNames.IMPORT_CAPTURE_LAYER.value)

    def set_directory(self, path: str):
        self.__directory = path

    def get_directory(self) -> str:
        return self.__directory

    @staticmethod
    def is_capture_file(path: str) -> bool:
        layer = Sdf.Layer.FindOrOpen(path)
        return Setup.is_layer_a_capture_file(layer)

    @staticmethod
    def is_layer_a_capture_file(layer: Sdf.Layer) -> bool:
        if not layer:
            return False
        if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == LayerType.capture.value:
            return True
        return False

    def get_game_name(self, path: str) -> str:
        return self._layer_manager.get_game_name_from_path(path)

    def _check_directory(self) -> bool:
        if not self.__directory:
            carb.log_error("Please set the current directory")
            return False
        stem = Path(self.__directory).name
        if stem not in [constants.CAPTURE_FOLDER, constants.REMIX_CAPTURE_FOLDER]:
            carb.log_error(f"{self.__directory} is not a capture directory")
            return False
        return True

    @omni.usd.handle_exception
    async def deferred_get_capture_files(self, callback):  # noqa PLW0238
        wrapped_fn = _async_wrap(self.get_capture_files)
        result = await wrapped_fn()
        await callback(result)

    def get_capture_files(self) -> List[str]:
        def _get_files(_file):
            return _file.is_file() and _file.suffix in constants.USD_EXTENSIONS and self.is_capture_file(str(_file))

        if not self._check_directory():
            return []

        result = [str(path) for path in Path(self.__directory).iterdir() if _get_files(path)]

        # It will deadlock
        # result = []
        # with concurrent.futures.ThreadPoolExecutor() as executor:
        #     for file, is_valid in executor.map(_get_files, Path(self.__directory).iterdir()):
        #         if is_valid:
        #             result.append(str(file))
        return sorted(result, reverse=True)

    def get_capture_image(self, path: str) -> Optional[str]:
        for folder in [".thumbs", "thumbs"]:
            image_path = Path(path).parent / folder / f"{Path(path).name}.dds"
            if image_path.exists():
                return str(image_path)
        return None

    @staticmethod
    def get_hashes_from_capture_layer(layer: Sdf.Layer) -> Tuple[Dict[str, Sdf.Path], Dict[str, Set[str]]]:
        """
        Faster version that use pre defined prims from a capture layer

        Args:
            layer: The layer to traverse

        Returns:
            A dictionary of the various hashes found and their respective prims
        """
        result = {}
        # for replaced assets, if a prim is a key of this dictionary, we use the list as a value instead.
        # For example, for material, if a material as an override and this materials is assigned to multiple meshes
        # we set all meshes as "replaced".
        result_switch_grouped = {}
        for path in [constants.ROOTNODE_LOOKS, constants.ROOTNODE_MESHES, constants.ROOTNODE_LIGHTS]:
            prim = layer.GetObjectAtPath(path)
            if path == constants.ROOTNODE_MESHES:
                for child in prim.nameChildren:
                    mesh_hash = str(child.path)[-16:]
                    if constants.MATERIAL_RELATIONSHIP in child.relationships:
                        materials = child.relationships[constants.MATERIAL_RELATIONSHIP].targetPathList.explicitItems
                        # Always take the first material as there should never be more than 1 material here
                        mat_hash = str(materials[0])[-16:]
                        result[mat_hash] = materials[0]
                        if mat_hash not in result_switch_grouped:
                            result_switch_grouped[mat_hash] = set()
                        result_switch_grouped[mat_hash].add(mesh_hash)
                    result[mesh_hash] = child.path
            else:
                for child in prim.nameChildren:
                    result[str(child.path)[-16:]] = child.path
        return result, result_switch_grouped

    @omni.usd.handle_exception
    async def async_get_replaced_hashes(self, layer_path: str, replaced_items: List[str]) -> Tuple[Set[str], Set[str]]:
        """
        Get the number of asset replaced from a capture layer and the current replacement layer

        Args:
            layer_path: the capture layer path
            replaced_items: list of hash from the replacement layer

        Returns:
            Replaced hash from the current layer path, all hashes from the current layer path
        """
        wrapped_fn = _async_wrap(functools.partial(Sdf.Layer.FindOrOpen, layer_path))
        _layer = await wrapped_fn()
        if _layer is None:
            return set(), set()
        hashes, grouped_hashes = self.get_captured_hashes(_layer, ignore_capture_check=True)
        captured_items = set()
        if hashes:
            captured_items = set(hashes.keys())
        replaced_result = set()
        for replaced_item in replaced_items:
            if replaced_item in replaced_result:
                continue
            # if this is a material was edited/replaced and the material is from mesh(es), we set the mesh(es)
            # as replaced asset(s) (not the material)
            mesh_from_mat = grouped_hashes.get(replaced_item, set())
            if mesh_from_mat:
                for mesh in mesh_from_mat:
                    replaced_result.add(mesh)
                continue
            if replaced_item in captured_items:
                replaced_result.add(replaced_item)
        all_assets_result = set()
        for captured_item in captured_items:
            if captured_item in all_assets_result or captured_item in grouped_hashes:
                continue
            all_assets_result.add(captured_item)
        return replaced_result, all_assets_result

    def get_captured_hashes(
        self, layer: Sdf.Layer, ignore_capture_check: bool = False
    ) -> Tuple[Dict[str, Sdf.Path], Dict[str, Set[str]]]:
        if not ignore_capture_check and not self.is_layer_a_capture_file(layer):
            return {}, {}
        return Setup.get_hashes_from_capture_layer(layer)

    def destroy(self):
        _get_event_manager_instance().unregister_global_custom_event(
            constants.GlobalEventNames.IMPORT_CAPTURE_LAYER.value
        )
        _reset_default_attrs(self)

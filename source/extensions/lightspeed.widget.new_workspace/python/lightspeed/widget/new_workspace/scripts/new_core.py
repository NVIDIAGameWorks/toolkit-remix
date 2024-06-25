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

import asyncio
import functools
import typing

import carb.settings
import omni.kit.commands
import omni.kit.window.file
import omni.usd
from lightspeed.layer_manager.core import LSS_LAYER_GAME_NAME, LayerManagerCore, LayerType
from omni.kit.usd.layers import LayerUtils
from omni.usd import handle_exception

if typing.TYPE_CHECKING:
    from lightspeed.widget.content_viewer.scripts.core import ContentData

from pxr import Sdf, Usd, UsdGeom


class NewGameWorkspaceCore:
    def __init__(self):
        self.__default_attr = {"_stage_event_sub": None}
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self._layer_manager = LayerManagerCore()

        self.__fns_to_execute_on_event = []

    @handle_exception
    async def ___deferred_setup_persepctive_camera(self):
        await omni.kit.app.get_app().next_update_async()

        # setup the session camera to match the capture camera
        stage = omni.usd.get_context().get_stage()
        capture_layer = self._layer_manager.get_layer(LayerType.capture)
        if capture_layer is None:
            carb.log_warn("Can't find a capture layer, won't be setting up the default camera to match game")
            return
        session_layer = stage.GetSessionLayer()
        current_edit_layer = Sdf.Find(LayerUtils.get_edit_target(stage))
        swap_edit_targets = current_edit_layer != session_layer
        try:
            if swap_edit_targets:
                LayerUtils.set_edit_target(stage, session_layer.identifier)

            carb.log_info("Setting up perspective camera from capture")
            Sdf.CopySpec(capture_layer, "/RootNode/Camera", session_layer, "/OmniverseKit_Persp")
        finally:
            if swap_edit_targets:
                LayerUtils.set_edit_target(stage, current_edit_layer.identifier)

    def load_game_workspace(self, path, callback=None):
        context = omni.usd.get_context()
        context.new_stage_with_callback(functools.partial(self.__load_game_workspace, path, callback=callback))

    def __load_game_workspace(self, path, result: bool, error: str, callback=None):
        if callback:
            self.__fns_to_execute_on_event.append(callback)
        # Crash, use omni.kit.window.file.open_stage
        # context = omni.usd.get_context()
        # context.open_stage(path)
        omni.kit.window.file.open_stage(path)
        self._layer_manager.set_edit_target_layer(LayerType.replacement)
        asyncio.ensure_future(self.___deferred_setup_persepctive_camera())

    def create_game_workspace(
        self, capture_data, use_existing_layer, existing_enhancement_layer_path, game, callback=None
    ):
        context = omni.usd.get_context()
        context.new_stage_with_callback(
            functools.partial(
                self.__create_game_workspace,
                capture_data,
                use_existing_layer,
                existing_enhancement_layer_path,
                game,
                callback=callback,
            )
        )

    def __copy_metadata_from_stage_to_stage(self, stage_source, stage_destination):
        # copy over layer-meta-data from capture layer
        UsdGeom.SetStageUpAxis(stage_destination, UsdGeom.GetStageUpAxis(stage_source))
        UsdGeom.SetStageMetersPerUnit(stage_destination, UsdGeom.GetStageMetersPerUnit(stage_source))
        time_codes = stage_source.GetTimeCodesPerSecond()
        stage_destination.SetTimeCodesPerSecond(time_codes)

    def __create_game_workspace(
        self,
        capture_data: "ContentData",
        use_existing_layer: bool,
        enhancement_layer_path: str,
        game: "ContentData",
        result: bool,
        error: str,
        callback=None,
    ):
        if callback:
            self.__fns_to_execute_on_event.append(callback)
        self._setup_stage_event()
        carb.log_info("Create game workspace")

        # copy over layer-meta-data from capture layer
        stage = omni.usd.get_context().get_stage()
        capture_stage = Usd.Stage.Open(capture_data.path)
        self.__copy_metadata_from_stage_to_stage(capture_stage, stage)

        # add the capture layer
        self._layer_manager.insert_sublayer(capture_data.path, LayerType.capture, add_custom_layer_data=False)
        self._layer_manager.lock_layer(LayerType.capture)
        asyncio.ensure_future(self.___deferred_setup_persepctive_camera())

        # add the replacement layer if exist
        if use_existing_layer:
            self._layer_manager.insert_sublayer(
                enhancement_layer_path, LayerType.replacement, sublayer_insert_position=0
            )
        else:  # if not, we create it
            layer = self._layer_manager.create_new_sublayer(
                LayerType.replacement, path=enhancement_layer_path, sublayer_create_position=0
            )
            # replacement layer needs to have the same TimeCodesPerSecond as the capture layer
            # for reference deletion to work. See OM-42663 for more info.
            time_codes = capture_stage.GetTimeCodesPerSecond()
            replacement_stage = Usd.Stage.Open(layer.realPath)
            replacement_stage.SetTimeCodesPerSecond(time_codes)
            replacement_stage.Save()
        layer_instance = self._layer_manager.get_layer_instance(LayerType.replacement)
        if layer_instance is None:
            carb.log_error(f"Can't find a layer schema type {LayerType.replacement.value}")
            return
        layer_instance.set_custom_layer_data({LSS_LAYER_GAME_NAME: game.title})

    def _setup_stage_event(self):
        """We listen to stage event when we are running but turn it off otherwise"""
        self._stage_event_sub = (
            omni.usd.get_context()
            .get_stage_event_stream()
            .create_subscription_to_pop(self._on_stage_event, name="Load Game Workspace Core")
        )

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.ASSETS_LOADED):
            if self.__fns_to_execute_on_event:
                for fn_to_execute_on_event in self.__fns_to_execute_on_event:
                    fn_to_execute_on_event()
            self._stage_event_sub = None
            self.__fns_to_execute_on_event = []

    def destroy(self):
        self.__fns_to_execute_on_event = []
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

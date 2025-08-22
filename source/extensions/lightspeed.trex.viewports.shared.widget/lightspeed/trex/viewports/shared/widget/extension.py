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

import contextlib
from typing import TYPE_CHECKING, Dict, Optional

import carb
import omni.ext
from lightspeed.light.gizmos.layer import LightGizmosLayer as _LightGizmosLayer
from lightspeed.particle.gizmos.layer import ParticleGizmosLayer as _ParticleGizmosLayer
from lightspeed.trex.viewports.manipulators import camera_default_factory as _manipulator_camera_default
from lightspeed.trex.viewports.manipulators import grid_default_factory as _manipulator_grid_default
from lightspeed.trex.viewports.manipulators import prim_transform_default_factory as _prim_transform_manipulator
from lightspeed.trex.viewports.manipulators import selection_default_factory as _manipulator_selection_default
from lightspeed.ui_scene.light_manipulator.layer import LightManipulatorLayer as _LightManipulatorLayer
from omni.kit.viewport.registry import RegisterScene, RegisterViewportLayer
from omni.kit.widget.toolbar import get_instance as _get_toolbar_instance

from .scene.layer import ViewportSceneLayer
from .scene.scenes import camera_axis_default_factory as _camera_axis_default_factory
from .scene.scenes import origin_default_factory as _origin_default_factory
from .setup_ui import SetupUI as _ViewportSetupUI
from .stats.layer import ViewportStatsLayer
from .tools.layer import ViewportToolsLayer
from .tools.teleport import create_button_instance as _create_teleporter_toolbar_button_group
from .tools.teleport import delete_button_instance as _delete_teleporter_toolbar_button_group
from .tools.teleport import teleporter_factory as _teleporter_factory

if TYPE_CHECKING:
    from omni.kit.widget.viewport.api import ViewportAPI

_VIEWPORT_MANAGER_INSTANCE: dict[str, _ViewportSetupUI] | None = None


def get_instances() -> Optional[Dict[str, _ViewportSetupUI]]:
    return _VIEWPORT_MANAGER_INSTANCE


def get_instance(context_name: str) -> Optional[_ViewportSetupUI]:
    if context_name in _VIEWPORT_MANAGER_INSTANCE:
        return _VIEWPORT_MANAGER_INSTANCE[context_name]
    return None


def get_active_viewport() -> Optional[_ViewportSetupUI]:
    if not _VIEWPORT_MANAGER_INSTANCE:
        return None
    for viewport in _VIEWPORT_MANAGER_INSTANCE.values():
        if viewport.is_active():
            return viewport
    return None


def create_instance(context_name: str) -> _ViewportSetupUI:
    global _VIEWPORT_MANAGER_INSTANCE
    viewport = _ViewportSetupUI(context_name)
    if _VIEWPORT_MANAGER_INSTANCE is None:
        _VIEWPORT_MANAGER_INSTANCE = {}
    _VIEWPORT_MANAGER_INSTANCE.update({context_name: viewport})
    return viewport


def get_viewport_api(context_name: str) -> Optional["ViewportAPI"]:
    viewport = get_instance(context_name)
    if not viewport:
        return None
    return viewport.viewport_api


class TrexViewportSharedExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def __init__(self):
        super().__init__()
        self.__registered = None
        self.__teleport_button_group = None

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.viewports.shared.widget] Startup")
        self.__register_scenes()
        self.__add_tools()

    def __register_scenes(self):
        # scenes. But scenes are filtered in ViewportSceneLayer
        self.__registered = []
        self.__registered.append(
            RegisterScene(_manipulator_selection_default, "omni.kit.viewport.manipulator.Selection")
        )
        self.__registered.append(RegisterScene(_manipulator_camera_default, "omni.kit.viewport.manipulator.Camera"))
        self.__registered.append(RegisterScene(_prim_transform_manipulator, "omni.kit.lss.viewport.manipulator.prim"))
        self.__registered.append(RegisterScene(_teleporter_factory, "omni.kit.lss.viewport.tools.teleport"))

        # self.__registered.append(
        #     RegisterScene(_grid_default_factory, "omni.kit.viewport.scene.SimpleGrid")
        # )  # use legacy grid for now
        self.__registered.append(RegisterScene(_origin_default_factory, "omni.kit.viewport.scene.SimpleOrigin"))
        self.__registered.append(
            RegisterViewportLayer(_camera_axis_default_factory, "omni.kit.viewport.scene.CameraAxisLayer")
        )

        # legacy grid
        self.__registered.append(RegisterScene(_manipulator_grid_default, "omni.kit.viewport.scene.LegacyGrid"))

        # layers
        self.__registered.append(RegisterViewportLayer(ViewportStatsLayer, "omni.kit.viewport.ViewportStats"))
        self.__registered.append(RegisterViewportLayer(ViewportSceneLayer, "omni.kit.viewport.SceneLayer"))
        self.__registered.append(RegisterViewportLayer(_LightGizmosLayer, "omni.kit.viewport.LightGizmosLayer"))
        self.__registered.append(RegisterViewportLayer(_ParticleGizmosLayer, "omni.kit.viewport.ParticleGizmosLayer"))
        self.__registered.append(
            RegisterViewportLayer(_LightManipulatorLayer, "omni.kit.viewport.LightManipulatorLayer")
        )
        self.__registered.append(RegisterViewportLayer(ViewportToolsLayer, "omni.kit.viewport.ViewportTools"))

    def __unregister_scenes(self, registered):
        for item in registered:
            with contextlib.suppress(Exception):
                item.destroy()

    def __add_tools(self):
        toolbar = _get_toolbar_instance()
        self.__teleport_button_group = _create_teleporter_toolbar_button_group()
        toolbar.add_widget(self.__teleport_button_group, 12)

    def __remove_tools(self):
        if self.__teleport_button_group:
            toolbar = _get_toolbar_instance()
            toolbar.remove_widget(self.__teleport_button_group)
            self.__teleport_button_group.clean()
            _delete_teleporter_toolbar_button_group()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.viewports.shared.widget] Shutdown")
        if self.__registered:
            self.__unregister_scenes(self.__registered)
        self.__remove_tools()
        self.__registered = None

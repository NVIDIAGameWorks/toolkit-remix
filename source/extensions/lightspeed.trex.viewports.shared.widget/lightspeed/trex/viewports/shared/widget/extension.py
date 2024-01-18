"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import contextlib
from typing import TYPE_CHECKING, Dict, Optional

import carb
import omni.ext
from lightspeed.light.gizmos.layer import LightGizmosLayer as _LightGizmosLayer
from lightspeed.trex.viewports.manipulators import camera_default_factory as _manipulator_camera_default
from lightspeed.trex.viewports.manipulators import grid_default_factory as _manipulator_grid_default
from lightspeed.trex.viewports.manipulators import prim_transform_default_factory as _prim_transform_manipulator
from lightspeed.trex.viewports.manipulators import selection_default_factory as _manipulator_selection_default
from omni.kit.viewport.registry import RegisterScene, RegisterViewportLayer

from .scene.layer import ViewportSceneLayer
from .scene.scenes import camera_axis_default_factory as _camera_axis_default_factory
from .scene.scenes import origin_default_factory as _origin_default_factory
from .setup_ui import SetupUI as _ViewportSetupUI
from .stats.layer import ViewportStatsLayer
from .tools.layer import ViewportToolsLayer

if TYPE_CHECKING:
    from omni.kit.widget.viewport.api import ViewportAPI

_VIEWPORT_MANAGER_INSTANCE = None


def get_instances() -> Optional[Dict[str, _ViewportSetupUI]]:
    return _VIEWPORT_MANAGER_INSTANCE


def get_instance(context_name: str) -> Optional[_ViewportSetupUI]:
    if context_name in _VIEWPORT_MANAGER_INSTANCE:
        return _VIEWPORT_MANAGER_INSTANCE[context_name]
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

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.viewports.shared.widget] Startup")
        self.__register_scenes()

    def __register_scenes(self):
        # scenes. But scenes are filtered in ViewportSceneLayer
        self.__registered = []
        self.__registered.append(
            RegisterScene(_manipulator_selection_default, "omni.kit.viewport.manipulator.Selection")
        )
        self.__registered.append(RegisterScene(_manipulator_camera_default, "omni.kit.viewport.manipulator.Camera"))
        self.__registered.append(RegisterScene(_prim_transform_manipulator, "omni.kit.lss.viewport.manipulator.prim"))

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
        self.__registered.append(RegisterViewportLayer(ViewportToolsLayer, "omni.kit.viewport.ViewportTools"))
        self.__registered.append(RegisterViewportLayer(_LightGizmosLayer, "omni.kit.viewport.LightGizmosLayer"))

    def __unregister_scenes(self, registered):
        for item in registered:
            with contextlib.suppress(Exception):
                item.destroy()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.viewports.shared.widget] Shutdown")
        if self.__registered:
            self.__unregister_scenes(self.__registered)
        self.__registered = None

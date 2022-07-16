"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.viewports.manipulators import create_selection_default_manipulator
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.manipulator.camera import ViewportCameraManipulator
from omni.kit.manipulator.prim import PrimTransformManipulator
from omni.kit.widget.viewport import ViewportWidget
from omni.ui import scene as sc


class SetupUI:
    def __init__(self, context):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_viewport": None,
            "_camera_manip": None,
            "_prim_manip": None,
            "_selection": None,
            "_scene_view": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = context  # can get the name of the context?
        self.__create_ui()

    def __create_ui(self):
        with ui.ZStack():
            ui.Rectangle(name="WorkspaceBackground")
            self._viewport = ViewportWidget(
                usd_context_name=TrexContexts.STAGE_CRAFT.value,
                resolution="fill_frame",
                camera_path="/OmniverseKit_Persp",
            )
            self._scene_view = sc.SceneView(aspect_ratio_policy=sc.AspectRatioPolicy.STRETCH)

            with self._scene_view.scene:
                self._prim_manip = PrimTransformManipulator(
                    usd_context_name=TrexContexts.STAGE_CRAFT.value, viewport_api=self._viewport.viewport_api
                )
                self._camera_manip = ViewportCameraManipulator(self._viewport.viewport_api)
                self._selection = create_selection_default_manipulator(self._viewport.viewport_api)
            self._viewport.viewport_api.add_scene_view(self._scene_view)

    def destroy(self):
        _reset_default_attrs(self)

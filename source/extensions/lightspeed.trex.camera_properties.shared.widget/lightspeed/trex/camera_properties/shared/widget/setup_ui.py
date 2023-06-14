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
import omni.usd
from omni.flux.properties_pane.properties.usd.widget import PropertyWidget as _PropertyWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import UsdGeom


class SetupUI:
    def __init__(self, context_name: str):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_frame_none": None,
            "_properties_frames": None,
            "_property_widget": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._properties_frames = {}
        self.__create_ui()

    def __create_ui(self):
        with ui.ZStack():
            self._frame_none = ui.Frame(visible=True)
            self._properties_frames[None] = self._frame_none
            with self._frame_none:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        ui.Spacer(height=0)
                        with ui.VStack(width=0):
                            ui.Spacer()
                            ui.Label("None", name="PropertiesWidgetLabel")
                            ui.Spacer()
                        ui.Spacer(height=0)
            self._frame_mesh_prim = ui.Frame(visible=False)
            self._properties_frames[UsdGeom.Camera] = self._frame_mesh_prim
            with self._frame_mesh_prim:
                with ui.VStack(spacing=8):
                    self._property_widget = _PropertyWidget(self._context_name)

    def refresh(self, path: str):
        stage = self._context.get_stage()
        if not stage:
            return
        found = False
        prim = stage.GetPrimAtPath(path)
        if not prim.IsValid():
            return
        for item_type, frame in self._properties_frames.items():
            if item_type is None:
                self._properties_frames[None].visible = False
                continue
            value = prim.IsA(item_type)
            frame.visible = value
            if value:
                found = True
        if not found:
            self._properties_frames[None].visible = True
        else:
            self._property_widget.show(True)

            self._property_widget.refresh([path])

    def show(self, value):
        self._property_widget.show(value)

    def destroy(self):
        _reset_default_attrs(self)

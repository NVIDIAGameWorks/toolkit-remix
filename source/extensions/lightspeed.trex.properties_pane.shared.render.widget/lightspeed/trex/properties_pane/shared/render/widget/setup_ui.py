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
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class RenderPane:
    def __init__(self, context_name: str):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_root_frame": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self.__create_ui()

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            ui.Label("Render settings")

    def __on_collapsable_frame_changed(self, widget, collapsed):  # noqa PLW0238, TODO
        widget.show(not collapsed)

    def refresh(self, engine_name: str, render_mode: str):
        pass

    def show(self, value: bool):
        # Update the widget visibility
        self._root_frame.visible = value

    def destroy(self):
        _reset_default_attrs(self)

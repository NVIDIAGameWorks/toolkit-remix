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

import omni.ui as ui
import carb.settings
from lightspeed.hdremix.renderer_settings.dlss_settings import (
    DLSS_SETTINGS_TITLE,
    SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE,
)
from lightspeed.hdremix.renderer_settings.dlss_settings_panel import DlssSettingsPanel
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class RenderPane:
    """Show global renderer controls in the viewport properties pane."""

    def __init__(self, context_name: str):
        """Build the render settings pane."""

        self._default_attr = {
            "_root_frame": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._settings = carb.settings.get_settings()
        self._dlss_availability_subscription = None
        self._dlss_frame = None
        self._dlss_settings_panel = None

        self._context_name = context_name
        self.__create_ui()

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            self._dlss_frame = ui.Frame(visible=bool(self._settings.get(SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE)))
            with self._dlss_frame:
                with ui.CollapsableFrame(DLSS_SETTINGS_TITLE, collapsed=False):
                    self._dlss_settings_panel = DlssSettingsPanel("render_settings_dlss_neural_rendering")
        self._dlss_availability_subscription = self._settings.subscribe_to_node_change_events(
            SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE, self.__on_dlss_neural_rendering_availability_changed
        )

    def __on_dlss_neural_rendering_availability_changed(self, *_args, **_kwargs) -> None:
        if self._dlss_frame is not None:
            self._dlss_frame.visible = bool(self._settings.get(SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE))

    def __on_collapsable_frame_changed(self, widget, collapsed):
        widget.show(not collapsed)

    def refresh(self, engine_name: str, render_mode: str):
        pass

    def show(self, value: bool):
        # Update the widget visibility
        self._root_frame.visible = value

    def destroy(self):
        """Release the shared DLSS panel and render-pane state."""
        if self._settings is not None and self._dlss_availability_subscription is not None:
            self._settings.unsubscribe_to_change_events(self._dlss_availability_subscription)
        self._dlss_availability_subscription = None
        self._dlss_frame = None
        self._settings = None
        if self._dlss_settings_panel is not None:
            self._dlss_settings_panel.destroy()
            self._dlss_settings_panel = None
        _reset_default_attrs(self)

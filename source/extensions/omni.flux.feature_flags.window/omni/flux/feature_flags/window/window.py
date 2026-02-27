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

__all__ = ["FeatureFlagsWindow"]

import carb
import omni.appwindow
from omni import ui
from omni.flux.feature_flags.widget import FeatureFlagsWidget
from omni.flux.utils.common import reset_default_attrs


class FeatureFlagsWindow:
    FEATURE_FLAGS_WINDOW_TITLE = "/exts/omni.flux.feature_flags.window/title"

    def __init__(self, **kwargs):
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._window = None
        self._widget = None
        self._app_window_size_changed_sub = None

        title = carb.settings.get_settings().get(self.FEATURE_FLAGS_WINDOW_TITLE) or "Feature Flags"

        self._build_ui(title, **kwargs)

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = {
            "_window": None,
            "_widget": None,
            "_app_window_size_changed_sub": None,
        }
        return default_attr

    @property
    def window(self) -> ui.Window | None:
        return self._window

    def show(self, value: bool):
        """
        Show or hide the window.

        Args:
            value: True to show the window, False to hide it.
        """
        self._window.visible = value
        if value:
            self._center_window()

    def _center_window(self):
        """Re-center the window in the current application viewport."""
        if not self._window:
            return
        app_window = omni.appwindow.get_default_app_window()
        size = app_window.get_size()
        dpi_scale = ui.Workspace.get_dpi_scale()
        viewport_width = size[0] / dpi_scale
        viewport_height = size[1] / dpi_scale
        self._window.position_x = (viewport_width - self._window.width) / 2
        self._window.position_y = (viewport_height - self._window.height) / 2

    def _on_app_window_resized(self, _):
        """Re-center the dialog when the main application window is resized."""
        if self._window and self._window.visible:
            self._center_window()

    def _on_visibility_changed(self, value: bool):
        """
        Pass visibility change event to the widget.

        Args:
            value: True to show the widget, False to hide it.
        """
        if self._widget:
            self._widget.show(value)

    def _build_ui(self, title: str, **kwargs):
        self._window = ui.Window(
            title,
            name=kwargs.get("name") or title,
            width=kwargs.get("width") or 500,
            height=kwargs.get("height") or 400,
            visibility_changed_fn=self._on_visibility_changed,
            **kwargs,
        )

        with self._window.frame:
            self._widget = FeatureFlagsWidget()

        self._app_window_size_changed_sub = (
            omni.appwindow.get_default_app_window()
            .get_window_resize_event_stream()
            .create_subscription_to_pop(self._on_app_window_resized, name="FeatureFlagsWindowAppWindowResized")
        )

        return self._window

    def destroy(self):
        reset_default_attrs(self)

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
from typing import Any
from collections.abc import Callable

import carb.events
import omni.appwindow
import omni.ui as ui
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.kit.browser.asset.delegate import AssetDetailDelegate as _AssetDetailDelegate
from omni.kit.browser.asset.model import AssetBrowserModel as _AssetBrowserModel
from omni.kit.browser.folder.core import TreeFolderBrowserWidget as _TreeFolderBrowserWidget


class AssetDetailDelegate(_AssetDetailDelegate):
    def on_click(self, item) -> None:
        """Override to do nothing"""
        pass

    def on_right_click(self, item) -> None:
        """Override to do nothing"""
        pass

    def on_double_click(self, item) -> None:
        """Override to do nothing"""
        pass

    def on_drag(self, item) -> None:
        """Override to do nothing"""
        pass


class AssetBrowserModel(_AssetBrowserModel):
    def execute(self, item) -> None:
        """Override to do nothing"""
        pass


class AssetBrowserWindow:
    _SIZE_PERCENT_WINDOW = 0.86

    def __init__(self, add_callback_fn: Callable[[list[str | _OmniUrl]], Any]):
        self.__window = None
        self.__browser_model = None
        self.__delegate = None
        self.__widget = None
        self.__close_on_add_checkbox = None
        self.__add_callback_fn = add_callback_fn

        appwindow_stream = omni.appwindow.get_default_app_window().get_window_resize_event_stream()
        self.__subcription_app_window_size_changed = appwindow_stream.create_subscription_to_pop(
            self._on_app_window_size_changed, name="On app window resized", order=0
        )

    def __create_ui(self):
        app_window = omni.appwindow.get_default_app_window()
        size = app_window.get_size()
        dpi_scale = ui.Workspace.get_dpi_scale()
        self.__browser_model = AssetBrowserModel()
        self.__delegate = AssetDetailDelegate(self.__browser_model)
        self.__window = ui.Window(
            "Remix Assets",
            width=size[0] * self._SIZE_PERCENT_WINDOW / dpi_scale,
            height=size[1] * self._SIZE_PERCENT_WINDOW / dpi_scale,
            visible=False,
            flags=ui.WINDOW_FLAGS_MODAL | ui.WINDOW_FLAGS_NO_DOCKING,
        )
        with self.__window.frame:
            with ui.VStack():
                self.__widget = _TreeFolderBrowserWidget(self.__browser_model, detail_delegate=self.__delegate)
                with ui.HStack(spacing=ui.Pixel(16), height=ui.Pixel(24)):
                    ui.Spacer()
                    ui.Button("Add selection", clicked_fn=self.__add_selected_items)
                    with ui.HStack(spacing=ui.Pixel(16)):
                        ui.Spacer()
                        ui.Label("Close window on add", width=0)
                        with ui.VStack(height=ui.Pixel(24), width=0):
                            ui.Spacer()
                            self.__close_on_add_checkbox = ui.CheckBox()
                            self.__close_on_add_checkbox.model.set_value(True)
                            ui.Spacer()
                        ui.Spacer(width=ui.Pixel(24))

    def _on_app_window_size_changed(self, event: carb.events.IEvent):
        asyncio.ensure_future(self._deferred_on_app_window_size_changed())

    @omni.usd.handle_exception
    async def _deferred_on_app_window_size_changed(self):
        if self.__window is not None:
            app_window = omni.appwindow.get_default_app_window()
            size = app_window.get_size()
            dpi_scale = ui.Workspace.get_dpi_scale()
            self.__window.width = size[0] * self._SIZE_PERCENT_WINDOW / dpi_scale
            self.__window.height = size[1] * self._SIZE_PERCENT_WINDOW / dpi_scale

    def __add_selected_items(self):
        self.__add_callback_fn([item.url for item in self.__widget.detail_selection])
        if self.__close_on_add_checkbox.model.get_value_as_bool():
            self.show_window(False)

    def show_window(self, visible) -> None:
        if self.__window is None:
            self.__create_ui()
        self._on_app_window_size_changed(None)
        self.__window.visible = visible

    def destroy(self):
        self.__subcription_app_window_size_changed = None
        self.__browser_model = None
        self.__close_on_add_checkbox = None
        self.__delegate = None
        self.__widget = None
        self.__window = None

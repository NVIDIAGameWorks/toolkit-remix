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

from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.trex.utils.widget import WorkspaceWidget as _WorkspaceWidget
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni import ui
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config

from .registry import Groups as _Groups
from .registry import ItemDescriptor as _ItemDescriptor
from .registry import get_items as _get_sidebar_items
from .registry import subscribe_items_change


class SetupUI(_WorkspaceWidget):
    __ICON_SIZE = 32

    def __init__(self, window_frame: ui.Frame):
        """Nvidia StageCraft Components Pane"""
        self.__window_frame = window_frame
        self.__sub_sidebar_items_changed = subscribe_items_change(self._create_ui)  # noqa PLW0238
        self._create_ui()

    def _create_ui(self):
        with self.__window_frame:
            ui.Rectangle(name="Background_GREY_26")
            with ui.HStack():
                with ui.VStack(width=ui.Pixel(56)):
                    ui.Spacer(height=ui.Pixel(16))
                    ui.Image(
                        "",
                        name="Home",
                        width=ui.Fraction(1.0),
                        height=ui.Pixel(self.__ICON_SIZE),
                        tooltip="Return to Home",
                        mouse_released_fn=self._return_to_home,
                        pixel_aligned=True,
                    )

                    self.__build_widgets_from_registry()

    def __build_widgets_from_registry(self):
        widgets = _get_sidebar_items()
        layout_widgets = widgets.get(_Groups.LAYOUTS)
        ungrouped_widgets = widgets.get(_Groups.UNGROUPED)
        custom_group_widgets = {
            group: items for group, items in widgets.items() if group not in [_Groups.LAYOUTS, _Groups.UNGROUPED]
        }

        if layout_widgets:
            self.__build_widget_group(_Groups.LAYOUTS, layout_widgets)

        if custom_group_widgets:
            for group in custom_group_widgets:
                self.__build_widget_group(group, custom_group_widgets[group])

        if ungrouped_widgets:
            self.__build_widget_group("", widgets[_Groups.UNGROUPED])

    def __build_widget_group(self, group_name: str, widgets: list[_ItemDescriptor]):
        ui.Spacer(height=ui.Pixel(16))
        ui.Rectangle(name="Background_GREY_60", height=ui.Pixel(1), width=ui.Fraction(1.0))
        if group_name:
            ui.Spacer(height=ui.Pixel(8))
            ui.Label(group_name, height=ui.Pixel(12), alignment=ui.Alignment.CENTER, name="Color_WHITE_60")

        ui.Spacer(height=ui.Pixel(16))

        with ui.VStack(spacing=ui.Pixel(16)):
            for widget in sorted(widgets, key=lambda w: w.sort_index):
                image_name = widget.name if widget.enabled else f"{widget.name}Disabled"
                mouse_fn = widget.mouse_released_fn if widget.enabled else None
                # Use disabled_tooltip if the widget is disabled and a disabled_tooltip is provided
                tooltip = widget.tooltip if widget.enabled else (widget.disabled_tooltip or widget.tooltip)
                ui.Image(
                    "",
                    name=image_name,
                    width=ui.Fraction(1.0),
                    height=ui.Pixel(self.__ICON_SIZE),
                    tooltip=tooltip,
                    mouse_released_fn=mouse_fn,
                    pixel_aligned=True,
                )

    def _return_to_home(self, x, y, b, m):
        if b != 0:
            return
        load_layout(_get_quicklayout_config(_LayoutFiles.HOME_PAGE))

    def show(self, visible: bool):
        """Implements WorkspaceWidget interface. Sidebar is always visible."""
        pass

    def destroy(self):
        """Clean up resources."""
        self.__sub_sidebar_items_changed = None  # noqa: PLW0238
        self.__window_frame = None

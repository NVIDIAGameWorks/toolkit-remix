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
from collections.abc import Callable

from omni import ui
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget


class PropertyCollapsableFrame:
    def __init__(
        self,
        title: str,
        collapsed: bool = False,
        show_info_icon: bool = False,
        pinnable: bool = False,
        pinned_text_fn: Callable[[], str] | None = None,
        unpinned_fn: Callable[[], None] | None = None,
        enabled: bool = True,
    ):
        """
        Collapsable frame with expandable widget on the right and an info icon

        Args:
            title: the title to show
            collapsed:  collapsed or not by default
            show_info_icon: show the info icon or not
            pinnable: whether to show the pin icon to allow for pinning
            pinned_text_fn: function to update the pin descriptor text
            unpinned_fn: function to call after unpinning
            enabled: root widget enabled or not
        """
        self.__title = title
        self.__enabled = enabled
        self._info_image = None
        self.__cm = None
        self.__show_info_icon = show_info_icon
        self.__pinnable = pinnable
        self.__pinned = False
        self.__pinned_text_fn = pinned_text_fn
        self.__unpinned_fn = unpinned_fn
        self.__pinned_text = ""
        self.__lock_icon = None
        self.__frame = ui.CollapsableFrame(
            title=self.__title,
            collapsed=collapsed,
            height=0,
            name="PropertiesPaneSection",
            build_header_fn=self._build_frame_header,
            enabled=self.__enabled,
            identifier="PropertyCollapsableFrame",
        )

    @property
    def enabled(self):
        return self.__enabled

    @enabled.setter
    def enabled(self, value: bool):
        self.__frame.enabled = value
        self.__enabled = value

    @contextlib.contextmanager
    def _contextmanager(self):
        with self.__frame as frame:
            yield frame

    def __enter__(self):
        self.__cm = self._contextmanager()
        return self.__cm.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        return self.__cm.__exit__(exc_type, exc_value, traceback)

    @property
    def root(self):
        return self.__frame

    def get_info_widget(self) -> ui.Image:
        """
        Get the info widget

        Returns:
            The info widget
        """
        return self._info_image

    @property
    def pinned(self):
        return self.__pinned

    def _click_pin(self):
        self.__pinned = not self.__pinned
        self.__lock_icon.name = "Pin" if self.__pinned else "PinOff"

        # If we are pinning, update the pin text
        if self.__pinned and self.__pinned_text_fn is not None:
            self.__pinned_text = self.__pinned_text_fn()

        if self.__unpinned_fn is not None and not self.__pinned:
            self.__unpinned_fn()
        self.__frame.rebuild()

    def _build_frame_header(self, collapsed, text, info_text: str = ""):
        """Custom header for CollapsibleFrame"""
        if collapsed:
            name_override_triangle = "ImagePropertiesPaneSectionTriangleCollapsed"
        else:
            name_override_triangle = "ImagePropertiesPaneSectionTriangleExpanded"

        with ui.VStack(height=0):
            with ui.HStack(height=0):
                with ui.VStack(height=0, width=0):
                    ui.Spacer(height=4)
                    ui.Label(text, name="PropertiesPaneSectionTitle")
                    ui.Spacer(height=ui.Pixel(8), width=0)
                if self.__show_info_icon:
                    ui.Spacer(width=ui.Pixel(8))
                    with ui.VStack(height=0, width=0):
                        ui.Spacer(height=2)
                        self._info_image = _InfoIconWidget(info_text)
                ui.Spacer()
                if self.__pinnable:
                    with ui.VStack(width=ui.Pixel(8), content_clipping=True):
                        ui.Spacer()
                        self.__lock_icon = ui.Image(
                            name="Pin" if self.__pinned else "PinOff",
                            width=ui.Pixel(14),
                            height=ui.Pixel(14),
                            tooltip="Click to pin these properties",
                            mouse_pressed_fn=lambda *_: self._click_pin(),
                            identifier="property_frame_pin_icon",
                        )
                        ui.Spacer()
                    ui.Spacer(width=8)
                with ui.VStack(width=ui.Pixel(8)):
                    ui.Spacer()
                    ui.Image(
                        style_type_name_override=name_override_triangle,
                        width=ui.Pixel(8),
                        height=ui.Pixel(8),
                        identifier="PropertyCollapsableFrameArrow",
                    )
                    ui.Spacer()
            ui.Line(name="PropertiesPaneSectionTitle", style_type_name_override="FieldWarning" if self.__pinned else "")
            if self.__pinnable and self.__pinned and self.__pinned_text_fn is not None:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(3))
                    ui.Label(
                        self.__pinned_text,
                        alignment=ui.Alignment.LEFT,
                        style_type_name_override="FieldWarning",
                        identifier="pin_label_text",
                    )
            ui.Spacer(width=ui.Pixel(8))

    def destroy(self):
        self._info_image = None
        self.__cm = None


class PropertyCollapsableFrameWithInfoPopup(PropertyCollapsableFrame):
    def __init__(self, *args, info_text: str = "", pinnable: bool = False, **kwargs):
        """
        Same as PropertyCollapsableFrame, but when we put the mouse over the info icon, it will show a popup with the
        text you want to show

        Args:
            *args: args of PropertyCollapsableFrame
            info_text: the text you want to show
            pinnable: whether to show the clickable icon image for pinning
            **kwargs: kwargs of PropertyCollapsableFrame
        """
        super().__init__(*args, **kwargs, show_info_icon=True, pinnable=pinnable)
        self.__info_text = info_text

    def _build_frame_header(self, collapsed, text, info_text: str = ""):
        super()._build_frame_header(collapsed, text, self.__info_text)

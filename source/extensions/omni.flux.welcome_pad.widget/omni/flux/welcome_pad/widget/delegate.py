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

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.label import create_label_with_font
from omni.flux.utils.widget.resources import get_image

from .model import HEADER_DICT  # noqa PLE0402


class Delegate(ui.AbstractItemDelegate):
    def __init__(self, word_wrap_description: bool = True):
        """
        Args:
            word_wrap_description: word wrap the description
        """
        super().__init__()
        self._default_attrs = {
            "_title_images_provider": None,
            "_frames": None,
            "_image_widgets": None,
            "_background_rectangles": None,
        }
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)

        self.__word_wrap_description = word_wrap_description
        self._frames = {}
        self._image_widgets = {}
        self._background_rectangles = {}
        self._title_images_provider = []
        self.__on_widget_built = _Event()

    def reset_delegate(self):
        self.destroy()
        self._frames = {}
        self._background_rectangles = {}
        self._image_widgets = {}
        self._title_images_provider = []

    def _widget_built(self, item, column_id, level, expanded):
        """Call the event object that has the list of functions"""
        self.__on_widget_built(item, column_id, level, expanded)

    def subscribe_widget_built(self, callback):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_widget_built, callback)

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def get_background_widgets(self):
        return self._background_rectangles

    def get_image_widgets(self):
        return self._image_widgets

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.VStack():
                with ui.ZStack():
                    self._background_rectangles[item.title] = ui.Rectangle(
                        opaque_for_mouse_events=True,
                        name="WelcomePadContent",
                        mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
                        mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(b, item),
                        mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, item),
                        checked=not item.enabled,
                    )
                    with ui.VStack(height=ui.Pixel(152)):
                        ui.Spacer(height=ui.Pixel(4))
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(4))
                            image = item.get_image()
                            if not image.strip():
                                image = str(get_image("default", ext_name="omni.flux.welcome_pad.widget"))
                                image_widget = ui.Image(
                                    image,
                                    height=ui.Pixel(144),
                                    width=ui.Pixel(144),
                                    name="WelcomePadDefault",
                                    checked=not item.enabled,
                                )
                            else:
                                image_widget = ui.Image(
                                    image,
                                    height=ui.Pixel(144),
                                    width=ui.Pixel(144),
                                    name="WelcomePadImage",
                                    checked=not item.enabled,
                                )
                            self._image_widgets[item.title] = image_widget
                            ui.Spacer(width=ui.Pixel(16))
                            with ui.VStack():
                                if item.use_title_override_delegate:
                                    item.title_override_delegate()
                                else:
                                    style = ui.Style.get_instance()
                                    current_dict = style.default
                                    if "ImageWithProvider::WelcomePadItemTitle" not in current_dict:
                                        # use regular labels
                                        ui.Label(item.title, checked=not item.enabled, name="WelcomePadItemTitle")
                                    else:
                                        # use custom styled font
                                        self._frames[item.title] = ui.Frame()
                                        with self._frames[item.title]:
                                            title_images_provider, image_provider, _ = create_label_with_font(
                                                item.title, "WelcomePadItemTitle", custom_image_height=ui.Pixel(24)
                                            )
                                            image_provider.checked = not item.enabled
                                            self._title_images_provider.append(title_images_provider)

                                with ui.ScrollingFrame(
                                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                    horizontal_scrollbar_policy=(
                                        ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF
                                        if self.__word_wrap_description
                                        else ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                                    ),
                                    scroll_y_max=0,
                                    height=ui.Pixel(116 - 3),
                                    name="WelcomePadItem",
                                    scroll_x_changed_fn=lambda x: self._on_description_scrolled_x(x, item),
                                    scroll_y_changed_fn=lambda y: self._on_description_scrolled_y(y, item),
                                ):
                                    if item.use_description_override_delegate:
                                        item.description_override_delegate()
                                    else:
                                        ui.Label(
                                            item.description,
                                            name="WelcomePadItemDescription",
                                            alignment=ui.Alignment.LEFT,
                                            word_wrap=self.__word_wrap_description,
                                            height=0,
                                            checked=not item.enabled,
                                        )
                        ui.Spacer(height=ui.Pixel(4))
                ui.Spacer(height=ui.Pixel(16))
        self._widget_built(item, column_id, level, expanded)

    def _on_item_mouse_pressed(self, button, item):
        if button != 0:
            return
        item.on_mouse_pressed()

    def _on_item_mouse_released(self, button, item):
        if button != 0:
            return
        item.on_mouse_released()

    def _on_item_hovered(self, hovered, item):
        item.on_hovered(hovered)

    def _on_description_scrolled_x(self, x, item):
        item.on_description_scrolled_x(x)

    def _on_description_scrolled_y(self, y, item):
        item.on_description_scrolled_y(y)

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        if self._frames is not None:
            for _, frame in self._frames.items():
                frame.clear()
        _reset_default_attrs(self)

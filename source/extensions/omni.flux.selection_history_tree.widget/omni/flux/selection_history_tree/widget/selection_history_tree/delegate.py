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

import omni.kit.app
import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.color import hex_to_color as _hex_to_color
from omni.flux.utils.widget.gradient import create_gradient as _create_gradient


class SelectionHistoryDelegate(ui.AbstractItemDelegate):
    __DEFAULT_IMAGE_ICON_SIZE = 24

    def __init__(self):
        super().__init__()

        self._default_attr = {
            "_path_scroll_frames": None,
            "_gradient_frame": None,
            "_zstack_scroll": None,
            "_gradient_image_provider": None,
            "_gradient_image_with_provider": None,
            "_gradient_array": None,
            "_gradient_array_hovered": None,
            "_gradient_array_selected": None,
            "_current_selection": None,
            "_hovered_items": None,
            "_background_rectangle": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._current_selection = []
        self._hovered_items = {}
        self._background_rectangle = {}

        self._path_scroll_frames = {}
        self._zstack_scroll = {}
        self._gradient_frame = {}
        self._gradient_image_provider = {}
        self._gradient_image_with_provider = {}

        self.__item_is_pressed = False  # noqa PLW0238

        # gradient
        style = ui.Style.get_instance()
        self.__gradient_color1 = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient"]["background_color"]
        )
        self.__gradient_color2 = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient"]["background_gradient_color"]
        )
        self.__gradient_color1_hovered = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_hovered"]["background_color"]
        )
        self.__gradient_color2_hovered = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_hovered"]["background_gradient_color"]
        )
        self.__gradient_color1_selected = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_selected"]["background_color"]
        )
        self.__gradient_color2_selected = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_selected"]["background_gradient_color"]
        )
        self.__gradient_width = 48
        self.__gradient_height = self.__DEFAULT_IMAGE_ICON_SIZE
        self._gradient_array = _create_gradient(
            self.__gradient_width,
            self.__gradient_height,
            self.__gradient_color1,
            self.__gradient_color2,
            (True, True, True, True),
        )
        self._gradient_array_hovered = _create_gradient(
            self.__gradient_width,
            self.__gradient_height,
            self.__gradient_color1_hovered,
            self.__gradient_color2_hovered,
            (True, True, True, True),
        )
        self._gradient_array_selected = _create_gradient(
            self.__gradient_width,
            self.__gradient_height,
            self.__gradient_color1_selected,
            self.__gradient_color2_selected,
            (True, True, True, True),
        )

    def build_widget(self, model, item, column_id, level, expanded):
        if item is None:
            return
        if column_id == 0:
            with ui.HStack(mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, item)):
                with ui.ZStack():
                    if id(item) not in self._background_rectangle:
                        self._background_rectangle[id(item)] = []
                    self._background_rectangle[id(item)].append(ui.Rectangle(style_type_name_override="TreeView.Item"))
                    with ui.HStack():
                        ui.Spacer(height=0, width=ui.Pixel(8))
                        with ui.HStack():
                            with ui.HStack(
                                mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
                                mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(b, item),
                                tooltip=item.tooltip,
                            ):
                                with ui.Frame(
                                    height=0,
                                    separate_window=True,  # to be able to select
                                ):
                                    self._zstack_scroll = ui.ZStack()
                                    with self._zstack_scroll:
                                        self._path_scroll_frames[id(item)] = ui.ScrollingFrame(
                                            name="TreePanelBackground",
                                            height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE),
                                            # width=ui.Percent(90),
                                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            scroll_y_max=0,
                                        )
                                        with self._path_scroll_frames[id(item)]:
                                            with ui.HStack():
                                                # Labels are red for prims that do not exist
                                                cur_style_name = "PropertiesPaneSectionTreeItemError"
                                                if item.is_valid():
                                                    cur_style_name = "PropertiesPaneSectionTreeItem"
                                                ui.Label(
                                                    item.title,
                                                    style_type_name_override=cur_style_name,
                                                    tooltip=item.tooltip,
                                                    identifier="title",
                                                )
                                                ui.Spacer(
                                                    height=0, width=ui.Pixel(self.__gradient_width / 2)
                                                )  # because of gradiant
                                        with ui.HStack():
                                            ui.Spacer()
                                            self._gradient_frame[id(item)] = ui.Frame(
                                                separate_window=True, width=ui.Pixel(self.__gradient_width)
                                            )

        asyncio.ensure_future(self._add_gradient_or_not(item))

    @omni.usd.handle_exception
    async def _add_gradient_or_not(self, item):
        await omni.kit.app.get_app().next_update_async()
        if (
            self._path_scroll_frames
            and id(item) in self._path_scroll_frames
            and self._path_scroll_frames[id(item)].scroll_x_max > 0
        ):
            with self._gradient_frame[id(item)]:
                # add gradient
                self._gradient_image_provider[id(item)] = ui.ByteImageProvider()
                self._gradient_image_with_provider[id(item)] = ui.ImageWithProvider(
                    self._gradient_image_provider[id(item)],
                    height=self.__gradient_height,
                    fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                    name="HeaderNvidiaBackground",
                )
                if item in self._current_selection:
                    self._gradient_image_provider[id(item)].set_bytes_data(
                        self._gradient_array_selected.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
                    )
                else:
                    self._gradient_image_provider[id(item)].set_bytes_data(
                        self._gradient_array.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
                    )

    def _on_item_hovered(self, hovered, item):
        self._hovered_items[id(item)] = hovered
        for rectangle in self._background_rectangle.get(id(item), []):
            rectangle.style_type_name_override = (
                "TreeView.Item.IsHovered" if hovered and item not in self._current_selection else "TreeView.Item"
            )
        self.refresh_gradient_color(item, deferred=False)

    def _on_item_mouse_pressed(self, button, item):
        if button != 0:
            return
        self.__item_is_pressed = True  # noqa PLW0238
        self.refresh_gradient_color(item)

    def _on_item_mouse_released(self, button, item):
        if button != 0:
            return
        self.__item_is_pressed = False  # noqa PLW0238
        self.refresh_gradient_color(item)

    def refresh_gradient_color(self, item, deferred=True):
        if deferred:
            asyncio.ensure_future(self.__deferred_refresh_gradient_color(item))
        else:
            self.__do_refresh_gradient_color(item)

    def on_item_selected(self, selected_items, all_items):
        self._current_selection = selected_items
        for item in all_items:
            self.refresh_gradient_color(item, deferred=False)
            for rectangle in self._background_rectangle.get(id(item), []):
                rectangle.style_type_name_override = (
                    "TreeView.Item.selected" if item in selected_items else "TreeView.Item"
                )

    @omni.usd.handle_exception
    async def __deferred_refresh_gradient_color(self, item):
        """Wait for the delegate to generate the gradient"""
        if id(item) not in self._gradient_image_provider:
            # wait for the gradient to generate?
            # at least 10 frames
            found = False
            for _ in range(10):
                await omni.kit.app.get_app().next_update_async()
                if not self._gradient_image_provider:
                    continue
                if id(item) in self._gradient_image_provider:
                    found = True
                    break
            if not found:
                return
        self.__do_refresh_gradient_color(item)

    def __do_refresh_gradient_color(self, item):
        if id(item) not in self._gradient_image_provider:
            return
        is_hovered = self._hovered_items.get(id(item), False)
        is_selected = item in self._current_selection
        if is_selected:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_selected.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
            )
        elif is_hovered and not is_selected:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_hovered.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
            )
        else:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
            )

    def reset(self):
        self._current_selection = []
        self._hovered_items = {}

        self._path_scroll_frames = {}
        self._zstack_scroll = {}
        self._gradient_frame = {}
        self._gradient_image_provider = {}
        self._gradient_image_with_provider = {}
        self._background_rectangle = {}

    def get_path_scroll_frames(self):
        """
        Get the scroll frames used in the delegates. This can be used to control the scrolling of the items externally.

        Returns:
            A list of the scroll frames displayed in the tree widget
        """
        return self._path_scroll_frames

    def destroy(self):
        _reset_default_attrs(self)

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
from collections.abc import Callable

import omni.ui as ui
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.color import hex_to_color as _hex_to_color
from omni.flux.utils.widget.gradient import create_gradient as _create_gradient

from .item_model import ComponentTypes, ItemBase


class BookmarkDelegate(ui.AbstractItemDelegate):
    __DEFAULT_IMAGE_ICON_SIZE = 24

    def __init__(self):
        super().__init__()

        self._default_attr = {
            "_dragged_item": None,
            "_current_selection": None,
            "_hovered_items": None,
            "_gradient_frame": None,
            "_gradient_image_provider": None,
            "_gradient_image_with_provider": None,
            "_scroll_frames": None,
            "_sub_on_value_changed": None,
            "_sub_on_edit_finished": None,
            "_new_item_model": None,
            "_new_item_field_widget": None,
            "_gradient_array": None,
            "_gradient_array_hovered": None,
            "_gradient_array_selected": None,
            "_gradient_array_secondary": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._initialize_gradient_styles()
        self._initialize_internal_members()

        self.__on_item_expanded = _Event()
        self.__on_add_clicked = _Event()
        self.__on_remove_clicked = _Event()
        self.__on_delete_clicked = _Event()

    @property
    def dragged_item(self) -> ItemBase | None:
        """
        The item currently getting dragged by the user.
        """
        return self._dragged_item

    def get_scroll_frames(self):
        """
        Get the scroll frames used in the delegates. This can be used to control the scrolling of the items externally.

        Returns:
            A list of the scroll frames displayed in the tree widget
        """
        return self._scroll_frames

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch core that opens or closes subtree"""
        if item is None:
            return
        if column_id == 0:
            with ui.HStack():
                with ui.ZStack():
                    if id(item) not in self._background_items:
                        self._background_items[id(item)] = []
                    with ui.ZStack():
                        with ui.VStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                            spacer = ui.Line(height=ui.Pixel(2), visible=False, name="TreeSpacer")
                            rectangle = ui.Rectangle(
                                style_type_name_override=self.__get_item_background_style(item),
                                mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, model, item),
                            )
                        with ui.VStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                            ui.Spacer(
                                height=ui.Pixel(2),
                                mouse_hovered_fn=lambda hovered: self._on_trigger_hovered(hovered, item),
                            )
                    self._background_items[id(item)].append((spacer, rectangle))
                    with ui.VStack():
                        ui.Spacer()
                        with ui.HStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                            ui.Spacer(height=0, width=ui.Pixel((level - 1) * 16 + 8))
                            with ui.ZStack(width=ui.Pixel(20)):
                                if item.can_have_children and item.children:
                                    # Draw the +/- icon
                                    with ui.HStack(
                                        width=0,
                                        mouse_released_fn=lambda x, y, b, m: self._on_item_expanded(
                                            b, item, not expanded
                                        ),
                                    ):
                                        ui.Spacer(height=0, width=ui.Pixel(4))
                                        style_type_name_override = (
                                            "TreeView.Item.Minus" if expanded else "TreeView.Item.Plus"
                                        )
                                        with ui.VStack(width=ui.Pixel(16)):
                                            ui.Spacer(width=0)
                                            ui.Image(
                                                "",
                                                width=10,
                                                height=10,
                                                style_type_name_override=style_type_name_override,
                                            )
                                            ui.Spacer(width=0)
                            with ui.HStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE), width=0):
                                if item.component_type == ComponentTypes.bookmark_collection.value:
                                    with ui.VStack(width=ui.Pixel(16)):
                                        ui.Spacer(width=0)
                                        ui.Image("", height=ui.Pixel(16), name="Bookmark")
                                        ui.Spacer(width=0)
                                elif item.component_type == ComponentTypes.create_collection.value:
                                    with ui.VStack(width=ui.Pixel(16)):
                                        ui.Spacer(width=0)
                                        ui.Image("", height=ui.Pixel(16), name="AddStatic")
                                        ui.Spacer(width=0)
                        ui.Spacer()

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a model per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.HStack():
                with ui.ZStack():
                    if id(item) not in self._background_items:
                        self._background_items[id(item)] = []
                    with ui.ZStack():
                        with ui.VStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                            spacer = ui.Line(height=ui.Pixel(2), visible=False, name="TreeSpacer")
                            rectangle = ui.Rectangle(
                                style_type_name_override=self.__get_item_background_style(item),
                                mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, model, item),
                            )
                        with ui.VStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                            ui.Spacer(
                                height=ui.Pixel(2),
                                mouse_hovered_fn=lambda hovered: self._on_trigger_hovered(hovered, item),
                            )
                    self._background_items[id(item)].append((spacer, rectangle))
                    with ui.HStack():
                        ui.Spacer(height=0, width=ui.Pixel(8))
                        with ui.HStack():
                            with ui.HStack(
                                mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
                                mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(b, item),
                                mouse_double_clicked_fn=lambda x, y, b, m: item.on_mouse_double_clicked(),
                                key_pressed_fn=lambda key, _, pressed: item.on_key_pressed(key, pressed),
                            ):
                                with ui.Frame(height=0, separate_window=True):
                                    with ui.ZStack():
                                        self._scroll_frames[id(item)] = ui.ScrollingFrame(
                                            name="TreePanelBackground",
                                            height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE),
                                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            scroll_y_max=0,
                                        )
                                        with self._scroll_frames[id(item)]:
                                            with ui.HStack():
                                                style_name = "PropertiesPaneSectionTreeItem"
                                                if item.component_type == ComponentTypes.create_collection.value:
                                                    style_name = "PropertiesPaneSectionTreeItem60"
                                                ui.Label(item.title, name=style_name)
                                                ui.Spacer(
                                                    height=0, width=ui.Pixel(self.__gradient_width / 2)
                                                )  # because of gradiant
                                        with ui.HStack():
                                            ui.Spacer()
                                            self._gradient_frame[id(item)] = ui.Frame(
                                                separate_window=True, width=ui.Pixel(self.__gradient_width)
                                            )
                            if item.component_type == ComponentTypes.bookmark_collection.value:
                                with ui.VStack(width=ui.Pixel(16), content_clipping=True):
                                    ui.Spacer(width=0)
                                    ui.Image(
                                        "",
                                        height=ui.Pixel(16),
                                        name="TrashCan",
                                        tooltip="Delete the bookmark collection",
                                        mouse_released_fn=lambda x, y, b, m: self._on_delete_clicked(b, item),
                                    )
                                    ui.Spacer(width=0)
                                ui.Spacer(height=0, width=ui.Pixel(8))
                            if item.component_type != ComponentTypes.create_collection.value:
                                if item.can_have_children:
                                    with ui.VStack(width=ui.Pixel(16), content_clipping=True):
                                        ui.Spacer(width=0)
                                        ui.Image(
                                            "",
                                            height=ui.Pixel(16),
                                            name="Add",
                                            tooltip="Add current selection to the bookmark",
                                            mouse_released_fn=lambda x, y, b, m: self._on_add_clicked(b, item),
                                        )
                                        ui.Spacer(width=0)
                                    ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(width=ui.Pixel(16), content_clipping=True):
                                    ui.Spacer(width=0)
                                    ui.Image(
                                        "",
                                        height=ui.Pixel(16),
                                        name="Subtract",
                                        tooltip="Remove current selection from the bookmark",
                                        mouse_released_fn=lambda x, y, b, m: self._on_remove_clicked(b, item),
                                    )
                                    ui.Spacer(width=0)

        asyncio.ensure_future(self._add_gradient_or_not(item))

    def refresh_gradient_color(self, item: ItemBase, deferred: bool = True) -> None:
        """
        Refresh the item gradient based on selection, hover state, etc.

        Args:
            item: the item to refresh
            deferred: whether the refresh should be deferred to a future frame
        """
        if deferred:
            asyncio.ensure_future(self.__deferred_refresh_gradient_color(item))
        else:
            self.__do_refresh_gradient_color(item)

    def on_item_selected(
        self, primary_items: list[ItemBase], secondary_items: list[ItemBase], all_items: list[ItemBase]
    ) -> None:
        """
        Callback for when the tree widget selection changed.

        Args:
            primary_items: the selected items
            secondary_items: the secondary selection items
            all_items: all items in the model
        """
        self._hovered_items.clear()
        self._primary_selection = list(set(primary_items))
        self._secondary_selection = list(set(secondary_items))
        for item in set(all_items):
            self.refresh_gradient_color(item)
            for _, rectangle in self._background_items.get(id(item), []):
                rectangle.style_type_name_override = self.__get_item_background_style(item)

    def __get_item_background_style(self, item: ItemBase, hovered: bool = None, model=None):
        include_hover = hovered is not None and model is not None
        if item in self._primary_selection:
            return "TreeView.Item.selected"
        if item in self._secondary_selection:
            return "TreeView.Item.semi_selected"
        if include_hover and hovered and (self._dragged_item is None or model.drop_accepted(item, self._dragged_item)):
            return "TreeView.Item.IsHovered"
        return "TreeView.Item"

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
        is_selected_primary = item in self._primary_selection
        is_selected_secondary = item in self._secondary_selection
        # Default gradient
        self._gradient_image_provider[id(item)].set_bytes_data(
            self._gradient_array.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
        )
        # Override gradients
        if is_selected_primary:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_selected.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
            )
        elif is_selected_secondary:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_secondary.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
            )
        elif is_hovered:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_hovered.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
            )

    @omni.usd.handle_exception
    async def _add_gradient_or_not(self, item):
        await omni.kit.app.get_app().next_update_async()
        if self._scroll_frames and id(item) in self._scroll_frames and self._scroll_frames[id(item)].scroll_x_max > 0:
            with self._gradient_frame[id(item)]:
                # add gradient
                self._gradient_image_provider[id(item)] = ui.ByteImageProvider()
                self._gradient_image_with_provider[id(item)] = ui.ImageWithProvider(
                    self._gradient_image_provider[id(item)],
                    height=self.__gradient_height,
                    fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                    name="HeaderNvidiaBackground",
                )
                self._gradient_image_provider[id(item)].set_bytes_data(
                    self._gradient_array.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
                )

    def _on_trigger_hovered(self, hovered, item):
        can_hover = (
            item.parent is None
            and self._dragged_item is not None
            and self._dragged_item.component_type == ComponentTypes.bookmark_collection.value
        )
        for spacer, _ in self._background_items.get(id(item), []):
            spacer.visible = can_hover and hovered

    def _on_item_hovered(self, hovered, model, item):
        self._hovered_items[id(item)] = hovered
        for _, rectangle in self._background_items.get(id(item), []):
            rectangle.style_type_name_override = self.__get_item_background_style(item, hovered=hovered, model=model)
        self.refresh_gradient_color(item, deferred=False)

    def _on_item_mouse_pressed(self, button, item):
        if button != 0 or self._dragged_item is not None:
            return
        self._dragged_item = (
            item
            if item.component_type in [ComponentTypes.bookmark_collection.value, ComponentTypes.bookmark_item.value]
            else None
        )

    def _on_item_mouse_released(self, button, item):
        if button != 0:
            return
        self._dragged_item = None
        for background_item in self._background_items.values():
            for spacer, _ in background_item:
                spacer.visible = False
        item.on_mouse_clicked()

    def _on_item_valid_changed(self, is_valid):
        if self._new_item_field_widget is None:
            return
        self._new_item_field_widget.style_type_name_override = "Field" if is_valid else "FieldError"

    def _on_item_expanded(self, button, item, expanded):
        if button != 0:
            return
        self.__on_item_expanded(item, expanded)

    def subscribe_on_item_expanded(self, function: Callable):
        """
        Subscribe to the *on_item_expanded* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_expanded, function)

    def _on_add_clicked(self, button, item):
        if button != 0:
            return
        self.__on_add_clicked(item)

    def subscribe_on_add_clicked(self, function: Callable):
        """
        Subscribe to the *on_add_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_add_clicked, function)

    def _on_remove_clicked(self, button, item):
        if button != 0:
            return
        self.__on_remove_clicked(item)

    def subscribe_on_remove_clicked(self, function: Callable):
        """
        Subscribe to the *on_remove_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_remove_clicked, function)

    def _on_delete_clicked(self, button, item):
        if button != 0:
            return
        self.__on_delete_clicked(item)

    def subscribe_on_delete_clicked(self, function: Callable):
        """
        Subscribe to the *on_remove_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_delete_clicked, function)

    def _initialize_internal_members(self):
        self._dragged_item = None

        self._primary_selection = []
        self._secondary_selection = []
        self._hovered_items = {}
        self._background_items = {}

        self._gradient_frame = {}
        self._gradient_image_provider = {}
        self._gradient_image_with_provider = {}
        self._scroll_frames = {}

    def _initialize_gradient_styles(self):
        style = ui.Style.get_instance()
        current_dict = style.default
        if "ImageWithProvider::SelectionGradient" not in current_dict:
            current_dict["ImageWithProvider::SelectionGradient"] = {
                "background_color": 0x00303030,
                "background_gradient_color": 0xFF303030,
            }
        if "ImageWithProvider::SelectionGradient_hovered" not in current_dict:
            current_dict["ImageWithProvider::SelectionGradient_hovered"] = {
                "background_color": 0x00453F2B,
                "background_gradient_color": 0xFF453F2B,
            }
        if "ImageWithProvider::SelectionGradient_selected" not in current_dict:
            current_dict["ImageWithProvider::SelectionGradient_selected"] = {
                "background_color": 0x00836C1D,
                "background_gradient_color": 0xFF594E26,
            }
        if "ImageWithProvider::SelectionGradient_secondary" not in current_dict:
            current_dict["ImageWithProvider::SelectionGradient_secondary"] = {
                "background_color": 0x00594E26,
                "background_gradient_color": 0xFF594E26,
            }
        style.default = current_dict

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
        self.__gradient_color1_secondary = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_secondary"]["background_color"]
        )
        self.__gradient_color2_secondary = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_secondary"]["background_gradient_color"]
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
        self._gradient_array_secondary = _create_gradient(
            self.__gradient_width,
            self.__gradient_height,
            self.__gradient_color1_secondary,
            self.__gradient_color2_secondary,
            (True, True, True, True),
        )

    def destroy(self):
        _reset_default_attrs(self)

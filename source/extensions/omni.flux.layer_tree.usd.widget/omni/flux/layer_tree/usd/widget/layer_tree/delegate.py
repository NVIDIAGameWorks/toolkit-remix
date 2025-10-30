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

import abc
import asyncio
from functools import partial
from typing import Callable, List

import omni.ui as ui
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.path_utils import open_file_using_os_default
from omni.flux.utils.widget.color import hex_to_color as _hex_to_color
from omni.flux.utils.widget.gradient import create_gradient as _create_gradient
from omni.flux.utils.widget.tree_widget import TreeDelegateBase as _TreeDelegateBase

from .item_model import ItemBase
from .model import LayerModel


class LayerDelegate(_TreeDelegateBase):
    __DEFAULT_IMAGE_ICON_SIZE = 24

    def __init__(self):
        super().__init__()

        self._initialize_gradient_styles()
        self._initialize_internal_members()

        # State changes
        self.__on_item_expanded = _Event()
        # Item buttons
        self.__on_set_authoring_layer = _Event()
        self.__on_remove_clicked = _Event()
        self.__on_save_clicked = _Event()
        self.__on_lock_clicked = _Event()
        self.__on_visible_clicked = _Event()
        # Right click menu
        self.__on_export_clicked = _Event()
        self.__on_save_as_clicked = _Event()
        self.__on_merge_clicked = _Event()
        self.__on_transfer_clicked = _Event()

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_background_items": None,
                "_context_menu_widgets": None,
                "_primary_selection": None,
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
            }
        )
        return default_attr

    @property
    def _dynamic_edit_target_icons(self):
        return True

    def get_scroll_frames(self):
        """
        Get the scroll frames used in the delegates. This can be used to control the scrolling of the items externally.

        Returns:
            A list of the scroll frames displayed in the tree widget
        """
        return self._scroll_frames

    def build_branch(self, model: LayerModel, item: ItemBase, column_id, level, expanded):
        """Create a branch core that opens or closes subtree"""
        if item is None:
            return
        if column_id == 0:
            with ui.ZStack():
                if id(item) not in self._background_items:
                    self._background_items[id(item)] = []
                with ui.ZStack():
                    with ui.VStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                        spacer = ui.Line(height=ui.Pixel(2), visible=False, name="TreeSpacer")
                        rectangle = ui.Rectangle(
                            style_type_name_override="TreeView.Item",
                            mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, model, item),
                        )
                    with ui.VStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                        ui.Spacer(
                            height=ui.Pixel(2),
                            mouse_hovered_fn=lambda hovered: self._on_trigger_hovered(hovered, model, item),
                        )
                self._background_items[id(item)].append((spacer, rectangle))
                with ui.Frame():
                    with ui.VStack():
                        ui.Spacer()
                        with ui.HStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                            with ui.HStack(width=0):
                                self._build_branch_start_icons(model, item)
                            ui.Spacer(height=0, width=ui.Pixel((level - 1) * 16))
                            with ui.ZStack(width=ui.Pixel(20)):
                                if item.can_have_children and item.children:
                                    # Draw the +/- icon
                                    with ui.HStack(
                                        identifier="expansion_stack",
                                        width=0,
                                        mouse_released_fn=lambda x, y, b, m: self._item_expanded(
                                            b, model, item, not expanded
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
                                self._build_branch_end_icons(model, item)
                        ui.Spacer()

    def _build_widget(self, model: LayerModel, item: ItemBase, column_id, level, expanded):
        """Create a model per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.ZStack(identifier="layer_item_root"):
                if id(item) not in self._background_items:
                    self._background_items[id(item)] = []
                with ui.ZStack():
                    with ui.VStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                        spacer = ui.Line(height=ui.Pixel(2), visible=False, name="TreeSpacer")
                        rectangle = ui.Rectangle(
                            style_type_name_override="TreeView.Item",
                            mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, model, item),
                        )
                    with ui.VStack(height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE)):
                        ui.Spacer(
                            height=ui.Pixel(2),
                            mouse_hovered_fn=lambda hovered: self._on_trigger_hovered(hovered, model, item),
                        )
                self._background_items[id(item)].append((spacer, rectangle))
                with ui.HStack():
                    ui.Spacer(height=0, width=ui.Pixel(4))
                    with ui.HStack():
                        with ui.Frame(
                            height=0,
                            separate_window=True,
                            mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
                            mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(b, item),
                            key_pressed_fn=lambda key, _, pressed: item.on_key_pressed(key, pressed),
                            tooltip=item.data["layer"].identifier if item.data["layer"] else "Invalid Layer",
                        ):
                            with ui.ZStack():
                                if item.data["authoring"]:
                                    with ui.ZStack():
                                        with ui.ScrollingFrame(
                                            name="ActiveLayerBackground",
                                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            scroll_y_max=0,
                                        ):
                                            with ui.HStack():
                                                for _ in range(5):
                                                    ui.Image(
                                                        "",
                                                        name="ActiveLayerBackground",
                                                        fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                                        height=ui.Pixel(256),
                                                        width=ui.Pixel(256),
                                                    )
                                self._scroll_frames[id(item)] = ui.ScrollingFrame(
                                    name="TreePanelBackground",
                                    height=ui.Pixel(self.__DEFAULT_IMAGE_ICON_SIZE),
                                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                    scroll_y_max=0,
                                )
                                with self._scroll_frames[id(item)]:
                                    with ui.HStack():
                                        ui.Spacer(width=ui.Pixel(4))
                                        with ui.VStack():
                                            ui.Label(item.title, name="PropertiesPaneSectionTreeItem")
                                            ui.Spacer(height=ui.Pixel(4))
                                        ui.Spacer(
                                            height=0, width=ui.Pixel(self.__gradient_width / 2)
                                        )  # because of gradiant
                                with ui.HStack():
                                    ui.Spacer()
                                    self._gradient_frame[id(item)] = ui.Frame(
                                        separate_window=True, width=ui.Pixel(self.__gradient_width)
                                    )
                        self._build_widget_icons(model, item)

        asyncio.ensure_future(self._add_gradient_or_not(item))

    def _show_context_menu(self, model, item):
        super()._show_context_menu(model, item)

        self._context_menu_widgets[id(item)] = ui.Menu("Layer Menu", direction=ui.Direction.LEFT_TO_RIGHT)
        with self._context_menu_widgets[id(item)]:
            if item.data["savable"]:
                ui.MenuItem(
                    "Save As",
                    triggered_fn=partial(self._on_save_as_clicked, item),
                )
            ui.MenuItem(
                "Export Layer",
                triggered_fn=partial(self._on_export_clicked, item),
            )
            ui.MenuItem(
                "Reveal in File Explorer",
                triggered_fn=lambda: open_file_using_os_default(str(item.data["layer"].realPath)),
            )
            mergeable_layers = [item for item in self._primary_selection if not item.data["locked"]]
            if len(mergeable_layers) > 1:
                ui.MenuItem(
                    "Merge Layers",
                    triggered_fn=partial(self._on_merge_clicked, mergeable_layers),
                )
            if not item.data["locked"] and not item.data["exclude_add_child"]:
                with ui.MenuItemCollection("Transfer Overrides to"):
                    ui.MenuItem(
                        "New Layer",
                        triggered_fn=partial(self._on_transfer_clicked, item, False),
                    )
                    ui.MenuItem(
                        "Existing Layer",
                        triggered_fn=partial(self._on_transfer_clicked, item, True),
                    )
        self._context_menu_widgets[id(item)].show()

    def _build_branch_start_icons(self, model: LayerModel, item: ItemBase):
        """Can be overriden to customize the branch icons"""
        ui.Spacer(width=ui.Pixel(8), height=0)

    def _build_branch_end_icons(self, model: LayerModel, item: ItemBase):
        """Can be overriden to customize the branch icons"""
        with ui.VStack(width=ui.Pixel(16)):
            ui.Spacer(width=0)
            if (
                item.data["exclude_edit_target"]
                or item.data["locked"]
                or not item.data["visible"]
                or not item.data["parent_visible"]
            ):
                tooltip = "The layer cannot be set as edit target"
                icon = "LayerDisabled"
                if item.data["exclude_edit_target"]:
                    tooltip += ": The layer is an invalid target"
                elif item.data["locked"]:
                    tooltip += ": The layer is locked"
                elif not item.data["visible"]:
                    tooltip += ": The layer is muted"
                elif not item.data["parent_visible"]:
                    tooltip += ": A parent layer is muted"
            else:
                if item.data["authoring"]:
                    tooltip = "The layer is the active Edit Target"
                    icon = "LayerActive"
                else:
                    tooltip = "Set the layer as the Edit Target"
                    icon = "Layer"
            ui.Image(
                "",
                height=ui.Pixel(16),
                name=icon if self._dynamic_edit_target_icons else "LayerStatic",
                tooltip=tooltip if self._dynamic_edit_target_icons else "",
                mouse_released_fn=lambda x, y, b, m: self._on_set_authoring_layer(b, model, item),
                enabled=not item.data["locked"]
                and not item.data["exclude_edit_target"]
                and item.data["visible"]
                and item.data["parent_visible"],
            )
            ui.Spacer(width=0)

    def _build_widget_icons(self, model: LayerModel, item: ItemBase):
        """Can be overriden to customize the widget icons"""
        ui.Spacer(height=0, width=ui.Pixel(8))
        with ui.VStack(width=ui.Pixel(16), content_clipping=True):
            if not item.data["exclude_remove"]:
                ui.Spacer(width=0)
                if item.parent is not None:
                    ui.Image(
                        "",
                        height=ui.Pixel(16),
                        name="TrashCan",
                        tooltip="Delete the layer",
                        mouse_released_fn=lambda x, y, b, m: self._on_remove_clicked(b, model, item),
                    )
                ui.Spacer(width=0)
        ui.Spacer(height=0, width=ui.Pixel(8))
        with ui.VStack(width=ui.Pixel(16), content_clipping=True):
            if item.parent is not None and not item.data["exclude_lock"]:
                ui.Spacer(width=0)
                ui.Image(
                    "",
                    height=ui.Pixel(16),
                    name="Lock" if item.data["locked"] else "Unlock",
                    tooltip="Unlock the layer" if item.data["locked"] else "Lock the layer",
                    mouse_released_fn=lambda x, y, b, m: self._on_lock_clicked(b, model, item),
                )
                ui.Spacer(width=0)
        # Unequal to better center the icons visually
        ui.Spacer(height=0, width=ui.Pixel(6))
        with ui.VStack(width=ui.Pixel(16), content_clipping=True):
            if item.parent is not None and not item.data["exclude_mute"]:
                ui.Spacer(width=0)
                name = "Eye" if item.data["visible"] else "EyeOff"
                tooltip = "Mute the layer" if item.data["visible"] else "Un-mute the layer"
                if not item.data["can_toggle_mute"]:
                    name = "EyeDisabled"
                    tooltip = "Cannot mute the Edit Target or any of its parent layers"
                elif not item.data["parent_visible"]:
                    name = "EyeOffDisabled"
                    tooltip = "The layer's muteness state is inherited from a muted parent layer"
                ui.Image(
                    "",
                    height=ui.Pixel(16),
                    name=name,
                    tooltip=tooltip,
                    mouse_released_fn=lambda x, y, b, m: self._on_visible_clicked(b, model, item),
                    enabled=item.data["can_toggle_mute"],
                )
                ui.Spacer(width=0)
        # Unequal to better center the icons visually
        ui.Spacer(height=0, width=ui.Pixel(10))
        with ui.VStack(width=ui.Pixel(16), content_clipping=True):
            ui.Spacer(width=0)
            tooltip = "The layer cannot be saved"
            if item.data["savable"]:
                if item.data["dirty"]:
                    tooltip = "Save the layer"
                else:
                    tooltip = "The layer has no active changes"
            ui.Image(
                "",
                height=ui.Pixel(16),
                name="Save" if item.data["savable"] and item.data["dirty"] else "SaveDisabled",
                tooltip=tooltip,
                mouse_released_fn=lambda x, y, b, m: self._on_save_clicked(b, model, item),
            )
            ui.Spacer(width=0)

    def refresh_gradient_color(self, item: ItemBase, model: LayerModel, deferred: bool = True) -> None:
        """
        Refresh the item gradient based on selection, hover state, etc.

        Args:
            item: the item to refresh
            model: the model
            deferred: whether the refresh should be deferred to a future frame
        """
        if deferred:
            asyncio.ensure_future(self.__deferred_refresh_gradient_color(item, model))
        else:
            self.__do_refresh_gradient_color(item, model)

    def on_item_selected(self, primary_items: List[ItemBase], all_items: List[ItemBase], model: LayerModel) -> None:
        """
        Callback for when the tree widget selection changed.

        Args:
            primary_items: the selected items
            all_items: all items in the model
            model: the model
        """
        self._primary_selection = primary_items
        for item in all_items:
            self.refresh_gradient_color(item, model)
            for _, rectangle in self._background_items.get(id(item), []):
                if item in primary_items:
                    style_name = "TreeView.Item.selected"
                else:
                    style_name = "TreeView.Item"
                rectangle.style_type_name_override = style_name

    @omni.usd.handle_exception
    async def __deferred_refresh_gradient_color(self, item, model):
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
        self.__do_refresh_gradient_color(item, model)

    def __do_refresh_gradient_color(self, item, model):
        if id(item) not in self._gradient_image_provider:
            return
        is_hovered = self._hovered_items.get(id(item), False)
        is_selected_primary = item in self._primary_selection
        # Default gradient
        self._gradient_image_provider[id(item)].set_bytes_data(
            self._gradient_array.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
        )
        # Override gradients
        if is_selected_primary:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_selected.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
            )
        elif is_hovered and (self._dragged_item is None or model.drop_accepted(item, self._dragged_item)):
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_hovered.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
            )

    @omni.usd.handle_exception
    async def _add_gradient_or_not(self, item):
        await omni.kit.app.get_app().next_update_async()

        # Because of the spare frame, the item may not exist anymore
        if not (item and item.data):
            return

        if (
            self._scroll_frames
            and id(item) in self._scroll_frames
            and (self._scroll_frames[id(item)].scroll_x_max > 0 or item.data["authoring"])
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
                self._gradient_image_provider[id(item)].set_bytes_data(
                    self._gradient_array.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
                )

    def _on_trigger_hovered(self, hovered, model, item):
        can_hover = self._dragged_item is not None and model.drop_accepted(item, self._dragged_item, 1)
        for spacer, _ in self._background_items.get(id(item), []):
            spacer.visible = can_hover and hovered

    def _on_item_hovered(self, hovered, model, item):
        self._hovered_items[id(item)] = hovered
        for _, rectangle in self._background_items.get(id(item), []):
            if item in self._primary_selection:
                style_name = "TreeView.Item.selected"
            elif hovered and (self._dragged_item is None or model.drop_accepted(item, self._dragged_item)):
                style_name = "TreeView.Item.IsHovered"
            else:
                style_name = "TreeView.Item"
            rectangle.style_type_name_override = style_name
        self.refresh_gradient_color(item, model, deferred=False)

    def _on_item_mouse_pressed(self, button, item):
        if button != 0 or self._dragged_item is not None:
            return
        self._dragged_item = item

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

    def _item_expanded(self, button: int, model: LayerModel, item: ItemBase, expanded: bool):
        self._item_clicked(button, True, model, item)
        if button != 0:
            return
        self.__on_item_expanded(expanded)

    def subscribe_on_item_expanded(self, function: Callable):
        """
        Subscribe to the *on_item_expanded* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_expanded, function)

    def _on_set_authoring_layer(self, button: int, model: LayerModel, item: ItemBase):
        # Update the selection to make sure the clicked item is included
        self._item_clicked(button, True, model, item)
        if (
            button != 0
            or item.data["locked"]
            or item.data["exclude_edit_target"]
            or not item.data["visible"]
            or not item.data["parent_visible"]
        ):
            return
        self.__on_set_authoring_layer(item)

    def subscribe_on_set_authoring_layer(self, function: Callable):
        """
        Subscribe to the *on_set_authoring_layer* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_set_authoring_layer, function)

    def _on_remove_clicked(self, button: int, model: LayerModel, item: ItemBase):
        # Update the selection to make sure the clicked item is included
        self._item_clicked(button, True, model, item)
        if button != 0 or item.data["exclude_remove"]:
            return
        self.__on_remove_clicked()

    def subscribe_on_remove_clicked(self, function: Callable):
        """
        Subscribe to the *on_remove_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_remove_clicked, function)

    def _on_save_clicked(self, button: int, model: LayerModel, item: ItemBase):
        # Update the selection to make sure the clicked item is included
        self._item_clicked(button, True, model, item)
        if button != 0 or not item.data["savable"]:
            return
        self.__on_save_clicked()

    def subscribe_on_save_clicked(self, function: Callable):
        """
        Subscribe to the *on_save_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_save_clicked, function)

    def _on_lock_clicked(self, button: int, model: LayerModel, item: ItemBase):
        # Update the selection to make sure the clicked item is included
        self._item_clicked(button, True, model, item)
        if button != 0 or item.data["exclude_lock"]:
            return
        self.__on_lock_clicked(item.data["locked"])

    def subscribe_on_lock_clicked(self, function: Callable):
        """
        Subscribe to the *on_lock_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_lock_clicked, function)

    def _on_visible_clicked(self, button: int, model: LayerModel, item: ItemBase):
        # Update the selection to make sure the clicked item is included
        self._item_clicked(button, True, model, item)
        if (
            button != 0
            or item.data["exclude_mute"]
            or not item.data["can_toggle_mute"]
            or not item.data["parent_visible"]
        ):
            return
        self.__on_visible_clicked(item.data["visible"])

    def subscribe_on_visible_clicked(self, function: Callable):
        """
        Subscribe to the *on_visible_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_visible_clicked, function)

    def _on_export_clicked(self, item):
        self.__on_export_clicked(item)

    def subscribe_on_export_clicked(self, function: Callable):
        """
        Subscribe to the *on_export_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_export_clicked, function)

    def _on_save_as_clicked(self, item):
        if not item.data["savable"]:
            return
        self.__on_save_as_clicked(item)

    def subscribe_on_save_as_clicked(self, function: Callable):
        """
        Subscribe to the *on_save_as_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_save_as_clicked, function)

    def _on_merge_clicked(self, items):
        if not items:
            return
        self.__on_merge_clicked(items)

    def subscribe_on_merge_clicked(self, function: Callable):
        """
        Subscribe to the *on_merge_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_merge_clicked, function)

    def _on_transfer_clicked(self, item, existing):
        self.__on_transfer_clicked(item, existing)

    def subscribe_on_transfer_clicked(self, function: Callable):
        """
        Subscribe to the *on_transfer_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_transfer_clicked, function)

    def _initialize_internal_members(self):
        self._dragged_item = None

        self._primary_selection = []
        self._hovered_items = {}
        self._background_items = {}
        self._context_menu_widgets = {}

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

    def destroy(self):
        _reset_default_attrs(self)

"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import os
import typing
from typing import Callable

import omni.ui as ui
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.color import hex_to_color as _hex_to_color
from omni.flux.utils.widget.gradient import create_gradient as _create_gradient

from .model import HEADER_DICT
from .model import ItemAddNewReferenceFileMesh as _ItemAddNewReferenceFileMesh
from .model import ItemInstanceMesh as _ItemInstanceMesh
from .model import ItemInstancesMeshGroup as _ItemInstancesMeshGroup
from .model import ItemMesh as _ItemMesh
from .model import ItemReferenceFileMesh as _ItemReferenceFileMesh

if typing.TYPE_CHECKING:
    from pxr import Usd


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the action lister"""

    DEFAULT_IMAGE_ICON_SIZE = 24

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
        self.__gradient_height = self.DEFAULT_IMAGE_ICON_SIZE
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

        self.__on_delete_reference = _Event()
        self.__on_toggle_visibility = _Event()
        self.__on_frame_prim = _Event()
        self.__on_toggle_nickname = _Event()

    def _delete_reference(self, item: _ItemReferenceFileMesh):
        """Call the event object that has the list of functions"""
        self.__on_delete_reference(item)

    def subscribe_delete_reference(self, function: Callable[["Usd.Prim", str], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_delete_reference, function)

    def _toggle_visibility(self, prim: "Usd.Prim"):
        """Call the event object that has the list of functions"""
        self.__on_toggle_visibility(prim)

    def subscribe_toggle_visibility(self, function: Callable[["Usd.Prim"], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_toggle_visibility, function)

    def _frame_prim(self, prim: "Usd.Prim"):
        """Call the event object that has the list of functions"""
        self.__on_frame_prim(prim)

    def subscribe_frame_prim(self, function: Callable[["Usd.Prim"], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_frame_prim, function)

    def _toggle_nickname(self, prim: "Usd.Prim"):
        """Call the event object that has the list of functions"""
        self.__on_toggle_nickname(prim)

    def subscribe_toggle_nickname(self, function: Callable[["Usd.Prim"], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_toggle_nickname, function)

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
        return self._path_scroll_frames

    def __generate_tool_tip(self, item) -> str:
        if isinstance(item, _ItemMesh):
            return item.path
        if isinstance(item, _ItemReferenceFileMesh):
            return item.path
        if isinstance(item, _ItemAddNewReferenceFileMesh):
            return item.display
        if isinstance(item, _ItemInstancesMeshGroup):
            return item.display
        if isinstance(item, _ItemInstanceMesh):
            return item.path
        return ""

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        if column_id == 0:
            with ui.ZStack(mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, item)):
                if id(item) not in self._background_rectangle:
                    self._background_rectangle[id(item)] = []
                self._background_rectangle[id(item)].append(
                    ui.Rectangle(height=self.DEFAULT_IMAGE_ICON_SIZE, style_type_name_override="TreeView.Item")
                )
                with ui.VStack():
                    ui.Spacer()
                    with ui.HStack(width=16 * (level + 2), height=self.DEFAULT_IMAGE_ICON_SIZE):
                        # ui.Spacer()
                        if model.can_item_have_children(item):
                            # Draw the +/- icon
                            style_type_name_override = "TreeView.Item.Minus" if expanded else "TreeView.Item.Plus"
                            with ui.VStack(width=ui.Pixel(16)):
                                ui.Spacer(width=0)
                                ui.Image(
                                    "",
                                    width=10,
                                    height=10,
                                    style_type_name_override=style_type_name_override,
                                )
                                ui.Spacer(width=0)
                        else:
                            ui.Spacer(width=ui.Pixel(16))
                        with ui.HStack():
                            ui.Spacer(height=0, width=ui.Pixel(8))
                            with ui.VStack(width=ui.Pixel(16)):
                                ui.Spacer(width=0)
                                if isinstance(item, (_ItemMesh, _ItemReferenceFileMesh)):
                                    ui.Image("", height=ui.Pixel(16), name="Hexagon")
                                elif isinstance(item, _ItemAddNewReferenceFileMesh):
                                    ui.Image("", height=ui.Pixel(16), name="Add")
                                elif isinstance(item, _ItemInstancesMeshGroup):
                                    ui.Image("", height=ui.Pixel(16), name="FolderClosed")
                                ui.Spacer(width=0)
                    ui.Spacer()

    # noinspection PyUnusedLocal
    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
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
                            tooltip = self.__generate_tool_tip(item)
                            with ui.HStack(
                                mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
                                mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(b, item),
                                tooltip=tooltip,
                            ):
                                with ui.Frame(
                                    height=0,
                                    separate_window=True,  # to be able to select
                                ):
                                    self._zstack_scroll = ui.ZStack()
                                    with self._zstack_scroll:
                                        self._path_scroll_frames[id(item)] = ui.ScrollingFrame(
                                            name="TreePanelBackground",
                                            height=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE),
                                            # width=ui.Percent(90),
                                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            scroll_y_max=0,
                                        )
                                        with self._path_scroll_frames[id(item)]:
                                            with ui.HStack():
                                                if isinstance(item, _ItemMesh):
                                                    ui.Label(item.prim.GetName(), name="PropertiesPaneSectionTreeItem")
                                                elif isinstance(item, _ItemReferenceFileMesh):
                                                    ui.Label(
                                                        os.path.basename(item.path),
                                                        name="PropertiesPaneSectionTreeItem",
                                                    )
                                                elif isinstance(item, _ItemAddNewReferenceFileMesh):
                                                    ui.Label(item.display, name="PropertiesPaneSectionTreeItem60")
                                                elif isinstance(item, _ItemInstancesMeshGroup):
                                                    ui.Label(item.display, name="PropertiesPaneSectionTreeItem")
                                                elif isinstance(item, _ItemInstanceMesh):
                                                    ui.Label(
                                                        os.path.basename(item.path),
                                                        name="PropertiesPaneSectionTreeItem",
                                                    )
                                                ui.Spacer(
                                                    height=0, width=ui.Pixel(self.__gradient_width / 2)
                                                )  # because of gradiant
                                        with ui.HStack():
                                            ui.Spacer()
                                            self._gradient_frame[id(item)] = ui.Frame(
                                                separate_window=True, width=ui.Pixel(self.__gradient_width)
                                            )
                            if isinstance(item, _ItemMesh):
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(
                                    width=ui.Pixel(16),
                                    content_clipping=True,
                                ):
                                    ui.Spacer(width=0)
                                    ui.Image(
                                        "",
                                        height=ui.Pixel(16),
                                        name="Nickname",
                                        tooltip="Switch between nickname and real prim name",
                                        mouse_released_fn=lambda x, y, b, m: self._on_nickname_mouse_released(b, item),
                                    )
                                    ui.Spacer(width=0)
                            elif isinstance(item, _ItemReferenceFileMesh):
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(
                                    width=ui.Pixel(16),
                                    content_clipping=True,
                                ):
                                    ui.Spacer(width=0)
                                    ui.Image(
                                        "",
                                        height=ui.Pixel(16),
                                        name="Subtract",
                                        tooltip="Delete the asset",
                                        mouse_released_fn=lambda x, y, b, m: self._on_delete_ref_mouse_released(
                                            b, item
                                        ),
                                    )
                                    ui.Spacer(width=0)
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(
                                    width=ui.Pixel(16),
                                    content_clipping=True,
                                ):
                                    ui.Spacer(width=0)
                                    ui.Image(
                                        "",
                                        height=ui.Pixel(16),
                                        name="Eye",
                                        tooltip=(
                                            "Hide/show the asset. Keep in mind that the exporter will ignore the "
                                            "value"
                                        ),
                                        mouse_released_fn=lambda x, y, b, m: self._on_visibility_mouse_released(
                                            b, item
                                        ),
                                    )
                                    ui.Spacer(width=0)
                            elif isinstance(item, _ItemInstanceMesh):
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(
                                    width=ui.Pixel(16),
                                    content_clipping=True,
                                ):
                                    ui.Spacer(width=0)
                                    ui.Image(
                                        "",
                                        height=ui.Pixel(16),
                                        name="Frame",
                                        tooltip="Frame instance in the viewport",
                                        mouse_released_fn=lambda x, y, b, m: self._on_frame_mouse_released(b, item),
                                    )
                                    ui.Spacer(width=0)
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(
                                    width=ui.Pixel(16),
                                    content_clipping=True,
                                ):
                                    ui.Spacer(width=0)
                                    ui.Image(
                                        "",
                                        height=ui.Pixel(16),
                                        name="Eye",
                                        tooltip=(
                                            "Hide/show the asset. Keep in mind that the exporter will ignore "
                                            "the value"
                                        ),
                                        mouse_released_fn=lambda x, y, b, m: self._on_visibility_mouse_released(
                                            b, item
                                        ),
                                    )
                                    ui.Spacer(width=0)
                        ui.Spacer(height=0, width=ui.Pixel(8))

        asyncio.ensure_future(self._add_gradient_or_not(item))

    def _on_item_hovered(self, hovered, item):
        self._hovered_items[id(item)] = hovered
        for rectangle in self._background_rectangle.get(id(item), []):
            rectangle.style_type_name_override = (
                "TreeView.Item.IsHovered" if hovered and item not in self._current_selection else "TreeView.Item"
            )
        self.refresh_gradient_color(item, deferred=False)

    def _on_nickname_mouse_released(self, button, item):
        if button != 0:
            return
        self._toggle_nickname(item.prim)

    def _on_delete_ref_mouse_released(self, button, item):
        if button != 0:
            return
        self._delete_reference(item)

    def _on_visibility_mouse_released(self, button, item):
        if button != 0:
            return
        self._toggle_visibility(item.prim)

    def _on_frame_mouse_released(self, button, item):
        if button != 0:
            return
        self._frame_prim(item.prim)

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

    def on_item_selected(self, selected_items, all_items):
        self._current_selection = selected_items
        for item in all_items:
            self.refresh_gradient_color(item)
            for rectangle in self._background_rectangle.get(id(item), []):
                rectangle.style_type_name_override = (
                    "TreeView.Item.selected" if item in selected_items else "TreeView.Item"
                )

    @omni.usd.handle_exception
    async def _add_gradient_or_not(self, item):
        await omni.kit.app.get_app().next_update_async()
        if self._path_scroll_frames[id(item)].scroll_x_max > 0:
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

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        _reset_default_attrs(self)

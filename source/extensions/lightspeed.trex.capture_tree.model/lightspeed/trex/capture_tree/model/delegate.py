"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import functools
import os

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.color import color_to_hex as _color_to_hex
from omni.flux.utils.widget.loader import Loader as _Loader

from .model import HEADER_DICT


class CaptureTreeDelegate(ui.AbstractItemDelegate):
    """Delegate of the action lister"""

    DEFAULT_BIG_IMAGE_SIZE = (600, 600)
    DEFAULT_NO_IMAGE_SIZE = (400, 100)
    DEFAULT_IMAGE_ICON_SIZE = 24

    def __init__(self, preview_on_hover: bool = True):
        super().__init__()

        self._default_attr = {
            "_preview_on_hover": None,
            "_path_scroll_frames": None,
            "_window_bigger_image": None,
            "_bigger_image": None,
            "_no_image_label": None,
            "_on_import_layer_pressed_event": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._preview_on_hover = preview_on_hover
        self._path_scroll_frames = {}

        self.__cancel_mouse_hovered = False
        self.__current_big_image_item = None
        self.__create_bigger_image_ui()

    def get_path_scroll_frames(self):
        return self._path_scroll_frames

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch model that opens or closes subtree"""
        if column_id == 0:
            frame = ui.Frame()
            with frame:
                if item.image:
                    image_widget = ui.Image(
                        item.image,
                        height=self.DEFAULT_IMAGE_ICON_SIZE,
                        width=self.DEFAULT_IMAGE_ICON_SIZE,
                        identifier="item_thumbnail",
                    )
                else:
                    image_widget = ui.Rectangle(
                        height=self.DEFAULT_IMAGE_ICON_SIZE,
                        width=self.DEFAULT_IMAGE_ICON_SIZE,
                        identifier="item_no_thumbnail",
                    )
            frame.set_mouse_hovered_fn(functools.partial(self._on_image_hovered, image_widget, item))

    def get_window_bigger_image(self):
        return self._window_bigger_image

    def __create_bigger_image_ui(self):
        flags = ui.WINDOW_FLAGS_NO_COLLAPSE
        flags |= ui.WINDOW_FLAGS_NO_CLOSE
        flags |= ui.WINDOW_FLAGS_NO_MOVE
        flags |= ui.WINDOW_FLAGS_NO_RESIZE
        flags |= ui.WINDOW_FLAGS_NO_SCROLLBAR
        flags |= ui.WINDOW_FLAGS_NO_DOCKING
        flags |= ui.WINDOW_FLAGS_NO_BACKGROUND
        flags |= ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE
        flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR
        flags |= ui.WINDOW_FLAGS_POPUP

        self._window_bigger_image = ui.Window(
            "Capture image bigger",
            width=self.DEFAULT_BIG_IMAGE_SIZE[0],
            height=self.DEFAULT_BIG_IMAGE_SIZE[1],
            visible=False,
            flags=flags,
            identifier="big_thumbnail",
        )
        with self._window_bigger_image.frame:
            stack = ui.ZStack()
            with stack:
                ui.Rectangle(name="PropertiesPaneSectionWindowImageBackground")
                with ui.ScrollingFrame(
                    name="TreePanelBackground",
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    scroll_y_max=0,
                ):
                    with ui.VStack():
                        for _ in range(5):
                            with ui.HStack():
                                for _ in range(3):
                                    ui.Image(
                                        "",
                                        name="TreePanelLinesBackground",
                                        fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                        height=ui.Pixel(256),
                                        width=ui.Pixel(256),
                                    )
                with ui.Frame(separate_window=True):  # to keep the Z depth order
                    with ui.ZStack():
                        self._bigger_image = ui.Image("", identifier="big_image")
                        self._no_image_label = ui.Label(
                            "No image",
                            alignment=ui.Alignment.CENTER,
                            name="PropertiesPaneSectionCaptureTreeItemNoImage",
                            visible=False,
                            identifier="no_image",
                        )
            stack.set_mouse_hovered_fn(self.__on_bigger_image_hovered)

    def __on_bigger_image_hovered(self, hovered):
        self.__cancel_mouse_hovered = hovered
        if not hovered:
            self._window_bigger_image.visible = False

    def _on_image_hovered(self, image_widget, item, hovered):
        if (
            self.__cancel_mouse_hovered
            and hovered
            and self._window_bigger_image.visible
            and self.__current_big_image_item == item
        ):
            return

        if not item:
            return

        if hovered and self._preview_on_hover:
            self._bigger_image.source_url = item.image if item.image else ""
            self._no_image_label.visible = not bool(item.image)
            if item.image:
                self._window_bigger_image.width = self.DEFAULT_BIG_IMAGE_SIZE[0]
                self._window_bigger_image.height = self.DEFAULT_BIG_IMAGE_SIZE[1]
            else:
                self._window_bigger_image.width = self.DEFAULT_NO_IMAGE_SIZE[0]
                self._window_bigger_image.height = self.DEFAULT_NO_IMAGE_SIZE[1]
            self._window_bigger_image.position_x = image_widget.screen_position_x + image_widget.computed_width + 10
            self._window_bigger_image.position_y = image_widget.screen_position_y
            self._window_bigger_image.visible = True
            self.__cancel_mouse_hovered = True
        elif self.__current_big_image_item and self.__current_big_image_item.path == item.path:
            self._window_bigger_image.visible = False
            self.__cancel_mouse_hovered = False

        self.__current_big_image_item = item

    # noinspection PyUnusedLocal
    def build_widget(self, model, item, column_id, level, expanded):
        """Create a model per item"""
        if item is None:
            return
        with ui.HStack():
            if column_id == 0:
                with ui.HStack():
                    ui.Spacer(height=0, width=ui.Pixel(8))
                    with ui.Frame(height=0, separate_window=True):
                        self._path_scroll_frames[id(item)] = ui.ScrollingFrame(
                            name="TreePanelBackground",
                            height=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE),
                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            scroll_y_max=0,
                        )
                        with self._path_scroll_frames[id(item)]:
                            ui.Label(
                                os.path.basename(item.path),
                                name="PropertiesPaneSectionTreeItem",
                                tooltip=item.path,
                                identifier="item_title",
                            )
                    ui.Spacer(height=0, width=ui.Pixel(8))
            if column_id == 1:
                with ui.ZStack():
                    if item.replaced_items is not None and item.total_items is not None:
                        color = self.__get_progress_color(
                            item.replaced_items / item.total_items if item.total_items > 0 else 0
                        )
                        ui.Rectangle(
                            height=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE) - 2,
                            style={"background_color": color},
                        )
                        with ui.HStack():
                            ui.Spacer()
                            ui.Label(
                                f"{'{:.0f}'.format(item.replaced_items)} / {'{:.0f}'.format(item.total_items)}",
                                width=0,
                                name="ProgressLabel",
                            )
                            ui.Spacer()
                    else:
                        with ui.HStack():
                            ui.Spacer()
                            _Loader()
                            ui.Spacer()

    def build_header(self, column_id):
        """Build the header"""
        with ui.VStack(height=ui.Pixel(24)):
            style_type_name = "TreeView.Header"
            ui.Label(
                HEADER_DICT[column_id][0],
                style_type_name_override=style_type_name,
                alignment=ui.Alignment.CENTER,
                tooltip=HEADER_DICT[column_id][1],
            )

    def __get_progress_color(self, progress: float):
        r = min(255.0, (1.0 - progress) * 2.0 * 255.0) / 255
        g = min(255.0, progress * 2.0 * 255.0) / 255
        return _color_to_hex((r, g, 0, 0.3))

    def destroy(self):
        _reset_default_attrs(self)

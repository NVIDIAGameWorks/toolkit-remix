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

from .model import HEADER_DICT


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the action lister"""

    DEFAULT_BIG_IMAGE_SIZE = (600, 600)
    DEFAULT_NO_IMAGE_SIZE = (400, 100)
    DEFAULT_IMAGE_ICON_SIZE = 24

    def __init__(self):
        super().__init__()

        self._default_attr = {
            "_window_bigger_image": None,
            "_bigger_image": None,
            "_no_image_label": None,
            "_path_scroll_frames": None,
            "_on_import_layer_pressed_event": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._path_scroll_frames = {}
        self.__cancel_mouse_hovered = False
        self.__current_big_image_item = None
        self.__create_bigger_image_ui()

    def get_path_scroll_frames(self):
        return self._path_scroll_frames

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        if column_id == 0:
            frame = ui.Frame()
            with frame:
                if item.image:
                    image_widget = ui.Image(
                        item.image, height=self.DEFAULT_IMAGE_ICON_SIZE, width=self.DEFAULT_IMAGE_ICON_SIZE
                    )
                else:
                    image_widget = ui.Rectangle(height=self.DEFAULT_IMAGE_ICON_SIZE, width=self.DEFAULT_IMAGE_ICON_SIZE)
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
                        self._bigger_image = ui.Image("")
                        self._no_image_label = ui.Label(
                            "No image",
                            alignment=ui.Alignment.CENTER,
                            name="PropertiesPaneSectionCaptureTreeItemNoImage",
                            visible=False,
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
        if hovered:
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
        elif self.__current_big_image_item.path == item.path:
            self._window_bigger_image.visible = False
            self.__cancel_mouse_hovered = False
        self.__current_big_image_item = item

    # noinspection PyUnusedLocal
    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""

        if item is None:
            return
        if column_id == 0:
            with ui.HStack():
                ui.Spacer(height=0, width=ui.Pixel(8))
                with ui.Frame(height=0, separate_window=True):
                    self._path_scroll_frames[id(item)] = ui.ScrollingFrame(
                        name="TreePanelBackground",
                        height=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE),
                        width=ui.Percent(100),
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        scroll_y_max=0,
                    )
                    with self._path_scroll_frames[id(item)]:
                        ui.Label(os.path.basename(item.path), name="PropertiesPaneSectionTreeItem", tooltip=item.path)

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        _reset_default_attrs(self)

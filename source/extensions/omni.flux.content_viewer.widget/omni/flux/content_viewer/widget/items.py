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
import typing
from typing import Any, Callable, Dict, Optional, Type

import carb.input
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import async_wrap as _async_wrap
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .utils import is_path_readable as _is_path_readable

if typing.TYPE_CHECKING:
    from omni.flux.content_viewer.widget.core import BaseContentData, ContentData, ContentDataAdd, ContentViewerCore


class BaseContentItem(ui.AbstractItem):
    """Base item to use to show an item in the grid or list view"""

    def __init__(
        self,
        content_data: Type["BaseContentData"],
        core: Type["ContentViewerCore"],
        grid_column_width: int,
        grid_row_height: int,
        grid_root_frame: ui.Widget,
        list_mode: bool = False,
    ):
        """
        Init

        Args:
            content_data: the data that the item will represent
            core: the core of the viewer
            grid_column_width: the width of the grid columns
            grid_row_height: the height of the grid columns
            grid_root_frame: the root frame of the item, used by the grid view
            list_mode: show the item for a grid view or list view
        """
        super().__init__()
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._style = ui.Style.get_instance().default

        self._grid_column_width = grid_column_width
        self._grid_row_height = grid_row_height
        self.content_data = content_data
        self._core = core
        self._list_mode = list_mode

        self._list_root_frames = None  # for list view. Each column in a frame
        self._list_root_labels = None  # for list view. Each column in a frame

        self.__current_grid_scale_size = None
        self.__is_selected = False

        self.__on_resized_grid_task = None
        self.__create_ui_task = None

        self._grid_root_frame = grid_root_frame

        self._update_default_style()
        if list_mode:
            self.title_model = ui.SimpleStringModel(self.content_data.title)
        else:
            self.__create_ui()

    def _update_default_style(self):
        """
        This widget generate image from text. It needs to read keys from a the global style.
        If those keys doesn't exist, we add them here (or it will crash). With this, the widget will work even without
        global style that sets those keys
        """
        if "Label::ContentViewerWidgetItemListTitle" not in self._style:
            self._style["Label::ContentViewerWidgetItemListTitle"] = {"color": 0x99FFFFFF, "font_size": 14}
            self._style["Label::ContentViewerWidgetItemListTitle:selected"] = {"color": 0xFFFFFFFF, "font_size": 14}
            self._style["Label::ContentViewerWidgetItemListTitle:hovered"] = {"color": 0xCCFFFFFF, "font_size": 14}

    @property
    def default_attr(self) -> Dict[str, Any]:
        """Default attribute with default values created in the class that will be destroyed during closing"""
        return {
            "_core": None,
            "_grid_root_frame": None,
            "_grid_column_width": None,
            "_grid_row_height": None,
            "_list_root_frames": None,
            "_list_root_labels": None,
        }

    def __create_ui(self):
        """Create the UI"""
        if self.__create_ui_task:
            self.__create_ui_task.cancel()
        self.__create_ui_task = asyncio.ensure_future(self.__deferred_create_ui())

    def get_current_grid_scale_size(self) -> int:
        """Get the current grid scale size"""
        return self.__current_grid_scale_size

    def on_resized_grid(self, grid_scale_size: int):
        """
        Called when the grid is resized

        Args:
            grid_scale_size: the scale value of the grid
        """
        self.__current_grid_scale_size = grid_scale_size
        if self.__on_resized_grid_task:
            self.__on_resized_grid_task.cancel()
        self.__on_resized_grid_task = asyncio.ensure_future(self.__deferred_on_resized_grid(grid_scale_size))

    @omni.usd.handle_exception
    async def __deferred_on_resized_grid(self, grid_scale_size: int):
        """
        Smooth the value/give a new range

        Args:
            grid_scale_size: the scale value of the grid
        """
        old_max = 200
        old_min = 0
        new_max = 140
        new_min = 60
        old_range = old_max - old_min
        new_range = new_max - new_min
        new_value = (((grid_scale_size - old_min) * new_range) / old_range) + new_min

        await self._deferred_on_resized_grid(grid_scale_size, new_value)

    @omni.usd.handle_exception
    async def _deferred_on_resized_grid(self, grid_size, new_value):
        if self._list_mode:
            if self._list_root_frames is not None:
                for frame in self._list_root_frames.values():
                    frame.height = ui.Pixel(self._grid_row_height / 100 * grid_size)
            if self._list_root_labels is not None:
                self._style["Label::ContentViewerWidgetItemListTitle"]["font_size"] = (
                    grid_size / 100
                ) * self.TITLE_FONT_SIZE
                for label in self._list_root_labels.values():
                    label.style = self._style["Label::ContentViewerWidgetItemListTitle"]

    def get_grid_row_height(self) -> int:
        """Get the grid row height"""
        return self._grid_row_height

    def set_selected(self, value: bool):
        """
        Set the item selected or not

        Args:
            value: the selection value
        """
        self.__is_selected = value

    def is_selected(self) -> bool:
        """Tell is th e item is selected"""
        return self.__is_selected

    @omni.usd.handle_exception
    async def __deferred_create_ui(self):
        """Create the UI"""
        if self._grid_root_frame is None:
            await self._deferred_create_ui()
        else:
            with self._grid_root_frame:  # needed because async
                await self._deferred_create_ui()

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _deferred_create_ui(self):
        pass

    def set_list_root_frames(self, value: Dict[str, ui.Frame]):
        """
        Save frames that will be resized when the scale of the list view change

        Args:
            value: the name of the frame as a key, the ui.Frame as a value
        """
        self._list_root_frames = value

    def get_list_root_frames(self) -> Dict[str, ui.Frame]:
        """Get the root frames that the list view use when we scale it"""
        return self._list_root_frames

    def set_list_root_labels(self, value: Dict[str, ui.Label]):
        """
        Save labels that will be resized when the scale of the list view change

        Args:
            value: the name of the label as a key, the ui.Label as a value
        """
        self._list_root_labels = value

    def get_list_root_labels(self) -> Dict[str, ui.Label]:
        """Get the root labels that the list view use when we scale it"""
        return self._list_root_labels

    @abc.abstractmethod
    def on_mouse_clicked(self, x, y, b, m):  # noqa PLC0103
        """Called when the item is clicked on"""
        pass

    def on_mouse_released(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is released"""
        pass

    def on_mouse_moved(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is moved"""
        pass

    def destroy(self):
        if self.__on_resized_grid_task:
            self.__on_resized_grid_task.cancel()
        self.__on_resized_grid_task = None
        self.__current_grid_scale_size = None
        if self.__create_ui_task:
            self.__create_ui_task.cancel()
        self.__create_ui_task = None
        _reset_default_attrs(self)

    def __repr__(self):
        return f'"{self.content_data.title}"'


class ContentItemAdd(BaseContentItem):
    """
    Content Item Add. This is an item that you can use to "Add" data
    """

    #: The size of the label that will be shown when the content doesn't exist
    NO_FONT_SIZE = 14
    #: The size of the label that will be shown as a title (bottom of the item)
    TITLE_FONT_SIZE = 14

    """Instance"""

    def __init__(
        self,
        content_data: Type["ContentDataAdd"],
        core: Type["ContentViewerCore"],
        grid_column_width: int,
        grid_row_height: int,
        grid_root_frame: ui.Widget,
        list_mode: bool = False,
    ):
        """
        Init

        Args:
            content_data: the data that the item will represent
            core: the core of the viewer
            grid_column_width: the width of the grid columns
            grid_row_height: the height of the grid columns
            grid_root_frame: the root frame of the item, used by the grid view
            list_mode: show the item for a grid view or list view
        """

        if not list_mode:
            self.__overlay_wide_rectangle = None
            self.__overlay_highlight_rectangle = None  # noqa PLW0238

        super().__init__(content_data, core, grid_column_width, grid_row_height, grid_root_frame, list_mode=list_mode)

        if list_mode:
            self.title_model = ui.SimpleStringModel("Add new")

    def _update_default_style(self):
        """
        This widget generate image from text. It needs to read keys from a the global style.
        If those keys doesn't exist, we add them here (or it will crash). With this, the widget will work even without
        global style that sets those keys
        """
        super()._update_default_style()
        if "Label::ContentViewerWidgetItemNoImage" not in self._style:
            self._style["Label::ContentViewerWidgetItemNoImage"] = {"font_size": 14, "margin": 5}

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _deferred_create_ui(self):
        """Create the UI"""
        with ui.ZStack():
            self.__overlay_wide_rectangle = ui.Rectangle(
                name="ContentViewerWidgetItemSelected",
                mouse_pressed_fn=self.on_mouse_clicked,
                mouse_released_fn=self.on_mouse_released,
                mouse_moved_fn=self.on_mouse_moved,
            )
            # highlight rectangle when the mouse is over it
            self.__overlay_highlight_rectangle = ui.Rectangle(name="ContentViewerWidgetItemOverlay")  # noqa PLW0238
            with ui.VStack():
                ui.Spacer(height=ui.Percent(4 / (self._grid_row_height / 100)))
                with ui.HStack(height=ui.Percent(144 / (self._grid_row_height / 100))):
                    ui.Spacer(width=ui.Percent(4 / (self._grid_column_width / 100)))
                    with ui.ZStack():
                        # no image/loading frame for label
                        with ui.Frame():
                            updated_style = self._style["Label::ContentViewerWidgetItemNoImage"].copy()
                            updated_style["font_size"] = self.NO_FONT_SIZE
                            ui.Label("Image", name="ContentViewerWidgetItemNoImage", style=updated_style)
                            ui.Image("", name="ContentViewerWidgetItemAddAdd")

                    ui.Spacer(width=ui.Percent(4 / (self._grid_column_width / 100)))
                ui.Spacer(height=ui.Percent(4 / (self._grid_row_height / 100)))

    def set_selected(self, value: bool):
        """
        Set the item selected or not

        Args:
            value: the selection value
        """
        super().set_selected(value)
        if not self._list_mode:
            self.__overlay_wide_rectangle.selected = value

    def on_mouse_clicked(self, x, y, b, m):  # noqa PLC0103
        """Called when the item is clicked on"""
        self._core.set_item_was_clicked(True)
        self._core.set_selection(self.content_data)

    def on_mouse_released(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is released"""
        pass

    def on_mouse_moved(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is moved"""
        pass

    def destroy(self):
        self.__overlay_highlight_rectangle = None  # noqa PLW0238
        self.__overlay_wide_rectangle = None
        super().destroy()

    def __repr__(self):
        return "Add widget"


class ContentItem(BaseContentItem):
    """
    Content Item. This is an item that you can use to show any data that has a path
    """

    #: The size of the label that will be shown when the content doesn't exist
    NO_FONT_SIZE = 14
    #: The size of the label that will be shown as a title (bottom of the item)
    TITLE_FONT_SIZE = 14
    #: Say if we would be able to select another item when this one is already selected
    MULTI_SELECTION = True
    #: Say if we would be able to drag the item
    DRAG = False
    #: Say if we should be select the checkpoint version or not
    CAN_CHOSE_CHECKPOINT = False

    """Instance"""

    def __init__(
        self,
        content_data: Type["ContentData"],
        core,
        grid_column_width,
        grid_row_height,
        grid_root_frame,
        list_mode=False,
    ):
        """Content Item represent the UI of 1 content"""
        self.content_data = content_data
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self.__create_ui_checkpoint_task = None

        if not list_mode:
            self.__checkpoint_zstack = None
            self.__checkpoint_combobox = None
            self.__overlay_wide_rectangle = None
            self.__overlay_highlight_rectangle = None
            self.__no_image_frame = None
            self.__no_usd_path_frame = None
            self.__title_frame = None
            self.__image_frame = None
            self.__label_message_no_image = None

            self._primary_thumbnail_loaded_subscription = core.subscribe_primary_thumbnail_loaded(
                self._on_primary_thumbnail_loaded
            )

        super().__init__(content_data, core, grid_column_width, grid_row_height, grid_root_frame, list_mode=list_mode)

    def _update_default_style(self):
        """
        This widget generate image from text. It needs to read keys from a the global style.
        If those keys doesn't exist, we add them here (or it will crash). With this, the widget will work even without
        global style that sets those keys
        """
        super()._update_default_style()
        if "Label::ContentViewerWidgetItemNoImage" not in self._style:
            self._style["Label::ContentViewerWidgetItemNoImage"] = {"font_size": 14, "margin": 5}
        if "Label::ContentViewerWidgetItemWrong" not in self._style:
            self._style["Label::ContentViewerWidgetItemWrong"] = {"color": 0xDB0000FF, "font_size": 14}
        if "Label::ContentViewerWidgetItemTitle" not in self._style:
            self._style["Label::ContentViewerWidgetItemTitle"] = {"color": 0x99FFFFFF, "font_size": 14}
            self._style["Label::ContentViewerWidgetItemTitle:selected"] = {"color": 0xFFFFFFFF, "font_size": 14}

    @property
    def default_attr(self):
        """Default attribute with default values created in the class that will be destroyed during closing"""
        return {
            "_content_viewer_widget_items_no_image": None,
            "_content_viewer_widget_item_wrong": None,
            "_content_viewer_widget_item_title": None,
            "_content_viewer_widget_item_title_label": None,
        }

    @omni.usd.handle_exception
    async def is_usd_path_valid(self, callback: Callable[[bool], Any]):
        """
        Check is the path exist or not

        Args:
            callback: the function that will be called after the path it checked
        """
        if self.content_data.path:
            result = await _is_path_readable(self.content_data.path)
        else:
            result = True
        callback(result)

    @omni.usd.handle_exception
    async def __deferred_primary_image(self, callback):
        wrapped_fn = _async_wrap(callback)
        result = await wrapped_fn()
        if self._core is None:
            return
        self._core.primary_thumbnail_loaded(self.content_data, result)

    @omni.usd.handle_exception
    async def __deferred_update_ui(self):
        def do_update_ui(result):
            if not result:
                if self.__no_usd_path_frame is None:
                    return
                self.__no_usd_path_frame.clear()
                with self.__no_usd_path_frame:
                    self._content_viewer_widget_item_wrong = ui.Label(
                        "Item not found",
                        alignment=ui.Alignment.CENTER,
                        word_wrap=True,
                        name="ContentViewerWidgetItemWrong",
                    )
            if self.__no_usd_path_frame is None:
                return
            self.__no_usd_path_frame.visible = not result
            name = "ContentViewerWidgetItemOverlayWrong" if not result else "ContentViewerWidgetItemOverlay"
            self.__overlay_highlight_rectangle.name = name
            with self.__no_image_frame:
                alignment = ui.Alignment.CENTER_BOTTOM if self.__no_usd_path_frame.visible else ui.Alignment.CENTER
                updated_style = self._style["Label::ContentViewerWidgetItemNoImage"].copy()
                updated_style["font_size"] = self.NO_FONT_SIZE
                self._content_viewer_widget_items_no_image = ui.Label(
                    self.__label_message_no_image,
                    alignment=alignment,
                    name="ContentViewerWidgetItemNoImage",
                    style=updated_style,
                )

        await self.is_usd_path_valid(do_update_ui)

    def _on_primary_thumbnail_loaded(self, content_data, thumbnail_path):
        if content_data != self.content_data:
            return
        if thumbnail_path:
            self.__no_image_frame.clear()
            self.__no_image_frame.visible = False
            self.__image_frame.visible = True
            with self.__image_frame:
                ui.Image(thumbnail_path, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT, visible=True)
        else:
            self.__label_message_no_image = "No image"
            self.__no_image_frame.visible = True
            self.__no_image_frame.clear()
            with self.__no_image_frame:
                updated_style = self._style["Label::ContentViewerWidgetItemNoImage"].copy()
                updated_style["font_size"] = self.NO_FONT_SIZE

                alignment = ui.Alignment.CENTER_BOTTOM if self.__no_usd_path_frame.visible else ui.Alignment.CENTER
                self._content_viewer_widget_items_no_image = ui.Label(
                    self.__label_message_no_image,
                    alignment=alignment,
                    name="ContentViewerWidgetItemNoImage",
                    style=updated_style,
                )

    @omni.usd.handle_exception
    async def _deferred_on_resized_grid(self, grid_size, new_value):
        self.__create_labels()
        await super()._deferred_on_resized_grid(grid_size, new_value)
        if not self._list_mode:
            self._style["Label::ContentViewerWidgetItemNoImage"]["font_size"] = (grid_size / 100) * self.NO_FONT_SIZE
            self._style["Label::ContentViewerWidgetItemWrong"]["font_size"] = (grid_size / 100) * self.NO_FONT_SIZE
            self._style["Label::ContentViewerWidgetItemTitle"]["font_size"] = (new_value / 100) * self.TITLE_FONT_SIZE

            self._content_viewer_widget_items_no_image.style = self._style["Label::ContentViewerWidgetItemNoImage"]
            self._content_viewer_widget_item_wrong.style = self._style["Label::ContentViewerWidgetItemWrong"]
            self._content_viewer_widget_item_title_label.style = self._style["Label::ContentViewerWidgetItemTitle"]

    def __create_labels(self):
        """Create all 'no' labels (no image, no usd...)"""
        if not self._list_mode:
            if self.__no_image_frame is not None:
                self.__no_image_frame.clear()
                with self.__no_image_frame:
                    alignment = ui.Alignment.CENTER_BOTTOM if self.__no_usd_path_frame.visible else ui.Alignment.CENTER
                    self._content_viewer_widget_items_no_image = ui.Label(
                        self.__label_message_no_image, alignment=alignment, name="ContentViewerWidgetItemNoImage"
                    )
            if self.__no_usd_path_frame is not None:
                self.__no_usd_path_frame.clear()
                with self.__no_usd_path_frame:
                    self._content_viewer_widget_item_wrong = ui.Label(
                        "Item not found",
                        alignment=ui.Alignment.CENTER,
                        word_wrap=True,
                        name="ContentViewerWidgetItemWrong",
                    )
            if self.__title_frame is not None:
                self.__title_frame.clear()
                with self.__title_frame:
                    self._content_viewer_widget_item_title_label = ui.Label(
                        self.content_data.title,
                        alignment=ui.Alignment.LEFT,
                        name="ContentViewerWidgetItemTitle",
                        word_wrap=True,
                    )

    @omni.usd.handle_exception
    async def __deferred_create_ui_checkpoint(self, frame):
        def do_it():
            if self.content_data.is_checkpointed():
                result, entries = omni.client.list_checkpoints(self.content_data.path)
                if result == omni.client.Result.OK:
                    return entries
            return None

        wrapped_fn = _async_wrap(do_it)
        entries = await wrapped_fn()
        if entries is not None:
            with frame:
                with ui.VStack():
                    ui.Spacer()
                    with ui.HStack(height=0):
                        ui.Spacer()
                        self.__checkpoint_zstack = ui.ZStack(width=60, tooltip=entries[-1].comment)
                        with self.__checkpoint_zstack:
                            if self.CAN_CHOSE_CHECKPOINT:
                                ui.Rectangle(name="ContentViewerWidgetItemCheckPointChose")
                                self.__checkpoint_combobox = ui.ComboBox(
                                    0,
                                    *reversed([f"v{entry.relative_path[1:]}" for entry in entries]),
                                    mouse_pressed_fn=self._on_checkpoint_combobox_mouse_clicked,
                                    mouse_released_fn=self._on_checkpoint_combobox_mouse_released,
                                )
                                self.__checkpoint_combobox.model.add_item_changed_fn(self._on_checkpoint_changed)
                            else:
                                ui.Rectangle(name="ContentViewerWidgetItemCheckPoint")
                                ui.Label(
                                    [f"v{entry.relative_path[1:]}" for entry in entries][-1],
                                    alignment=ui.Alignment.CENTER,
                                )

    @omni.usd.handle_exception
    async def _deferred_create_ui(self):
        """Create the UI"""
        with ui.ZStack():
            self.__overlay_wide_rectangle = ui.Rectangle(
                name="ContentViewerWidgetItemSelected",
                mouse_pressed_fn=self.on_mouse_clicked,
                mouse_released_fn=self.on_mouse_released,
                mouse_moved_fn=self.on_mouse_moved,
            )
            # highlight rectangle when the mouse is over it
            self.__overlay_highlight_rectangle = ui.Rectangle(name="ContentViewerWidgetItemOverlay")
            if self.DRAG:
                self.__overlay_wide_rectangle.set_drag_fn(self._on_drag)
            with ui.HStack():
                ui.Spacer(width=ui.Percent(4 / (self._grid_column_width / 100)))
                with ui.VStack():
                    ui.Spacer(height=ui.Percent(4 / (self._grid_row_height / 100)))
                    with ui.ZStack(height=ui.Percent(160 / (self._grid_row_height / 100))):
                        # Grid image
                        ui.Image("", name="ContentViewerWidgetItemGrid")
                        with ui.VStack():
                            ui.Spacer(height=ui.Percent(16 / (self._grid_row_height / 100)))
                            with ui.HStack():
                                ui.Spacer(width=ui.Percent(16 / (self._grid_column_width / 100)))
                                with ui.ZStack():
                                    # image frame
                                    self.__image_frame = ui.Frame(visible=False)

                                    # no image/loading frame for label
                                    self.__no_image_frame = ui.Frame()
                                    self.__label_message_no_image = "Loading..."

                                    # no usd path frame for label
                                    self.__no_usd_path_frame = ui.Frame(visible=False)

                                    # checkpint
                                    if self.__create_ui_checkpoint_task:
                                        self.__create_ui_checkpoint_task.cancel()
                                    self.__create_ui_checkpoint_task = asyncio.ensure_future(
                                        self.__deferred_create_ui_checkpoint(ui.Frame())
                                    )
                                ui.Spacer(width=ui.Percent(16 / (self._grid_column_width / 100)))
                            ui.Spacer(height=ui.Percent(16 / (self._grid_column_width / 100)))
                    with ui.HStack():
                        ui.Spacer(width=ui.Percent(4 / (self._grid_column_width / 100)))
                        self.__title_frame = ui.Frame()
                        ui.Spacer(width=ui.Percent(4 / (self._grid_column_width / 100)))
                    ui.Spacer(height=ui.Percent(4 / (self._grid_row_height / 100)))
                ui.Spacer(width=ui.Percent(4 / (self._grid_column_width / 100)))
        self.__create_labels()
        # get the primary image async for speed
        image_fn = self.content_data.image_path_fn
        if image_fn is not None:
            await self.__deferred_primary_image(image_fn)
        else:
            self._on_primary_thumbnail_loaded(self.content_data, None)
        # update the ui in async functions for speed (ui that need to check usd path for example, etc etc)
        await self.__deferred_update_ui()

    def _on_drag(self):
        return self.content_data.path

    def destroy(self):
        if not self._list_mode:
            self.__background_image = None  # noqa PLW0238
            self.__checkpoint_zstack = None
            self.__checkpoint_combobox = None
            self.__overlay_wide_rectangle = None
            self.__overlay_highlight_rectangle = None
            self.__no_image_frame = None
            self.__no_usd_path_frame = None
            self.__title_frame = None
            self.__image_frame = None
            self.__label_message_no_image = None
            if self.__create_ui_checkpoint_task:
                self.__create_ui_checkpoint_task.cancel()
            self.__create_ui_checkpoint_task = None
        super().destroy()

    def set_selected(self, value: bool):
        """
        Set the item selected or not

        Args:
            value: the selection value
        """
        super().set_selected(value)
        if not self._list_mode:
            self.__overlay_wide_rectangle.selected = value
            self._content_viewer_widget_item_title_label.selected = value

    def _on_checkpoint_changed(self, model, item):
        entry = self.get_current_checkpoint()
        if entry is not None:
            self.content_data.checkpoint_version = entry.relative_path[1:]
            self.__checkpoint_zstack.set_tooltip(entry.comment)

    def get_current_checkpoint(self) -> Optional[omni.client.ListEntry]:
        """Get the current checkpoint version"""
        if self.CAN_CHOSE_CHECKPOINT and self.content_data.is_checkpointed():
            result, entries = omni.client.list_checkpoints(self.content_data.path)
            if result == omni.client.Result.OK:
                return entries[::-1][self.__checkpoint_combobox.model.get_item_value_model().as_int]
        return None

    def _on_checkpoint_combobox_mouse_clicked(self, x, y, b, m):  # noqa PLC0103
        self._core.set_block_selection(True)

    def _on_checkpoint_combobox_mouse_released(self, x, y, b, m):  # noqa PLC0103
        self._core.set_block_selection(False)

    def on_mouse_clicked(self, x, y, b, m):  # noqa PLC0103
        """Called when the item is clicked on"""
        if b != 0:
            return
        if self._core.is_selection_blocked():
            return
        self._core.set_item_was_clicked(True)
        key_mod = m & ~ui.Widget.FLAG_WANT_CAPTURE_KEYBOARD
        if key_mod == int(carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT) and self.MULTI_SELECTION:
            self._core.set_selection(self.content_data, append_in_between=True)
        elif key_mod == int(carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL) and self.MULTI_SELECTION:
            self._core.set_selection(self.content_data, append=True)
        else:
            self._core.set_selection(self.content_data)

    def on_mouse_released(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is released"""
        pass  # PLW0107

    def on_mouse_moved(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is moved"""
        pass  # PLW0107

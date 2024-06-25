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
import typing
from typing import Any, Dict, List, Optional, Type

import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .core import ContentDataAdd as _ContentDataAdd
from .items import ContentItem as _ContentItem
from .items import ContentItemAdd as _ContentItemAdd
from .tree_delegate import Delegate as _DelegateTreeView
from .tree_model import Model as _ModelTreeView

if typing.TYPE_CHECKING:
    from .core import BaseContentData, ContentViewerCore
    from .items import BaseContentItem


class ContentViewerWidget:
    """
    Widget that let show any data into a grid view or a list view
    """

    #: Show the view as a list or not by default
    LIST_VIEW_MODE: bool = False
    #: Height of the row of the list view
    WIDTH_BACKGROUND_SLIDER: int = 100
    #: Delegate of the list view
    HEIGHT_BACKGROUND_SLIDER: int = 60
    #: Show the slider to resize the view or refresh the content
    GRID_COLUMN_WIDTH: int = 110
    #: Value that will smooth the slide that will scale the view
    GRID_ROW_HEIGHT: int = 120
    #: Width of the slider
    LIST_ROW_HEIGHT: int = 36
    #: Height of the slider
    CONTENT_ITEM_TYPE: Type[_ContentItem] = _ContentItem
    #: Width of the column of the grid view
    LIST_DELEGATE_TREE_VIEW: Type[_DelegateTreeView] = _DelegateTreeView
    #: Height of the column of the grid view
    ENABLE_ADD_ITEM: bool = False
    #: Class that will be used as an item
    SHOW_REFRESH_AND_SLIDER: bool = True
    #: Enable the "Add" item in the view
    SLIDER_SMOOTHER: int = 2

    """Instance"""

    def __init__(self, core: "ContentViewerCore"):
        """
        Init

        Args:
            core: the core to use
        """
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self._core = core

        self._model_subscription = self._core.subscribe_content_changed(self._on_content_changed)
        self._selection_subscription = self._core.subscribe_selection_changed(self._on_selection_changed)
        self._error_get_data_subscription = self._core.subscribe_error_get_data(self._on_error_get_data)

        self.__is_list_view_mode = self.LIST_VIEW_MODE

        self.__frame_grid = None
        self.__frame_list = None
        self.__label_error = None
        self.__tree_view = None
        self.__scroll_frame = None
        self.__content_grid = None
        self.__on_scroll_frame_mouse_clicked_task = None
        self.__content_items = None
        self.__content_data = None
        self.__slider = None
        self.__filter_content_title_value = None

        self.__block_list_selection = False  # noqa PLW0238

        self.__model_tree_view = _ModelTreeView()
        self.__delegate_tree_view = self.LIST_DELEGATE_TREE_VIEW()

        self._create_ui()

    def set_list_view_mode(self, value: bool):
        """
        Set the view as a list

        Args:
            value: show as a list or not
        """
        self.__is_list_view_mode = value

    def get_content_items(self) -> List[Type["BaseContentItem"]]:
        """Get all content items"""
        return self.__content_items

    def _block_list_selection(func):  # noqa N805
        def do(self, *args, **kwargs):  # noqa PLC0103
            self.__block_list_selection = True  # noqa PLW0212
            func(self, *args, **kwargs)  # noqa PLE1102
            self.__block_list_selection = False  # noqa PLW0212

        return do

    @property
    def default_attr(self) -> Dict[str, Any]:
        """Default attribute with default values created in the class that will be destroyed during closing"""
        return {"_core": None}

    @_block_list_selection
    def _on_selection_changed(self, contents_data: List[Type["BaseContentData"]]):
        """Called when the selection of an item content is changed"""
        if self.__content_items is None:
            return
        to_list_select = []
        for content_item in self.__content_items:
            value = content_item.content_data in contents_data
            content_item.set_selected(value)
            if value:
                to_list_select.append(content_item)

        if self.__is_list_view_mode:
            self.__tree_view.selection = to_list_select

    def _on_error_get_data(self, message):
        """Called when there was an error getting data"""
        if self.__label_error is None:
            return
        if message is not None:
            self.__label_error.text = message
        self.__label_error.visible = True

    def _on_content_changed(self, content_data: List[Type["BaseContentData"]]):
        """Called when the content is changed"""

        if self.__frame_grid is None:
            return

        self.__label_error.visible = False

        self.__content_items = []
        self.__content_data = content_data
        self.__frame_list.visible = self.__is_list_view_mode
        self.__frame_grid.visible = not self.__frame_list.visible

        if self.__is_list_view_mode:
            with self.__frame_list:
                size = self.GRID_ROW_HEIGHT / (self.GRID_ROW_HEIGHT / self.LIST_ROW_HEIGHT)
                if self.__tree_view is None:
                    with ui.ScrollingFrame(name="ContentViewerWidgetItemList"):
                        self.__tree_view = ui.TreeView(
                            self.__model_tree_view,
                            delegate=self.__delegate_tree_view,
                            root_visible=False,
                            header_visible=False,
                            columns_resizable=True,
                            name="ContentViewerWidgetItemList",
                            column_widths=[ui.Pixel(size)],
                        )
                if self.ENABLE_ADD_ITEM:
                    self.__content_items.insert(
                        0,
                        _ContentItemAdd(
                            _ContentDataAdd(title="Add new"),
                            self._core,
                            self.GRID_COLUMN_WIDTH,
                            size,
                            None,
                            list_mode=self.__is_list_view_mode,
                        ),
                    )
                for data in content_data:
                    if not self._filter_fn(self.__filter_content_title_value, data):
                        continue
                    self.__content_items.append(
                        self.CONTENT_ITEM_TYPE(
                            data, self._core, self.GRID_COLUMN_WIDTH, size, None, list_mode=self.__is_list_view_mode
                        )
                    )
                self.__model_tree_view.refresh(self.__content_items)
        else:
            self.__frame_grid.clear()
            with self.__frame_grid:
                self.__content_grid = ui.VGrid(column_width=self.GRID_COLUMN_WIDTH, row_height=self.GRID_ROW_HEIGHT)
                with self.__content_grid:
                    if self.ENABLE_ADD_ITEM:
                        frame = ui.Frame()
                        self.__content_items.insert(
                            0,
                            _ContentItemAdd(
                                _ContentDataAdd(title="Add new"),
                                self._core,
                                self.GRID_COLUMN_WIDTH,
                                self.GRID_ROW_HEIGHT,
                                frame,
                            ),
                        )
                    for data in content_data:
                        if not self._filter_fn(self.__filter_content_title_value, data):
                            continue
                        frame = ui.Frame()
                        self.__content_items.append(
                            self.CONTENT_ITEM_TYPE(
                                data,
                                self._core,
                                self.GRID_COLUMN_WIDTH,
                                self.GRID_ROW_HEIGHT,
                                frame,
                                list_mode=self.__is_list_view_mode,
                            )
                        )
        self._resize_grid()

    def _create_ui(self):
        """Create the main UI"""
        with ui.Frame():
            with ui.ZStack(content_clipping=True):
                self.__scroll_frame = ui.ScrollingFrame(
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    mouse_pressed_fn=lambda x, y, b, m: self._on_scroll_frame_mouse_clicked(),
                )
                with self.__scroll_frame:
                    with ui.ZStack():
                        ui.Rectangle(name="ContentViewerWidgetBackground")
                        self.__frame_grid = ui.Frame(visible=not self.__is_list_view_mode)
                        self.__frame_list = ui.Frame(visible=self.__is_list_view_mode)
                # slider for change the size of the grid
                if self.SHOW_REFRESH_AND_SLIDER:
                    with ui.Frame(separate_window=True):
                        with ui.HStack():
                            ui.Spacer(width=ui.Fraction(40))
                            with ui.VStack(width=ui.Pixel(self.WIDTH_BACKGROUND_SLIDER)):
                                ui.Spacer(height=ui.Fraction(40))
                                with ui.ZStack(height=ui.Pixel(self.HEIGHT_BACKGROUND_SLIDER)):
                                    ui.Rectangle(name="ContentViewerWidgetSlider")
                                    with ui.VStack():
                                        ui.Spacer(height=ui.Fraction(1))
                                        with ui.HStack(height=ui.Fraction(10), content_clipping=True):
                                            ui.Spacer(width=7)
                                            ui.Label("Refresh", name="ContentViewerWidgetRefresh")
                                            ui.Image(
                                                "",
                                                name="ContentViewerWidgetRefresh",
                                                mouse_pressed_fn=lambda x, y, b, m: self._on_refresh_clicked(),
                                            )
                                        with ui.HStack(height=ui.Fraction(10), content_clipping=True):
                                            ui.Spacer(width=ui.Fraction(1))
                                            self.__slider = ui.IntSlider(
                                                min=0,
                                                max=200,
                                                alignment=ui.Alignment.CENTER,
                                                width=ui.Pixel(self.WIDTH_BACKGROUND_SLIDER - 10),
                                            )
                                            self.__slider.model.set_value(100)
                                            self.__slider.model.add_value_changed_fn(lambda m: self._resize_grid())
                                            ui.Spacer(width=ui.Fraction(1))
                                        ui.Spacer(height=ui.Fraction(1))
                                ui.Spacer(height=ui.Fraction(2))
                            ui.Spacer(width=ui.Fraction(1))
                with ui.Frame(separate_window=True):
                    self.__label_error = ui.Label(
                        "Error", name="ContentViewerWidgetError", alignment=ui.Alignment.CENTER, visible=False
                    )

    def _on_refresh_clicked(self):
        """Called when the ui is refreshed"""
        self._core.refresh_content()

    def set_filter_content_title_value(self, text: Optional[str]):
        """
        Set the value text.

        Args:
            text: This text will be used as an arg for the _filter_fn() method
        """
        self.__filter_content_title_value = text

    def filter_content(self, text: Optional[str]):
        """
        Filter the content with this text and refresh the view

        Args:
            text: This text will be used as an arg for the _filter_fn() method
        """
        self.__filter_content_title_value = text
        self._on_content_changed(self.__content_data)

    def _filter_fn(self, text: Optional[str], data: Type["BaseContentData"]) -> bool:
        """
        Default filter function

        Args:
            text: the input text that will be used to filter
            data: the item

        Returns:
            If the item should be shown or not
        """
        if text is not None and text.lower() not in data.title.lower():
            return False
        return True

    def _on_scroll_frame_mouse_clicked(self):
        """Called when we click in the UI but not on a content"""
        if self.__on_scroll_frame_mouse_clicked_task:
            self.__on_scroll_frame_mouse_clicked_task.cancel()
        self.__on_scroll_frame_mouse_clicked_task = asyncio.ensure_future(
            self.__deferred_on_scroll_frame_mouse_clicked()
        )

    @omni.usd.handle_exception
    async def __deferred_on_scroll_frame_mouse_clicked(self):
        await omni.kit.app.get_app().next_update_async()
        if self._core is None:
            return
        if self._core.is_selection_blocked():
            return
        if not self._core.was_item_clicked():
            self._core.set_selection(None)
        self._core.set_item_was_clicked(False)

    def _resize_grid(self):
        """Called when the grid is resized"""
        if (not self.__content_data and not self.ENABLE_ADD_ITEM) or not self.SHOW_REFRESH_AND_SLIDER:
            return
        value = self.__slider.model.as_int
        if self.__is_list_view_mode:
            self.__tree_view.column_widths = [ui.Pixel(self.LIST_ROW_HEIGHT * (value / 100))]
        else:
            final_value = 100 - ((100 - value) / self.SLIDER_SMOOTHER)
            self.__content_grid.column_width = self.GRID_COLUMN_WIDTH * (final_value / 100)
            self.__content_grid.row_height = self.GRID_ROW_HEIGHT * (final_value / 100)
        for content_item in self.__content_items:
            content_item.on_resized_grid(value)

    def destroy(self):
        _reset_default_attrs(self)
        if self.__content_items:
            for content_item in self.__content_items:
                content_item.destroy()
        self.__frame_grid = None
        self.__frame_list = None
        self.__model_tree_view.destroy()
        self.__model_tree_view = None
        self.__delegate_tree_view.destroy()
        self.__delegate_tree_view = None
        self.__label_error = None
        self.__tree_view = None
        self.__slider = None
        self.__scroll_frame = None
        self.__on_scroll_frame_mouse_clicked_task = None
        self.__content_grid = None
        self.__content_items = None
        self.__content_data = None

        self.__filter_content_title_value = None
        instance = super()
        if instance:
            del instance

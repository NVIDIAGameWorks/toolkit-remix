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
import functools
import threading
from typing import Any, List, Optional

import omni.kit.app
from omni import ui, usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.hover import hover_helper as _hover_helper

from .selection_history_tree.delegate import SelectionHistoryDelegate
from .selection_history_tree.item_model import SelectionHistoryItem
from .selection_history_tree.model import SelectionHistoryModel


class SelectionHistoryWidget:
    _DEFAULT_TREE_FRAME_HEIGHT = 100
    _SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    _main_loop = asyncio.get_event_loop()

    def __init__(
        self, model: Optional[SelectionHistoryModel] = None, delegate: Optional[SelectionHistoryDelegate] = None
    ):
        self._default_attr = {
            "_model": None,
            "_delegate": None,
            "_sub_on_active_items_changed": None,
            "_tree_view_history": None,
            "_refresh_task": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__update_default_style()
        self.__loop = self._main_loop
        self.__block_active_items = False
        self.__item_changed_task = None
        self._model = model or SelectionHistoryModel()
        self._delegate = delegate or SelectionHistoryDelegate()

        # Model event
        self._sub_on_active_items_changed = self._model.subscribe_on_active_items_changed(self._on_active_items_changed)
        self._sub_on_item_changed = self._model.subscribe_item_changed_fn(self._on_item_changed)

        self.__create_ui()

    def __update_default_style(self):
        """
        We need default color value for the gradient
        """
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
                "background_gradient_color": 0xFF453F2B,  # hardened _BLUE_HOVERED over _GREY_50
            }
        if "ImageWithProvider::SelectionGradient_selected" not in current_dict:
            current_dict["ImageWithProvider::SelectionGradient_selected"] = {
                "background_color": 0x00836C1D,
                "background_gradient_color": 0xFF836C1D,  # hardened _BLUE_SELECTED over _GREY_50
            }
        if "ImageWithProvider::SelectionGradient_secondary" not in current_dict:
            current_dict["ImageWithProvider::SelectionGradient_secondary"] = {
                "background_color": 0x00594E26,
                "background_gradient_color": 0xFF594E26,  # hardened _BLUE_SEMI_SELECTED over _GREY_50
            }
        style.default = current_dict

    def show(self, value: bool):
        """
        Let the widget know if it's visible or not. Keep it for the pattern.
        """
        pass

    def __create_ui(self):
        with ui.VStack():
            self._manipulator_frame = ui.Frame(visible=True)
            with self._manipulator_frame:
                size_manipulator_height = 4
                with ui.ZStack():
                    with ui.VStack():
                        self._tree_scroll_frame = ui.ScrollingFrame(
                            name="PropertiesPaneSection",
                            height=ui.Pixel(self._DEFAULT_TREE_FRAME_HEIGHT),
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        )
                        with self._tree_scroll_frame:
                            self._tree_view_history = ui.TreeView(
                                self._model,
                                delegate=self._delegate,
                                header_visible=False,
                                column_widths=[ui.Fraction(1)],
                                style_type_name_override="TreeView.Selection",
                                identifier="main_tree",
                            )
                            self._tree_view_history.set_selection_changed_fn(self._on_selection_changed)
                    with ui.VStack():
                        ui.Spacer()
                        self._manip_frame = ui.Frame(height=size_manipulator_height)
                        with self._manip_frame:
                            self._slide_placer = ui.Placer(
                                draggable=True,
                                height=size_manipulator_height,
                                offset_x_changed_fn=self._on_slide_x_changed,
                                offset_y_changed_fn=functools.partial(
                                    self._on_slide_y_changed,
                                    size_manipulator_height,
                                ),
                            )
                            # Body
                            with self._slide_placer:
                                self._slider_manip = ui.Rectangle(
                                    width=ui.Percent(self._SIZE_PERCENT_MANIPULATOR_WIDTH),
                                    name="PropertiesPaneSectionTreeManipulator",
                                )
                                _hover_helper(self._slider_manip)

    def _on_slide_x_changed(self, x):
        size_manip = self._manip_frame.computed_width / 100 * self._SIZE_PERCENT_MANIPULATOR_WIDTH
        if x.value < 0:
            self._slide_placer.offset_x = 0
        elif x.value > self._manip_frame.computed_width - size_manip:
            self._slide_placer.offset_x = self._manip_frame.computed_width - size_manip

        item_path_scroll_frames = self._delegate.get_path_scroll_frames()
        if item_path_scroll_frames:
            max_frame_scroll_x = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
            value = (max_frame_scroll_x / (self._manip_frame.computed_width - size_manip)) * x
            for frame in item_path_scroll_frames.values():
                frame.scroll_x = value

    def _on_slide_y_changed(self, size_manip, y):
        if y.value < 0:
            self._slide_placer.offset_y = 0
        self._tree_scroll_frame.height = ui.Pixel(self._DEFAULT_TREE_FRAME_HEIGHT + y.value)

    def _block_active_items(func):  # noqa N805
        def do(self, *args, **kwargs):  # noqa PLC0103
            self.__block_active_items = True  # noqa PLW0212
            func(self, *args, **kwargs)  # noqa PLE1102

        return do

    @_block_active_items
    def _on_selection_changed(self, items: List[SelectionHistoryItem]):
        self._model.set_active_items(items)
        self._delegate.on_item_selected(items, self._model.get_item_children(None))

    def _on_item_changed(self, _model, _item):
        self._delegate.reset()

        if self.__item_changed_task:
            self.__item_changed_task.cancel()
        if threading.current_thread() is threading.main_thread():
            self.__item_changed_task = asyncio.ensure_future(self.__deferred_on_item_changed())
        else:
            self.__item_changed_task = asyncio.run_coroutine_threadsafe(self.__deferred_on_item_changed(), self.__loop)

    @usd.handle_exception
    async def __deferred_on_item_changed(self):
        await omni.kit.app.get_app().next_update_async()
        if not self._tree_view_history:
            return
        self._tree_view_history.dirty_widgets()
        self.__refresh_delegate_gradients()

    def __refresh_delegate_gradients(self):
        for item in self._tree_view_history.selection if self._tree_view_history is not None else []:
            if not self._delegate:
                return
            self._delegate.refresh_gradient_color(item, deferred=False)

    def _on_active_items_changed(self, active_items: List[Any]):
        if self.__block_active_items:
            self.__block_active_items = False
            return
        selection_items = []
        selection_history_items = self._model.get_item_children()
        for active_item in active_items:
            for item in selection_history_items:
                if item.data != active_item.data:
                    continue
                selection_items.append(item)
        items = [selection_items[0]] if selection_items else []
        self._tree_view_history.selection = items

    def destroy(self):
        if self.__item_changed_task:
            self.__item_changed_task.cancel()
        _reset_default_attrs(self)

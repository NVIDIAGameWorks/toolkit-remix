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

from functools import partial
from typing import TYPE_CHECKING

from omni import ui, usd
from omni.flux.custom_tags.core import CustomTagsCore
from omni.flux.custom_tags.window import EditCustomTagsWindow
from pydantic import Field, PrivateAttr

from .base import StageManagerUSDWidgetPlugin as _StageManagerUSDWidgetPlugin

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class CustomTagsWidgetPlugin(_StageManagerUSDWidgetPlugin):
    display_name: str = Field(default="Tags", exclude=True)
    tooltip: str = Field(default="", exclude=True)

    _padding: int = PrivateAttr(default=4)
    _row_height: int = PrivateAttr(default=20)

    _frame: ui.Frame | None = PrivateAttr(default=None)

    _arrow_left: ui.Image | None = PrivateAttr(default=None)
    _arrow_right: ui.Image | None = PrivateAttr(default=None)
    _scrolling_frame: ui.ScrollingFrame | None = PrivateAttr(default=None)
    _tags_stack: ui.HStack | None = PrivateAttr(default=None)

    _tag_widget_index: dict[int, int] = PrivateAttr(default={})
    _tag_widgets: dict[int, ui.Widget] = PrivateAttr(default={})

    _edit_window: EditCustomTagsWindow | None = PrivateAttr(default=None)

    def build_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        if not item.data:
            return
        self._frame = ui.Frame(build_fn=partial(self._build_frame, model, item))

    def build_overview_ui(self, model: "_StageManagerTreeModel"):
        pass

    def _build_frame(self, model, item):
        core = CustomTagsCore(context_name=self._context_name)

        self._tag_widgets[id(item)] = []
        self._tag_widget_index[id(item)] = 0

        with ui.HStack(computed_content_size_changed_fn=self._update_arrow_visibility):
            with ui.VStack(width=0):
                ui.Spacer(width=0)
                ui.Image(
                    "",
                    name="EditTag",
                    tooltip="Edit the Tags associated with the selected Prim(s)",
                    width=ui.Pixel(20),
                    height=ui.Pixel(20),
                    mouse_pressed_fn=partial(self._open_edit_window, model, item),
                )
                ui.Spacer(width=0)
            ui.Spacer(width=ui.Pixel(self._padding))
            self._arrow_left = ui.Image(
                "", width=ui.Pixel(20), mouse_pressed_fn=partial(self._scroll_tags, False, item)
            )
            self._scrolling_frame = ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                mouse_pressed_fn=lambda x, y, b, m: self._item_clicked(b, True, model, item),
                mouse_double_clicked_fn=partial(self._open_edit_window, model, item),
            )
            with self._scrolling_frame:
                self._tags_stack = ui.HStack(spacing=ui.Pixel(self._padding))
                with self._tags_stack:
                    for tag in sorted(core.get_prim_tags(item.data), key=core.get_tag_name):
                        with ui.VStack(width=0):
                            ui.Spacer(width=0)
                            with ui.ZStack(width=0, height=ui.Pixel(self._row_height)):
                                ui.Rectangle(name="CustomTag")
                                with ui.HStack(
                                    spacing=ui.Pixel(self._padding), width=0, height=0, alignment=ui.Alignment.CENTER
                                ):
                                    ui.Spacer(width=0, height=0)
                                    self._tag_widgets[id(item)].append(
                                        ui.Label(core.get_tag_name(tag), width=0, height=ui.Pixel(self._row_height))
                                    )
                                    ui.Spacer(width=0, height=0)
                            ui.Spacer(width=0)
            self._arrow_right = ui.Image(
                "", width=ui.Pixel(20), mouse_pressed_fn=partial(self._scroll_tags, True, item)
            )

    def _update_arrow_visibility(self):
        """
        Update the visibility of the Left and Right arrows based on the necessity of the buttons.
        """
        visible = self._scrolling_frame.computed_width < self._tags_stack.computed_width
        self._arrow_left.name = "ArrowLeft" if visible else ""
        self._arrow_right.name = "ArrowRight" if visible else ""
        self._arrow_left.tooltip = "Scroll the tag list to the left" if visible else ""
        self._arrow_right.tooltip = "Scroll the tag list to the right" if visible else ""

    def _scroll_tags(
        self,
        direction: bool,
        item: "_StageManagerTreeItem",
        x: int,
        y: int,
        b: int,
        m: int,
    ):
        """
        Scroll the tags scrolling frame by a set amount (`scroll_speed`)

        Args:
             direction: True = Right, False = Left
             item: The item that was built
             x: The clicked location's x component
             y: The clicked location's y component
             b: The button used to double-click
             m: Modified used while clicking
        """
        if b != 0 or id(item) not in self._tag_widgets or id(item) not in self._tag_widget_index:
            return

        widgets = self._tag_widgets[id(item)]
        index = self._tag_widget_index[id(item)]

        if not widgets:
            return

        # Focus the next widget & clamp the index
        index += 1 if direction else -1
        index = min(max(0, index), len(widgets) - 1)

        self._tag_widget_index[id(item)] = index

        # If scrolling right, move the next item to the left of the scroll bar,
        # otherwise move the previous item to the right of the scroll bar.
        # This ensures clearer movement on each click of the buttons.
        widgets[index].scroll_here_x(0.25 if direction else 0.75)

    def _open_edit_window(
        self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", x: int, y: int, b: int, m: int
    ):
        """
        Open the Edit Tags window using the currently selected items

        Args:
             model: The tree model
             item: The item that was built
             x: The clicked location's x component
             y: The clicked location's y component
             b: The button used to double-click
             m: Modifier used while clicking
        """
        if b != 0:
            return

        self._item_clicked(b, True, model, item)

        context = usd.get_context(self._context_name)
        selected_paths = context.get_selection().get_selected_prim_paths()

        self._edit_window = EditCustomTagsWindow(selected_paths, context_name=self._context_name)

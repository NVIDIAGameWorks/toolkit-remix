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

__all__ = ["RecentProjectDelegate"]

from functools import partial
from typing import Any
from collections.abc import Callable

import omni.kit.clipboard
from omni import ui
from omni.flux.utils.common import Event, EventSubscription
from omni.flux.utils.widget.tree_widget import TreeDelegateBase

from .items import RecentProjectItem
from .model import TREE_COLUMNS, RecentProjectModel


class RecentProjectDelegate(TreeDelegateBase):
    _ROW_HEIGHT = ui.Pixel(64)
    _ROW_PADDING = ui.Pixel(16)
    _THUMBNAIL_SIZE = ui.Pixel(48)
    _MENU_ICON_SIZE = ui.Pixel(16)

    def __init__(self):
        super().__init__()

        self._context_menu = None

        self.__on_item_open_project = Event()
        self.__on_item_show_in_explorer = Event()
        self.__on_item_remove_from_recent = Event()

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_context_menu": None,
            }
        )
        return default_attr

    def subscribe_item_open_project(self, callback: Callable[[str], Any]) -> EventSubscription:
        """
        Subscribe to the event triggered when the item should open a project
        """
        return EventSubscription(self.__on_item_open_project, callback)

    def subscribe_item_show_in_explorer(self, callback: Callable[[], Any]) -> EventSubscription:
        """
        Subscribe to the event triggered when the item should be opened in the file explorer
        """
        return EventSubscription(self.__on_item_show_in_explorer, callback)

    def subscribe_item_remove_from_recent(self, callback: Callable[[], Any]) -> EventSubscription:
        """
        Subscribe to the event triggered when the item should be removed from the recent projects list
        """
        return EventSubscription(self.__on_item_remove_from_recent, callback)

    def build_branch(
        self, model: RecentProjectModel, item: RecentProjectItem, column_id: int, level: int, expanded: bool
    ):
        # Do nothing. Leave this here
        return

    def _build_widget(
        self, model: RecentProjectModel, item: RecentProjectItem, column_id: int, level: int, expanded: bool
    ):
        if item is None:
            return

        with ui.ZStack():
            tooltip = ""
            if not item.exists:
                tooltip = "The project does not exist at the given location"

                # Add a red background when the project is invalid
                ui.Rectangle(name="HomeInvalidProject")

            with ui.VStack(
                height=self._ROW_HEIGHT,
                tooltip=tooltip,
                mouse_double_clicked_fn=partial(self._on_item_double_clicked, item),
            ):
                # Thumbnail
                if column_id == 0:
                    url = item.thumbnail or ""
                    name = "" if url else "RemixProject"

                    with ui.HStack():
                        ui.Spacer()
                        with ui.VStack(width=0):
                            ui.Spacer()
                            ui.Image(url, name=name, width=self._THUMBNAIL_SIZE, height=self._THUMBNAIL_SIZE)
                            ui.Spacer()
                        ui.Spacer()
                # Project Name and Path
                if column_id == 1:
                    with ui.HStack():
                        ui.Spacer(width=self._ROW_PADDING)
                        with ui.VStack(spacing=ui.Pixel(4)):
                            ui.Spacer()
                            ui.Label(item.name, name="HomeEmphasizedLabel", height=0)
                            ui.Label(item.path or "Unknown Project Path", name="HomeDiscreteLabel", height=0)
                            ui.Spacer()
                # Project Game
                if column_id == 2:
                    with ui.HStack():
                        ui.Spacer(width=self._ROW_PADDING)
                        ui.Label(item.game or "Unknown Game")
                # Project Version
                if column_id == 3:
                    with ui.HStack():
                        ui.Spacer(width=self._ROW_PADDING)
                        ui.Label(item.version or "0.0.0")
                # Project Last Modified Date
                if column_id == 4:
                    with ui.HStack():
                        ui.Spacer(width=self._ROW_PADDING)
                        ui.Label(item.last_modified or "Unknown Date")
                # Context Menu Button
                if column_id == 5:
                    with ui.HStack():
                        ui.Spacer()
                        with ui.VStack():
                            ui.Spacer()
                            ui.Image(
                                "",
                                name="More",
                                mouse_pressed_fn=partial(self._on_item_show_menu, model, item),
                                width=self._MENU_ICON_SIZE,
                                height=self._MENU_ICON_SIZE,
                            )
                            ui.Spacer()
                        ui.Spacer()
                # Row Separator
                ui.Rectangle(name="WizardSeparator", height=ui.Pixel(2))

    def _build_header(self, column_id: int):
        with ui.HStack():
            if column_id > 0:
                # Column Separator
                ui.Rectangle(name="WizardSeparator", width=ui.Pixel(1))
            # Add a bit of padding
            ui.Spacer(width=self._ROW_PADDING)
            ui.Label(TREE_COLUMNS.get(column_id), name="HomeEmphasizedLabel", height=self._ROW_HEIGHT)

    def _context_menu_shown(self, model: RecentProjectModel, item: RecentProjectItem):
        self._context_menu = ui.Menu("Context Menu")
        with self._context_menu:
            ui.MenuItem(
                "Open Project",
                triggered_fn=lambda: self.__on_item_open_project(item.path),
                enabled=item.exists,
            )
            ui.Separator()
            ui.MenuItem(
                "Copy Project Path",
                triggered_fn=lambda: omni.kit.clipboard.copy(item.path),
            )
            ui.MenuItem(
                "Show In Explorer",
                triggered_fn=self.__on_item_show_in_explorer,
                enabled=item.exists,
            )
            ui.Separator()
            ui.MenuItem(
                "Remove from Recent Projects",
                triggered_fn=self.__on_item_remove_from_recent,
            )
        self._context_menu.show()

        super()._context_menu_shown(model, item)

    def _on_item_show_menu(
        self, model: RecentProjectModel, item: RecentProjectItem, x: float, y: float, b: int, m: int
    ):
        """
        A callback to be executed when the context menu button is clicked.

        Args:
            model: The model of the tree.
            item: The item that was clicked.
            x: The x coordinate of the mouse click.
            y: The y coordinate of the mouse click.
            b: The mouse button that was clicked.
            m: The modifier keys that were pressed.
        """
        if b != 0:
            return
        self._item_clicked(1, True, model, item)

    def _on_item_double_clicked(self, item: RecentProjectItem, x: float, y: float, b: int, m: int):
        """
        A callback to be executed when the item is double clicked.

        Args:
            item: The item that was clicked.
            x: The x coordinate of the mouse click.
            y: The y coordinate of the mouse click.
            b: The mouse button that was clicked.
            m: The modifier keys that were pressed.
        """
        if b != 0:
            return
        self.__on_item_open_project(item.path)

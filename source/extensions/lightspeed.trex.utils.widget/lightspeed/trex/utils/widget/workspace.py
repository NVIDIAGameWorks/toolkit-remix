"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.kit
from omni import ui
from omni.kit.menu import utils as _menu_utils
from omni.kit.menu.utils import build_submenu_dict


class WorkspaceWidget(abc.ABC):
    """
    Interface for workspace window content widgets.
    All widgets used in WorkspaceWindowBase should implement this interface.
    """

    @abc.abstractmethod
    def show(self, visible: bool):
        """
        Enable/disable the widget and its subscriptions.

        Args:
            visible: True to enable updates and subscriptions, False to pause them.
        """
        pass

    @abc.abstractmethod
    def destroy(self):
        """
        Clean up all resources, subscriptions, and references.
        Called when the window is being permanently closed.
        """
        pass


class WorkspaceWindowBase(abc.ABC):
    """Base class with common functionalities for all workspace windows."""

    def __init__(
        self,
        usd_context_name: str | None = None,
        show_dock_tab_bars: bool = True,
    ):
        """
        Initializes WorkspaceWindow class.

        Args:
            usd_context_name: Name of the USD context to use.
            show_dock_tab_bars: Show the docking tab bars with window title, close button, etc.
        """

        self._window: ui.Window | ui.ToolBar | None = None

        # The actual widget contained within the Window.frame
        self._content: WorkspaceWidget | None = None

        # The "Window > Window Title" list of MenuItemDescription.
        self._menu_dict: dict[str, list[_menu_utils.MenuItemDescription]] | None = None
        self._usd_context_name = usd_context_name

        # Whether to show the tab bars in the window.
        self._show_dock_tab_bars = show_dock_tab_bars

        self.__sub_app_ready = None  # noqa PLW0238

    @property
    @abc.abstractmethod
    def title(self) -> str:
        """The Window title, also used as ID in Kit Workspace"""
        return ""

    @property
    @abc.abstractmethod
    def flags(self) -> int:
        """
        The Window flags integer mask.
        Check omni.ui.WINDOW_FLAGS_*
        """
        return ui.WINDOW_FLAGS_NONE

    def menu_path(self) -> str | None:
        """
        The menu path for this window in the Window menu. None means no menu entry.
        """
        return self.title

    def _create_window(self) -> ui.Window | ui.ToolBar:
        """
        Overridable method to create a ui.Window or ui.ToolBar instance.
        Default implementation configures a window with the title, flags, and padding.
        """
        window = ui.Window(self.title, visible=False, flags=self.flags)
        return window

    def create_window(self, width: int | None = None, height: int | None = None):
        """Creates the ui.Window instance and sets up the "Window" menu item."""
        if self._window:
            return

        self._window = self._create_window()

        if width is not None:
            self._window.width = width
        if height is not None:
            self._window.height = height

        self._window.padding_x = 0
        self._window.padding_y = 0

        self._window.set_visibility_changed_fn(self._on_visibility_changed)
        self._window.set_width_changed_fn(self._on_window_resized)
        self._window.set_height_changed_fn(self._on_window_resized)
        self._window.set_docked_changed_fn(self._on_dock_changed)

        if self.menu_path():
            # Editor Menu API must be used when the app is ready.
            def add_window_menu_item(*args):
                self.update_menu_item(False)
                self.__sub_app_ready = None  # noqa PLW0238

            startup_event_stream = omni.kit.app.get_app().get_startup_event_stream()
            self.__sub_app_ready = startup_event_stream.create_subscription_to_pop_by_type(  # noqa PLW0238
                omni.kit.app.EVENT_APP_READY, add_window_menu_item, name="Window Menu Item - App Ready"
            )

    def get_window(self) -> ui.Window | ui.ToolBar:
        if not self._window:
            raise RuntimeError("Window not created yet.")
        return self._window

    def show_window_fn(self, show: bool = True):
        if not self._window or show == self._window.visible:
            return

        self._window.visible = show

        if show:
            self._update_ui()
        else:
            if self._content:
                self._content.show(False)

    def cleanup(self):
        """
        Clean up all window resources.
        Properly destroys the content widget before cleanup.
        """
        # Clean up app ready subscription
        if self.__sub_app_ready:
            self.__sub_app_ready = None

        if self._content:
            self._content.destroy()
        self._content = None

        if self._window:
            self._window.destroy()
        self._window = None

        if self._menu_dict:
            for group in self._menu_dict:
                _menu_utils.remove_menu_items(self._menu_dict[group], group)
        self._menu_dict = None

    def update_menu_item(self, visible: bool):
        menu_path = self.menu_path()
        if not menu_path:
            return

        def toggle_callback(*args):
            is_visible = self._window and self._window.visible
            ui.Workspace.show_window(self.title, not is_visible)

        if not self._menu_dict:
            # path, item_name = menu_path.rsplit("/", 1) if "/" in menu_path else ("", menu_path)
            menus = [
                _menu_utils.MenuItemDescription(
                    name=f"Window/{menu_path}",
                    ticked=visible,
                    ticked_fn=lambda: self._window.visible,
                    onclick_fn=toggle_callback,
                )
            ]
            self._menu_dict = build_submenu_dict(menus)
            for group in self._menu_dict:
                _menu_utils.add_menu_items(self._menu_dict[group], group)

        _menu_utils.refresh_menu_items("Window")

    @abc.abstractmethod
    def _create_window_ui(self) -> WorkspaceWidget:
        """
        Populates the window.frame with this method and returns the widget.

        Returns:
            A widget that implements the WorkspaceWidget interface.
        """
        pass

    def _enforce_tab_bar_settings(self):
        if self._window:
            self._window.dock_tab_bar_enabled = self._show_dock_tab_bars
            self._window.dock_tab_bar_visible = self._show_dock_tab_bars

    def _update_ui(self):
        """
        Called when the window is shown, this method also creates the UI at first time coming from a hidden state.
        Use this to refresh UI widgets when set visible, but call super first.
        """
        if not self._content:
            with self._window.frame:
                self._content = self._create_window_ui()

        # Enable the widget when showing
        if self._content:
            self._content.show(True)

    def _on_window_resized(self, value: float):
        if self._window and self._window.docked:

            async def _enforce_after_resize():
                await omni.kit.app.get_app().next_update_async()
                self._enforce_tab_bar_settings()

            asyncio.ensure_future(_enforce_after_resize())

    def _on_visibility_changed(self, visible: bool):
        if visible:
            self._update_ui()
        else:
            if self._content:
                self._content.show(False)
        self.update_menu_item(visible)

    def _on_dock_changed(self, docked: bool):
        async def _refresh_tab_bars():
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            self._enforce_tab_bar_settings()

        asyncio.ensure_future(_refresh_tab_bars())

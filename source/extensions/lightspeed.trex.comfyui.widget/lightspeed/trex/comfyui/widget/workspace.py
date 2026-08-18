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

__all__ = ["ComfySetupWorkspace", "WorkflowSetupWorkspace"]

import asyncio

import omni.kit.app
from lightspeed.common.constants import WindowNames
from lightspeed.trex.comfyui.core.events import subscribe_comfyui_event
from lightspeed.trex.utils.widget.quicklayout import subscribe_layout_loaded
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase
from omni import ui

from .setup.widget import ComfySetupAdvancedWidget
from .workflow.widget import WorkflowSetupWidget


class ComfySetupWorkspace(WorkspaceWindowBase):
    """Host the AI Tools ComfyUI instance setup workspace.

    The window fits the height that the panel needs, so every connection state fits: a long message wraps in
    the banner, and the panel then needs more height. The panel fills a window that is taller than that, and
    keeps the Connect button at the bottom. The window fits again on every layout load, on every resize of
    the application window, and whenever the panel needs another height. It stops fitting once the user drags
    the splitter that it shares with the workflow window.
    """

    # Size the window opens at while it floats. A dock gives it the size of its column instead.
    _DEFAULT_WIDTH = 512
    _DEFAULT_HEIGHT = 256
    # Height of the dock tab row above the window. A dock node holds this row plus the window content.
    _DOCK_TAB_HEIGHT = 24

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the workspace, and follow layout loads and connection states.

        A layout load replaces the geometry of every window, but it only shows the windows that are hidden.
        A visible panel gets no visibility change, so it listens for the load itself. A connection state
        rebuilds the banner of the panel, which is the only row that changes height.

        Args:
            args: Positional arguments of the workspace base class.
            kwargs: Keyword arguments of the workspace base class.
        """
        super().__init__(*args, **kwargs)
        self._resized_by_user = False
        self._app_height = 0.0
        self._fit_height = 0.0
        self._fit_task: asyncio.Task | None = None
        self._layout_sub = subscribe_layout_loaded(self._fit_after_layout)
        self._state_sub = subscribe_comfyui_event(self._usd_context_name, self._fit_after_state)

    def cleanup(self) -> None:
        """Release the subscriptions and the pending fit, then clean up the window."""
        self._layout_sub = None
        self._state_sub = None
        self._cancel_fit()
        super().cleanup()

    def set_context_name(self, context_name: str) -> None:
        """Rebuild setup content when routing the window to another context.

        Args:
            context_name: USD context that the rebuilt setup widget should control.
        """
        if context_name == self._usd_context_name:
            return
        if self._content:
            self._content.destroy()
            self._content = None
        if self._window:
            self._window.frame.clear()
        self._usd_context_name = context_name
        self._state_sub = subscribe_comfyui_event(context_name, self._fit_after_state)
        if self._window and self._window.visible:
            self._update_ui()

    @property
    def title(self) -> str:
        """Return the setup workspace title.

        Returns:
            Registered ComfyUI setup window name.
        """
        return WindowNames.COMFYUI_SETUP.value

    def menu_path(self) -> str | None:
        """Return the setup workspace menu path.

        Returns:
            AI Tools menu path used to show the setup window.
        """
        return f"AI Tools/{self.title}"

    @property
    def flags(self) -> int:
        """Return window flags that delegate scrolling to child widgets.

        Returns:
            Combined no-scrollbar and no-mouse-scroll window flags.
        """
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window_ui(self):
        """Create the external-server setup widget.

        Returns:
            Setup widget bound to the workspace's current USD context.
        """
        return ComfySetupAdvancedWidget(context_name=self._usd_context_name)

    def _update_ui(self) -> None:
        """Build the setup content, and fit its dock the first time.

        A later build comes from a hide and show, or from a new USD context. Neither replaces the geometry of
        the window, so a resize by the user survives both.
        """
        super()._update_ui()
        if not self._app_height:
            self._fit()

    def _on_window_resized(self, value: float) -> None:
        """Fit the dock again after a resize, and stop after the user resizes the panel with the splitter.

        A dock scales the panel with the application window, so a new application height means the panel did
        not change on its own. A dock that keeps the height of the last fit did not move either: only its
        width changed, and the banner may wrap another number of lines in that width, so the panel fits
        again. Every other height comes from the splitter, and the window then keeps that height.

        The height of the panel cannot serve as the reference, because it changes with the message of the
        banner, and the height of the dock is on its way to the height of a fit while a fit waits.

        Args:
            value: New window size reported by the resize callback.
        """
        super()._on_window_resized(value)
        app_height = ui.Workspace.get_main_window_height()
        if app_height != self._app_height:
            self._app_height = app_height
            if not self._resized_by_user:
                self._fit()
        elif self._fit_task is None and self._fit_height and self._window is not None and self._window.docked:
            dock_height = ui.Workspace.get_dock_id_height(self._window.dock_id)
            if abs(dock_height - self._fit_height) > 1:
                self._resized_by_user = True
            elif not self._resized_by_user:
                self._fit()

    def _fit_after_state(self, _payload) -> None:
        """Fit the dock after a connection state rebuilds the banner, the only row that changes height.

        Args:
            _payload: ComfyUI event payload of the context of this window.
        """
        if not self._resized_by_user:
            self._fit()

    def _fit_after_layout(self) -> None:
        """Fit the dock after a layout load, which gives every window the geometry of the layout.

        The height of the last fit no longer describes the window, so it cannot show a resize by the user.
        The layout height arrives over the next frames, and it must not read as a drag of the splitter.
        """
        self._fit_height = 0.0
        self._fit()

    def _fit(self) -> None:
        """Ask for the height that fits the panel on the next frames.

        A fit request wins over an earlier resize by the user: a layout load replaced the geometry of the
        window, and the first build has no user height yet.
        """
        self._resized_by_user = False
        self._cancel_fit()
        self._fit_task = asyncio.ensure_future(self._fit_async())

    def _cancel_fit(self) -> None:
        """Drop the pending fit."""
        if self._fit_task is not None:
            self._fit_task.cancel()
            self._fit_task = None

    async def _fit_async(self) -> None:
        """Wait for the dock to hold the window, then give it the height that fits the panel.

        The first frame lets the dock take the window, and the second lets its geometry settle. A window
        that is hidden, floating, or that shares its dock node with another window keeps the height it has:
        a shared node holds two panels, so no single height fits it.

        These two frames are also the one moment that a drag of the splitter cannot stop: a dock scales with
        the application window over the same frames, and Kit reports both as a new dock height, so the
        resize callback cannot tell them apart while a fit waits. A drag that lands in that moment gets the
        height of the panel, and the next drag holds.
        """
        try:
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            window = self._window
            if window is None or not window.visible or not window.docked:
                return
            dock_id = window.dock_id
            if len(ui.Workspace.get_docked_windows(dock_id)) > 1:
                return
            if self._content is None:
                return
            height = self._content.needed_height + self._DOCK_TAB_HEIGHT
            if height <= self._DOCK_TAB_HEIGHT:
                return
            self._fit_height = height
            ui.Workspace.set_dock_id_height(dock_id, height)
            self._app_height = ui.Workspace.get_main_window_height()
        finally:
            # A cancelled fit reaches this line after the next fit started, and must keep that fit.
            if self._fit_task is asyncio.current_task():
                self._fit_task = None


class WorkflowSetupWorkspace(WorkspaceWindowBase):
    """Host the AI Tools ComfyUI workflow workspace."""

    def set_context_name(self, context_name: str) -> None:
        """Rebuild workflow content when routing the window to another context.

        Args:
            context_name: USD context that the rebuilt workflow widget should control.
        """
        if context_name == self._usd_context_name:
            return
        if self._content:
            self._content.destroy()
            self._content = None
        if self._window:
            self._window.frame.clear()
        self._usd_context_name = context_name
        if self._window and self._window.visible:
            self._update_ui()

    @property
    def title(self) -> str:
        """Return the workflow workspace title.

        Returns:
            Registered ComfyUI workflow window name.
        """
        return WindowNames.COMFYUI_WORKFLOW.value

    def menu_path(self) -> str | None:
        """Return the workflow workspace menu path.

        Returns:
            AI Tools menu path used to show the workflow window.
        """
        return f"AI Tools/{self.title}"

    @property
    def flags(self) -> int:
        """Return window flags that delegate scrolling to child widgets.

        Returns:
            Combined no-scrollbar and no-mouse-scroll window flags.
        """
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window_ui(self):
        """Create the context-aware workflow setup widget.

        Returns:
            Workflow widget bound to the workspace's current USD context.
        """
        return WorkflowSetupWidget(context_name=self._usd_context_name)

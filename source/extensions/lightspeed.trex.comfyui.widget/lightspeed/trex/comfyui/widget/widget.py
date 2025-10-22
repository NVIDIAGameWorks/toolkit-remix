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

__all__ = ["ComfyUIWidget"]

import asyncio
from functools import partial
from typing import Callable

from lightspeed.trex.comfyui.core import ComfyUIState, get_comfyui_instance
from lightspeed.trex.utils.widget import TrexMessageDialog
from omni import ui
from omni.flux.utils.widget.file_pickers import open_file_picker


class ComfyUIWidget:
    def __init__(self):
        self._core = get_comfyui_instance()

        self._state_changed_subscription = self._core.subscribe_state_changed(self._on_state_changed)

        self._async_tasks = {}

        self._window = None
        self._state_label = None
        self._install_button = None
        self._locate_button = None
        self._uninstall_button = None
        self._update_button = None
        self._refresh_button = None
        self._start_button = None
        self._stop_button = None
        self._restart_button = None

        self._build_ui()
        self._execute_task("initialize", self._core.initialize)

    def __del__(self):
        # Cancel all async tasks
        for task in self._async_tasks.values():
            task.cancel()

    def _build_ui(self):
        """
        Build the UI for the ComfyUI Widget.
        """
        with ui.VStack(spacing=ui.Pixel(8)):
            with ui.HStack(spacing=ui.Pixel(8)):
                ui.Spacer()
                ui.Label("Status: ", name="PropertiesPaneSectionTitle", width=0)
                self._state_label = ui.Label(self._core.state.value, width=0)
                ui.Spacer()
            self._install_button = ui.Button("Install", height=0, clicked_fn=self._install_clicked)
            self._locate_button = ui.Button("Locate", height=0, clicked_fn=self._locate_clicked)
            self._uninstall_button = ui.Button("Uninstall", height=0, clicked_fn=self._uninstall_clicked)
            self._update_button = ui.Button("Update", height=0, clicked_fn=self._update_clicked)

            ui.Rectangle(height=ui.Pixel(1))

            self._refresh_button = ui.Button("Refresh", height=0, clicked_fn=self._refresh_clicked)

            ui.Rectangle(height=ui.Pixel(1))

            self._start_button = ui.Button("Start", height=0, clicked_fn=self._start_clicked)
            self._stop_button = ui.Button("Stop", height=0, clicked_fn=self._stop_clicked)
            self._restart_button = ui.Button("Restart", height=0, clicked_fn=self._restart_clicked)

        self._update_button_states()

    def _on_state_changed(self, state: ComfyUIState):
        """
        Update the UI when the ComfyUI state changes.
        """
        if not self._state_label:
            return
        self._state_label.text = state.value
        self._update_button_states()

    def _update_button_states(self):
        """
        Update the enabled states and tooltips of the buttons in the UI.
        """
        if self._install_button:
            self._install_button.enabled = self._core.state in [ComfyUIState.NOT_FOUND, ComfyUIState.READY]
            self._install_button.tooltip = (
                "Select a directory to install ComfyUI in"
                if self._install_button.enabled
                else "ComfyUI cannot be installed at this time"
            )
        if self._locate_button:
            self._locate_button.enabled = self._core.state in [ComfyUIState.NOT_FOUND, ComfyUIState.READY]
            self._locate_button.tooltip = (
                "Select an existing ComfyUI installation directory"
                if self._locate_button.enabled
                else "ComfyUI installation directory cannot be located at this time"
            )
        if self._uninstall_button:
            self._uninstall_button.enabled = self._core.state == ComfyUIState.READY
            self._uninstall_button.tooltip = (
                "Delete the current ComfyUI installation from the filesystem"
                if self._uninstall_button.enabled
                else "ComfyUI cannot be uninstalled at this time"
            )
        if self._update_button:
            self._update_button.enabled = self._core.state == ComfyUIState.READY and self._core.update_available
            if not self._update_button.enabled:
                if self._core.update_available:
                    self._update_button.tooltip = "ComfyUI cannot be updated at this time"
                else:
                    self._update_button.tooltip = "No update available for the current ComfyUI installation"
            else:
                self._update_button.tooltip = "Update the current ComfyUI installation to the latest version"
        if self._refresh_button:
            self._refresh_button.enabled = self._core.state in [
                ComfyUIState.NOT_FOUND,
                ComfyUIState.FOUND,
                ComfyUIState.READY,
                ComfyUIState.ERROR,
            ]
            self._refresh_button.tooltip = (
                "Refresh the ComfyUI installation"
                if self._refresh_button.enabled
                else "ComfyUI cannot be refreshed at this time"
            )
        if self._start_button:
            self._start_button.enabled = self._core.state == ComfyUIState.READY
            self._start_button.tooltip = (
                "Start the ComfyUI server" if self._start_button.enabled else "ComfyUI cannot be started at this time"
            )
        if self._stop_button:
            self._stop_button.enabled = self._core.state in [ComfyUIState.STARTING, ComfyUIState.RUNNING]
            self._stop_button.tooltip = (
                "Stop the ComfyUI server" if self._stop_button.enabled else "ComfyUI cannot be stopped at this time"
            )
        if self._restart_button:
            self._restart_button.enabled = self._core.state in [ComfyUIState.STARTING, ComfyUIState.RUNNING]
            self._restart_button.tooltip = (
                "Restart the ComfyUI server"
                if self._restart_button.enabled
                else "ComfyUI cannot be restarted at this time"
            )

    def _install_clicked(self):
        """
        Callback for the install button.

        Initializes the ComfyUI core with a new ComfyUI installation directory.
        """
        open_file_picker(
            "Select Target ComfyUI Installation Directory",
            partial(self._initialize_comfyui, False),
            lambda _: None,
            apply_button_label="Select",
            select_directory=True,
            allow_multi_selection=False,
        )

    def _locate_clicked(self):
        """
        Callback for the locate button.

        Initializes the ComfyUI core with an existing ComfyUI installation directory.
        """
        open_file_picker(
            "Select Existing ComfyUI Installation Directory",
            partial(self._initialize_comfyui, True),
            lambda _: None,
            apply_button_label="Select",
            select_directory=True,
            validate_selection=(
                lambda dirname, filename: self._core.get_comfyui_directory(dirname, filename) is not None
            ),
            validation_failed_callback=self._validation_failed_callback,
            allow_multi_selection=False,
        )

    def _uninstall_clicked(self):
        """
        Callback for the uninstall button.

        Uninstalls the ComfyUI installation.
        """
        self._execute_task("uninstall", self._core.cleanup)

    def _update_clicked(self):
        """
        Callback for the update button.

        Updates the ComfyUI installation.
        """
        update_task = self._execute_task("update", self._core.update, force=False)
        update_task.add_done_callback(self._update_done_callback)

    def _refresh_clicked(self):
        """
        Callback for the refresh button.

        Refreshes the ComfyUI state. Discards the current ComfyUI installation and re-initializes it.
        """
        self._execute_task("refresh", self._core.refresh)

    def _start_clicked(self):
        """
        Callback for the start button.

        Starts the ComfyUI server.
        """
        self._execute_task("start", self._core.run)

    def _stop_clicked(self):
        """
        Callback for the stop button.

        Stops the ComfyUI server.
        """
        self._execute_task("stop", self._core.stop)

    def _restart_clicked(self):
        """
        Callback for the restart button.

        Restarts the ComfyUI server. (Equivalent to stopping and then starting the server)
        """
        self._execute_task("restart", self._core.restart)

    def _initialize_comfyui(self, open_or_install: bool, directory: str | list[str]):
        """
        Callback for the install and locate file pickers.

        Initializes the ComfyUI core with the selected directory.

        Args:
            directory: The directory or list of directories selected by the user (passed by the file picker callback)
            open_or_install: Whether to open the repository if it exists or install it if it doesn't exist
        """
        if isinstance(directory, list):
            if len(directory) == 0:
                return
            directory = directory[0]
        self._execute_task("initialize", self._core.initialize, directory, open_or_install=open_or_install)

    def _validation_failed_callback(self, _dirname: str, _filename: str):
        """
        Callback for the validation failed event of the install and locate file pickers.

        Displays a message dialog with the appropriate message.

        Args:
            _dirname: The directory name (passed by the file picker callback)
            _filename: The filename (passed by the file picker callback)
        """
        TrexMessageDialog(
            "The selected directory is not a valid ComfyUI installation directory.",
            title="Invalid Directory Selected",
            disable_cancel_button=True,
        )

    def _update_done_callback(self, future: asyncio.Future):
        """
        Callback for the update done event.
        """
        result = future.result()
        if result is not None and not result:
            TrexMessageDialog(
                (
                    "The ComfyUI update failed. Local changes that conflicted with the update were detected.\n\n"
                    "If you proceed with the update, any change made to the ComfyUI installation will be discarded.\n\n"
                    "We recommend you backup your changes before proceeding with the update.\n\n"
                    "Do you wish to discard your changes and proceed with the update?"
                ),
                title="ComfyUI Update Failed",
                ok_label="Force Update",
                ok_handler=lambda: self._execute_task("update", self._core.update, force=True),
                cancel_handler=lambda: None,
            )

    def _execute_task(self, key: str, function: Callable, *args, **kwargs) -> asyncio.Future:
        """
        Execute a task and store it in the _async_tasks dictionary.

        Enforces that only one task with the same key is running at a time.

        Returns:
            The future of the task.
        """
        if key in self._async_tasks:
            self._async_tasks[key].cancel()
        self._async_tasks[key] = asyncio.ensure_future(function(*args, **kwargs))

        return self._async_tasks[key]

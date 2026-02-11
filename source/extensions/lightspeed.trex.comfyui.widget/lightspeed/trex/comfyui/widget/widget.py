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
from collections.abc import Callable

from lightspeed.trex.comfyui.core import ComfyUIQueueType, ComfyUIState, get_comfyui_instance
from lightspeed.trex.utils.widget import TrexMessageDialog, WorkspaceWidget
from omni import ui
from omni.flux.utils.widget.file_pickers import open_file_picker


class ComfyUIWidget(WorkspaceWidget):
    _ICON_SIZE_MD = ui.Pixel(24)
    _ICON_SIZE_LG = ui.Pixel(32)

    _SPACING_MD = ui.Pixel(8)
    _SPACING_LG = ui.Pixel(16)

    _STATUS_HEIGHT = ui.Pixel(32)

    _SEPARATOR_HEIGHT = ui.Pixel(1)

    def __init__(self, context_name: str = ""):
        super().__init__()
        self._core = get_comfyui_instance(context_name=context_name)
        self._async_tasks = {}

        # Subscriptions - created/destroyed in show() based on visibility
        self._state_changed_subscription = None
        self._texture_selection_changed_subscription = None
        self._mesh_selection_changed_subscription = None

        # Build the UI and update the button states
        self._build_ui()
        self._update_button_states()
        self._execute_task("initialize", self._core.initialize)

    def __del__(self):
        # Cancel all async tasks
        for task in self._async_tasks.values():
            task.cancel()

    def show(self, visible: bool):
        """Enable/disable the widget and its subscriptions."""
        super().show(visible)
        if self.root_widget:
            self.root_widget.visible = visible

        if visible:
            # Create subscriptions when window becomes visible
            if not self._state_changed_subscription:
                self._state_changed_subscription = self._core.subscribe_comfyui_state_changed(self._on_state_changed)
            if not self._texture_selection_changed_subscription:
                self._texture_selection_changed_subscription = self._core.subscribe_texture_selection_changed(
                    self._on_selection_changed
                )
            if not self._mesh_selection_changed_subscription:
                self._mesh_selection_changed_subscription = self._core.subscribe_mesh_selection_changed(
                    self._on_selection_changed
                )
            self._update_button_states()
        else:
            # Destroy subscriptions when window becomes invisible
            self._state_changed_subscription = None
            self._texture_selection_changed_subscription = None
            self._mesh_selection_changed_subscription = None

    def destroy(self):
        """Clean up all resources, subscriptions, and references."""
        for task in self._async_tasks.values():
            task.cancel()
        self._async_tasks = {}
        self._state_changed_subscription = None
        self._texture_selection_changed_subscription = None
        self._mesh_selection_changed_subscription = None
        self.root_widget = None

    def _build_ui(self):
        """
        Build the UI for the ComfyUI Widget.
        """
        self.root_widget = ui.ScrollingFrame(name="WorkspaceBackground")
        with self.root_widget:
            with ui.HStack(spacing=self._SPACING_MD):
                ui.Spacer(width=0)
                with ui.VStack(spacing=self._SPACING_MD):
                    ui.Spacer(height=self._SPACING_MD)

                    with ui.HStack(spacing=self._SPACING_MD, height=0):
                        ui.Label("Status: ", name="PropertiesPaneSectionTitle", alignment=ui.Alignment.TOP, width=0)
                        with ui.ScrollingFrame(
                            height=self._STATUS_HEIGHT,
                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        ):
                            self._state_label = ui.Label(self._core.state.value)

                    with ui.HStack(spacing=self._SPACING_MD, height=0):
                        with ui.ZStack():
                            self._directory_field = ui.StringField(read_only=True)
                            self._directory_placeholder = ui.HStack(spacing=self._SPACING_MD)
                            with self._directory_placeholder:
                                ui.Spacer(width=0)
                                ui.Label("No ComfyUI installation found", name="Placeholder", width=0)
                                ui.Spacer(width=0)
                        self._install_button = ui.Image(
                            "",
                            name="Install",
                            height=self._ICON_SIZE_MD,
                            width=self._ICON_SIZE_MD,
                            mouse_pressed_fn=self._install_clicked,
                        )
                        self._locate_button = ui.Image(
                            "",
                            name="Locate",
                            height=self._ICON_SIZE_MD,
                            width=self._ICON_SIZE_MD,
                            mouse_pressed_fn=self._locate_clicked,
                        )
                        self._update_button = ui.Image(
                            "",
                            name="Update",
                            height=self._ICON_SIZE_MD,
                            width=self._ICON_SIZE_MD,
                            mouse_pressed_fn=self._update_clicked,
                            visible=False,
                        )
                        self._uninstall_button = ui.Image(
                            "",
                            name="Uninstall",
                            height=self._ICON_SIZE_MD,
                            width=self._ICON_SIZE_MD,
                            mouse_pressed_fn=self._uninstall_clicked,
                            visible=False,
                        )
                        self._refresh_button = ui.Image(
                            "",
                            name="Refresh",
                            height=self._ICON_SIZE_MD,
                            width=self._ICON_SIZE_MD,
                            mouse_pressed_fn=self._refresh_clicked,
                        )

                    ui.Rectangle(height=self._SEPARATOR_HEIGHT, name="WizardSeparator")

                    with ui.HStack(spacing=self._SPACING_MD, height=0):
                        ui.Spacer(height=0)
                        self._start_button = ui.Image(
                            "",
                            name="Start",
                            height=self._ICON_SIZE_LG,
                            width=self._ICON_SIZE_MD,
                            mouse_pressed_fn=self._start_clicked,
                        )
                        self._stop_button = ui.Image(
                            "",
                            name="Stop",
                            height=self._ICON_SIZE_LG,
                            width=self._ICON_SIZE_LG,
                            mouse_pressed_fn=self._stop_clicked,
                        )
                        self._restart_button = ui.Image(
                            "",
                            name="Restart",
                            height=self._ICON_SIZE_LG,
                            width=self._ICON_SIZE_MD,
                            mouse_pressed_fn=self._restart_clicked,
                        )
                        ui.Spacer(height=0)

                    ui.Rectangle(height=self._SEPARATOR_HEIGHT, name="WizardSeparator")

                    self._open_ui_button = ui.Button("Open in Browser", height=0, clicked_fn=self._open_ui_clicked)

                    ui.Rectangle(height=self._SEPARATOR_HEIGHT, name="WizardSeparator")

                    with ui.VStack(spacing=self._SPACING_MD):
                        self._texture_queue_button = ui.Button(
                            "Process Selected Textures",
                            height=0,
                            clicked_fn=partial(self._add_to_queue_clicked, ComfyUIQueueType.TEXTURE),
                        )
                        self._mesh_queue_button = ui.Button(
                            "Process Selected Meshes",
                            height=0,
                            clicked_fn=partial(self._add_to_queue_clicked, ComfyUIQueueType.MESH),
                            visible=False,  # Disabled until the workflow is implemented
                        )

                    ui.Spacer(height=0)
                ui.Spacer(width=0)

    def _on_state_changed(self, state: ComfyUIState):
        """
        Update the UI when the ComfyUI state changes.
        Subscription destroyed when window invisible.
        """
        if not self._state_label:
            return
        self._state_label.text = state.value
        self._update_button_states()

    def _on_selection_changed(self, _: list[str]):
        """
        Update the UI when the selection changes.
        Subscription destroyed when window invisible.
        """
        self._update_queue_button_states()

    def _update_button_states(self):
        """
        Update the enabled states and tooltips of the buttons in the UI.
        """
        # Update the enabled states for all the buttons
        install_button_enabled = self._core.state == ComfyUIState.NOT_FOUND
        locate_button_enabled = self._core.state == ComfyUIState.NOT_FOUND
        uninstall_button_enabled = self._core.state == ComfyUIState.READY
        update_button_enabled = self._core.state == ComfyUIState.READY and bool(self._core.update_available)
        refresh_button_enabled = self._core.state in [
            ComfyUIState.NOT_FOUND,
            ComfyUIState.FOUND,
            ComfyUIState.READY,
            ComfyUIState.ERROR,
        ]
        start_button_enabled = self._core.state == ComfyUIState.READY
        stop_button_enabled = self._core.state in [ComfyUIState.STARTING, ComfyUIState.RUNNING]
        restart_button_enabled = self._core.state in [ComfyUIState.STARTING, ComfyUIState.RUNNING]
        open_ui_button_enabled = self._core.state == ComfyUIState.RUNNING

        # Update the visibility and tooltips for all the buttons
        if self._directory_placeholder:
            self._directory_placeholder.visible = self._core.installation_directory is None

        if self._directory_field:
            self._directory_field.model.set_value(self._core.installation_directory or "")
            self._directory_field.tooltip = self._core.installation_directory or "No ComfyUI installation was found"

        if self._install_button:
            self._install_button.visible = install_button_enabled
            self._install_button.enabled = install_button_enabled
            self._install_button.tooltip = (
                "Select a directory to install ComfyUI in"
                if install_button_enabled
                else "ComfyUI cannot be installed at this time"
            )

        if self._locate_button:
            self._locate_button.visible = locate_button_enabled
            self._locate_button.enabled = locate_button_enabled
            self._locate_button.tooltip = (
                "Select an existing ComfyUI installation directory"
                if locate_button_enabled
                else "ComfyUI installation directory cannot be located at this time"
            )

        if self._uninstall_button:
            # Only show the uninstall button when the install button is not visible
            self._uninstall_button.visible = not install_button_enabled
            self._uninstall_button.enabled = uninstall_button_enabled
            self._uninstall_button.tooltip = (
                "Delete the current ComfyUI installation from the filesystem"
                if uninstall_button_enabled
                else "The current ComfyUI installation cannot be deleted at this time"
            )

        if self._update_button:
            # Only show the update button when the locate button is not visible
            self._update_button.visible = not locate_button_enabled
            self._update_button.enabled = update_button_enabled
            if update_button_enabled:
                self._update_button.tooltip = "Update the current ComfyUI installation to the latest version"
            elif self._core.update_available is None:
                self._update_button.tooltip = "Failed to check for updates. Check the logs for more details."
            else:
                self._update_button.tooltip = "No update available for the current ComfyUI installation"

        if self._refresh_button:
            self._refresh_button.enabled = refresh_button_enabled
            self._refresh_button.tooltip = (
                "Refresh the ComfyUI installation state"
                if refresh_button_enabled
                else "An action is in progress. Please wait for it to complete before refreshing."
            )
        if self._start_button:
            self._start_button.enabled = start_button_enabled
            self._start_button.tooltip = (
                "Start the ComfyUI server"
                if start_button_enabled
                else "Install or locate a ComfyUI installation before starting the server"
            )
        if self._stop_button:
            self._stop_button.enabled = stop_button_enabled
            self._stop_button.tooltip = "Stop ComfyUI" if stop_button_enabled else "ComfyUI is not running"
        if self._restart_button:
            self._restart_button.enabled = restart_button_enabled
            self._restart_button.tooltip = "Restart ComfyUI" if restart_button_enabled else "ComfyUI is not running"
        if self._open_ui_button:
            self._open_ui_button.enabled = open_ui_button_enabled
            self._open_ui_button.tooltip = (
                "Open the ComfyUI UI in the default browser" if open_ui_button_enabled else "ComfyUI is not running"
            )
        self._update_queue_button_states()

    def _update_queue_button_states(self):
        """
        Update the enabled states and tooltips of the Add to Queue buttons in the UI.
        """
        server_running = self._core.state == ComfyUIState.RUNNING
        has_textures_selected = len(self._core.textures_selection) > 0
        has_meshes_selected = len(self._core.meshes_selection) > 0

        if self._texture_queue_button:
            self._texture_queue_button.enabled = server_running and has_textures_selected
            if self._texture_queue_button.enabled:
                self._texture_queue_button.tooltip = (
                    "Add the currently selected textures to the ComfyUI processing queue"
                )
            elif not server_running:
                self._texture_queue_button.tooltip = "ComfyUI is not running"
            elif not has_textures_selected:
                self._texture_queue_button.tooltip = "No textures are currently selected"
        if self._mesh_queue_button:
            self._mesh_queue_button.enabled = server_running and has_meshes_selected
            if self._mesh_queue_button.enabled:
                self._mesh_queue_button.tooltip = "Add the currently selected meshes to the ComfyUI processing queue"
            elif not server_running:
                self._mesh_queue_button.tooltip = "ComfyUI is not running"
            elif not has_meshes_selected:
                self._mesh_queue_button.tooltip = "No meshes are currently selected"

    def _install_clicked(self, _x: float, _y: float, button: int, _modifiers: int):
        """
        Callback for the install button.

        Initializes the ComfyUI core with a new ComfyUI installation directory.
        """
        if button != 0 or not self._install_button or not self._install_button.enabled:
            return

        open_file_picker(
            "Select Target ComfyUI Installation Directory",
            self._initialize_comfyui,
            lambda _: None,
            apply_button_label="Select",
            select_directory=True,
            allow_multi_selection=False,
        )

    def _locate_clicked(self, _x: float, _y: float, button: int, _modifiers: int):
        """
        Callback for the locate button.

        Initializes the ComfyUI core with an existing ComfyUI installation directory.
        """
        if button != 0 or not self._locate_button or not self._locate_button.enabled:
            return

        open_file_picker(
            "Select Existing ComfyUI Installation Directory",
            self._initialize_comfyui,
            lambda _: None,
            apply_button_label="Select",
            select_directory=True,
            validate_selection=(
                lambda dirname, filename: self._core.get_comfyui_directory(dirname, filename) is not None
            ),
            validation_failed_callback=self._validation_failed_callback,
            allow_multi_selection=False,
        )

    def _uninstall_clicked(self, _x: float, _y: float, button: int, _modifiers: int):
        """
        Callback for the uninstall button.

        Uninstalls the ComfyUI installation.
        """
        if button != 0 or not self._uninstall_button or not self._uninstall_button.enabled:
            return

        self._execute_task("uninstall", self._core.cleanup)

    def _update_clicked(self, _x: float, _y: float, button: int, _modifiers: int):
        """
        Callback for the update button.

        Updates the ComfyUI installation.
        """
        if button != 0 or not self._update_button or not self._update_button.enabled:
            return

        update_task = self._execute_task("update", self._core.update, force=False)
        update_task.add_done_callback(self._update_done_callback)

    def _refresh_clicked(self, _x: float, _y: float, button: int, _modifiers: int):
        """
        Callback for the refresh button.

        Refreshes the ComfyUI state. Discards the current ComfyUI installation and re-initializes it.
        """
        if button != 0 or not self._refresh_button or not self._refresh_button.enabled:
            return

        self._execute_task("refresh", self._core.refresh)

    def _start_clicked(self, _x: float, _y: float, button: int, _modifiers: int):
        """
        Callback for the start button.

        Starts the ComfyUI server.
        """
        if button != 0 or not self._start_button or not self._start_button.enabled:
            return

        self._execute_task("start", self._core.run)

    def _stop_clicked(self, _x: float, _y: float, button: int, _modifiers: int):
        """
        Callback for the stop button.

        Stops the ComfyUI server.
        """
        if button != 0 or not self._stop_button or not self._stop_button.enabled:
            return

        self._execute_task("stop", self._core.stop)

    def _restart_clicked(self, _x: float, _y: float, button: int, _modifiers: int):
        """
        Callback for the restart button.

        Restarts the ComfyUI server. (Equivalent to stopping and then starting the server)
        """
        if button != 0 or not self._restart_button or not self._restart_button.enabled:
            return

        self._execute_task("restart", self._core.restart)

    def _open_ui_clicked(self):
        """
        Callback for the Open UI button.

        Opens the ComfyUI UI in the default browser.
        """
        self._core.open_ui()

    def _add_to_queue_clicked(self, queue_type: ComfyUIQueueType):
        """
        Callback for the Add to Queue button.

        Adds the selected textures or meshes to the ComfyUI processing queue.
        """
        self._execute_task("add_to_queue", self._core.add_to_queue, queue_type)

    def _initialize_comfyui(self, directory: str | list[str]):
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
        self._execute_task("initialize", self._core.initialize, repository_directory=directory, open_or_install=False)

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

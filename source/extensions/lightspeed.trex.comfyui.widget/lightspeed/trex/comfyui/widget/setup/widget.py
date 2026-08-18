"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["ComfySetupAdvancedWidget"]

import asyncio
import webbrowser
from collections.abc import Awaitable, Callable

import carb
from lightspeed.trex.comfyui.core.connection import get_connected_endpoint
from lightspeed.trex.comfyui.core.enums import ComfyUIEventType, ComfyUIProtocol, ComfyUIState
from lightspeed.trex.comfyui.core.events import subscribe_comfyui_event
from lightspeed.trex.comfyui.core.extension import get_comfyui_core_instance
from lightspeed.trex.comfyui.core.url import build_url, is_valid_host, is_valid_port, parse_url
from lightspeed.trex.utils.widget.workspace import WorkspaceWidget
from omni import ui


class ComfySetupAdvancedWidget(WorkspaceWidget):
    """Configure and connect a USD context to an external ComfyUI server."""

    _TAB_HEIGHT = ui.Pixel(32)
    _SPACING_SM = ui.Pixel(4)
    _SPACING_MD = ui.Pixel(8)
    _SPACING_LG = ui.Pixel(16)
    _ERROR_DIALOG_WIDTH = ui.Pixel(600)
    _ERROR_DIALOG_HEIGHT = ui.Pixel(300)

    _PROTOCOL_WIDTH = ui.Pixel(72)
    _HOST_WIDTH = ui.Fraction(1)
    _PORT_WIDTH = ui.Pixel(72)
    _ICON_SIZE = ui.Pixel(16)
    _PROTOCOLS = tuple(ComfyUIProtocol)

    _STATE_TEXT_MAP = {
        ComfyUIState.READY: "Disconnected",
        ComfyUIState.STARTING: "Connecting",
        ComfyUIState.RUNNING: "Connected",
        ComfyUIState.ERROR: "Connection Failed",
    }

    _STATE_BANNER_STYLE_MAP = {
        ComfyUIState.READY: "ComfyUIStatusDisconnected",
        ComfyUIState.STARTING: "ComfyUIStatusConnecting",
        ComfyUIState.RUNNING: "ComfyUIStatusConnected",
        ComfyUIState.ERROR: "ComfyUIStatusError",
    }

    _BUTTON_TEXT_MAP = {
        ComfyUIState.READY: "Connect",
        ComfyUIState.STARTING: "Connecting...",
        ComfyUIState.RUNNING: "Disconnect",
        ComfyUIState.ERROR: "Retry",
    }

    _BUTTON_TOOLTIP_MAP = {
        ComfyUIState.READY: "Connect to the ComfyUI server.",
        ComfyUIState.STARTING: "Connecting to the ComfyUI server.",
        ComfyUIState.RUNNING: "Disconnect from the ComfyUI server.",
        ComfyUIState.ERROR: "Try connecting to the ComfyUI server again.",
    }

    def __init__(self, context_name: str):
        """Initialize external-server controls for a USD context.

        Args:
            context_name: USD context whose ComfyUI connection settings are edited.
        """
        self._context_name = context_name
        self._core = get_comfyui_core_instance(context_name=context_name)

        self._protocol_combo = None
        self._host_field = None
        self._port_field = None
        self._standard_port_image = None
        self._status_frame = None
        self._connect_button = None
        self._connection_error_dialog = None
        self._connection_error_field = None
        self._event_sub = None
        self._action_task = None
        self._updating_protocol = False

        super().__init__()

        self._build_ui()

        self._event_sub = subscribe_comfyui_event(context_name, self._on_core_event)

    def _build_ui(self):
        """Build the setup mode tabs and external-server controls."""
        with ui.ZStack():
            ui.Rectangle(name="TabBackground")
            with ui.VStack():
                with ui.HStack(height=0):
                    with ui.ZStack(
                        width=ui.Fraction(1),
                        height=self._TAB_HEIGHT,
                        tooltip="Use a fully managed ComfyUI server with automatic setup.",
                    ):
                        ui.Rectangle(name="TransparentBackground", identifier="ComfySetupManagedTab")
                        ui.Label(
                            "Managed",
                            name="PropertiesWidgetLabelDisabled",
                            alignment=ui.Alignment.CENTER,
                        )
                    with ui.ZStack(
                        width=ui.Fraction(1),
                        height=self._TAB_HEIGHT,
                        tooltip="Connect to a ComfyUI server running locally, on a network, or in the cloud.",
                    ):
                        ui.Rectangle(name="WorkspaceBackground", identifier="ComfySetupExternalTab")
                        ui.Label("External", name="PropertiesWidgetLabel", alignment=ui.Alignment.CENTER)
                with ui.ZStack():
                    ui.Rectangle(name="WorkspaceBackground", identifier="ComfySetupContent")
                    self._build_external_ui()

    def _build_external_ui(self):
        """Build external-server connection and status controls."""
        protocol_options = [protocol.scheme for protocol in self._PROTOCOLS]
        protocol_index = self._PROTOCOLS.index(self._core.settings.protocol)

        with ui.HStack(spacing=self._SPACING_LG):
            ui.Spacer(width=0)
            with ui.VStack(spacing=self._SPACING_LG):
                ui.Spacer(height=0)
                state = self._core.state
                self._status_frame = ui.Frame(height=0, build_fn=self._build_status)
                with ui.HStack(spacing=self._SPACING_LG, height=0):
                    with ui.VStack(width=self._PROTOCOL_WIDTH):
                        ui.Label("Protocol")
                        self._protocol_combo = ui.ComboBox(
                            protocol_index,
                            *protocol_options,
                            identifier="ComfySetupProtocol",
                            tooltip="Connection protocol (HTTP or HTTPS)",
                        )
                        self._protocol_combo.model.add_item_changed_fn(self._on_protocol_changed)
                    with ui.VStack(width=self._HOST_WIDTH):
                        ui.Label("Host")
                        self._host_field = ui.StringField(
                            identifier="ComfySetupHost",
                            tooltip="Server hostname or IP. Paste a full URL (e.g. http://host:port)"
                            " to auto-set protocol and port",
                        )
                        self._host_field.model.set_value(self._core.settings.host)
                        self._host_field.model.add_end_edit_fn(self._on_host_changed)
                    with ui.VStack(width=self._PORT_WIDTH):
                        ui.Label("Port")
                        with ui.HStack(spacing=self._SPACING_SM):
                            self._port_field = ui.IntField(
                                identifier="ComfySetupPort",
                                tooltip="Server port number (1-65535)",
                            )
                            self._port_field.model.set_value(self._core.settings.port)
                            self._port_field.model.add_end_edit_fn(self._on_port_changed)

                            ports_info = ", ".join(
                                f"{protocol.scheme.upper()}={protocol.standard_port}" for protocol in self._PROTOCOLS
                            )
                            with ui.VStack(width=self._ICON_SIZE):
                                ui.Spacer()
                                self._standard_port_image = ui.Image(
                                    "",
                                    name="Web",
                                    identifier="ComfySetupStandardPort",
                                    width=self._ICON_SIZE,
                                    height=self._ICON_SIZE,
                                    tooltip=f"Set to standard port ({ports_info})",
                                    mouse_released_fn=self._on_set_standard_port,
                                )
                                ui.Spacer()
                button_text = self._BUTTON_TEXT_MAP.get(state, "Connect")
                self._connect_button = ui.Button(
                    button_text,
                    height=0,
                    clicked_fn=self._on_connect_clicked,
                    identifier="ComfySetupConnect",
                    tooltip=self._BUTTON_TOOLTIP_MAP.get(state, "Connect to or disconnect from the ComfyUI server."),
                )
                ui.Spacer(height=0)
            ui.Spacer(width=0)
        self.update_state_display()

    def _build_status(self) -> None:
        """Build the banner and only the action valid for the current connection state."""
        state = self._core.state
        if state == ComfyUIState.RUNNING and not self._core.is_connected:
            state = ComfyUIState.READY
        endpoint = (
            get_connected_endpoint(self._context_name)
            if state == ComfyUIState.RUNNING and self._core.is_connected
            else None
        )
        is_verified_running = state == ComfyUIState.RUNNING and endpoint is not None
        is_unavailable_connection = state == ComfyUIState.RUNNING and self._core.is_connected and endpoint is None
        display_state = ComfyUIState.READY if is_unavailable_connection else state
        title_text = (
            "Connection Unavailable" if is_unavailable_connection else self._STATE_TEXT_MAP.get(state, "Unknown")
        )
        detail_text = (
            "The verified ComfyUI endpoint is unavailable. Disconnect and reconnect to restore the connection."
            if is_unavailable_connection
            else build_url(*endpoint)
            if endpoint
            else self._get_state_tooltip(state)
        )

        with ui.ZStack(height=0):
            ui.Rectangle(
                name=self._STATE_BANNER_STYLE_MAP.get(display_state, "ComfyUIStatusDisconnected"),
                identifier="ComfySetupStatusBanner",
            )
            with ui.HStack(spacing=self._SPACING_LG, height=0):
                ui.Spacer(width=0)
                with ui.HStack(spacing=self._SPACING_MD, width=ui.Fraction(1), height=0):
                    with ui.VStack(spacing=self._SPACING_SM, width=ui.Fraction(1), height=0):
                        ui.Spacer(height=0)
                        ui.Label(
                            title_text,
                            name="ComfyUIStatusTitle",
                            width=ui.Fraction(1),
                            height=0,
                            word_wrap=True,
                        )
                        ui.Label(
                            detail_text,
                            name="ComfyUIStatusDetail",
                            width=ui.Fraction(1),
                            height=0,
                            word_wrap=True,
                            tooltip=detail_text,
                        )
                        ui.Spacer(height=0)
                    if is_verified_running:
                        with ui.VStack(width=0):
                            ui.Spacer()
                            ui.Button(
                                "Open Browser",
                                width=0,
                                height=0,
                                clicked_fn=self._on_open_browser_clicked,
                                identifier="ComfySetupOpenBrowser",
                                tooltip="Open the connected ComfyUI server in a browser.",
                            )
                            ui.Spacer()
                    elif state == ComfyUIState.ERROR:
                        with ui.VStack(width=0):
                            ui.Spacer()
                            ui.Button(
                                "Show Logs",
                                width=0,
                                height=0,
                                clicked_fn=self._on_show_logs_clicked,
                                identifier="ComfySetupShowLogs",
                                tooltip="Show the current ComfyUI connection failure.",
                            )
                            ui.Spacer()
                ui.Spacer(width=0)

    def destroy(self):
        """Release UI references, subscriptions, and the active connection task."""
        self._event_sub = None
        self._protocol_combo = None
        self._host_field = None
        self._port_field = None
        self._standard_port_image = None
        self._status_frame = None
        self._connect_button = None
        self._destroy_connection_error_dialog()
        if self._action_task:
            self._action_task.cancel()
            self._action_task = None

    def _on_core_event(self, event) -> None:
        """Update connection controls for relevant ComfyUI core events.

        Args:
            event: Core event describing a connection-state or settings change.
        """
        if event.event_type == ComfyUIEventType.STATE_CHANGED:
            self.update_state_display()
        elif event.event_type == ComfyUIEventType.SETTINGS_CHANGED:
            self._revert_protocol()
            self._revert_host()
            self._revert_port()
            self.update_state_display()

    def _on_connect_clicked(self) -> None:
        """Handle connect/disconnect button click."""
        state = self._core.state
        if state == ComfyUIState.STARTING:
            return
        if self._action_task and not self._action_task.done():
            return
        action = (
            self._core.shutdown if state == ComfyUIState.RUNNING and self._core.is_connected else self._core.connect
        )
        self._action_task = asyncio.ensure_future(self._run_connection_action(action))
        self._action_task.set_name("ComfyUIConnectionAction")

    async def _run_connection_action(self, action: Callable[[], Awaitable[None]]) -> None:
        """Await one connection action and report its expected failures.

        Args:
            action: Bound asynchronous connect or shutdown operation to execute.
        """
        try:
            await action()
        except (OSError, RuntimeError, ValueError) as error:
            carb.log_error(f"ComfyUI connection action failed: {error}")
        finally:
            self._action_task = None

    def update_state_display(self) -> None:
        """Update the state display from the core's current state."""
        state = self._core.state
        if state == ComfyUIState.RUNNING and not self._core.is_connected:
            state = ComfyUIState.READY
        if self._status_frame:
            self._status_frame.rebuild()
        if self._connect_button:
            self._connect_button.text = self._BUTTON_TEXT_MAP.get(state, "Connect")
            self._connect_button.enabled = state != ComfyUIState.STARTING
            self._connect_button.tooltip = self._BUTTON_TOOLTIP_MAP.get(
                state, "Connect to or disconnect from the ComfyUI server."
            )
        endpoint_enabled = self._can_edit_endpoint()
        if self._protocol_combo:
            self._protocol_combo.enabled = endpoint_enabled
        if self._host_field:
            self._host_field.enabled = endpoint_enabled
        if self._port_field:
            self._port_field.enabled = endpoint_enabled
        if self._standard_port_image:
            self._standard_port_image.enabled = endpoint_enabled

    def _on_open_browser_clicked(self) -> None:
        """Open the verified ComfyUI endpoint in the default browser."""
        is_verified_running = self._core.state == ComfyUIState.RUNNING and self._core.is_connected
        endpoint = get_connected_endpoint(self._context_name) if is_verified_running else None
        if endpoint is None:
            carb.log_warn("ComfyUI browser action skipped because the connection is no longer verified.")
            return
        try:
            opened = webbrowser.open(build_url(*endpoint), new=0, autoraise=True)
        except (OSError, RuntimeError, webbrowser.Error) as error:
            carb.log_error(f"Could not open the verified ComfyUI endpoint in the default browser: {error}")
            return
        if not opened:
            carb.log_error("Could not open the verified ComfyUI endpoint in the default browser.")

    def _on_show_logs_clicked(self) -> None:
        """Show technical details from the current failed connection attempt."""
        if self._core.state != ComfyUIState.ERROR:
            carb.log_warn("ComfyUI logs action skipped because the connection error is no longer active.")
            return
        settings = self._core.settings
        endpoint = build_url(settings.protocol.scheme, settings.host, settings.port)
        error = self._core.last_connection_error or self._core.status_message or "No error details are available."
        details = f"Endpoint: {endpoint}\n\nError: {error}"
        if self._connection_error_dialog and self._connection_error_field:
            self._connection_error_field.model.set_value(details)
            self._connection_error_dialog.visible = True
            return
        self._connection_error_dialog = ui.Window(
            "ComfyUI Connection Failed",
            visible=True,
            width=self._ERROR_DIALOG_WIDTH,
            height=self._ERROR_DIALOG_HEIGHT,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_CLOSE
                | ui.WINDOW_FLAGS_MODAL
            ),
        )
        with self._connection_error_dialog.frame:
            with ui.HStack(spacing=self._SPACING_LG):
                ui.Spacer(width=0)
                with ui.VStack(spacing=self._SPACING_LG):
                    ui.Spacer(height=0)
                    ui.Label(
                        "Select and copy the details below for troubleshooting.",
                        height=0,
                        word_wrap=True,
                    )
                    with ui.ZStack():
                        ui.Rectangle(name="WorkspaceBackground")
                        self._connection_error_field = ui.StringField(
                            multiline=True,
                            read_only=True,
                            identifier="ComfySetupConnectionErrorText",
                        )
                        self._connection_error_field.model.set_value(details)
                    with ui.HStack(height=0):
                        ui.Spacer()
                        ui.Button("Close", width=0, height=0, clicked_fn=self._hide_connection_error_dialog)
                    ui.Spacer(height=0)
                ui.Spacer(width=0)

    def _hide_connection_error_dialog(self) -> None:
        """Hide the current connection-error dialog."""
        if self._connection_error_dialog:
            self._connection_error_dialog.visible = False

    def _destroy_connection_error_dialog(self) -> None:
        """Destroy the current connection-error dialog, if one exists."""
        if not self._connection_error_dialog:
            return
        self._connection_error_dialog.destroy()
        self._connection_error_dialog = None
        self._connection_error_field = None

    def _can_edit_endpoint(self) -> bool:
        """Return whether changing server endpoint settings is safe.

        Returns:
            True while disconnected or after a failed connection attempt.
        """
        return self._core.state in (ComfyUIState.READY, ComfyUIState.ERROR) or (
            self._core.state == ComfyUIState.RUNNING and not self._core.is_connected
        )

    def _get_state_tooltip(self, state: ComfyUIState) -> str:
        """Return plain-language connection status and recovery guidance.

        Args:
            state: Connection state represented by the status label.

        Returns:
            User-facing detail for the current connection state.
        """
        if state is ComfyUIState.READY:
            return "ComfyUI is disconnected. Enter the server address, then select Connect."
        if state is ComfyUIState.STARTING:
            return self._core.status_message or "Connecting to the configured ComfyUI server."
        if state is ComfyUIState.RUNNING:
            return "ComfyUI is connected and ready."
        if state is ComfyUIState.ERROR:
            return self._core.status_message or (
                "Could not connect to ComfyUI. Check the server address and that ComfyUI is running, then try again."
            )
        return "The ComfyUI connection state is unavailable. Disconnect and try again."

    def _on_set_standard_port(self, x, y, button, modifier):
        """Set the port to the standard value for the current protocol.

        Args:
            x: Pointer x-coordinate supplied by the image callback.
            y: Pointer y-coordinate supplied by the image callback.
            button: Mouse button index that triggered the callback.
            modifier: Active keyboard-modifier flags supplied by the callback.
        """
        if button != 0 or not self._can_edit_endpoint():
            return
        protocol = self._core.settings.protocol
        if self._protocol_combo:
            protocol_index = self._protocol_combo.model.get_item_value_model().as_int
            if 0 <= protocol_index < len(self._PROTOCOLS):
                protocol = self._PROTOCOLS[protocol_index]
        standard_port = protocol.standard_port
        if self._port_field:
            self._port_field.model.set_value(standard_port)
        self._core.settings.set_port(standard_port)

    def _on_protocol_changed(self, model, item):
        """Persist a protocol selection while endpoint editing is allowed.

        Args:
            model: ComboBox model containing the selected protocol index.
            item: Changed ComboBox item supplied by the UI callback.
        """
        if self._updating_protocol:
            return
        if not self._can_edit_endpoint():
            self._revert_protocol()
            return
        index = model.get_item_value_model().as_int
        if 0 <= index < len(self._PROTOCOLS):
            self._core.settings.set_protocol(self._PROTOCOLS[index])
        else:
            self._revert_protocol()

    def _on_host_changed(self, model):
        """Validate and persist an endpoint host while editing is allowed.

        Args:
            model: String model containing a host name or complete endpoint URL.
        """
        if not self._can_edit_endpoint():
            self._revert_host()
            return
        value = model.as_string.strip()
        is_valid, protocol_str, host, port = parse_url(value)
        protocol = next((item for item in ComfyUIProtocol if item.scheme == protocol_str), None)

        if not is_valid or not host or not is_valid_host(host) or (protocol_str and not protocol):
            self._revert_host()
            return

        if protocol and self._protocol_combo:
            self._updating_protocol = True
            try:
                self._protocol_combo.model.get_item_value_model().set_value(self._PROTOCOLS.index(protocol))
            finally:
                self._updating_protocol = False
            self._core.settings.set_protocol(protocol)

        if port:
            if self._port_field:
                self._port_field.model.set_value(port)
            self._core.settings.set_port(port)
        elif protocol:
            if self._port_field:
                self._port_field.model.set_value(protocol.standard_port)
            self._core.settings.set_port(protocol.standard_port)

        self._core.settings.set_host(host)
        if self._host_field:
            self._host_field.model.set_value(host)

    def _on_port_changed(self, model):
        """Validate and persist an endpoint port while editing is allowed.

        Args:
            model: Integer model containing the candidate server port.
        """
        if not self._can_edit_endpoint():
            self._revert_port()
            return
        port = model.as_int
        if not is_valid_port(port):
            self._revert_port()
            return
        self._core.settings.set_port(port)

    def _revert_host(self):
        """Revert the host field to the last valid saved value."""
        if self._host_field:
            self._host_field.model.set_value(self._core.settings.host)

    def _revert_protocol(self):
        """Revert the protocol combo to the last persisted value."""
        if not self._protocol_combo:
            return
        self._updating_protocol = True
        try:
            self._protocol_combo.model.get_item_value_model().set_value(
                self._PROTOCOLS.index(self._core.settings.protocol)
            )
        finally:
            self._updating_protocol = False

    def _revert_port(self):
        """Revert the port field to the last valid saved value."""
        if self._port_field:
            self._port_field.model.set_value(self._core.settings.port)

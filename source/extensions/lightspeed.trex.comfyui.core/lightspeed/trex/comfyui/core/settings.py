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

from __future__ import annotations

__all__ = ["ComfyUISettings"]

from collections.abc import Callable

from carb.settings import get_settings

from .constants import COMFYUI_SETTINGS_ROOT
from .enums import ComfyUIProtocol
from .url import is_valid_host, is_valid_port


def _persistent_key(key: str) -> str:
    """Prepend the persistent prefix to a settings key.

    Args:
        key: Absolute extension settings key.

    Returns:
        Corresponding persistent settings key.
    """
    return f"/persistent{key}"


class ComfyUISettings:
    """Read and update persistent ComfyUI connection settings."""

    def __init__(
        self,
        *,
        settings_changed_callback: Callable[[str, object], None] | None = None,
    ):
        """Initialize the settings facade and optional change observer.

        Args:
            settings_changed_callback: Process-wide observer notified after a setting changes.
        """
        self._settings_changed_callback = settings_changed_callback

    def destroy(self) -> None:
        """Release observers retained by this settings facade."""
        self._settings_changed_callback = None

    @property
    def protocol(self) -> ComfyUIProtocol:
        """Return the configured connection protocol.

        Returns:
            Persisted protocol, or HTTP when the stored value is invalid.
        """
        value = get_settings().get(
            _persistent_key(f"{COMFYUI_SETTINGS_ROOT}/protocol"),
        )
        for protocol in ComfyUIProtocol:
            if protocol.scheme == value:
                return protocol
        return ComfyUIProtocol.HTTP

    def set_protocol(self, value: ComfyUIProtocol) -> None:
        """Persist the connection protocol and notify listeners.

        Args:
            value: The protocol to store.
        """
        if value == self.protocol:
            return
        get_settings().set(
            _persistent_key(f"{COMFYUI_SETTINGS_ROOT}/protocol"),
            value.scheme,
        )
        self._push_settings_changed("protocol", value)

    @property
    def host(self) -> str:
        """Return the configured ComfyUI server host.

        Returns:
            Persisted hostname or IP, or ``127.0.0.1`` when invalid.
        """
        value = get_settings().get_as_string(
            _persistent_key(f"{COMFYUI_SETTINGS_ROOT}/host"),
        )
        return value if is_valid_host(value) else "127.0.0.1"

    def set_host(self, value: str) -> None:
        """Persist the server host if valid and notify listeners.

        Args:
            value: Hostname or IP address to store.
        """
        if not is_valid_host(value):
            return
        if value == self.host:
            return
        get_settings().set(
            _persistent_key(f"{COMFYUI_SETTINGS_ROOT}/host"),
            value,
        )
        self._push_settings_changed("host", value)

    @property
    def port(self) -> int:
        """Return the configured ComfyUI server port.

        Returns:
            Persisted TCP port, or 8188 when invalid.
        """
        value = get_settings().get_as_int(
            _persistent_key(f"{COMFYUI_SETTINGS_ROOT}/port"),
        )
        return value if is_valid_port(value) else 8188

    def set_port(self, value: int) -> None:
        """Persist the server port if valid and notify listeners.

        Args:
            value: TCP port number to store.
        """
        if not is_valid_port(value):
            return
        if value == self.port:
            return
        get_settings().set(
            _persistent_key(f"{COMFYUI_SETTINGS_ROOT}/port"),
            value,
        )
        self._push_settings_changed("port", value)

    def _push_settings_changed(self, key: str, value: object) -> None:
        """Notify settings observers without rejecting an already committed write.

        Args:
            key: Short settings key name that changed.
            value: New value for the setting.
        """
        if self._settings_changed_callback:
            self._settings_changed_callback(key, value)

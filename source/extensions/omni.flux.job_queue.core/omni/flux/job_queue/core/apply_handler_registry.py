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

from collections.abc import Callable

from omni.flux.factory.base import FactoryBase

from .apply_handler_base import ApplyHandler

__all__ = ("ApplyHandlerRegistry",)


class ApplyHandlerRegistry(FactoryBase[ApplyHandler]):
    """Resolve only explicitly registered exact Apply handler types."""

    def __init__(self) -> None:
        """Initialize an empty registry with no process-owned change callback."""
        super().__init__()
        self._changed_callback: Callable[[], None] | None = None

    def register_plugins(self, plugins: list[type[ApplyHandler]]) -> None:
        """Register typed asynchronous handlers.

        Args:
            plugins: Concrete handler classes.
        """
        super().register_plugins(plugins)
        if self._changed_callback is not None:
            self._changed_callback()

    def unregister_plugins(self, plugins: list[type[ApplyHandler]]) -> None:
        """Unregister handler classes.

        Args:
            plugins: Registered handler classes.
        """
        super().unregister_plugins(plugins)
        if self._changed_callback is not None:
            self._changed_callback()

    def set_changed_callback(self, callback: Callable[[], None] | None) -> None:
        """Set the process-owned registration change callback.

        Args:
            callback: Callback invoked after exact registration changes.
        """
        self._changed_callback = callback

    def destroy(self) -> None:
        """Release registered handlers and the process-owned callback."""
        super().destroy()
        self._changed_callback = None

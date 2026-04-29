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
import typing

import omni.client
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.interactive_usd_notices import is_any_interaction_active as _is_any_interaction_active
from omni.flux.utils.common.interactive_usd_notices import (
    register_interaction_end_listener as _register_interaction_end_listener,
)

if typing.TYPE_CHECKING:
    from .model import FileModel as _FileModel


class FileListener:
    """Listens for file changes and refreshes matching file property models."""

    def __init__(self):
        """Create an empty file listener."""

        self._default_attr = {
            "_interaction_listener": None,
            "_listeners": None,
            "_models": None,
            "_pending_paths": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._models: list[_FileModel] = []
        self._listeners: dict[str, asyncio.Task] = {}
        self._pending_paths: dict[str, None] = {}

    @omni.usd.handle_exception
    async def __async_listener(self, path: str):
        while True:
            await asyncio.sleep(1)
            result, entry = await omni.client.stat_async(path)
            if result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.READABLE_FILE:
                self._on_file_changed(path)

    def _enable_listener(self, path: str):
        """Enable file polling for a path.

        Args:
            path: File path to poll for changes.
        """

        assert path not in self._listeners
        self._listeners[path] = asyncio.ensure_future(self.__async_listener(path))

    def _enable_interaction_listener(self):
        """Enable the interaction-end listener used to flush deferred file refreshes."""

        if self._interaction_listener is not None:
            return
        self._interaction_listener = _register_interaction_end_listener(self._on_interaction_finished)

    def _disable_listener(self, path: str):
        """Disable file polling for a path.

        Args:
            path: File path whose polling task should be cancelled.
        """

        if path in self._listeners:
            self._listeners[path].cancel()
            self._listeners.pop(path)

    def _disable_interaction_listener(self):
        """Disable the interaction-end listener when no models remain."""

        if self._interaction_listener is not None:
            self._interaction_listener.Revoke()
            self._interaction_listener = None

    def _on_file_changed(self, path):
        """Refresh or defer a model whose backing file changed.

        Args:
            path: File path that changed.
        """

        if _is_any_interaction_active():
            self._pending_paths[path] = None
            return
        self._refresh_path(path)

    def _on_interaction_finished(self, _stage):
        """Flush deferred file refreshes once all interactions finish.

        Args:
            _stage: Stage whose interaction ended.
        """

        if _is_any_interaction_active() or not self._pending_paths:
            return
        pending_paths = tuple(self._pending_paths.keys())
        self._pending_paths.clear()
        for path in pending_paths:
            self._refresh_path(path)

    def _refresh_path(self, path: str):
        """Refresh models that match a file path.

        Args:
            path: File path whose models should be refreshed.
        """

        for model in self._models:
            if path != model.path:
                continue
            model.refresh()

    def refresh_all(self):
        """Refresh all registered models."""

        for model in self._models:
            model.refresh()

    def add_model(self, model: "_FileModel"):
        """Add a model to listen to.

        Args:
            model: Model whose backing file should be observed.
        """

        if not any(f for f in self._models if f.path == model.path):
            self._enable_listener(model.path)
        self._enable_interaction_listener()

        self._models.append(model)

    def remove_model(self, model: "_FileModel"):
        """Remove a model that was being listened to.

        Args:
            model: Model whose backing file should no longer be observed.
        """

        if model in self._models:
            self._models.remove(model)
        if not any(f for f in self._models if f.path == model.path):
            self._disable_listener(model.path)
            self._pending_paths.pop(model.path, None)
        if not self._models:
            self._disable_interaction_listener()

    def destroy(self):
        """Cancel file listeners and revoke the interaction listener."""

        for listener in self._listeners.values():
            listener.cancel()
        self._disable_interaction_listener()

        _reset_default_attrs(self)

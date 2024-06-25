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
from typing import Dict, List

import omni.usd
from omni.flux.utils.common import deferred_destroy_tasks as _deferred_destroy_tasks
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl

from .common.items import ImportItem as _ImportItem


class FileListener:

    WAIT_TIME = 1

    def __init__(self):
        """A file listener that will check if a file is edited in real time"""
        self._default_attr = {"_listeners": None, "_models": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._reset()

    def _reset(self):
        self._models: List["_ImportItem"] = []
        self._listeners: Dict[str, asyncio.Task] = {}
        self.__previous_invalid_paths = set()

    @omni.usd.handle_exception
    async def __async_listener(self, path: str):
        while True:
            await asyncio.sleep(self.WAIT_TIME)
            result, _ = _ImportItem.is_valid(_OmniUrl(path), show_warning=False)
            if not result:
                self.__previous_invalid_paths.add(path)
                self._on_file_changed(path)
            elif result and path in self.__previous_invalid_paths:
                self.__previous_invalid_paths.remove(path)
                self._on_file_changed(path)

    def _enable_listener(self, path: str):
        """Enable the file listener to see if an attribute is changed"""
        if path in self._listeners:
            return
        self._listeners[path] = asyncio.ensure_future(self.__async_listener(path))

    def _disable_listener(self, path: str):
        """Disable the file listener"""
        if path in self._listeners:
            self._listeners[path].cancel()
            self._listeners.pop(path)

    def _on_file_changed(self, path):
        for model in self._models:
            if str(path) != str(model.path):
                continue
            model.on_item_changed()

    def refresh_all(self):
        """Refresh all attributes"""
        for model in self._models:
            model.on_item_changed()

    def add_model(self, model: "_ImportItem"):
        """
        Add a model and delegate to listen to

        Args:
            model: the model to listen
            delegate: the delegate to listen
        """
        if not any(f for f in self._models if f.path == model.path):
            self._enable_listener(str(model.path))

        self._models.append(model)

    def remove_model(self, model: "_ImportItem"):
        """
        Remove a model and delegate that we were listening to

        Args:
            model: the listened model
            delegate: the listened delegate
        """
        if model in self._models:
            self._models.remove(model)
        if not any(f for f in self._models if f.path == model.path):
            self._disable_listener(str(model.path))

    def destroy(self):
        asyncio.ensure_future(self.deferred_destroy())

    @omni.usd.handle_exception
    async def deferred_destroy(self):
        await _deferred_destroy_tasks(list(self._listeners.values()))
        for listener in self._listeners.values():
            listener.cancel()

        _reset_default_attrs(self)
        self._reset()

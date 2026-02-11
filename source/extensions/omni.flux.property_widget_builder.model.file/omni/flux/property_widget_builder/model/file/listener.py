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
from pxr import Tf, Usd

if typing.TYPE_CHECKING:
    from .model import FileModel as _FileModel


class FileListener:
    def __init__(self):
        """A file listener that will check if a file is edited in real time"""
        self._default_attr = {"_listeners": None, "_models": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._models: list[_FileModel] = []
        self._listeners: dict[Usd.Stage, Tf.Listener] = {}

    @omni.usd.handle_exception
    async def __async_listener(self, path: str):
        while True:
            await asyncio.sleep(1)
            result, entry = await omni.client.stat_async(path)
            if result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.READABLE_FILE:
                self._on_file_changed(path)

    def _enable_listener(self, path: str):
        """Enable the file listener to see if an attribute is changed"""
        assert path not in self._listeners
        self._listeners[path] = asyncio.ensure_future(self.__async_listener(path))

    def _disable_listener(self, path: str):
        """Disable the file listener"""
        if path in self._listeners:
            self._listeners[path].cancel()
            self._listeners.pop(path)

    def _on_file_changed(self, path):
        for model in self._models:
            if path != model.path:
                continue
            model.refresh()

    def refresh_all(self):
        """Refresh all attributes"""
        for model in self._models:
            model.refresh()

    def add_model(self, model: "_FileModel"):
        """
        Add a model and delegate to listen to

        Args:
            model: the model to listen
            delegate: the delegate to listen
        """
        if not any(f for f in self._models if f.path == model.path):
            self._enable_listener(model.path)

        self._models.append(model)

    def remove_model(self, model: "_FileModel"):
        """
        Remove a model and delegate that we were listening to

        Args:
            model: the listened model
            delegate: the listened delegate
        """
        if model in self._models:
            self._models.remove(model)
        if not any(f for f in self._models if f.path == model.path):
            self._disable_listener(model.path)

    def destroy(self):
        for listener in self._listeners.values():
            listener.cancel()

        _reset_default_attrs(self)

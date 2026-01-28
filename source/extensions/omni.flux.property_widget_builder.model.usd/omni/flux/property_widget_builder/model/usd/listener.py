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

import typing
from typing import Dict, List

from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Tf, Usd

if typing.TYPE_CHECKING:
    from .model import USDModel as _USDModel


class DisableAllListenersBlock:
    """Use to disable all listeners

    Example:
        If you add multiple entity at the same time, you can do:

        >>> with DisableAllListenersBlock(usd_listener_instance):
        >>>     for i in range(100):
        >>>         pass  # usd action
    """

    LIST_SELF = []

    def __init__(self, listener_instance):
        self.__listener_instance = listener_instance
        self.LIST_SELF.append(self)

    def __enter__(self):
        # handle nested context
        if self == self.LIST_SELF[0]:
            self.__listener_instance.tmp_disable_all_listeners()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self == self.LIST_SELF[0]:
            self.__listener_instance.tmp_enable_all_listeners()
            self.LIST_SELF.remove(self)


class USDListener:
    def __init__(self):
        """USD listener for the property widget"""
        self._default_attr = {"_listeners": None, "_models": None, "_tmp_models": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._models: List[_USDModel] = []
        self._tmp_models: List[_USDModel] = []
        self._listeners: Dict[Usd.Stage, Tf.Listener] = {}

    def tmp_enable_all_listeners(self):
        for model in self._tmp_models:
            self.add_model(model)
        self._tmp_models = []

    def tmp_disable_all_listeners(self):
        self._tmp_models = list(self._models)
        for model in self._tmp_models:
            self.remove_model(model)

    def _enable_listener(self, stage: Usd.Stage):
        """Enable the USD listener to see if an attribute is changed"""
        assert stage not in self._listeners
        self._listeners[stage] = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_changed, stage)

    def _disable_listener(self, stage: Usd.Stage):
        """Disable the USD listener"""
        if stage in self._listeners:
            self._listeners[stage].Revoke()
            self._listeners.pop(stage)

    def _on_usd_changed(self, notice, stage):
        for model in self._models:
            if model.supress_usd_events_during_widget_edit:
                continue

            if stage != model.stage:
                continue

            should_refresh = False
            for resynced_path in [*notice.GetChangedInfoOnlyPaths(), *notice.GetResyncedPaths()]:
                if "." not in str(resynced_path):  # not an attribute
                    continue
                attr = stage.GetPropertyAtPath(resynced_path)
                if not attr.IsValid():
                    continue
                prim = attr.GetPrim()
                if not prim.IsValid():
                    continue
                if prim.GetPath() not in model.prim_paths:
                    continue
                should_refresh = True
                break

            if should_refresh:
                model.refresh()

    def refresh_all(self):
        """Refresh all attributes"""
        for model in self._models:
            model.refresh()

    def add_model(self, model: "_USDModel"):
        """
        Add a model and delegate to listen to

        Args:
            model: the model to listen
            delegate: the delegate to listen
        """
        if not any(f for f in self._models if f.stage == model.stage):
            self._enable_listener(model.stage)

        self._models.append(model)

    def remove_model(self, model: "_USDModel"):
        """
        Remove a model and delegate that we were listening to

        Args:
            model: the listened model
        """
        if not model or not self._models:
            return
        if model in self._models:
            self._models.remove(model)
        if not any(f for f in self._models if f.stage == model.stage):
            self._disable_listener(model.stage)

    def destroy(self):
        for listener in self._listeners.values():
            listener.Revoke()

        _reset_default_attrs(self)

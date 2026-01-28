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

from omni import ui
from pxr import Tf, Usd


class USDListener:
    def __init__(self):
        self.__models = set()
        self.__listeners = {}

    def add_model(self, model: ui.AbstractItemModel):
        """
        Add a model to refresh when an event is triggered

        Args:
              model: the model to add
        """
        if not any(f for f in self.__models if f.stage == model.stage):
            self._enable_listener(model.stage)

        self.__models.add(model)

    def remove_model(self, model: ui.AbstractItemModel):
        """
        Remove a model to refresh

        Args:
              model: the model to remove
        """
        if model in self.__models:
            self.__models.remove(model)
        if not any(f for f in self.__models if f.stage == model.stage):
            self._disable_listener(model.stage)

    def _enable_listener(self, stage: Usd.Stage):
        assert stage not in self.__listeners
        self.__listeners[stage] = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_changed, stage)

    def _disable_listener(self, stage: Usd.Stage):
        if stage in self.__listeners:
            self.__listeners[stage].Revoke()
            self.__listeners.pop(stage)

    def _on_usd_changed(self, notice, stage):
        for model in self.__models:
            if stage != model.stage:
                continue

            should_refresh = False
            paths = notice.GetResyncedPaths()
            for path in paths:
                if path.IsPropertyPath():
                    continue
                should_refresh = True
                break
            if should_refresh:
                model.refresh()

    def destroy(self):
        if self.__listeners:
            for listener in self.__listeners.values():
                listener.Revoke()

        self.__listeners = None

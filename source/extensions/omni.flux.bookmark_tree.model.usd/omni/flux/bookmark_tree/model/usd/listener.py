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
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Tf, Usd


class USDListener:
    def __init__(self):
        self._default_attr = {
            "_models": None,
            "_listeners": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._models = set()
        self._listeners = {}

    def refresh_all(self):
        """Refresh all models held by the listener"""
        for model in self._models:
            model.refresh()

    def add_model(self, model: ui.AbstractItemModel):
        """
        Add a model to refresh when an event is triggered

        Args:
              model: the model to add
        """
        if not any(f for f in self._models if f.stage == model.stage):
            self._enable_listener(model.stage)

        self._models.add(model)

    def remove_model(self, model: ui.AbstractItemModel):
        """
        Remove a model to refresh

        Args:
              model: the model to remove
        """
        if model in self._models:
            self._models.remove(model)
        if not any(f for f in self._models if f.stage == model.stage):
            self._disable_listener(model.stage)

    def _enable_listener(self, stage: Usd.Stage):
        assert stage not in self._listeners
        self._listeners[stage] = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_changed, stage)

    def _disable_listener(self, stage: Usd.Stage):
        if stage in self._listeners:
            self._listeners[stage].Revoke()
            self._listeners.pop(stage)

    def _on_usd_changed(self, notice, stage):
        for model in self._models:
            model_base_path = model.get_bookmarks_base_path()
            should_refresh = False
            paths = notice.GetResyncedPaths() + notice.GetChangedInfoOnlyPaths()
            for path in paths:
                # If a bookmark collection was created or deleted with no item inside
                if str(path) == model_base_path:
                    should_refresh = True
                    break

                # Only care about paths where the path contains the bookmark base
                if model_base_path not in str(path):
                    continue
                # Only allow properties
                if not path.IsPropertyPath():
                    continue
                # Make sure it's a collection property
                name = path.name
                if len(str(name)) < 11 or str(name)[:11] != "collection:":
                    continue
                # Only track "includes" for item inclusions/exclusions
                if len(str(name)) < 9 or str(name)[-9:] != ":includes":
                    continue

                should_refresh = True
                break
            if should_refresh:
                model.refresh()

    def destroy(self):
        for listener in self._listeners.values():
            listener.Revoke()

        _reset_default_attrs(self)

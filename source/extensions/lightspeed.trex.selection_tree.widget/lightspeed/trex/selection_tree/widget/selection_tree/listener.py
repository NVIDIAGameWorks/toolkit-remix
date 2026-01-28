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

from __future__ import annotations

import re
import typing

from lightspeed.common.constants import LSS_NICKNAME, REGEX_HASH
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Tf, Usd

if typing.TYPE_CHECKING:
    from .model import ListModel


class USDListener:
    def __init__(self):
        """USD listener for the property widget"""
        self._default_attr = {"_listener": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.__models: list[ListModel] = []
        self._listener: Tf.Listener | None = None
        self.__regex_hash = re.compile(REGEX_HASH)

    def _enable_listener(self):
        """Enable the USD listener to see if an attribute is changed"""
        if self._listener is not None:
            return
        # Register globally without stage filter - we'll filter in the callback
        self._listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_changed, None)

    def _disable_listener(self):
        """Disable the USD listener"""
        if self._listener is not None:
            self._listener.Revoke()
            self._listener = None

    def _on_usd_changed(self, notice, sender):
        for model in self.__models:
            # Compare by root layer identifier to handle stage object differences
            model_stage = model.stage
            if not model_stage or sender != model_stage:
                continue

            should_refresh = False

            # Check for nickname attribute changes
            for changed_path in notice.GetChangedInfoOnlyPaths():
                if str(changed_path).endswith(LSS_NICKNAME):
                    should_refresh = True
                    break

            # Check resynced paths for nickname or prim changes
            if not should_refresh:
                for resynced_path in notice.GetResyncedPaths():
                    path_str = str(resynced_path)
                    # Check for nickname attribute creation
                    if path_str.endswith(LSS_NICKNAME):
                        should_refresh = True
                        break
                    # Original hash-based prim check
                    if "." in path_str:  # skip other attributes
                        continue
                    match = self.__regex_hash.match(path_str)
                    if not match:
                        continue
                    prim = model_stage.GetPrimAtPath(resynced_path)
                    if not prim.IsValid():
                        continue
                    should_refresh = True
                    break

            if should_refresh:
                model.refresh()

    def refresh_all(self):
        """Refresh all attributes"""
        for model in self.__models:
            model.refresh()

    def add_model(self, model: ListModel):
        """
        Add a model and delegate to listen to

        Args:
            model: the model to listen
        """
        if model not in self.__models:
            self.__models.append(model)
        # Enable global listener if we have any models
        if self.__models:
            self._enable_listener()

    def remove_model(self, model: ListModel):
        """
        Remove a model and delegate that we were listening to

        Args:
            model: the listened model
        """
        if model in self.__models:
            self.__models.remove(model)
        # Disable listener if no more models
        if not self.__models:
            self._disable_listener()

    def destroy(self):
        self.__models = None
        self._disable_listener()

        _reset_default_attrs(self)

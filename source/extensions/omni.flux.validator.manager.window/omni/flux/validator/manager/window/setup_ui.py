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

from typing import Type

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.flux.validator.manager.widget import ValidatorManagerWidget as _ValidatorManagerWidget

_WINDOW_INSTANCE = None


def get_window_instance():
    return _WINDOW_INSTANCE


class ValidatorManagerWindow:
    WINDOW_NAME = "Flux validator"

    def __init__(
        self,
        core: "_ManagerCore" = None,
        widget: Type["_ValidatorManagerWidget"] = None,
    ):
        """
        Create a footer widget

        Args:
            core: the manager core to use
            widget: the manager widget to use
        """

        self._default_attr = {"_manager_widget": None, "_window": None, "_core": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._core = core
        self.__create_ui(widget)

    @property
    def window(self):
        return self._window

    def __create_ui(self, widget):
        global _WINDOW_INSTANCE
        self._window = ui.Window(self.WINDOW_NAME, name=self.WINDOW_NAME, visible=True)

        with self._window.frame:
            self._manager_widget = widget(core=self._core) if widget else _ValidatorManagerWidget(core=self._core)

        _WINDOW_INSTANCE = self._window

    def destroy(self):
        _reset_default_attrs(self)

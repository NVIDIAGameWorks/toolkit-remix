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

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.validator.mass.widget import ValidatorMassWidget as _ValidatorMassWidget


class ValidatorMassWindow:
    WINDOW_NAME = "Flux Mass validator"

    def __init__(
        self,
        widget: type[_ValidatorMassWidget] = None,
    ):
        """
        Create a footer widget

        Args:
            cores: the manager core to use
        """

        self._default_attr = {"_manager_widget": None, "_window": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__create_ui(widget)

    @property
    def window(self):
        return self._window

    def __create_ui(self, widget):
        self._window = ui.Window(self.WINDOW_NAME, name=self.WINDOW_NAME, visible=True)

        with self._window.frame:
            self._manager_widget = widget() if widget else _ValidatorMassWidget()

    def destroy(self):
        _reset_default_attrs(self)

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


class Loader:
    def __init__(
        self,
        style_name: str = "Hourglass",
        width: ui.Length | int = 16,
        height: ui.Length | int = 16,
    ):
        self._default_attr = {
            "_style_name": None,
            "_width": None,
            "_height": None,
            "_icon_widget": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._style_name = style_name
        self._width = width
        self._height = height

        self._create_ui()

    def _create_ui(self):
        with ui.ZStack():
            self._icon_widget = ui.Image("", name=self._style_name, width=self._width, height=self._height)

    def destroy(self):
        _reset_default_attrs(self)

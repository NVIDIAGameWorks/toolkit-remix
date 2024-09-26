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
from omni.flux.stage_manager.widget import StageManagerWidget as _StageManagerWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

_window_instance = None


def get_window_instance():
    return _window_instance


class StageManagerManagerWindow:
    WINDOW_NAME = "Flux Stage Manager"

    def __init__(self):
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._window = None
        self._widget = None

        self.build_ui()

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_widget": None,
            "_window": None,
        }

    @property
    def window(self):
        return self._window

    def build_ui(self):
        global _window_instance
        self._window = ui.Window(
            self.WINDOW_NAME, name=self.WINDOW_NAME, visible=True, width=ui.Pixel(700), height=ui.Pixel(400)
        )

        with self._window.frame:
            self._widget = _StageManagerWidget()

        _window_instance = self._window

    def destroy(self):
        _reset_default_attrs(self)

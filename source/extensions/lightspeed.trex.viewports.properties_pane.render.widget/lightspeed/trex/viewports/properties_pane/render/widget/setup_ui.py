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


class RenderPane:
    def __init__(self, context_name: str):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_root_frame": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self.__create_ui()

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            ui.Label("Render settings")

    def __on_collapsable_frame_changed(self, widget, collapsed):
        widget.show(not collapsed)

    def refresh(self, engine_name: str, render_mode: str):
        pass

    def show(self, value: bool):
        # Update the widget visibility
        self._root_frame.visible = value

    def destroy(self):
        _reset_default_attrs(self)

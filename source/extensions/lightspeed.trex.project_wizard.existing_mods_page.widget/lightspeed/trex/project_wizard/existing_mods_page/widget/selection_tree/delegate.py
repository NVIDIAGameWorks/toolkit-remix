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


class ModSelectionDelegate(ui.AbstractItemDelegate):
    ROW_HEIGHT = 24
    ICON_SIZE = 20

    def __init__(self):
        super().__init__()

        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

    def build_widget(self, model, item, column_id, level, expanded):
        if item is None:
            return
        if column_id == 0:
            with ui.HStack(height=ui.Pixel(self.ROW_HEIGHT)):
                with ui.VStack(width=0):
                    ui.Spacer(width=0)
                    ui.Image("", name="Drag", width=ui.Pixel(self.ICON_SIZE), height=ui.Pixel(self.ICON_SIZE))
                    ui.Spacer(width=0)

                ui.Spacer(width=ui.Pixel(8), height=0)

                with ui.VStack(width=0):
                    ui.Spacer(width=0)
                    ui.Image("", name="LayerStatic", width=ui.Pixel(self.ICON_SIZE), height=ui.Pixel(self.ICON_SIZE))
                    ui.Spacer(width=0)

                ui.Spacer(width=ui.Pixel(8), height=0)

                ui.Label(item.title, tooltip=str(item.path), identifier="ExistingModLabel")

    def destroy(self):
        _reset_default_attrs(self)

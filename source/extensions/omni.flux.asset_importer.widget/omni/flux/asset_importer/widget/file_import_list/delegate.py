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


class FileImportListDelegate(ui.AbstractItemDelegate):
    __DEFAULT_HEIGHT_PIXEL = 24
    __DEFAULT_SPACER_PIXEL = 8

    def __init__(self):
        super().__init__()

        self._default_attr = {
            "_frames": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._frames = {}

    @property
    def frames(self) -> dict:
        return self._frames

    def build_widget(self, _model, item, column_id, _level, _expanded):
        """Create a widget per item"""
        if item is None or column_id != 0:
            return

        self._frames[id(item)] = ui.Frame()
        with self._frames[id(item)]:
            with ui.HStack(height=ui.Pixel(self.__DEFAULT_HEIGHT_PIXEL)):
                ui.Spacer(width=ui.Pixel(self.__DEFAULT_SPACER_PIXEL), height=0)
                valid, _ = item.is_valid(item.path, show_warning=False)
                ui.Label(
                    str(item.path),
                    width=0,
                    identifier="file_path",
                    tooltip=str(item.path),
                    style_type_name_override=(
                        "PropertiesPaneSectionTreeItem" if valid else "PropertiesPaneSectionTreeItemError"
                    ),
                )

                ui.Spacer(width=ui.Pixel(self.__DEFAULT_SPACER_PIXEL), height=0)

    def destroy(self):
        _reset_default_attrs(self)

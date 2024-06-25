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

from functools import partial
from typing import Dict

from omni import ui
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class TextureImportListDelegate(ui.AbstractItemDelegate):
    __DEFAULT_HEIGHT_PIXEL = 24
    __DEFAULT_SPACER_PIXEL = 8
    __COMBOBOX_WIDTH_PIXEL = 160

    _TEXTURE_TYPE_IMPORT_ENABLED_MAP = {
        _TextureTypes.DIFFUSE: True,
        _TextureTypes.ROUGHNESS: True,
        _TextureTypes.ANISOTROPY: False,
        _TextureTypes.METALLIC: True,
        _TextureTypes.EMISSIVE: True,
        _TextureTypes.NORMAL_OGL: True,
        _TextureTypes.NORMAL_DX: True,
        _TextureTypes.NORMAL_OTH: True,
        _TextureTypes.HEIGHT: True,
        _TextureTypes.TRANSMITTANCE: False,
        _TextureTypes.MEASUREMENT_DISTANCE: False,
        _TextureTypes.SINGLE_SCATTERING: False,
        _TextureTypes.OTHER: True,
    }

    def __init__(self):
        super().__init__()

        self._default_attr = {
            "_frames": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._frames = {}

    @property
    def frames(self) -> Dict:
        return self._frames

    def build_widget(self, _model, item, column_id, _level, _expanded):
        """Create a widget per item"""
        if item is None or column_id != 0:
            return

        # Only display texture types that can be populated
        texture_types = [t.value for t in _TextureTypes if self._TEXTURE_TYPE_IMPORT_ENABLED_MAP.get(t, False)]
        if item.texture_type.value in texture_types:
            selected_texture_type = texture_types.index(item.texture_type.value)
        else:
            selected_texture_type = _TextureTypes.OTHER

        self._frames[id(item)] = ui.Frame()
        with self._frames[id(item)]:
            with ui.HStack(height=ui.Pixel(self.__DEFAULT_HEIGHT_PIXEL)):
                ui.Spacer(width=ui.Pixel(self.__DEFAULT_SPACER_PIXEL), height=0)

                with ui.VStack(width=ui.Pixel(self.__COMBOBOX_WIDTH_PIXEL)):
                    ui.Spacer(width=0)
                    texture_type_combobox = ui.ComboBox(
                        selected_texture_type, *texture_types, height=0, identifier="texture_type"
                    )
                    texture_type_combobox.model.add_item_changed_fn(partial(self._on_item_type_changed, item))
                    ui.Spacer(width=0)

                ui.Spacer(width=ui.Pixel(self.__DEFAULT_SPACER_PIXEL), height=0)
                # TODO Bug OM-92725: Cannot use scroll view for the label only. Need to scroll the entire frame
                valid, _ = item.is_valid(item.path, show_warning=False)
                ui.Label(
                    item.path.name,
                    width=0,
                    identifier="file_path",
                    tooltip=str(item.path),
                    style_type_name_override=(
                        "PropertiesPaneSectionTreeItem" if valid else "PropertiesPaneSectionTreeItemError"
                    ),
                )
                ui.Spacer(width=ui.Pixel(self.__DEFAULT_SPACER_PIXEL), height=0)

    def _on_item_type_changed(self, item, model, _):
        selected_index = model.get_item_value_model().get_value_as_int()
        item.texture_type = [t for t in _TextureTypes if self._TEXTURE_TYPE_IMPORT_ENABLED_MAP.get(t, False)][
            selected_index
        ]

    def destroy(self):
        _reset_default_attrs(self)

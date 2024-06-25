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

from typing import TYPE_CHECKING, List

import omni.ui as ui
from omni.flux.property_widget_builder.delegates.default import DefaultField as _DefaultField
from omni.flux.property_widget_builder.delegates.int_value.bytes_to_human_read import BytesToHuman as _BytesToHuman
from omni.flux.property_widget_builder.delegates.string_value.default_label import NameField
from omni.flux.property_widget_builder.delegates.string_value.file_access import FileAccess as _FileAccess
from omni.flux.property_widget_builder.delegates.string_value.file_flags import FileFlags as _FileFlags
from omni.flux.property_widget_builder.delegates.string_value.multiline_field import MultilineField as _MultilineField
from omni.flux.property_widget_builder.widget import Delegate as _Delegate
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import ItemModel as _ItemModel


class FileDelegate(_Delegate):
    """Delegate of the tree"""

    @property
    def default_attrs(self):
        default_attrs = super().default_attrs
        default_attrs.update({})
        return default_attrs

    def _build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return None
        if column_id == 0:
            builder = NameField()
            return builder.build_ui(item)
        if column_id == 1:
            if item.attribute == "size":
                attribute_builder = _BytesToHuman()
                return attribute_builder.build_ui(item)
            if item.attribute == "access":
                attribute_builder = _FileAccess()
                return attribute_builder.build_ui(item)
            if item.attribute == "flags":
                attribute_builder = _FileFlags()
                return attribute_builder.build_ui(item)
            is_multiline, line_count = self._is_multiline_field(item.value_models)
            if is_multiline:
                attribute_builder = _MultilineField(line_count)
                return attribute_builder.build_ui(item)
            attribute_builder = _DefaultField(ui.StringField)
            return attribute_builder.build_ui(item)
        return None

    def _is_multiline_field(self, values: List["_ItemModel"]):
        for value in values:
            if value.multiline[0]:
                return value.multiline
        return values[0].multiline

    def destroy(self):
        super().destroy()
        _reset_default_attrs(self)

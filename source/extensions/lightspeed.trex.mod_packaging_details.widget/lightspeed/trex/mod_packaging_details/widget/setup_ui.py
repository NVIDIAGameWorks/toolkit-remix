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
import omni.usd
from lightspeed.layer_manager.core import LSS_LAYER_MOD_NAME as _LSS_LAYER_MOD_NAME
from lightspeed.layer_manager.core import LSS_LAYER_MOD_NOTES as _LSS_LAYER_MOD_NOTES
from lightspeed.layer_manager.core import LSS_LAYER_MOD_VERSION as _LSS_LAYER_MOD_VERSION
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.packaging.core import ModPackagingSchema as _ModPackagingSchema
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl


class ModPackagingDetailsWidget:
    def __init__(self, context_name: str = ""):
        self._default_attr = {
            "_context_name": None,
            "_layer_manager": None,
            "_last_valid_name": None,
            "_last_valid_version": None,
            "_name_field": None,
            "_sub_name_field_changed": None,
            "_sub_name_field_end": None,
            "_version_field": None,
            "_sub_version_field_changed": None,
            "_sub_version_field_end": None,
            "_details_field": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._layer_manager = _LayerManagerCore(self._context_name)
        self._last_valid_name = ""
        self._last_valid_version = ""

        self.__create_ui()

    @property
    def mod_name(self) -> str:
        """
        Get the desired packaged mod name.
        """
        return self._name_field.model.get_value_as_string()

    @property
    def mod_version(self) -> str:
        """
        Get the desired packaged mod version.
        """
        return self._version_field.model.get_value_as_string()

    @property
    def mod_details(self) -> str:
        """
        Get the desired packaged mod details text.
        """
        return self._details_field.model.get_value_as_string()

    def show(self, value: bool):
        """
        Show or hide this widget.
        This will trigger refreshes on show.
        """
        if value:
            self._update_default_values()

    def __create_ui(self):
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(8))
            ui.Label("Name", name="PropertiesPaneSectionTitle")
            ui.Spacer(height=ui.Pixel(4))
            self._name_field = ui.StringField(identifier="name_field")
            self._sub_name_field_changed = self._name_field.model.subscribe_value_changed_fn(self._update_name_valid)
            self._sub_name_field_end = self._name_field.model.subscribe_end_edit_fn(self._on_name_field_end_edit)

            ui.Spacer(height=ui.Pixel(16))

            ui.Label("Version", name="PropertiesPaneSectionTitle")
            ui.Spacer(height=ui.Pixel(4))
            self._version_field = ui.StringField(identifier="version_field")
            self._sub_version_field_changed = self._version_field.model.subscribe_value_changed_fn(
                self._update_version_valid
            )
            self._sub_version_field_end = self._version_field.model.subscribe_end_edit_fn(
                self._on_version_field_end_edit
            )

            ui.Spacer(height=ui.Pixel(16))

            ui.Label("Details", name="PropertiesPaneSectionTitle")
            ui.Spacer(height=ui.Pixel(4))
            self._details_field = ui.StringField(multiline=True, height=ui.Pixel(90), identifier="details_field")

    def _update_default_values(self):
        replacement_layer = self._layer_manager.get_layer(_LayerType.replacement)

        # Update default mod name
        if _LSS_LAYER_MOD_NAME in replacement_layer.customLayerData:
            mod_name = replacement_layer.customLayerData[_LSS_LAYER_MOD_NAME]
        else:
            root_layer = omni.usd.get_context(self._context_name).get_stage().GetRootLayer()
            if root_layer:
                mod_name = _OmniUrl(root_layer.realPath).stem
            else:
                mod_name = _OmniUrl(replacement_layer.realPath).stem
        self._last_valid_name = mod_name
        self._name_field.model.set_value(mod_name)

        # Update default mod version
        mod_version = replacement_layer.customLayerData.get(_LSS_LAYER_MOD_VERSION, "1.0.0")
        self._last_valid_version = mod_version
        self._version_field.model.set_value(mod_version)

        # Update default mod details
        if _LSS_LAYER_MOD_NOTES in replacement_layer.customLayerData:
            self._details_field.model.set_value(replacement_layer.customLayerData[_LSS_LAYER_MOD_NOTES])

    def _update_name_valid(self, *_):
        error = None
        try:
            _ModPackagingSchema.is_not_empty(self._name_field.model.get_value_as_string().strip())
        except ValueError as e:
            error = str(e)
        is_valid = not bool(error)

        self._name_field.style_type_name_override = "Field" if is_valid else "FieldError"
        self._name_field.tooltip = "" if is_valid else error
        return is_valid

    def _on_name_field_end_edit(self, model):
        if self._update_name_valid():
            self._last_valid_name = model.get_value_as_string().strip()
        model.set_value(self._last_valid_name)

    def _update_version_valid(self, *_):
        error = None
        try:
            _ModPackagingSchema.is_valid_version(self._version_field.model.get_value_as_string().strip())
        except ValueError as e:
            error = str(e)
        is_valid = not bool(error)

        self._version_field.style_type_name_override = "Field" if is_valid else "FieldError"
        self._version_field.tooltip = "" if is_valid else error
        return is_valid

    def _on_version_field_end_edit(self, model):
        if self._update_version_valid():
            self._last_valid_version = model.get_value_as_string().strip()
        model.set_value(self._last_valid_version)

    def destroy(self):
        _reset_default_attrs(self)

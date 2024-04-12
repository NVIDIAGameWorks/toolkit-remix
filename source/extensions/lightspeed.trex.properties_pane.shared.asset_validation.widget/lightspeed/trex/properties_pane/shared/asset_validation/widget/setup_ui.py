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
import carb
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.path_utils import read_json_file as _read_json_file
from omni.flux.validator.manager.core import ManagerCore
from omni.flux.validator.manager.widget import ValidatorManagerWidget as _ValidatorManagerWidget


class AssetValidationPane:
    def __init__(self, context_name: str, schema_path: str):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_schema": None,
            "_context": None,
            "_root_frame": None,
            "_asset_validation_collapsable_frame": None,
            "_validation_widget": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._schema = _read_json_file(carb.tokens.get_tokens_interface().resolve(schema_path))
        self._context = omni.usd.get_context(context_name)

        self.__create_ui()

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.ScrollingFrame(
                name="PropertiesPaneSection",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(24))
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        self._validation_widget = _ValidatorManagerWidget(
                            core=ManagerCore(self._schema), use_global_style=True
                        )
                    ui.Spacer(height=ui.Pixel(8))

    def show(self, value):
        self._root_frame.visible = value
        if value:
            self._validation_widget.refresh()

    def destroy(self):
        _reset_default_attrs(self)

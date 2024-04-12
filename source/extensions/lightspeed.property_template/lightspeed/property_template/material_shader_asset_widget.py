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
from lightspeed.tool.material.widget import MaterialButtons
from omni.kit.property.material.scripts.usd_attribute_widget import UsdMaterialAttributeWidget
from pxr import UsdShade


class ShaderAssetWidget(UsdMaterialAttributeWidget):
    def __init__(self, title: str, extension_path: str):
        super().__init__(title=title, schema=UsdShade.Shader, include_names=[], exclude_names=[])
        self._button = MaterialButtons()

    def build_items(self):
        # self._collapsable_frame.name = "Frame"  # to have dark background
        with ui.VStack(spacing=8):
            ui.Label(
                "Please do NOT change the source asset MDL path attribute. Please uses the tool buttons bellow",
                name="label",
                alignment=ui.Alignment.LEFT_TOP,
            )
            with ui.CollapsableFrame(title="Tools", collapsed=False, height=0, style=self._button.get_style()):
                with ui.HStack(spacing=8):
                    self._button.create(48)
            super().build_items()

    def clean(self):
        self._button.clean()
        super().clean()


class MaterialAssetWidget(UsdMaterialAttributeWidget):
    def __init__(self, title: str, extension_path: str):
        super().__init__(title=title, schema=UsdShade.Material, include_names=[], exclude_names=[])
        self._button = MaterialButtons()

    def build_items(self):
        # self._collapsable_frame.name = "Frame"  # to have dark background
        with ui.VStack(spacing=8):
            ui.Label(
                "Please do NOT change the source asset MDL path attribute. Please uses the tool buttons bellow",
                name="label",
                alignment=ui.Alignment.LEFT_TOP,
            )
            with ui.CollapsableFrame(title="Tools", collapsed=False, height=0, style=self._button.get_style()):
                with ui.HStack(spacing=8):
                    self._button.create(48)
            super().build_items()

    def clean(self):
        self._button.clean()
        super().clean()

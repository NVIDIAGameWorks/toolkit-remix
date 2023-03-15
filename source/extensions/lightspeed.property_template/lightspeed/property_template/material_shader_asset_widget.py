"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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

"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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

"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui
from lightspeed.trex.layout.shared import SetupUI as ReplicatorLayout


class SetupUI(ReplicatorLayout):
    def _create_layout(self):
        with ui.VStack():
            ui.Label("Texture Craft layout", alignment=ui.Alignment.CENTER)
            with ui.HStack():
                ui.Spacer()
                ui.StringField(height=50)
                ui.Spacer()
            ui.Spacer()

    @property
    def button_name(self) -> str:
        return "TextureCraft"

    @property
    def button_priority(self) -> int:
        return 20

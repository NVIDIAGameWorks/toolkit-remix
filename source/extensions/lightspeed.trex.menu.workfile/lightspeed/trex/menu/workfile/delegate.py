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


class Delegate(ui.MenuDelegate):
    def build_item(self, item):
        with ui.ZStack():
            ui.Rectangle(height=ui.Pixel(24), name="MenuBurgerFloatingBackground")
            with ui.HStack():
                ui.Label(item.text, width=ui.Pixel(60))
                ui.Label(item.hotkey_text, name="MenuBurgerHotkey", alignment=ui.Alignment.RIGHT_CENTER)

    def build_title(self, item):
        pass

    def build_status(self, item):
        pass

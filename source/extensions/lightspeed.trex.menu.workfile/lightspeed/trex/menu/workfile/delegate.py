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

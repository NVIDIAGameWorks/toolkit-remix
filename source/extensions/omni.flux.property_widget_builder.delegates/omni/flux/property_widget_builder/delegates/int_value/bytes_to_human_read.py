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

__all__ = ("BytesToHuman",)

import math

import omni.ui as ui

from ..base import AbstractField


class BytesToHuman(AbstractField):
    """Delegate of the tree"""

    @staticmethod
    def convert_size(size_bytes, _item_model):
        """Convert bytes to something more readable"""
        size_bytes = int(size_bytes)
        if size_bytes == 0:
            return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"

    def build_ui(self, item) -> list[ui.Widget]:
        widgets = []

        with ui.HStack(height=ui.Pixel(24)):
            for i in range(item.element_count):

                item.value_models[i].set_display_fn(self.convert_size)

                style_name = f"{self.style_name}Read" if item.value_models[i].read_only else self.style_name

                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
                    widget = ui.StringField(
                        model=item.value_models[i],
                        read_only=item.value_models[i].read_only,
                        style_type_name_override=style_name,
                    )
                    self.set_dynamic_tooltip_fn(widget, item.value_models[i])
                    widgets.append(widget)
                    ui.Spacer(height=ui.Pixel(2))
        return widgets

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

__all__ = ("FileAccess",)

import omni.client
import omni.ui as ui

from ..base import AbstractField


class FileAccess(AbstractField):
    """Delegate of the tree"""

    @staticmethod
    def convert(value, _item_model):
        # convert access to human readable value
        text = "Read" if value & omni.client.AccessFlags.READ else "Can't read"
        text += "\nWrite" if value & omni.client.AccessFlags.WRITE else "\nCan't write"
        text += "\nAdmin" if value & omni.client.AccessFlags.ADMIN else "\nNot admin"
        return text

    def build_ui(self, item) -> list[ui.Widget]:  # noqa PLW0221
        widgets = []
        with ui.HStack(height=ui.Pixel(20 * 3)):
            for i in range(item.element_count):
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
                    item.value_models[i].set_display_fn(self.convert)
                    read_only = item.value_models[i].read_only
                    # string field is bigger than 16px h
                    widget = ui.StringField(
                        model=item.value_models[i],
                        read_only=read_only,
                        style_type_name_override=f"{self.style_name}Read" if read_only else self.style_name,
                    )
                    self.set_dynamic_tooltip_fn(widget, item.value_models[i])
                    widgets.append(widget)
                    ui.Spacer(height=ui.Pixel(2))
        return widgets

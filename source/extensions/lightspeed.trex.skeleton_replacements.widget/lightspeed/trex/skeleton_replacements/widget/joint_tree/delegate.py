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
from omni.flux.utils.widget.tree_widget import TreeDelegateBase as _TreeDelegateBase

from .item_model import JointItem
from .model import JointTreeModel


class JointDelegate(_TreeDelegateBase):
    ROW_HEIGHT = 24
    HEADER_DICT = {0: "Originally Bound Joint", 1: "", 2: "Driving Capture Joint"}

    def _build_widget(self, model: JointTreeModel, item: JointItem, column_id: int, level: int, expanded: bool):
        """Create a widget per column per item"""
        with ui.HStack(spacing=8):
            item_value_model = model.get_item_value_model(item, column_id)
            if column_id == 0:
                item.widget = ui.Label(
                    item_value_model.as_string.rsplit("/", 1)[-1],
                    style_type_name_override="Text",
                    height=self.ROW_HEIGHT,
                    width=ui.Fraction(1),
                    tooltip=item_value_model.as_string,
                    ellided_text=True,
                )
                ui.Spacer(width=0)
            if column_id == 1:
                ui.Spacer()
                ui.Image("", name="ArrowsLeftRight", width=self.ROW_HEIGHT, height=self.ROW_HEIGHT)
                ui.Spacer()
            if column_id == 2:
                ui.ComboBox(
                    item.remap_model(),
                    height=self.ROW_HEIGHT,
                    tooltip="Choose the best joint match for the captured joint on the replacement skeleton",
                )
                ui.Spacer(width=0)  # show a little highlight at the end of the line

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(
                self.HEADER_DICT[column_id],
                alignment=ui.Alignment.CENTER,
                style_type_name_override=style_type_name,
                height=self.ROW_HEIGHT,
            )

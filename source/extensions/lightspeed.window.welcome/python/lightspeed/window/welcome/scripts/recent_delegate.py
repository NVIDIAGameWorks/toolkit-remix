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
import os

import omni.ui as ui

from .recent_model import HEADER_DICT


class RecentDelegate(ui.AbstractItemDelegate):
    def __init__(self):
        """Window to list all content"""
        super().__init__()
        self.__default_attr = {}
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.ZStack():
                ui.Rectangle(name="item")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(5))
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(5))
                        ui.Label(os.path.basename(item.path), name="RecentBasename")
                        ui.Label(item.path, name="RecentFullPath")
                        ui.Spacer(height=ui.Pixel(5))
                    ui.Spacer(width=ui.Pixel(5))

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        for attr, value in self.__default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)

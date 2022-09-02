"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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

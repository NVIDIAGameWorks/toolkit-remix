"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui

from .model import HEADER_DICT


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the action lister"""

    def __init__(self):
        super(Delegate, self).__init__()

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    # noinspection PyUnusedLocal
    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            ui.Label(item.path, style_type_name_override="TreeView.Item")
        elif column_id == 1:
            name = "" if item.replaced_path_valid() else "NotValid"
            ui.Label(item.replaced_path, style_type_name_override="TreeView.Item", name=name)

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

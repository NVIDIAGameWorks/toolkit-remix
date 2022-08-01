"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import functools
import os

import omni.ui as ui

from .model import HEADER_DICT

_ICONS_DIR = os.path.dirname(__file__)
for _ in range(4):
    _ICONS_DIR = os.path.dirname(_ICONS_DIR)

_ICONS_DIR = os.path.join(_ICONS_DIR, "data", "icons")
_DICT_ICONS = {
    "plus": os.path.join(_ICONS_DIR, "Plus.svg"),
    "minus": os.path.join(_ICONS_DIR, "Minus.svg"),
}


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the action lister"""

    def __init__(self):
        super().__init__()
        self.__checkbox_widgets = {}
        self.__ignore_checkbox = False

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        if column_id == 0:
            with ui.HStack(width=16 * (level + 2), height=0):
                ui.Spacer()
                if model.can_item_have_children(item):
                    # Draw the +/- icon
                    image_name = "minus" if expanded else "plus"
                    ui.Image(
                        _DICT_ICONS[image_name],
                        width=10,
                        height=10,
                        style_type_name_override="TreeView.Item",
                    )
                    ui.Spacer(width=4)

    # noinspection PyUnusedLocal
    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            checkbox = ui.CheckBox()
            checkbox.model.set_value(item.enabled)
            checkbox.model.add_value_changed_fn(functools.partial(self._on_enabled_changed, item))
            self.__checkbox_widgets[id(item)] = checkbox
        elif column_id == 1:
            if item.children and item.data_type == "stage":
                ui.Label(item.stage_path, style_type_name_override="TreeView.Item")
            elif item.children and item.data_type != "stage":
                ui.Label(item.attr_path, style_type_name_override="TreeView.Item")
            else:
                ui.Label(item.display_old_path, style_type_name_override="TreeView.Item")
        elif column_id == 2 and not item.children:
            with ui.HStack():
                ui.Spacer(width=16)
                ui.Label(item.display_new_path, style_type_name_override="TreeView.Item")

    def _on_enabled_changed(self, item, model):
        def has_child_enabled(t_item):
            for child in t_item.children:
                if child.enabled:
                    return True
                if child.children and has_child_enabled(child):
                    return True
            return False

        def enable_all_children(item, value):
            item.enabled = value
            if id(item) in self.__checkbox_widgets:
                self.__checkbox_widgets[id(item)].model.set_value(value)
            for child in item.children:
                enable_all_children(child, value)

        def enable_all_parent(item, value):
            if not value and has_child_enabled(item):
                value = True
            item.enabled = value
            if id(item) in self.__checkbox_widgets:
                self.__checkbox_widgets[id(item)].model.set_value(value)
            if item.parent:
                enable_all_parent(item.parent, value)

        if self.__ignore_checkbox:
            return
        self.__ignore_checkbox = True
        value = model.get_value_as_bool()
        item.enabled = value
        for child in item.children:
            enable_all_children(child, value)
        if item.parent:
            enable_all_parent(item.parent, value)
        self.__ignore_checkbox = False

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        super().destroy()
        self.__checkbox_widgets = None

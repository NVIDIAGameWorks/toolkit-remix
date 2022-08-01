"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Dict

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

HEADER_DICT = {0: "Enabled", 1: "Old Path", 2: "New Path"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(
        self, stage_path, attr_path, old_path, display_old_path, new_path, display_new_path, children, parent, data_type
    ):
        super().__init__()
        self.enabled = False
        self.attr_path = attr_path
        self.data_type = data_type
        self.stage_path = stage_path
        self.old_path = old_path
        self.display_old_path = display_old_path
        self.new_path = new_path
        self.display_new_path = display_new_path
        self.children = children
        self.parent = parent
        self.stage_path_model = ui.SimpleStringModel(self.stage_path)

    def __repr__(self):
        return f'"{self.path}"'


class ListModel(ui.AbstractItemModel):
    """List model of actions"""

    def __init__(self):
        super().__init__()
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self.__children = []

    def refresh(self, data: Dict):
        """Refresh the list"""
        items = []
        for stage_path, data_types in data.items():  # noqa PLR1702
            children = []
            stage_item = Item(stage_path, None, None, None, None, None, children, None, "stage")
            for data_type, data1 in data_types.items():
                if data_type == "attr":
                    for attr_path, attr_data in data1.items():
                        child_tex = []
                        parent = Item(stage_path, attr_path, None, None, None, None, child_tex, stage_item, data_type)
                        for old_path, new_path in attr_data.items():
                            child_tex.append(
                                Item(
                                    stage_path, attr_path, old_path, old_path, new_path, new_path, [], parent, data_type
                                )
                            )
                        parent.children = child_tex
                        children.append(parent)
                elif data_type == "ref":
                    for prim_path, ref_data in data1.items():
                        ref_children = []
                        parent = Item(
                            stage_path, prim_path, None, None, None, None, ref_children, stage_item, data_type
                        )
                        for _ref_type, ref_path_data in ref_data.items():
                            for old_ref, new_ref in ref_path_data.items():
                                ref_children.append(
                                    Item(
                                        stage_path,
                                        str(prim_path) + str(old_ref.assetPath),
                                        old_ref,
                                        old_ref.assetPath,
                                        new_ref,
                                        new_ref.assetPath,
                                        [],
                                        parent,
                                        data_type,
                                    )
                                )
                        parent.children = ref_children
                        children.append(parent)
            stage_item.children = children
            items.append(stage_item)
        self.__children = items
        self._item_changed(None)

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__children
        return item.children

    def get_item_value_model_count(self, item):
        """The number of columns"""
        return len(HEADER_DICT.keys())

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if column_id == 0:
            return item.stage_path_model
        return None

    def destroy(self):
        _reset_default_attrs(self)

"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import omni.client
import omni.ui as ui
from lightspeed.event.save_recent.scripts.recent_saved_file_utils import get_instance

HEADER_DICT = {0: "Recent scenarios"}


class RecentItem(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, path):
        super(RecentItem, self).__init__()
        self.path = path
        self.path_model = ui.SimpleStringModel(self.path)

        _, stat_entry = omni.client.stat(path)
        self.readable = stat_entry.flags & omni.client.ItemFlags.READABLE_FILE
        self.modified_time = stat_entry.modified_time

    def __repr__(self):
        return f'"{self.path}"'


class RecentModel(ui.AbstractItemModel):
    """List model"""

    def __init__(self):
        super(RecentModel, self).__init__()
        self.__items = []
        self.refresh_list()

    def get_items(self):
        """Get current items"""
        return self.__items

    def refresh_list(self):
        """Refresh the list"""
        data = get_instance().get_recent_file_data()
        file_paths = list(data.keys())
        self.__items = [RecentItem(path) for path in file_paths]
        self.__items.sort(key=lambda item: item.modified_time, reverse=True)
        self._item_changed(None)

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__items
        return []

    def get_item_value_model_count(self, item):
        """The number of columns"""
        return len(HEADER_DICT.keys())

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if item is None:
            return self.root
        if column_id == 0:  # noqa R503
            return item.name_model
        return None

    def destroy(self):
        self.__items = []

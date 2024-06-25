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

HEADER_DICT = {0: "Image", 1: "Tags"}


class EntityItem(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, image_path, tags):
        super().__init__()
        self.image_path = image_path
        self.image_path_model = ui.SimpleStringModel(image_path)
        self.tags = tags
        self.tags_model = ui.SimpleStringModel(tags)

    def __repr__(self):
        return f'"{self.image_path}"'


class AssetDetailTagsModel(ui.AbstractItemModel):
    """List model of textures"""

    SIZE_ADDITIONAL_THUMBNAIL = 100

    def __init__(self, core):
        super().__init__()
        self._core = core
        self.__filter_str = ""
        self.__all_items = []
        self.__image_paths = []

    def set_filter_str(self, filter_str: str):
        """Set the filter that filters names"""
        self.__filter_str = filter_str
        self.refresh_list()

    def refresh_image_paths(self, path):
        """Refresh images paths to use"""
        if not path:
            return
        self.__image_paths = self._core.get_additional_thumbnail(path)
        self.refresh_list()

    def refresh_list(self):
        """Refresh the list"""
        self.__all_items = []
        for i, image_path in enumerate(self.__image_paths):
            tag = f"tag_{i}"  # TODO: add tags
            if self.__filter_str not in tag.lower():
                continue
            self.__all_items.append(EntityItem(image_path, tag))

        self._item_changed(None)

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__all_items
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
            return self.__root
        if column_id == 0:
            return item.image_path_model
        if column_id == 1:
            return item.tags_model
        return None

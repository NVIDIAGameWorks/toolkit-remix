"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb
import omni.ui as ui

HEADER_DICT = {0: "Image", 1: "Tags"}


class EntityItem(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, image_path, tags):
        super(EntityItem, self).__init__()
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
        super(AssetDetailTagsModel, self).__init__()
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
        elif column_id == 1:
            return item.tags_model

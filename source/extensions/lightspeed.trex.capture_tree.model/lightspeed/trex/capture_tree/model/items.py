"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from omni import ui


class CaptureTreeItem(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, path, image):
        super().__init__()
        self.path = path
        self.image = image
        self.path_model = ui.SimpleStringModel(self.path)
        self.replaced_items = None
        self.total_items = None

    def __repr__(self):
        return f'"{self.path}"'

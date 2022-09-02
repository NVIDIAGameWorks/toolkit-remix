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

import omni.ui as ui

from .model_detail_popup import HEADER_DICT


class AssetDetailTagsDelegate(ui.AbstractItemDelegate):
    """Delegate of the Mapper Batcher"""

    def __init__(self, on_image_hovered_fn):
        super().__init__()
        self.__on_image_hovered_fn = on_image_hovered_fn

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.VStack():
                ui.Spacer(height=5)
                with ui.HStack():
                    ui.Spacer(width=5)
                    image = ui.Image(
                        item.image_path, width=model.SIZE_ADDITIONAL_THUMBNAIL, height=model.SIZE_ADDITIONAL_THUMBNAIL
                    )
                    image.set_mouse_hovered_fn(functools.partial(self.__on_image_hovered_fn, image))
                    ui.Spacer(width=5)
                ui.Spacer(height=5)
        elif column_id == 1:
            ui.Label(item.tags, style_type_name_override="TreeView.Item", alignment=ui.Alignment.CENTER)

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

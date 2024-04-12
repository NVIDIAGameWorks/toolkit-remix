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

"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["GraphEditTreeDelegate"]

from omni import ui
from omni.flux.utils.widget.tree_widget import TreeDelegateBase

from .items import GraphEditTreeItem
from .model import GraphEditTreeModel


class GraphEditTreeDelegate(TreeDelegateBase):
    ROW_HEIGHT = TreeDelegateBase.DEFAULT_IMAGE_ICON_SIZE
    SPACER_WIDTH_SM = ui.Pixel(4)

    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def build_branch(
        self, model: GraphEditTreeModel, item: GraphEditTreeItem, column_id: int, level: int, expanded: bool
    ):
        return

    def _build_widget(
        self, model: GraphEditTreeModel, item: GraphEditTreeItem, column_id: int, level: int, expanded: bool
    ):
        with ui.HStack(height=self.ROW_HEIGHT):
            ui.Spacer(width=self.SPACER_WIDTH_SM)
            match column_id:
                case 0:
                    ui.Label(item.name, tooltip=item.prim_path)
                case 1:
                    ui.Label(item.parent_path, tooltip=item.prim_path, elided_text=True)
                case _:
                    return

    def _build_header(self, column_id: int):
        with ui.HStack(height=self.ROW_HEIGHT):
            ui.Spacer(width=self.SPACER_WIDTH_SM)
            ui.Label(GraphEditTreeModel.COLUMN_MAP.get(column_id, ""))

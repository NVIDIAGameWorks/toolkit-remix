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

from typing import TYPE_CHECKING

from lightspeed.common.constants import HIDDEN_REMIX_CATEGORIES as _HIDDEN_REMIX_CATEGORIES
from lightspeed.common.constants import REMIX_CATEGORIES_DISPLAY_NAMES as _REMIX_CATEGORIES_DISPLAY_NAMES
from omni import ui
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class IsCategoryHiddenStateWidgetPlugin(_StageManagerStateWidgetPlugin):
    def build_icon_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        if not item.data:
            ui.Spacer(width=self._icon_size, height=self._icon_size)
            return

        hidden_category = []
        for attr in item.data.GetAttributes():
            category_name = _REMIX_CATEGORIES_DISPLAY_NAMES.get(attr.GetName(), "")
            if category_name in _HIDDEN_REMIX_CATEGORIES and attr.Get():
                hidden_category.append(category_name)
        categories = ", ".join(hidden_category)
        is_hidden = len(hidden_category) > 0
        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size,
            name="CategoriesHidden" if is_hidden else "CategoriesShown",
            tooltip=(
                f"Prim will not be visible because the {categories} {'categories' if len(hidden_category) > 1 else 'category'} are not rendered in the viewport."  # noqa E501
                if is_hidden
                else "Prim will be visible in the viewport because the category is rendered in the viewport."
            ),
            identifier="category_state_widget_image",
        )

    def build_overview_ui(self, model: "_StageManagerTreeModel"):
        pass

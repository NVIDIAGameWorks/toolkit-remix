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
from enum import Enum
from typing import List

from omni.flux.tree_panel.widget.tree.model import Item as _Item


class EnumItems(Enum):
    MOD_SETUP = "Captures / Setup"
    ASSET_REPLACEMENTS = "Asset Replacements"
    MOD_PACKAGING = "Mod Packaging"


class ModSetupItem(_Item):
    """Item of the model"""

    @property
    def component_type(self):
        return None

    def can_item_have_children(self, item):
        return False

    def on_mouse_pressed(self):
        pass

    @property
    def title(self):
        return EnumItems.MOD_SETUP.value


class AssetReplacementsItem(_Item):
    """Item of the model"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enabled = False

    @property
    def component_type(self):
        return None

    def can_item_have_children(self, item):
        return True

    def on_mouse_pressed(self):
        pass

    @property
    def title(self):
        return EnumItems.ASSET_REPLACEMENTS.value


class ModPackagingItem(_Item):
    """Item of the model"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enabled = False

    @property
    def component_type(self):
        return None

    def can_item_have_children(self, item):
        return True

    def on_mouse_pressed(self):
        pass

    @property
    def title(self):
        return EnumItems.MOD_PACKAGING.value


def create_all_items() -> List[_Item]:
    return [ModSetupItem(), AssetReplacementsItem(), ModPackagingItem()]

"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from enum import Enum
from typing import List

from omni.flux.tree_panel.widget.tree.model import Item as _Item


class EnumItems(Enum):
    MODEL_INGESTION = "Model Ingestion"
    TEXTURE_INGESTION = "Texture Ingestion"


class ModelIngestionItem(_Item):
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
        return EnumItems.MODEL_INGESTION.value


class TextureIngestionItem(_Item):
    """Item of the model"""

    @property
    def component_type(self):
        return None

    def can_item_have_children(self, item):
        return True

    def on_mouse_pressed(self):
        pass

    @property
    def title(self):
        return EnumItems.TEXTURE_INGESTION.value


def create_all_items() -> List[_Item]:
    return [ModelIngestionItem(), TextureIngestionItem()]

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

__all__ = ("OGN_FIELD_BUILDERS", "is_ogn_node_attr")

import omni.graph.core as og
from omni.flux.property_widget_builder.delegates.string_value.file_picker import FilePicker
from omni.flux.property_widget_builder.widget import Item
from omni.flux.stage_prim_picker.widget import StagePrimPickerField

from ..items import USDAttributeItem, USDRelationshipItem
from .base import USDBuilderList


def is_ogn_node_attr(item: Item, node_type: str, attr_name: str) -> bool:
    """
    Check if item is for a specific OmniGraph node type and attribute name.

    Args:
        item: The USD attribute item to check.
        node_type: The OmniGraph node type name (e.g., "my.ext.node.ConstAssetPath").
        attr_name: The attribute name to match (e.g., "inputs:value").

    Returns:
        True if item matches the node type and attribute name.
    """
    if not isinstance(item, USDAttributeItem):
        return False
    if not item.attribute_paths:
        return False
    # Check attribute name matches
    if not any(path.name == attr_name for path in item.attribute_paths):
        return False
    # Check node type via OmniGraph (NodeType.get_node_type() returns the type name string)
    prim_path = str(item.attribute_paths[0].GetPrimPath())
    node = og.get_node_by_path(prim_path)
    return node is not None and node.get_node_type().get_node_type() == node_type


OGN_FIELD_BUILDERS = USDBuilderList()

OGN_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:configPath",
    FilePicker(file_extension_options=[("*.conf", "Remix Config Files")], use_relative_paths=True),
)


@OGN_FIELD_BUILDERS.register_build(lambda item: isinstance(item, USDRelationshipItem))
def _relationship_builder(item):
    """
    Build a StagePrimPickerField for USD relationship items.

    Reads configuration from item.ui_metadata which can contain:
        - path_patterns: List of glob patterns to filter prim paths
        - prim_filter: Callable to filter prims
        - prim_types: List of prim type names to include
        - initial_items: Number of items to show initially (default: 20)
        - header_text: Text shown on the left side of dropdown header
        - header_tooltip: Tooltip shown in info icon on right side of header
        - row_build_fn: Custom row builder function with signature:
                        (prim_path: str, prim_type: str, clicked_fn: Callable | None, row_height: int) -> None
    """
    ui_metadata = item.ui_metadata
    return StagePrimPickerField(
        context_name=item.context_name,
        path_patterns=ui_metadata.get("path_patterns"),
        prim_filter=ui_metadata.get("prim_filter"),
        prim_types=ui_metadata.get("prim_types"),
        initial_items=ui_metadata.get("initial_items", 20),
        header_text=ui_metadata.get("header_text"),
        header_tooltip=ui_metadata.get("header_tooltip"),
        row_build_fn=ui_metadata.get("row_build_fn"),
    ).build_ui(item)

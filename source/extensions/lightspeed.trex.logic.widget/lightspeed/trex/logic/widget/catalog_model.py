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

__all__ = ["ComponentNodeTypeCatalogModel", "OmniGraphNodeQuickSearchModel"]


import omni.graph.core as og
import omni.graph.tools.ogn as ogn
from omni.graph.window.core import OmniGraphNodeTypeCatalogModel
from omni.graph.window.core.graph_config import CategoryStyles
from omni.graph.window.core.graph_config import Paths as CoreGraphConfigExtPaths
from omni.graph.window.core.graph_config import lerp_color_to_secondary, rgb_to_abgr

# Hack: Add Remix Logic categories to the hardcoded node catalog
CategoryStyles.STYLE_BY_CATEGORY.update(
    {
        k: (rgb_to_abgr(v[0]), v[1], rgb_to_abgr(lerp_color_to_secondary(v[0])))
        for k, v in {
            "Act": (
                0x53B5EC,
                f"{CoreGraphConfigExtPaths.ICON_PATH}/node/type_function_noBorder_dark.svg",
            ),  # Override light blue
            "Constants": (
                0xD2D4D3,
                f"{CoreGraphConfigExtPaths.ICON_PATH}/node/type_constant_noBorder_dark.svg",
            ),  # Slightly dimmed off-white, less bright than Transform
            "Sense": (
                0x00FF8A,
                f"{CoreGraphConfigExtPaths.ICON_PATH}/node/type_event_noBorder_dark.svg",
            ),  # Bright green (minimal yellow)
            "Transform": (
                0xF2F4F3,
                f"{CoreGraphConfigExtPaths.ICON_PATH}/node/type_math_noBorder_dark.svg",
            ),  # Bright silvery off-white
        }.items()
    }
)


class ComponentNodeTypeCatalogModel(OmniGraphNodeTypeCatalogModel):
    """
    Model used by the node catalog to select nodes for dragging into the graph.
    """

    def allow_node_type(self, node_type_name: str):
        """Override of the base to filter out action-graph types"""
        if not super().allow_node_type(node_type_name):
            return False

        node_type = og.get_node_type(node_type_name)
        category_metadata = node_type.get_metadata(ogn.MetadataKeys.CATEGORIES)
        if category_metadata:
            categories = category_metadata.split(",")
            for category in categories:
                graph_filter = self._checked_get_graph_filter_from_category(category)
                if graph_filter and (graph_filter == "action"):
                    return False
        return True


class OmniGraphNodeQuickSearchModel(ComponentNodeTypeCatalogModel):
    """
    Model used by the QuickSearch window to select nodes for adding to the graph.
    """

    # Workaround for OM-99274. See note below.
    _node_created = False

    def execute(self, item):
        """The user pressed enter or clicked on an item"""
        # Mime Data has the information about USD types.
        data = self.get_drag_mime_data(item)
        if not data:
            return

        # Workaround for OM-99274. See note in omni.graph.window.core's catalog_model.py for details.
        # This check is to prevent the node being added twice once OM-99274 is fixed. It should be removed
        # at the same time as the corresponding code in omni.graph.window.core.
        if not __class__._node_created:  # noqa: SLF001
            __class__._node_created = True  # noqa: SLF001
            from .extension import RemixLogicGraphExtension  # noqa: PLC0415

            RemixLogicGraphExtension.add_node(data, False)

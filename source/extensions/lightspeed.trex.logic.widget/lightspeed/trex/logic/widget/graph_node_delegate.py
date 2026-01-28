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

import omni.graph.core as og
import omni.graph.tools.ogn as ogn
import omni.ui as ui
from omni.graph.window.core import OmniGraphModel, OmniGraphNodeDelegate
from omni.kit.graph.delegate.modern import HEADER, ICON, NODE_WIDTH_MARGIN, GraphNodeDelegateFull
from omni.kit.widget.graph.abstract_graph_node_delegate import GraphNodeDescription


class RemixLogicNodeDelegate(OmniGraphNodeDelegate):
    def node_header(self, model: OmniGraphModel, node_desc: GraphNodeDescription):
        """Override the node header to add a description of the node type."""
        (error_state, error_name, message, error_icon) = self.get_error_state(model, node_desc)
        with ui.ZStack():
            self.build_header(model[node_desc.node].name, model, node_desc, error_state)

            # override the existing tooltip
            node_type_name = model[node_desc.node].node_type_name
            namespace, _, type_name = node_type_name.rpartition(".") if node_type_name else ["", "", "Virtual Node"]
            tips = [error_name, f"{type_name} ({namespace})"]

            # Add node type description if available
            if node_type_name:
                node_type = og.get_node_type(node_type_name)
                if node_type and node_type.is_valid():
                    description = node_type.get_metadata(ogn.MetadataKeys.DESCRIPTION)
                    if description:
                        tips.append(description)

            if message:
                tips = [message] + tips
            GraphNodeDelegateFull.build_tooltip(tips)
            # Apply an error/warning icon if needed.
            if error_state != og.Severity.INFO:
                with ui.HStack():
                    ui.Spacer()
                    with ui.VStack(alignment=ui.Alignment.RIGHT_CENTER, width=HEADER["sec_height"]):
                        ui.Spacer(height=NODE_WIDTH_MARGIN + ICON["border"])
                        with ui.HStack(width=HEADER["sec_height"] - ICON["border"]):
                            with ui.ZStack(
                                height=HEADER["sec_height"] - 2 * ICON["border"], alignment=ui.Alignment.RIGHT_CENTER
                            ):
                                ui.Rectangle(style_type_name_override="Graph.Node.Icon.Background")
                                ui.Image(
                                    error_icon,
                                    height=HEADER["sec_height"] - 3 * ICON["border"],
                                    fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                )

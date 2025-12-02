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

__all__ = ["LogicGraphCore"]

import omni.graph.core as og
import omni.usd
from lightspeed.common.constants import OMNI_GRAPH_TYPE
from lightspeed.trex.utils.common.prim_utils import (
    get_prototype,
    is_in_light_group,
    is_in_mesh_group,
    is_light_asset,
    is_mesh_asset,
)
from pxr import Sdf, Usd


class LogicGraphCore:
    """
    Core logic for Remix Logic graphs.
    """

    @staticmethod
    def get_graph_root_prim(selected_prim: Usd.Prim) -> Usd.Prim | None:
        prim = get_prototype(selected_prim)
        if not prim or not (is_in_mesh_group(prim) or is_in_light_group(prim)):
            return None

        parent = prim
        while parent:
            if is_mesh_asset(parent) or is_light_asset(parent):
                return parent
            parent = parent.GetParent()

        return None

    @staticmethod
    def is_graph_prim_editable(graph: Usd.Prim) -> bool:
        """Returns True if the given graph prim is editable by the remix application"""
        if not graph:
            return False
        # We only want to edit graphs via the prim in a valid prototype location, not one of its instances
        return is_in_mesh_group(graph) or is_in_light_group(graph)

    @staticmethod
    def create_graph_at_path(
        stage: Usd.Stage, graph_root_path: Sdf.Path, name_prefix: str, evaluator_type: str = "RemixLogicGraph"
    ) -> Sdf.Path:
        graph_path = Sdf.Path(name_prefix).MakeAbsolutePath(graph_root_path)
        graph_path = omni.usd.get_stage_next_free_path(stage, graph_path, True)
        graph = og.get_global_orchestration_graphs()[0]

        # Create the global compute graph
        og.cmds.CreateGraphAsNode(
            graph=graph,
            node_name=Sdf.Path(graph_path).name,
            graph_path=graph_path,
            evaluator_name=evaluator_type,
            is_global_graph=True,
            backed_by_usd=True,
            fc_backing_type=og.GraphBackingType.GRAPH_BACKING_TYPE_FLATCACHE_SHARED,
            pipeline_stage=og.GraphPipelineStage.GRAPH_PIPELINE_STAGE_SIMULATION,
        )
        return Sdf.Path(graph_path)

    @staticmethod
    def get_existing_logic_graphs(stage: Usd.Stage, paths: list[Sdf.Path]) -> list[Usd.Prim]:
        """Get the names of the existing logic graphs under provided paths"""
        existing_graphs: list[Usd.Prim] = []
        for path in paths:
            root_prim = stage.GetPrimAtPath(path)
            for prim in Usd.PrimRange(root_prim):
                if prim.GetTypeName() == OMNI_GRAPH_TYPE:
                    existing_graphs.append(prim)
        return sorted(existing_graphs, key=lambda x: x.GetPath())

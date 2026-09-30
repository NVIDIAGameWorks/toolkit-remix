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

from unittest.mock import Mock, patch

import omni.kit.test
import omni.usd
from lightspeed.trex.logic.core import LogicGraphCore, graphs
from pxr import Sdf, Usd


class TestLogicGraphCore(omni.kit.test.AsyncTestCase):
    """
    Test LogicGraphCore functionality.
    """

    async def test_create_graph_at_path(self):
        # Arrange: Create a test prim
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage: Usd.Stage = self._context.get_stage()
        self._stage.DefinePrim("/World/TestPrim", "Xform")

        # Act: Create a graph at the path
        test_graph = LogicGraphCore.create_graph_at_path(
            self._stage, Sdf.Path("/World/TestPrim"), "TestGraph", "RemixLogicGraph"
        )

        # Verify the graph was created
        self.assertIsNotNone(test_graph)
        self.assertEqual(str(test_graph), "/World/TestPrim/TestGraph")

    def test_get_graph_root_prim_shared_cache_reuses_ancestors_and_keeps_roots_distinct(self):
        """Reuse shared ancestor results without mixing mesh and light roots."""
        # Arrange
        mesh, parent, first, second, light, light_child = [Mock(spec=Usd.Prim) for _ in range(6)]
        mesh_path = "/RootNode/meshes/mesh_0123456789ABCDEF"
        light_path = "/RootNode/lights/light_FEDCBA9876543210"
        prims = [mesh, parent, first, second, light, light_child]
        for prim, path, owner in (
            (mesh, mesh_path, None),
            (parent, f"{mesh_path}/Group", mesh),
            (first, f"{mesh_path}/Group/First", parent),
            (second, f"{mesh_path}/Group/Second", parent),
            (light, light_path, None),
            (light_child, f"{light_path}/Child", light),
        ):
            prim.GetPath.return_value = Sdf.Path(path)
            prim.GetParent.return_value = owner
        roots_by_path = {}
        with patch.object(graphs, "get_prototype", side_effect=lambda prim: prim):
            # Act
            results = [
                LogicGraphCore.get_graph_root_prim(prim, roots_by_path) for prim in (first, second, light_child, first)
            ]

        # Assert
        self.assertEqual(results, [mesh, mesh, light, mesh])
        parent.GetParent.assert_called_once_with()
        first.GetParent.assert_called_once_with()
        self.assertEqual(sum(prim.GetParent.call_count for prim in prims), 4)

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

import omni.kit.test
import omni.usd
from lightspeed.trex.logic.core import LogicGraphCore
from pxr import Sdf, Usd


class TestLogicGraphCore(omni.kit.test.AsyncTestCase):
    """
    Test LogicGraphCore functionality.
    """

    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage: Usd.Stage = self._context.get_stage()

    async def test_create_graph_at_path(self):
        # Arrange: Create a test prim
        self._stage.DefinePrim("/World/TestPrim", "Xform")

        # Act: Create a graph at the path
        test_graph = LogicGraphCore.create_graph_at_path(
            self._stage, Sdf.Path("/World/TestPrim"), "TestGraph", "RemixLogicGraph"
        )

        # Verify the graph was created
        self.assertIsNotNone(test_graph)
        self.assertEqual(str(test_graph), "/World/TestPrim/TestGraph")

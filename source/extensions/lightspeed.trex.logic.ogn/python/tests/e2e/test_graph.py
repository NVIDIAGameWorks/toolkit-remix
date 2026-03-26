"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import importlib.util
import os

import omni.graph.core as og
import omni.graph.core.tests as ogts
import omni.usd

import lightspeed.trex.logic.ogn.ogn.CounterDatabase as _CounterDatabaseMod
import lightspeed.trex.logic.ogn.ogn.SmoothDatabase as _SmoothDatabaseMod
from lightspeed.trex.logic.ogn._impl.type_resolution import standard_initialize


def _ensure_node_types_registered():
    """Register OGN node types needed for testing.

    In the minimal test harness (omni.app.test_ext.kit), OGN node types are not
    formally registered with the graph registry. The auto-generated OGN tests
    sidestep this by loading USDA templates. For programmatic node creation via
    og.Controller.edit(), the types must be explicitly registered.
    """
    nodes_dir = os.path.join(os.path.dirname(_CounterDatabaseMod.__file__), "nodes")

    for db_cls, module_name in [
        (_CounterDatabaseMod.CounterDatabase, "Counter"),
        (_SmoothDatabaseMod.SmoothDatabase, "Smooth"),
    ]:
        if db_cls.NODE_TYPE_CLASS is not None:
            continue
        spec = importlib.util.spec_from_file_location(module_name, os.path.join(nodes_dir, f"{module_name}.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        db_cls.register(getattr(mod, module_name))


class TestRemixLogicGraph(ogts.OmniGraphTestCase):
    """End-to-end tests for Remix Logic OmniGraph callback registration and connection validation."""

    async def setUp(self):
        await super().setUp()
        _ensure_node_types_registered()

    async def test_set_compute_incomplete(self):
        """Verify basic graph creation, connection, and evaluation works for Remix Logic nodes."""
        controller = og.Controller(undoable=False)
        keys = og.Controller.Keys

        # Arrange
        (
            _,
            (counter_node, smooth_node),
            _,
            _,
        ) = controller.edit(
            "/TestGraph",
            {
                keys.CREATE_NODES: [
                    ("Counter", "lightspeed.trex.logic.Counter"),
                    ("Smooth", "lightspeed.trex.logic.Smooth"),
                ],
                keys.SET_VALUES: ("Counter.inputs:defaultValue", 7.5),
                keys.CONNECT: [("Counter.outputs:value", "Smooth.inputs:input")],
            },
        )

        # Act
        await controller.evaluate()

        # Assert
        # REMIX: We don't really care about the compute() results since the runtime runs the logic for us.
        value_out = controller.attribute("outputs:value", counter_node)
        self.assertEqual(controller.get(value_out), 0.0)
        smooth_in = controller.attribute("inputs:input", smooth_node)
        self.assertEqual(controller.get(smooth_in), 0.0)

    async def test_callback_survives_node_delete(self):
        """Verify callback registration works on a node created after another is deleted.

        Regression test: previously, stale per-handle state could prevent callback
        registration on a new node that received a recycled handle.
        """
        controller = og.Controller(undoable=False)
        keys = og.Controller.Keys

        # Arrange
        (_, (_, node_b), _, _) = controller.edit(
            "/TestGraph",
            {
                keys.CREATE_NODES: [
                    ("NodeA", "lightspeed.trex.logic.Counter"),
                    ("NodeB", "lightspeed.trex.logic.Counter"),
                ],
            },
        )
        omni.usd.get_context().get_stage().RemovePrim(node_b.get_prim_path())
        await controller.evaluate()

        (_, (node_c,), _, _) = controller.edit(
            "/TestGraph",
            {keys.CREATE_NODES: [("NodeC", "lightspeed.trex.logic.Smooth")]},
        )

        # Act
        standard_initialize(None, node_c)
        controller.edit(
            "/TestGraph",
            {keys.CONNECT: [("NodeA.outputs:value", "NodeC.inputs:input")]},
        )
        await controller.evaluate()

        # Assert
        input_attr = node_c.get_attribute("inputs:input")
        upstream = input_attr.get_upstream_connections()
        self.assertEqual(len(upstream), 1)

    async def test_callback_registers_on_every_call(self):
        """Verify standard_initialize can be called multiple times without breaking the callback."""
        controller = og.Controller(undoable=False)
        keys = og.Controller.Keys

        # Arrange
        (_, (_, node_b), _, _) = controller.edit(
            "/TestGraph",
            {
                keys.CREATE_NODES: [
                    ("NodeA", "lightspeed.trex.logic.Counter"),
                    ("NodeB", "lightspeed.trex.logic.Smooth"),
                ],
            },
        )

        # Act
        standard_initialize(None, node_b)
        standard_initialize(None, node_b)
        standard_initialize(None, node_b)
        controller.edit(
            "/TestGraph",
            {keys.CONNECT: [("NodeA.outputs:value", "NodeB.inputs:input")]},
        )
        await controller.evaluate()

        # Assert
        input_attr = node_b.get_attribute("inputs:input")
        upstream = input_attr.get_upstream_connections()
        self.assertEqual(len(upstream), 1)

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

import asyncio

import omni.graph.core as og
import omni.kit.commands
import omni.usd
from lightspeed.trex.logic.widget.graph_window import RemixLogicGraphWindow
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from pxr import Sdf, UsdGeom

_GRAPH_PATH = "/RootNode/meshes/mesh_0000000000000001/TestGraph"


class TestLogicGraphViewport(AsyncTestCase):
    """Exercise graph nodes and connections through the graph window."""

    async def setUp(self):
        """Open a real stage and graph window."""
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._window = RemixLogicGraphWindow("LogicGraphVisualTest", width=1000, height=700, position_x=0, position_y=0)

    async def tearDown(self):
        """Close the graph window and stage."""
        self._window.destroy()
        self._window = None
        await self._context.close_stage_async()

    async def test_open_graph_displays_nodes_connections_and_removes_deleted_node(self):
        """Display graph data and remove the selected node through a public command."""
        stage = self._context.get_stage()
        UsdGeom.Xform.Define(stage, "/RootNode/meshes/mesh_0000000000000001")
        connections = [
            ("constA.inputs:value", "add.inputs:a"),
            ("constA.inputs:value", "add.inputs:b"),
            ("add.outputs:sum", "simple.inputs:a_float"),
        ]
        keys = og.Controller.Keys
        og.Controller.edit(
            {"graph_path": _GRAPH_PATH, "evaluator_name": "component"},
            {
                keys.CREATE_NODES: [
                    ("constA", "omni.graph.nodes.ConstantFloat"),
                    ("add", "omni.graph.nodes.Add"),
                    ("simple", "omni.graph.tutorials.SimpleData"),
                ],
                keys.SET_VALUES: [("constA.inputs:value", 1.5)],
                keys.CONNECT: connections,
            },
        )

        # Open the graph through its selection dialog. The editor must show all nodes and connections.
        edit = await self.__wait_for(
            lambda: ui_test.find(f"{self._window.title}//Frame/**/Button[*].name=='Edit Graph'")
        )
        await edit.click()
        graph = await self.__wait_for(lambda: ui_test.find("Select Graph To Edit//Frame/**/Label[*].text=='TestGraph'"))
        await graph.click()
        select = await self.__wait_for(lambda: ui_test.find("Select Graph To Edit//Frame/**/Button[*].text=='Select'"))
        await self.__wait_for(lambda: select.widget.enabled)
        await select.click()
        widget = self._window.get_graph_widget()
        await self.__wait_for(
            lambda: (
                widget.model is not None
                and widget.get_current_graph_item() == stage.GetPrimAtPath(_GRAPH_PATH)
                and len(widget._graph_view._node_widgets) == 3
                and all(
                    node.computed_width > 0 and node.computed_height > 0
                    for node in widget._graph_view._node_widgets.values()
                )
            )
        )
        model = widget.model
        view = widget._graph_view
        self.assertEqual(model.get_graph(None).get_path_to_graph(), _GRAPH_PATH)
        self.assertEqual(
            set(model.nodes), {stage.GetPrimAtPath(f"{_GRAPH_PATH}/{name}") for name in ("constA", "add", "simple")}
        )
        self.assertEqual(set(view._node_widgets), set(model.nodes))
        self.assertTrue(all(node.visible for node in view._node_widgets.values()))
        for source, target in connections:
            self.assertEqual(model[Sdf.Path(f"{_GRAPH_PATH}/{target}")].inputs, [Sdf.Path(f"{_GRAPH_PATH}/{source}")])
        curves_query = f"{self._window.title}//Frame/**/FreeBezierCurve[*]"
        await self.__wait_for(lambda: len(ui_test.find_all(curves_query)) >= 3)
        self.assertTrue(all(curve.widget.visible for curve in ui_test.find_all(curves_query)))

        # Select a displayed node and delete it. USD and the editor must retain only the other nodes and connection.
        nodes_query = f"{self._window.title}//Frame/**/Label[*].style_type_name_override=='Graph.Node.Label.ZoomIn'"
        node_prim = stage.GetPrimAtPath(f"{_GRAPH_PATH}/constA")
        # The graph rebuild can replace labels. Read the header from the current node widget.

        def node_position():
            header = view._node_widgets[node_prim].header_frame
            center = ui_test.WidgetRef(header, self._window.title).center
            position = ui_test.Vec2(*view.mouse_to_screen(center.x, center.y))
            return (
                position
                if view.smooth_zoom and 0 < position.x < self._window.width and 0 < position.y < self._window.height
                else None
            )

        position = await self.__wait_for(node_position)
        await ui_test.input.emulate_mouse_move(position)
        await ui_test.input.emulate_mouse_move_and_click(position)
        await self.__wait_for(lambda: view.selection == [node_prim])
        omni.kit.commands.execute("DeletePrims", paths=[f"{_GRAPH_PATH}/constA"])
        await self.__wait_for(
            lambda: len(ui_test.find_all(nodes_query)) == 2 and len(ui_test.find_all(curves_query)) == 1
        )
        self.assertFalse(stage.GetPrimAtPath(f"{_GRAPH_PATH}/constA"))
        self.assertCountEqual(
            [label.widget.text for label in ui_test.find_all(nodes_query)],
            ["Add", "Tutorial Node: Attributes With Simple Data"],
        )
        self.assertTrue(ui_test.find_all(curves_query)[0].widget.visible)

    async def __wait_for(self, condition):
        async with asyncio.timeout(10):
            while not (result := condition()):
                await ui_test.human_delay()
        return result

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

import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import carb
import omni.graph.core as og
import omni.kit.test
import omni.ui as ui
import omni.usd
from lightspeed.trex.logic.widget.graph_widget import RemixLogicGraphWidget
from omni.graph.window.core import OmniGraphWindow, _is_kit_version_or_greater
from omni.graph.window.core.graph_config import Supports
from omni.kit.test_suite.helpers import wait_stage_loading

EXT_PATH = Path(carb.tokens.get_tokens_interface().resolve("${lightspeed.trex.logic.widget}"))


class OgRemixLogicTestGraphWidget(RemixLogicGraphWidget):
    def on_build_startup(self):
        # Start with an empty graph.
        pass


class TestOgWindowComponentUI(omni.kit.test.AsyncTestCase):
    TEST_GRAPH_PATH = "/World/TestGraph"

    async def setUp(self):
        self._usd_dir = EXT_PATH.absolute().resolve().joinpath("data/tests")
        self._graph_window = None

        # Patch is_graph_editable to always return True so test graphs pass remix specific check
        # This affects header display for editable graphs.
        self._is_graph_editable_patcher = patch(
            "lightspeed.trex.logic.widget.graph_widget.RemixLogicGraphWidget.is_graph_editable",
            return_value=True,
        )
        self._is_graph_editable_patcher.start()

    async def tearDown(self):
        if self._is_graph_editable_patcher:
            self._is_graph_editable_patcher.stop()
            self._is_graph_editable_patcher = None

        if self._graph_window:
            self._graph_window.destroy()
            self._graph_window = None

    async def __initialize_test_window(self):
        await omni.usd.get_context().new_stage_async()
        stage = omni.usd.get_context().get_stage()

        # OM-79384, hack to fix failing tests, see release notes for omni.graph.window.core 1.44.1
        # and version 1.3.16 of this extension.
        # rather than use OgRemixLogicTestWindow (previous behavior), we now create an OmniGraphWindow object and
        # pass in a function to call during on_build_window. This way Pybind11 does not delete the parent object from
        # its
        # cache during garbage collection which results in the following error when these tests are run on Linux.
        #    TypeError: __init__(self, lightspeed.trex.logic.widget..) called with invalid `self` argument
        graph_window = OmniGraphWindow(
            "OgWindowComponentTest",
            createWidgetFunc=OgRemixLogicTestGraphWidget,
            flags=ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_TITLE_BAR | ui.WINDOW_FLAGS_NO_RESIZE,
            position_x=0,
            position_y=0,
            width=1200,
            height=800,
        )

        self._graph_window = graph_window
        return stage, graph_window

    async def __import_graph(self, graph_window, graph_prim):
        graph_window._import_prims(None, [graph_prim])

        async with asyncio.timeout(10):
            while (
                graph_window._main_widget is None
                or graph_window._main_widget.model is None
                or graph_window._main_widget.get_current_graph_item() != graph_prim
            ):
                await omni.kit.app.get_app().next_update_async()

    @unittest.skip("Skipping test_compound_nodes. Compound subgraphs are disabled via monkey patch for now.")
    @unittest.skipIf(os.name == "posix" and os.getenv("ETM_ACTIVE"), "OM-79384: Skip test in Linux ETM")
    @unittest.skipIf(not _is_kit_version_or_greater((105, 1)), "105.1 required for compound subgraphs")
    async def test_compound_nodes(self):
        # requires kit support for compounds
        if not Supports.compound_graphs():
            return

        _, graph_window = await self.__initialize_test_window()

        controller = og.Controller()
        usd_context = omni.usd.get_context()

        test_file_path = self._usd_dir.joinpath("compound_types.usda").absolute()
        await usd_context.open_stage_async(str(test_file_path))
        await wait_stage_loading()

        await self.__import_graph(graph_window, controller.prim("/World/PushGraph"))

        model = graph_window._main_widget.model
        self.assertEqual(model.get_graph(None).get_path_to_graph(), "/World/PushGraph")
        self.assertEqual(
            {node.GetName() for node in model.nodes},
            {
                "bundlecompound",
                "constantcompound",
                "debugcompound",
                "flowcompound",
                "functioncompound",
                "genericcompound",
                "inputcompound",
                "mathcompound",
                "scenegraphcompound",
                "compoundnode",
                "uicompound",
                "animationcompound",
            },
        )

    @unittest.skip("Skipping test_enter_compound. Compound subgraphs are disabled via monkey patch for now.")
    @unittest.skipIf(os.name == "posix" and os.getenv("ETM_ACTIVE"), "OM-79384: Skip test in Linux ETM")
    @unittest.skipIf(not _is_kit_version_or_greater((105, 1)), "105.1 required for compound subgraphs")
    async def test_enter_compound(self):
        # requires kit support for compounds
        if not Supports.compound_subgraphs():
            return

        stage, graph_window = await self.__initialize_test_window()

        controller = og.Controller()
        keys = og.Controller.Keys
        (graph, _, _, _) = controller.edit(
            self.TEST_GRAPH_PATH,
            {
                keys.CREATE_NODES: [
                    ("constA", "omni.graph.nodes.ConstantFloat"),
                    ("add", "omni.graph.nodes.Add"),
                    ("simple", "omni.graph.tutorials.SimpleData"),
                ],
                keys.SET_VALUES: [("constA.inputs:value", 1.5)],
                keys.CONNECT: [
                    ("constA.inputs:value", "add.inputs:a"),
                    ("constA.inputs:value", "add.inputs:b"),
                    ("add.outputs:sum", "simple.inputs:a_float"),
                ],
            },
        )

        await self.__import_graph(graph_window, controller.prim(graph.get_path_to_graph()))
        graph_window._main_widget.model.create_subgraph_compound(
            [
                controller.prim(f"{self.TEST_GRAPH_PATH}/add"),
                controller.prim(f"{self.TEST_GRAPH_PATH}/simple"),
            ]
        )

        # Verify that compound is selected after creation
        self.assertEqual(
            graph_window._main_widget.model.selection,
            [stage.GetPrimAtPath(f"{self.TEST_GRAPH_PATH}/compound")],
        )

        # Enter the compound and check its graph and connection.
        widget = graph_window._main_widget
        widget.enter_compound(controller.prim(f"{self.TEST_GRAPH_PATH}/compound"))

        compound_graph = stage.GetPrimAtPath(f"{self.TEST_GRAPH_PATH}/compound/Subgraph")
        self.assertEqual(widget.get_current_graph_item(), compound_graph)
        self.assertEqual({node.GetName() for node in widget.model[compound_graph].nodes}, {"add", "simple"})
        self.assertEqual(
            widget.model[compound_graph.GetPath().AppendChild("simple").AppendProperty("inputs:a_float")].inputs,
            [compound_graph.GetPath().AppendChild("add").AppendProperty("outputs:sum")],
        )

    async def _validate_enter_compound(self, graph_create_fn, compounds: list[str]):
        # requires kit support for compounds
        if not Supports.compound_subgraphs():
            return None

        _, graph_window = await self.__initialize_test_window()
        graph = graph_create_fn()

        await self.__import_graph(graph_window, og.Controller.prim(graph.get_path_to_graph()))

        # Enter each compound and check the current graph.
        widget = graph_window._main_widget
        for compound in compounds:
            compound_node = og.Controller.node(compound)
            widget.enter_compound(og.Controller.prim(compound))
            self.assertEqual(
                str(widget.get_current_graph_item().GetPath()),
                compound_node.get_compound_graph_instance().get_path_to_graph(),
            )

        return widget

    @unittest.skip("Skipping test_compound_no_connections. Compound subgraphs are disabled via monkey patch for now.")
    @unittest.skipIf(os.name == "posix" and os.getenv("ETM_ACTIVE"), "OM-79384: Skip test in Linux ETM")
    @unittest.skipIf(not _is_kit_version_or_greater((105, 1)), "105.1 required for compound subgraphs")
    async def test_compound_no_connections(self):
        """Check that a compound without connections retains both virtual nodes."""

        def create_graph():
            controller = og.Controller(update_usd=True)
            keys = og.Controller.Keys
            (graph, _, _, _) = controller.edit(
                self.TEST_GRAPH_PATH,
                {
                    keys.CREATE_NODES: [
                        (
                            "compound",
                            {
                                keys.CREATE_NODES: [
                                    ("add", "omni.graph.nodes.Add"),
                                ]
                            },
                        )
                    ],
                },
            )
            return graph

        widget = await self._validate_enter_compound(create_graph, [f"{self.TEST_GRAPH_PATH}/compound"])

        model = widget.model
        compound_graph = widget.get_current_graph_item()
        self.assertEqual({node.GetName() for node in model[compound_graph].nodes}, {"add"})
        self.assertEqual(model[compound_graph].ports, [])
        isolation_model = widget._isolation_model
        self.assertCountEqual(
            [isolation_model[node].type for node in isolation_model.nodes],
            ["omni.graph.nodes.Add", "InputNode", "OutputNode"],
        )
        for name in ("a", "b"):
            self.assertEqual(
                model[compound_graph.GetPath().AppendChild("add").AppendProperty(f"inputs:{name}")].inputs,
                [],
            )

    @unittest.skip("Skipping test_enter_nested_compound. Compound subgraphs are disabled via monkey patch for now.")
    @unittest.skipIf(os.name == "posix" and os.getenv("ETM_ACTIVE"), "OM-79384: Skip test in Linux ETM")
    @unittest.skipIf(not _is_kit_version_or_greater((105, 1)), "105.1 required for compound subgraphs")
    async def test_enter_nested_compound(self):
        """Check the nodes and promoted connections inside a nested compound."""

        def create_graph():
            controller = og.Controller(update_usd=True)
            keys = og.Controller.Keys
            (graph, _, _, _) = controller.edit(
                self.TEST_GRAPH_PATH,
                {
                    keys.CREATE_NODES: [
                        (
                            "compound",
                            {
                                keys.CREATE_NODES: [
                                    (
                                        "compound2",
                                        {
                                            keys.CREATE_NODES: [
                                                ("add", "omni.graph.nodes.Add"),
                                            ],
                                            keys.PROMOTE_ATTRIBUTES: [
                                                ("add.inputs:a", "inputs:val_1"),
                                                ("add.inputs:b", "inputs:val_2"),
                                                ("add.outputs:sum", "outputs:value"),
                                            ],
                                        },
                                    ),
                                ]
                            },
                        )
                    ],
                },
            )
            return graph

        widget = await self._validate_enter_compound(
            create_graph,
            [f"{self.TEST_GRAPH_PATH}/compound", f"{self.TEST_GRAPH_PATH}/compound/Subgraph/compound2"],
        )

        compound_graph = widget.get_current_graph_item()
        self.assertEqual({node.GetName() for node in widget.model[compound_graph].nodes}, {"add"})
        graph_path = compound_graph.GetPath()
        self.assertCountEqual(
            widget.model[compound_graph].ports,
            [graph_path.AppendProperty(name) for name in ("inputs:val_1", "inputs:val_2", "outputs:value")],
        )
        for source, target in (
            (graph_path.AppendProperty("inputs:val_1"), graph_path.AppendChild("add").AppendProperty("inputs:a")),
            (graph_path.AppendProperty("inputs:val_2"), graph_path.AppendChild("add").AppendProperty("inputs:b")),
        ):
            self.assertEqual(widget.model[target].inputs, [source])
        self.assertEqual(
            widget.model[graph_path.AppendProperty("outputs:value")].outputs,
            [graph_path.AppendChild("add").AppendProperty("outputs:sum")],
        )

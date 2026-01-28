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

import os
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

import carb
import omni.graph.core as og
import omni.kit.test
import omni.ui as ui
import omni.usd
from lightspeed.trex.logic.widget.catalog_model import ComponentNodeTypeCatalogModel
from lightspeed.trex.logic.widget.graph_widget import RemixLogicGraphWidget
from lightspeed.trex.logic.widget.graph_window import RemixLogicGraphWindow
from omni.graph.window.core import OmniGraphWindow, _is_kit_version_or_greater
from omni.graph.window.core.graph_config import Supports
from omni.ui.tests.test_base import OmniUiTest

EXT_PATH = Path(carb.tokens.get_tokens_interface().resolve("${lightspeed.trex.logic.widget}"))


class OgRemixLogicTestCatalogModel(ComponentNodeTypeCatalogModel):
    def allow_node_type(self, node_type_name: str):
        # Let the base class have its say.
        if not super().allow_node_type(node_type_name):
            return False

        # special case for compound nodes. This allows them, but should not impact
        # tests with no compounds in the scene
        if "local.nodes" in node_type_name:
            return True

        # We don't want to have to change the golden images every time
        # a new category or node type is added (the number of node types
        # in each category is displayed on the catalog widget).
        # So we restrict the allowed node types to a static set.
        return node_type_name in (
            "omni.graph.nodes.Add",  # Math
            "omni.graph.nodes.ConstantFloat",  # Constants
            "omni.graph.nodes.ConstantInt",  # Constants
            "omni.graph.tutorials.SimpleData",
        )  # Tutorials


class OgRemixLogicTestGraphWidget(RemixLogicGraphWidget):
    def on_build_startup(self):
        # We don't want the initial Edit/Create selection widgets, just a blank graph.
        pass


class OgRemixLogicTestWindow(RemixLogicGraphWindow):
    def on_build_window(self):
        self._main_widget = OgRemixLogicTestGraphWidget(catalog_model=OgRemixLogicTestCatalogModel())


class TestOgWindowComponentUI(OmniUiTest):
    TEST_GRAPH_PATH = "/World/TestGraph"

    async def setUp(self):
        await super().setUp()
        self._golden_img_dir = EXT_PATH.absolute().resolve().joinpath("data/tests")
        self._usd_dir = EXT_PATH.absolute().resolve().joinpath("data/tests")
        self._graph_window = None
        self._window = None

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

        self._window = None
        self._golden_img_dir = None
        await super().tearDown()

    async def __initialize_test_window(self):
        await omni.usd.get_context().new_stage_async()
        stage = omni.usd.get_context().get_stage()

        window = await self.create_test_window(width=1200, height=800)

        # OM-79384, hack to fix failing tests, see release notes for omni.graph.window.core 1.44.1
        # and version 1.3.16 of this extension.
        # rather than use OgRemixLogicTestWindow (previous behavior), we now create an OmniGraphWindow object and
        # pass in a function to call during on_build_window. This way Pybind11 does not delete the parent object from
        # its
        # cache during garbage collection which results in the following error when these tests are run on Linux.
        #    TypeError: __init__(self, lightspeed.trex.logic.widget..) called with invalid `self` argument
        graph_window = OmniGraphWindow(
            "OgWindowComponentTest",
            createWidgetFunc=partial(OgRemixLogicTestGraphWidget, catalog_model=OgRemixLogicTestCatalogModel()),
            flags=ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_TITLE_BAR | ui.WINDOW_FLAGS_NO_RESIZE,
            position_x=0,
            position_y=0,
            width=1200,
            height=800,
        )

        self._graph_window = graph_window
        self._window = window

        for _ in range(5):
            await omni.kit.app.get_app().next_update_async()

        # Close the catalog so that our golden images don't break whenever the categories or node counts change.
        graph_window._main_widget._splitter_left._button.call_clicked_fn()  # noqa: SLF001

        for _ in range(5):
            await omni.kit.app.get_app().next_update_async()

        return (stage, window, graph_window)

    async def __wait_for_window_to_draw(self):
        # It takes 6 frames for the nodes and connections to all draw in
        # their proper positions.
        for _ in range(6):
            await omni.kit.app.get_app().next_update_async()

    @unittest.skipIf(os.name == "posix" and os.getenv("ETM_ACTIVE"), "OM-79384: Skip test in Linux ETM")
    async def test_simple_graph(self):
        _, _, graph_window = await self.__initialize_test_window()

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

        graph_window._import_prims(None, [controller.prim(graph.get_path_to_graph())])  # noqa: SLF001

        await self.__wait_for_window_to_draw()
        await self.finalize_test(
            golden_img_dir=self._golden_img_dir,
            golden_img_name="lightspeed.trex.logic.widget.test_simple_graph.png",
        )

    @unittest.skip("Skipping test_compound_nodes. Compound subgraphs are disabled via monkey patch for now.")
    @unittest.skipIf(os.name == "posix" and os.getenv("ETM_ACTIVE"), "OM-79384: Skip test in Linux ETM")
    @unittest.skipIf(not _is_kit_version_or_greater((105, 1)), "105.1 required for compound subgraphs")
    async def test_compound_nodes(self):
        from omni.kit.test_suite.helpers import wait_stage_loading

        # requires kit support for compounds
        if not Supports.compound_graphs():
            return

        _, _, graph_window = await self.__initialize_test_window()

        controller = og.Controller()
        usd_context = omni.usd.get_context()

        test_file_path = self._usd_dir.joinpath("compound_types.usda").absolute()
        await usd_context.open_stage_async(str(test_file_path))
        await wait_stage_loading()

        graph_window._import_prims(None, [controller.prim("/World/PushGraph")])  # noqa: SLF001

        await self.__wait_for_window_to_draw()
        await self.finalize_test(
            golden_img_dir=self._golden_img_dir,
            golden_img_name="lightspeed.trex.logic.widget.test_compound_nodes.png",
        )

    @unittest.skip("Skipping test_enter_compound. Compound subgraphs are disabled via monkey patch for now.")
    @unittest.skipIf(os.name == "posix" and os.getenv("ETM_ACTIVE"), "OM-79384: Skip test in Linux ETM")
    @unittest.skipIf(not _is_kit_version_or_greater((105, 1)), "105.1 required for compound subgraphs")
    async def test_enter_compound(self):
        # requires kit support for compounds
        if not Supports.compound_subgraphs():
            return

        stage, _, graph_window = await self.__initialize_test_window()

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

        graph_window._import_prims(None, [controller.prim(graph.get_path_to_graph())])  # noqa: SLF001
        await self.__wait_for_window_to_draw()
        graph_window._main_widget.model.create_subgraph_compound(  # noqa: SLF001
            [controller.prim(f"{self.TEST_GRAPH_PATH}/add"), controller.prim(f"{self.TEST_GRAPH_PATH}/simple")]
        )
        await self.__wait_for_window_to_draw()

        # Verify that compound is selected after creation
        self.assertEqual(
            graph_window._main_widget.model.selection,  # noqa: SLF001
            [stage.GetPrimAtPath(f"{self.TEST_GRAPH_PATH}/compound")],
        )

        # Verify that entering a compound shows the nodes
        graph_window._main_widget.enter_compound(controller.prim(f"{self.TEST_GRAPH_PATH}/compound"))  # noqa: SLF001

        await self.__wait_for_window_to_draw()
        await self.finalize_test(
            golden_img_dir=self._golden_img_dir,
            golden_img_name="lightspeed.trex.logic.widget.test_enter_compounds.png",
        )

    async def _validate_enter_compound(self, graph_create_fn, compounds: list[str], test_name: str):
        # requires kit support for compounds
        if not Supports.compound_subgraphs():
            return

        _stage, _, graph_window = await self.__initialize_test_window()
        graph = graph_create_fn()

        graph_window._import_prims(None, [og.Controller.prim(graph.get_path_to_graph())])  # noqa: SLF001
        await self.__wait_for_window_to_draw()

        # Verify that entering a compound shows the nodes
        # dig down in the compounds
        for compound in compounds:
            graph_window._main_widget.enter_compound(og.Controller.prim(compound))  # noqa: SLF001
            await self.__wait_for_window_to_draw()

        await self.finalize_test(
            golden_img_dir=self._golden_img_dir,
            golden_img_name=f"lightspeed.trex.logic.widget.{test_name}.png",
        )

    @unittest.skip("Skipping test_compound_no_connections. Compound subgraphs are disabled via monkey patch for now.")
    @unittest.skipIf(os.name == "posix" and os.getenv("ETM_ACTIVE"), "OM-79384: Skip test in Linux ETM")
    @unittest.skipIf(not _is_kit_version_or_greater((105, 1)), "105.1 required for compound subgraphs")
    async def test_compound_no_connections(self):
        """Test entering a compound with no connections produces unconnected input and output virtual nodes in the
        image"""

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

        await self._validate_enter_compound(
            create_graph, [f"{self.TEST_GRAPH_PATH}/compound"], "compound_no_connections"
        )

    @unittest.skip("Skipping test_enter_nested_compound. Compound subgraphs are disabled via monkey patch for now.")
    @unittest.skipIf(os.name == "posix" and os.getenv("ETM_ACTIVE"), "OM-79384: Skip test in Linux ETM")
    @unittest.skipIf(not _is_kit_version_or_greater((105, 1)), "105.1 required for compound subgraphs")
    async def test_enter_nested_compound(self):
        """Test entering a nested compound with connections"""

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

        await self._validate_enter_compound(
            create_graph,
            [f"{self.TEST_GRAPH_PATH}/compound", f"{self.TEST_GRAPH_PATH}/compound/Subgraph/compound2"],
            "enter_nested_compound",
        )

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

import tempfile
from pathlib import Path
from unittest.mock import patch

import omni.kit
import omni.kit.test
import omni.usd
from omni.flux.selection_history_tree.model.usd import UsdSelectionHistoryModel as _UsdSelectionHistoryModel
from omni.kit.test_suite.helpers import get_test_data_path


class TestUSDSelectionHistoryModel(omni.kit.test.AsyncTestCase):
    async def _open_default_stage(self):
        await omni.usd.get_context().open_stage_async(get_test_data_path(__name__, "usd/cubes.usda"))
        self.stage = omni.usd.get_context().get_stage()

    async def setUp(self):
        await self._open_default_stage()
        self.temp_dir = tempfile.TemporaryDirectory()

    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()

    async def test_insert_item_from_selection(self):
        model = _UsdSelectionHistoryModel()

        prim1 = self.stage.GetPrimAtPath("/World/Cube0")
        prim2 = self.stage.GetPrimAtPath("/World/Cube1")
        prim3 = self.stage.GetPrimAtPath("/World/Cube2")

        # REMIX-1083 testing insert_items method instead of _on_active_items_changed
        # since we're not updating active items:
        with patch.object(model, "insert_items") as mock:
            omni.usd.get_context().get_selection().set_selected_prim_paths([str(prim1.GetPath())], False)
            for _ in range(2):
                await omni.kit.app.get_app().next_update_async()
            omni.usd.get_context().get_selection().set_selected_prim_paths([str(prim2.GetPath())], False)
            for _ in range(2):
                await omni.kit.app.get_app().next_update_async()
            omni.usd.get_context().get_selection().set_selected_prim_paths([str(prim3.GetPath())], False)
            for _ in range(2):
                await omni.kit.app.get_app().next_update_async()
            items = model.get_item_children(None)

            self.assertEqual(model.get_item_children(None), items)

            self.assertEqual(3, mock.call_count)
            args, _ = mock.call_args
            # last selected is at the top of the list
            self.assertEqual(prim3, args[0][0].data)

    async def test_select_in_stage_no_listener(self):
        model = _UsdSelectionHistoryModel()
        model.enable_listeners(False)

        prim1 = self.stage.GetPrimAtPath("/World/Cube0")
        prim2 = self.stage.GetPrimAtPath("/World/Cube1")
        prim3 = self.stage.GetPrimAtPath("/World/Cube2")

        omni.usd.get_context().get_selection().set_selected_prim_paths([str(prim1.GetPath())], False)
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()
        omni.usd.get_context().get_selection().set_selected_prim_paths([str(prim2.GetPath())], False)
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()
        omni.usd.get_context().get_selection().set_selected_prim_paths([str(prim3.GetPath())], False)
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()
        items = model.get_item_children(None)

        self.assertFalse(items)
        model.enable_listeners(True)

    async def test_save_layer_custom_data(self):
        prim1 = self.stage.GetPrimAtPath("/World/Cube0")
        prim2 = self.stage.GetPrimAtPath("/World/Cube1")

        omni.usd.get_context().get_selection().set_selected_prim_paths([str(prim1.GetPath())], False)
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()
        omni.usd.get_context().get_selection().set_selected_prim_paths([str(prim2.GetPath())], False)
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()

        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        await omni.usd.get_context().save_as_stage_async(str(layer0_path))
        await omni.kit.app.get_app().next_update_async()
        await omni.usd.get_context().open_stage_async(str(layer0_path))
        stage = omni.usd.get_context().get_stage()
        layer = stage.GetRootLayer()
        self.assertEqual(
            layer.customLayerData.get("SelectionHistoryList"),
            {
                "0": str(prim2.GetPath()),
                "1": str(prim1.GetPath()),
            },
        )

        await self._open_default_stage()

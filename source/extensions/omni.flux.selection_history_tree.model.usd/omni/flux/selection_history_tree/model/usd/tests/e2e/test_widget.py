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

import omni.kit
import omni.kit.commands
import omni.kit.test
import omni.ui as ui
import omni.usd
from omni.flux.selection_history_tree.model.usd import UsdSelectionHistoryItem as _UsdSelectionHistoryItem
from omni.flux.selection_history_tree.model.usd import UsdSelectionHistoryModel as _UsdSelectionHistoryModel
from omni.flux.selection_history_tree.widget import SelectionHistoryWidget as _SelectionHistoryWidget
from omni.kit import ui_test
from omni.kit.test_suite.helpers import get_test_data_path


class TestSelectionHistoryWidget(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        await omni.usd.get_context().open_stage_async(get_test_data_path(__name__, "usd/cubes.usda"))
        self.stage = omni.usd.get_context().get_stage()

    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def __setup_widget(self, name):
        model = _UsdSelectionHistoryModel()
        window = ui.Window(f"TestSelectionHistoryUI{name}", height=800, width=400)
        with window.frame:
            wid = _SelectionHistoryWidget(model=model)

        await ui_test.human_delay(human_delay_speed=1)

        return window, model, wid

    async def __destroy_setup(self, window, _model, wid):
        await ui_test.human_delay(human_delay_speed=1)
        wid.destroy()
        window.frame.clear()
        window.destroy()

        await ui_test.human_delay(human_delay_speed=1)

    async def test_click_on_item_select_viewport(self):
        window, model, _wid = await self.__setup_widget(
            "test_click_on_item_select_viewport"
        )  # Keep in memory during test

        prim1 = self.stage.GetPrimAtPath("/World/Cube0")
        prim2 = self.stage.GetPrimAtPath("/World/Cube1")
        prim3 = self.stage.GetPrimAtPath("/World/Cube2")

        items = [
            _UsdSelectionHistoryItem(prim1.GetName(), data=prim1, tooltip="Tooltip0"),
            _UsdSelectionHistoryItem(prim2.GetName(), data=prim2, tooltip="Tooltip0"),
            _UsdSelectionHistoryItem(prim3.GetName(), data=prim3, tooltip="Tooltip0"),
        ]
        model.insert_items(items)

        list_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='title'")
        await list_items[1].click()
        selection = omni.usd.get_context().get_selection().get_selected_prim_paths()

        self.assertEqual(selection, [str(prim2.GetPath())])

        await self.__destroy_setup(window, model, _wid)

    async def test_delete_prim(self):
        window, model, _wid = await self.__setup_widget(
            "test_click_on_item_select_viewport"
        )  # Keep in memory during test
        model.enable_listeners(True)

        prim1 = self.stage.GetPrimAtPath("/World/Cube0")
        prim2 = self.stage.GetPrimAtPath("/World/Cube1")
        prim3 = self.stage.GetPrimAtPath("/World/Cube2")

        items = [
            _UsdSelectionHistoryItem(prim1.GetName(), data=prim1, tooltip="Tooltip0"),
            _UsdSelectionHistoryItem(prim2.GetName(), data=prim2, tooltip="Tooltip0"),
            _UsdSelectionHistoryItem(prim3.GetName(), data=prim3, tooltip="Tooltip0"),
        ]
        model.insert_items(items)

        omni.kit.commands.execute(
            "DeletePrims",
            paths=[str(prim2.GetPath())],
        )

        list_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='title'")
        self.assertEqual(list_items[1].widget.style_type_name_override, "PropertiesPaneSectionTreeItemError")
        model.enable_listeners(False)

        await self.__destroy_setup(window, model, _wid)

    async def test_delete_prim_emable_disable_listener(self):
        window, model, _wid = await self.__setup_widget(
            "test_click_on_item_select_viewport"
        )  # Keep in memory during test
        model.enable_listeners(True)

        prim1 = self.stage.GetPrimAtPath("/World/Cube0")
        prim2 = self.stage.GetPrimAtPath("/World/Cube1")
        prim3 = self.stage.GetPrimAtPath("/World/Cube2")

        items = [
            _UsdSelectionHistoryItem(prim1.GetName(), data=prim1, tooltip="Tooltip0"),
            _UsdSelectionHistoryItem(prim2.GetName(), data=prim2, tooltip="Tooltip0"),
            _UsdSelectionHistoryItem(prim3.GetName(), data=prim3, tooltip="Tooltip0"),
        ]
        model.insert_items(items)

        omni.kit.commands.execute(
            "DeletePrims",
            paths=[str(prim2.GetPath())],
        )

        list_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='title'")
        self.assertEqual(list_items[1].widget.style_type_name_override, "PropertiesPaneSectionTreeItemError")

        model.enable_listeners(False)

        omni.kit.commands.execute(
            "DeletePrims",
            paths=[str(prim1.GetPath())],
        )
        list_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='title'")

        self.assertNotEqual(list_items[0].widget.style_type_name_override, "PropertiesPaneSectionTreeItemError")
        await self.__destroy_setup(window, model, _wid)

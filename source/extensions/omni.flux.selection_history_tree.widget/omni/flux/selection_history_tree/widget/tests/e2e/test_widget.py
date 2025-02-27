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

from unittest.mock import patch

import omni.kit
import omni.kit.test
import omni.ui as ui
import omni.usd
from omni.flux.selection_history_tree.widget import SelectionHistoryItem as _SelectionHistoryItem
from omni.flux.selection_history_tree.widget import SelectionHistoryModel as _SelectionHistoryModel
from omni.flux.selection_history_tree.widget import SelectionHistoryWidget as _SelectionHistoryWidget
from omni.kit import ui_test


class TestSelectionHistoryWidget(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def __setup_widget(self, name):
        model = _SelectionHistoryModel()
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
        #
        await ui_test.human_delay(human_delay_speed=1)

    async def test_default_list_is_none(self):
        window, _model, _wid = await self.__setup_widget("test_default_list_is_none")  # Keep in memory during test

        list_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='title'")
        self.assertFalse(list_items)

        await self.__destroy_setup(window, _model, _wid)

    async def test_default_list_insert(self):
        window, _model, _wid = await self.__setup_widget("test_default_list_insert")  # Keep in memory during test

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        _model.insert_items(items)

        list_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='title'")
        self.assertEqual(len(list_items), 3)

        await self.__destroy_setup(window, _model, _wid)

    async def test_set_active(self):
        window, _model, _wid = await self.__setup_widget("test_set_active")  # Keep in memory during test

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        _model.insert_items(items)
        _model.set_active_items([items[1]])

        tree_view = ui_test.find(f"{window.title}//Frame/**/TreeView[*].identifier=='main_tree'")
        self.assertEqual(tree_view.widget.selection, [items[1]])

        await self.__destroy_setup(window, _model, _wid)

    async def test_change_selection(self):
        window, _model, _wid = await self.__setup_widget("test_change_selection")  # Keep in memory during test

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        _model.insert_items(items)
        list_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='title'")

        with patch.object(_model, "_on_active_items_changed") as mock:
            await list_items[1].click()
            self.assertEqual(1, mock.call_count)
            args, _ = mock.call_args
            self.assertEqual(([items[1]],), args)

        await self.__destroy_setup(window, _model, _wid)

    async def test_item_not_valid(self):
        window, _model, _wid = await self.__setup_widget("test_item_not_valid")  # Keep in memory during test

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        _model.insert_items(items)

        with patch.object(items[1], "is_valid") as mock:
            mock.return_value = False
            _model.refresh()

            list_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='title'")
            self.assertEqual(list_items[1].widget.style_type_name_override, "PropertiesPaneSectionTreeItemError")

        await self.__destroy_setup(window, _model, _wid)

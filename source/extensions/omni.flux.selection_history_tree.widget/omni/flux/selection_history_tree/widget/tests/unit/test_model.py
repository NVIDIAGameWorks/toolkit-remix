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
import omni.usd
from omni.flux.selection_history_tree.widget import SelectionHistoryItem as _SelectionHistoryItem
from omni.flux.selection_history_tree.widget import SelectionHistoryModel as _SelectionHistoryModel
from omni.kit.test_suite.helpers import wait_stage_loading


class TestSelectionHistoryModel(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_insert_item_default(self):
        model = _SelectionHistoryModel()

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        model.insert_items(items)

        self.assertEqual(model.get_item_children(None), list(reversed(items)))

    async def test_insert_same_item_default(self):
        model = _SelectionHistoryModel()

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        model.insert_items(items)

        self.assertEqual(model.get_item_children(None), [items[3], items[2], items[0]])

    async def test_insert_item_max_list(self):
        model = _SelectionHistoryModel()

        items = []
        for i in range(model.MAX_LIST_LENGTH + 10):
            items.append(_SelectionHistoryItem(f"Item{i}", data=f"Data{i}", tooltip=f"Tooltip{i}"))
        model.insert_items(items)

        self.assertEqual(len(model.get_item_children(None)), model.MAX_LIST_LENGTH)

    async def test_insert_item_end(self):
        model = _SelectionHistoryModel()

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        model.insert_items(items, idx=len(items))

        self.assertEqual(model.get_item_children(None), items)

    async def test_reset(self):
        model = _SelectionHistoryModel()

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        model.insert_items(items)
        model.reset()

        self.assertEqual(model.get_item_children(None), [])

    async def test_set_active_items(self):
        model = _SelectionHistoryModel()

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        model.insert_items(items)

        with patch.object(model, "_on_active_items_changed") as mock:
            model.set_active_items([items[1]])
            self.assertEqual(1, mock.call_count)
            args, _ = mock.call_args
            self.assertEqual(([items[1]],), args)

    async def test_get_active_items(self):
        model = _SelectionHistoryModel()

        items = [
            _SelectionHistoryItem("Item0", data="Data0", tooltip="Tooltip0"),
            _SelectionHistoryItem("Item1", data="Data1", tooltip="Tooltip1"),
            _SelectionHistoryItem("Item2", data="Data2", tooltip="Tooltip2"),
        ]
        model.insert_items(items)

        model.set_active_items(items[1])
        self.assertIsNone(model.get_active_items())  # by default it will return nothing

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

__all__ = ("TestContextMenu",)

import omni.kit.clipboard
import omni.kit.test
import omni.kit.ui_test

from ...ui_components import AsyncTestPropertyWidget, MockClipboard, TestItem


class TestContextMenu(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        # Create a unique clipboard per-test. This avoids race conditions when dealing with the system clipboard.
        self._clipboard = MockClipboard()
        self._clipboard.start()

    async def tearDown(self):
        self._clipboard.stop()

    async def test_shown(self):
        async with AsyncTestPropertyWidget() as helper:
            items = [
                TestItem([("N_1", "V_1")]),
                TestItem([("N_2", "V_2")]),
                TestItem([("N_3", "V_3")]),
            ]
            await helper.set_items(items)
            await helper.click_item(items[0], right_click=True)

            context_menu = helper.get_context_menu()
            self.assertTrue(context_menu is not None)
            self.assertTrue(context_menu.shown)
            context_menu.hide()

    async def test_copy_all(self):
        async with AsyncTestPropertyWidget() as helper:
            item1 = TestItem([("N_1", "V_1")])
            item2 = TestItem([("N_2", "V_2")])

            await helper.set_items([item1, item2])

            await helper.click_item(item1, right_click=True)
            await omni.kit.ui_test.menu.select_context_menu("Copy All", menu_root=helper.get_context_menu())

            raw = omni.kit.clipboard.paste()
            self.assertEqual(raw, '[{"names": ["N_1"], "values": ["V_1"]}, {"names": ["N_2"], "values": ["V_2"]}]')

    async def test_copy_all_paste_all(self):
        async with AsyncTestPropertyWidget() as helper:
            item1 = TestItem([("N_1", "V_1")])
            item2 = TestItem([("N_2", "V_2")])

            await helper.set_items([item1, item2])

            await helper.click_item(item1, right_click=True)
            await omni.kit.ui_test.menu.select_context_menu("Copy All", menu_root=helper.get_context_menu())

            test_item1 = TestItem([("N_1", "")])
            test_item2 = TestItem([("N_2", "")])

            await helper.set_items([test_item1, test_item2])

            await helper.click_item(test_item2, right_click=True)
            await omni.kit.ui_test.menu.select_context_menu("Paste All", menu_root=helper.get_context_menu())

            self.assertSequenceEqual(test_item1.get_value(), ["V_1"])
            self.assertSequenceEqual(test_item2.get_value(), ["V_2"])

    async def test_copy_all_paste_selection(self):
        async with AsyncTestPropertyWidget() as helper:
            item1 = TestItem([("N_1", "V_1")])
            item2 = TestItem([("N_2", "V_2")])

            await helper.set_items([item1, item2])

            await helper.click_item(item1, right_click=True)
            await omni.kit.ui_test.menu.select_context_menu("Copy All", menu_root=helper.get_context_menu())

            test_item1 = TestItem([("N_1", "")])
            test_item2 = TestItem([("N_2", "")])

            await helper.set_items([test_item1, test_item2])

            await helper.select_items([test_item2])

            await helper.click_item(test_item2, right_click=True)
            await omni.kit.ui_test.menu.select_context_menu("Paste Selected", menu_root=helper.get_context_menu())

            self.assertSequenceEqual(test_item1.get_value(), [""])
            self.assertSequenceEqual(test_item2.get_value(), ["V_2"])

    async def test_copy_selection_paste_all(self):
        async with AsyncTestPropertyWidget() as helper:
            item1 = TestItem([("N_1", "V_1")])
            item2 = TestItem([("N_2", "V_2")])

            await helper.set_items([item1, item2])

            await helper.select_items([item1])

            await helper.click_item(item1, right_click=True)
            await omni.kit.ui_test.menu.select_context_menu("Copy Selected", menu_root=helper.get_context_menu())

            test_item1 = TestItem([("N_1", "")])
            test_item2 = TestItem([("N_2", "")])

            await helper.set_items([test_item1, test_item2])

            await helper.select_items([])

            await helper.click_item(test_item2, right_click=True)
            await omni.kit.ui_test.menu.select_context_menu("Paste All", menu_root=helper.get_context_menu())

            self.assertSequenceEqual(test_item1.get_value(), ["V_1"])
            self.assertSequenceEqual(test_item2.get_value(), [""])

    async def test_copy_selection_paste_selection(self):
        async with AsyncTestPropertyWidget() as helper:
            item1 = TestItem([("N_1", "V_1")])
            item2 = TestItem([("N_2", "V_2")])

            await helper.set_items([item1, item2])

            await helper.select_items([item1])

            await helper.click_item(item1, right_click=True)
            await omni.kit.ui_test.menu.select_context_menu("Copy Selected", menu_root=helper.get_context_menu())

            test_item1 = TestItem([("N_1", "")])
            test_item2 = TestItem([("N_2", "")])

            await helper.set_items([test_item1, test_item2])

            await helper.select_items([test_item2])

            await helper.click_item(test_item2, right_click=True)
            # Paste Selected MenuItem should be disabled here because nothing in selection matches what's on the
            # clipboard. We can do a quick test that clicking it does nothing.
            await omni.kit.ui_test.menu.select_context_menu("Paste Selected", menu_root=helper.get_context_menu())

            self.assertSequenceEqual(test_item1.get_value(), [""])
            self.assertSequenceEqual(test_item2.get_value(), [""])

            await helper.select_items([test_item1])

            await helper.click_item(test_item1, right_click=True)
            await omni.kit.ui_test.menu.select_context_menu("Paste Selected", menu_root=helper.get_context_menu())

            self.assertSequenceEqual(test_item1.get_value(), ["V_1"])
            self.assertSequenceEqual(test_item2.get_value(), [""])

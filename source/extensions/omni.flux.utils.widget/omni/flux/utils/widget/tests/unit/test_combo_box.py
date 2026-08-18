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

__all__ = ["TestSectionedComboBox"]

import omni.kit.test
import omni.ui as ui

from omni.flux.utils.widget import SectionedComboBox, SectionedComboItem


class TestSectionedComboBox(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._window = ui.Window("TestSectionedComboBox", height=200, width=200)
        self._combo_box = None

    async def tearDown(self):
        if self._combo_box is not None:
            self._combo_box.destroy()
        self._window.destroy()

    def _build_combo_box(self, items: list[SectionedComboItem], selected_index: int = 0) -> SectionedComboBox:
        with self._window.frame:
            self._combo_box = SectionedComboBox(items=items, selected_index=selected_index)
        return self._combo_box

    async def test_constructor_clamps_selected_index_to_last_item(self):
        items = [SectionedComboItem("First"), SectionedComboItem("Second"), SectionedComboItem("Third")]

        combo_box = self._build_combo_box(items, selected_index=10)

        self.assertEqual(combo_box.selected_index, 2)
        self.assertEqual(combo_box.selected_item, items[2])

    async def test_constructor_clamps_selected_index_to_first_item(self):
        items = [SectionedComboItem("First"), SectionedComboItem("Second")]

        combo_box = self._build_combo_box(items, selected_index=-10)

        self.assertEqual(combo_box.selected_index, 0)
        self.assertEqual(combo_box.selected_item, items[0])

    async def test_set_items_clamps_selected_index_to_last_item(self):
        combo_box = self._build_combo_box([SectionedComboItem("Original")])
        items = [SectionedComboItem("First"), SectionedComboItem("Second"), SectionedComboItem("Third")]

        combo_box.set_items(items, selected_index=10)

        self.assertEqual(combo_box.selected_index, 2)
        self.assertEqual(combo_box.selected_item, items[2])

    async def test_set_items_resets_selection_when_empty(self):
        combo_box = self._build_combo_box([SectionedComboItem("Original")])

        combo_box.set_items([])

        self.assertEqual(combo_box.selected_index, 0)
        self.assertIsNone(combo_box.selected_item)

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

__all__ = ("TestClipboard",)

import omni.flux.property_widget_builder.widget.tree.clipboard as clipboard
import omni.kit.clipboard
import omni.kit.test

from ...ui_components import MockClipboard, TestItem


class TestClipboard(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        # Create a unique clipboard per-test. This avoids race conditions when dealing with the system clipboard.
        self._clipboard = MockClipboard()
        self._clipboard.start()

    async def tearDown(self):
        self._clipboard.stop()

    async def test_copy(self):
        orig_items = [
            TestItem([("CN_1", "CV_1")]),
            TestItem([("CN_2", "CV_2")]),
        ]
        clipboard.copy(orig_items)
        raw = omni.kit.clipboard.paste()
        self.assertEqual(raw, '[{"names": ["CN_1"], "values": ["CV_1"]}, {"names": ["CN_2"], "values": ["CV_2"]}]')

    async def test_paste(self):
        clipboard.copy(
            [
                TestItem([("N_1", "V_1")]),
                TestItem([("N_2", "V_2")]),
            ]
        )

        new_items = [
            TestItem([("N_1", "")]),
            TestItem([("N_2", "")]),
        ]

        matches = [x for x, _ in clipboard.iter_clipboard_changes(new_items)]
        self.assertEqual(new_items, matches)

        clipboard.paste(new_items)
        self.assertEqual(new_items[0].get_value(), ["V_1"])
        self.assertEqual(new_items[1].get_value(), ["V_2"])

    async def test_copy_multiple_paste_single(self):
        clipboard.copy(
            [
                TestItem([("N_1", "V_1")]),
                TestItem([("N_2", "V_2")]),
            ]
        )

        new_items = [
            TestItem([("N_1", "")]),
        ]

        matches = [x for x, _ in clipboard.iter_clipboard_changes(new_items)]
        self.assertEqual(new_items, matches)

        clipboard.paste(new_items)
        self.assertEqual(new_items[0].get_value(), ["V_1"])

    async def test_copy_single_paste_multiple(self):
        clipboard.copy(
            [
                TestItem([("N_1", "V_1")]),
            ]
        )

        test_items = [
            TestItem([("N_1", "")]),
            TestItem([("N_2", "")]),
        ]

        clipboard.paste(test_items)
        self.assertEqual(test_items[0].get_value(), ["V_1"])
        self.assertEqual(test_items[1].get_value(), [""])

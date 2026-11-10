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

import json

from carb.input import KeyboardInput

import omni.kit.clipboard
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.kit.notification_manager import destroy_all_notifications, get_all_notifications

from ...ui_components import AsyncTestPropertyWidget, TestItem


async def _select_context_menu(menu_path: str):
    """Choose a context-menu action and wait for its feedback."""
    await omni.kit.ui_test.menu.select_context_menu(menu_path, offset=omni.kit.ui_test.Vec2(10, 10))
    await omni.kit.ui_test.human_delay()


async def _hover_menu_item(context_menu: ui.Menu, text: str) -> ui.MenuItem:
    """Hover a native menu item through the same public inspector used by Kit's menu test helper."""
    item = next(
        child
        for child in ui.Inspector.get_children(context_menu)
        if isinstance(child, ui.MenuItem) and child.text == text
    )
    await omni.kit.ui_test.emulate_mouse_move(
        omni.kit.ui_test.Vec2(item.screen_position_x + 10, item.screen_position_y + item.computed_height / 2)
    )
    await omni.kit.ui_test.human_delay()
    return item


class TestContextMenu(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        """Preserve the real clipboard and clear notifications before each workflow."""
        self._clipboard_before = omni.kit.clipboard.paste()
        omni.kit.clipboard.copy("")
        destroy_all_notifications()

    async def tearDown(self):
        """Restore the clipboard and dismiss feedback left by failed assertions."""
        omni.kit.clipboard.copy(self._clipboard_before or "")
        destroy_all_notifications()

    async def test_shown(self):
        async with AsyncTestPropertyWidget() as helper:
            items = [
                TestItem([("N_1", "V_1")]),
                TestItem([("N_2", "V_2")]),
                TestItem([("N_3", "V_3")]),
            ]
            await helper.set_items(items)
            await helper.click_item(items[0], right_click=True)
            await omni.kit.ui_test.human_delay()

            context_menu = helper.get_context_menu()
            self.assertTrue(context_menu is not None)
            self.assertTrue(context_menu.shown)
            context_menu.hide()

    async def test_copy_all_paste_all(self):
        async with AsyncTestPropertyWidget() as helper:
            item1 = TestItem([("N_1", "V_1")])
            item2 = TestItem([("N_2", "V_2")])

            await helper.set_items([item1, item2])

            await helper.click_item(item1, right_click=True)
            await omni.kit.ui_test.human_delay()
            await _select_context_menu("Copy All")

            test_item1 = TestItem([("N_1", "")])
            test_item2 = TestItem([("N_2", "")])

            await helper.set_items([test_item1, test_item2])

            await helper.click_item(test_item2, right_click=True)
            await omni.kit.ui_test.human_delay()
            await _select_context_menu("Paste All")

            self.assertSequenceEqual(test_item1.get_value(), ["V_1"])
            self.assertSequenceEqual(test_item2.get_value(), ["V_2"])
            self.assertEqual(get_all_notifications(), [])
            window = ui.Workspace.get_window("Properties do not match")
            self.assertTrue(window is None or not window.visible)

    async def test_copy_all_paste_selection(self):
        async with AsyncTestPropertyWidget() as helper:
            item1 = TestItem([("N_1", "V_1")])
            item2 = TestItem([("N_2", "V_2")])

            await helper.set_items([item1, item2])

            await helper.click_item(item1, right_click=True)
            await omni.kit.ui_test.human_delay()
            await _select_context_menu("Copy All")

            test_item1 = TestItem([("N_1", "")])
            test_item2 = TestItem([("N_2", "")])

            await helper.set_items([test_item1, test_item2])

            await helper.select_items([test_item2])
            await omni.kit.ui_test.human_delay()

            await helper.click_item(test_item2, right_click=True)
            await omni.kit.ui_test.human_delay()
            await _select_context_menu("Paste Selected")

            self.assertSequenceEqual(test_item1.get_value(), [""])
            self.assertSequenceEqual(test_item2.get_value(), ["V_2"])
            notifications = get_all_notifications()
            self.assertEqual(len(notifications), 1)
            self.assertEqual(notifications[0].info.button_infos, [])

    async def test_copy_selection_paste_all(self):
        async with AsyncTestPropertyWidget() as helper:
            item1 = TestItem([("N_1", "V_1")])
            item2 = TestItem([("N_2", "V_2")])

            await helper.set_items([item1, item2])

            await helper.select_items([item1])
            await omni.kit.ui_test.human_delay()

            await helper.click_item(item1, right_click=True)
            await omni.kit.ui_test.human_delay()
            await _select_context_menu("Copy Selected")

            test_item1 = TestItem([("N_1", "")])
            test_item2 = TestItem([("N_2", "")])

            await helper.set_items([test_item1, test_item2])

            await helper.select_items([])
            await omni.kit.ui_test.human_delay()

            await helper.click_item(test_item2, right_click=True)
            await omni.kit.ui_test.human_delay()
            await _select_context_menu("Paste All")

            self.assertSequenceEqual(test_item1.get_value(), ["V_1"])
            self.assertSequenceEqual(test_item2.get_value(), [""])

    async def test_copy_unmatched_properties_stays_quiet_and_paste_remains_disabled(self):
        """Allow another property copy without warning about the previous clipboard contents."""
        async with AsyncTestPropertyWidget() as helper:
            # Copy from one property set and open an unrelated set's context menu.
            source = TestItem([("SourceOnly", "Copied")])
            await helper.set_items([source])
            await helper.click_item(source, right_click=True)
            await omni.kit.ui_test.human_delay()
            await _select_context_menu("Copy Selected")
            destination = TestItem([("DestinationOnly", "Keep")])
            await helper.set_items([destination])
            await helper.click_item(destination, right_click=True)
            await omni.kit.ui_test.human_delay()
            menu = await omni.kit.ui_test.menu.get_context_menu(helper.get_context_menu())
            self.assertNotIn("Paste All", menu["_"])
            self.assertNotIn("Why can't I paste?", menu["_"])
            paste_item = await _hover_menu_item(helper.get_context_menu(), "Paste All")
            self.assertFalse(paste_item.enabled)
            self.assertEqual(paste_item.tooltip, "No matching attributes found.")
            self.assertEqual(get_all_notifications(), [])

            # Copying the unrelated destination replaces the clipboard without attempting a paste.
            await _select_context_menu("Copy Selected")
            self.assertEqual(destination.get_value(), ["Keep"])
            self.assertEqual(
                json.loads(omni.kit.clipboard.paste())[0]["properties"],
                [{"name": ["DestinationOnly"], "value": ["Keep"]}],
            )
            self.assertEqual(get_all_notifications(), [])

    async def test_paste_invalid_or_unrelated_clipboard_keeps_both_actions_disabled(self):
        """Do not offer property paste for malformed data or unrelated clipboard text."""
        async with AsyncTestPropertyWidget() as helper:
            destination = TestItem([("Destination", "Keep")])
            await helper.set_items([destination])
            await helper.click_item(destination)
            await omni.kit.ui_test.human_delay()
            for content in ("", "Not property data", '{"path": "texture.dds"}', '[{"properties": []}]'):
                with self.subTest(clipboard=content):
                    # Opening the context menu with invalid clipboard contents cannot enable a paste attempt.
                    omni.kit.clipboard.copy(content)
                    await helper.click_item(destination, right_click=True)
                    await omni.kit.ui_test.human_delay()
                    menu = await omni.kit.ui_test.menu.get_context_menu(helper.get_context_menu())
                    self.assertNotIn("Paste All", menu["_"])
                    self.assertNotIn("Paste Selected", menu["_"])
                    self.assertNotIn("Why can't I paste?", menu["_"])
                    self.assertEqual(destination.get_value(), ["Keep"])
                    self.assertEqual(get_all_notifications(), [])
                    await omni.kit.ui_test.emulate_mouse_move_and_click(
                        omni.kit.ui_test.Vec2(helper.window.position_x + 5, helper.window.position_y + 5)
                    )
                    await omni.kit.ui_test.human_delay()

    async def test_copy_selection_paste_selection(self):
        """Explain a disabled selection paste and allow a quiet matching retry."""
        async with AsyncTestPropertyWidget() as helper:
            item1 = TestItem([("N_1", "V_1")])
            item2 = TestItem([("N_2", "V_2")])

            await helper.set_items([item1, item2])

            await helper.click_item(item1)
            await omni.kit.ui_test.human_delay()

            await helper.click_item(item1, right_click=True)
            await omni.kit.ui_test.human_delay()
            await _select_context_menu("Copy Selected")

            test_item1 = TestItem([("N_1", "")])
            test_item2 = TestItem([("N_2", "")])

            await helper.set_items([test_item1, test_item2])

            await helper.click_item(test_item2)
            await omni.kit.ui_test.human_delay()

            await helper.click_item(test_item2, right_click=True)
            await omni.kit.ui_test.human_delay()
            # A selected-row mismatch stays quiet when Paste All still has a compatible destination.
            menu = await omni.kit.ui_test.menu.get_context_menu(helper.get_context_menu())
            self.assertNotIn("Paste Selected", menu["_"])
            self.assertIn("Paste All", menu["_"])
            self.assertNotIn("Why can't I paste?", menu["_"])
            paste_item = await _hover_menu_item(helper.get_context_menu(), "Paste Selected")
            self.assertFalse(paste_item.enabled)
            self.assertEqual(paste_item.tooltip, "No matching attributes found.")
            self.assertEqual(get_all_notifications(), [])

            self.assertSequenceEqual(test_item1.get_value(), [""])
            self.assertSequenceEqual(test_item2.get_value(), [""])
            self.assertFalse(
                any(
                    window.title == "Properties do not match" and window.visible
                    for window in ui.Workspace.get_windows()
                )
            )
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
            await omni.kit.ui_test.human_delay()

            await helper.click_item(test_item1)
            await omni.kit.ui_test.human_delay()

            await helper.click_item(test_item1, right_click=True)
            await omni.kit.ui_test.human_delay()
            menu = await omni.kit.ui_test.menu.get_context_menu(helper.get_context_menu())
            self.assertIn("Paste Selected", menu["_"])
            self.assertNotIn("Why can't I paste?", menu["_"])
            await _select_context_menu("Paste Selected")

            self.assertSequenceEqual(test_item1.get_value(), ["V_1"])
            self.assertSequenceEqual(test_item2.get_value(), [""])
            self.assertEqual(get_all_notifications(), [])

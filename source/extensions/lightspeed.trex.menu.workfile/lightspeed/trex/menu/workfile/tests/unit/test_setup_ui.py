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

from unittest.mock import patch

import omni.kit.test
from lightspeed.trex.menu.workfile.setup_ui import SetupUI
from omni.kit.menu.utils import MenuActionControl


class TestSetupUI(omni.kit.test.AsyncTestCase):
    async def test_register_menu_items_undo_and_redo_do_not_declare_hotkeys(self):
        """Undo and Redo use global hotkeys, so their menu entries must not register duplicate shortcuts."""
        # Arrange
        captured_menu_items = []

        with (
            patch("lightspeed.trex.menu.workfile.setup_ui.get_eventdispatcher"),
            patch("lightspeed.trex.menu.workfile.setup_ui.get_action_registry"),
            patch(
                "lightspeed.trex.menu.workfile.setup_ui._build_submenu_dict",
                side_effect=lambda menu_items: captured_menu_items.extend(menu_items) or {},
            ),
            patch("lightspeed.trex.menu.workfile.setup_ui._menu_utils.add_menu_items"),
            patch("lightspeed.trex.menu.workfile.setup_ui._menu_utils.set_default_menu_priority"),
        ):
            setup_ui = SetupUI()
            try:
                # Act
                setup_ui._SetupUI__on_app_ready(None)
            finally:
                setup_ui.destroy()

        # Assert
        undo_item = next(item for item in captured_menu_items if item.name == "Edit/Undo")
        redo_item = next(item for item in captured_menu_items if item.name == "Edit/Redo")
        self.assertIsNone(undo_item.hotkey)
        self.assertIsNone(redo_item.hotkey)
        self.assertEqual(undo_item.onclick_action, ("lightspeed.trex.menu.workfile", "undo", MenuActionControl.NODELAY))
        self.assertEqual(redo_item.onclick_action, ("lightspeed.trex.menu.workfile", "redo", MenuActionControl.NODELAY))

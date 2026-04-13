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

from unittest.mock import Mock, patch

import omni.kit.test
from lightspeed.trex.menu.workfile.setup_ui import SetupUI


class TestSetupUI(omni.kit.test.AsyncTestCase):
    async def test_register_menu_items_undo_and_redo_do_not_declare_hotkeys(self):
        """Undo/Redo are already registered globally, so the menu entries must stay unbound."""
        # Arrange
        captured_menu_items = []
        startup_stream = Mock()
        startup_stream.create_subscription_to_pop_by_type.return_value = object()
        app = Mock()
        app.get_startup_event_stream.return_value = startup_stream

        with (
            patch("lightspeed.trex.menu.workfile.setup_ui.omni.kit.app.get_app", return_value=app),
            patch(
                "lightspeed.trex.menu.workfile.setup_ui._build_submenu_dict",
                side_effect=lambda menu_items: captured_menu_items.extend(menu_items) or {},
            ),
            patch("lightspeed.trex.menu.workfile.setup_ui._menu_utils.add_menu_items"),
            patch("lightspeed.trex.menu.workfile.setup_ui._menu_utils.set_default_menu_priority"),
        ):
            setup_ui = SetupUI()

            # Act
            setup_ui._SetupUI__register_menu_items()

        # Assert
        undo_item = next(item for item in captured_menu_items if item.name == "Edit/Undo")
        redo_item = next(item for item in captured_menu_items if item.name == "Edit/Redo")
        self.assertIsNone(undo_item.hotkey)
        self.assertIsNone(redo_item.hotkey)

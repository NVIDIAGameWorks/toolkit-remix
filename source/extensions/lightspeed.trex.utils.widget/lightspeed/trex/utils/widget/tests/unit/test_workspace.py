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

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from lightspeed.trex.utils.widget import workspace
from omni.kit.test import AsyncTestCase


class _WorkspaceWindow(workspace.WorkspaceWindowBase):
    """Supply a title and a mocked window without native UI resources."""

    def __init__(self, title: str):
        """Initialize the supplied title and an initially hidden mocked window."""
        super().__init__()
        self._title = title
        self._window = MagicMock(visible=False)

    @property
    def title(self) -> str:
        """Return the workspace window title."""
        return self._title

    @property
    def flags(self) -> int:
        """Return the flags for the mocked window."""
        return 0

    def _create_window_ui(self) -> workspace.WorkspaceWidget:
        """Return mocked content without native UI resources."""
        return MagicMock(spec=workspace.WorkspaceWidget)


class TestWorkspaceWindowBase(AsyncTestCase):
    """Test menu action ownership and callbacks with mocked UI dependencies."""

    async def setUp(self):
        """Replace the action registry, menu utilities, and native UI dependencies."""
        self._patches = ExitStack()
        self.addCleanup(self._patches.close)
        self._registry = MagicMock()
        self._patches.enter_context(patch.object(workspace, "get_action_registry", return_value=self._registry))
        self._menu_utils = self._patches.enter_context(patch.object(workspace, "_menu_utils"))
        self._menu_utils.MenuItemDescription.side_effect = SimpleNamespace
        self._patches.enter_context(
            patch.object(workspace, "build_submenu_dict", side_effect=lambda menus: {"Window": menus})
        )
        self._ui = self._patches.enter_context(patch.object(workspace, "ui"))

    async def test_update_menu_item_with_different_titles_registers_distinct_menu_actions(self):
        """Give each menu item the action registered for its own window title."""
        # Arrange
        first, second = self._make_windows()
        first.update_menu_item(False)
        expected_actions = [
            ("lightspeed.trex.utils.widget", "toggle_window:First Window"),
            ("lightspeed.trex.utils.widget", "toggle_window:Second Window"),
        ]

        # Act
        second.update_menu_item(False)

        # Assert
        self.assertEqual(
            [registration.args[:2] for registration in self._registry.register_action.call_args_list],
            expected_actions,
        )
        self.assertEqual(
            [window._menu_dict["Window"][0].onclick_action for window in (first, second)],
            [(*action, self._menu_utils.MenuActionControl.NODELAY) for action in expected_actions],
        )

    async def test_update_menu_item_with_existing_menu_does_not_register_another_action(self):
        """Refresh an existing menu without replacing its action or menu item."""
        # Arrange
        first, second = self._make_windows()
        first.update_menu_item(False)
        second.update_menu_item(False)
        original_menu = first._menu_dict

        # Act
        first.update_menu_item(True)

        # Assert
        self.assertEqual(self._registry.register_action.call_count, 2)
        self.assertEqual(self._menu_utils.MenuItemDescription.call_count, 2)
        self.assertEqual(self._menu_utils.add_menu_items.call_count, 2)
        self.assertIs(first._menu_dict, original_menu)

    async def test_menu_action_with_each_visibility_toggles_only_its_titled_window(self):
        """Resolve each menu action to the callback for that title and invert visibility."""
        for index in (0, 1):
            for visible in (False, True):
                with self.subTest(title=f"window={index}, visible={visible}"):
                    # Arrange
                    windows = self._make_windows()
                    for window in windows:
                        window.update_menu_item(False)
                    target = windows[index]
                    target.get_window().visible = visible
                    windows[1 - index].get_window().visible = not visible
                    callbacks = {
                        registration.args[:2]: registration.args[2]
                        for registration in self._registry.register_action.call_args_list
                    }
                    callback = callbacks[target._menu_dict["Window"][0].onclick_action[:2]]
                    self._ui.Workspace.show_window.reset_mock()

                    # Act
                    callback()

                    # Assert
                    self._ui.Workspace.show_window.assert_called_once_with(target.title, not visible)

    async def test_ticked_fn_after_visibility_change_returns_current_window_visibility(self):
        """Read each window's current visibility instead of its initial menu state."""
        for index in (0, 1):
            for visible in (False, True):
                with self.subTest(title=f"window={index}, visible={visible}"):
                    # Arrange
                    windows = self._make_windows()
                    for window in windows:
                        window.update_menu_item(False)
                    target = windows[index]
                    menu_item = target._menu_dict["Window"][0]
                    target.get_window().visible = visible
                    windows[1 - index].get_window().visible = not visible

                    # Act
                    ticked = menu_item.ticked_fn()

                    # Assert
                    self.assertIs(ticked, visible)

    async def test_cleanup_with_two_windows_deregisters_only_the_owned_action_after_menu_removal(self):
        """Remove only the target window's menu and action during cleanup."""
        for index in (0, 1):
            with self.subTest(title=f"window={index}"):
                # Arrange
                windows = self._make_windows()
                for window in windows:
                    window.update_menu_item(False)
                target = windows[index]
                menu_items = target._menu_dict["Window"]
                lifecycle = MagicMock()
                lifecycle.attach_mock(self._menu_utils.remove_menu_items, "remove_menu_items")
                lifecycle.attach_mock(self._registry.deregister_action, "deregister_action")

                # Act
                target.cleanup()

                # Assert
                self.assertEqual(
                    lifecycle.mock_calls,
                    [
                        call.remove_menu_items(menu_items, "Window"),
                        call.deregister_action("lightspeed.trex.utils.widget", f"toggle_window:{target.title}"),
                    ],
                )
                self._registry.deregister_all_actions_for_extension.assert_not_called()
                windows[1 - index].get_window().destroy.assert_not_called()

    def _make_windows(self) -> tuple[_WorkspaceWindow, _WorkspaceWindow]:
        """Create two workspace windows and retain cleanup until after assertions."""
        windows = (_WorkspaceWindow("First Window"), _WorkspaceWindow("Second Window"))
        for window in windows:
            self.addCleanup(window.cleanup)
        return windows

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

from carb.input import KeyboardInput, MouseEventType
from carb.settings import get_settings
from omni import ui
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test import Vec2

from ... import FieldPopupWindow

__all__ = ["TestFieldPopupWindow"]

_SIZE = (200.0, 120.0)
_LAUNCHER_WIDTH = ui.Pixel(200)
_LAUNCHER_HEIGHT = ui.Pixel(90)


class TestFieldPopupWindow(AsyncTestCase):
    """Exercise native editor chrome through actual controls."""

    async def setUp(self):
        """Prepare a disposable editor type with real content and a detachment observation."""
        self._editor = None
        self._released = 0
        test = self

        class Editor(FieldPopupWindow):
            """Build native content inside the shared property window."""

            def _build_content(self) -> None:
                """Render content inside the native window."""
                ui.Label("1.0")

            def _release_content(self) -> None:
                """Observe actual native detachment before content cleanup."""
                test.assertEqual(ui.Inspector.get_children(self.frame), [])
                test._released += 1

        self._editor_type = Editor

    async def tearDown(self):
        """Release native content even when an interaction assertion fails."""
        try:
            if self._editor is not None:
                self._editor.destroy()
            await ui_test.human_delay(1)
        finally:
            self._editor = None
            self._editor_type = None
            await ui_test.human_delay(1)

    async def test_native_chrome_moves_resizes_closes_and_reopens_editor(self):
        """Exercise native chrome, fresh reopening, and outside-button dismissal without dismissing held launch."""
        expected_dpi = get_settings().get("/app/window/dpiScaleOverride")
        if expected_dpi is not None and expected_dpi > 0:
            self.assertAlmostEqual(ui.Workspace.get_dpi_scale(), expected_dpi)

        def open_editor(_x, _y, button, _modifiers):
            """Construct and retain a fresh native editor for this launch."""
            if button == 0:
                self._editor = self._editor_type(title="Roughness - Curve Editor", context_name=None)
                anchor_rect = None
                if self._released:
                    anchor_rect = (
                        launch_button.screen_position_x,
                        launch_button.screen_position_y,
                        launch_button.computed_width,
                        launch_button.computed_height,
                    )
                self._editor.open(preferred_size=_SIZE, anchor_rect=anchor_rect)

        launcher = ui.Window(
            "FloatingEditorLauncher", width=_LAUNCHER_WIDTH, height=_LAUNCHER_HEIGHT, position_x=8, position_y=8
        )
        button_events = (
            (MouseEventType.LEFT_BUTTON_DOWN, MouseEventType.LEFT_BUTTON_UP),
            (MouseEventType.RIGHT_BUTTON_DOWN, MouseEventType.RIGHT_BUTTON_UP),
            (MouseEventType.MIDDLE_BUTTON_DOWN, MouseEventType.MIDDLE_BUTTON_UP),
        )
        try:
            with launcher.frame:
                launch_button = ui.Button(
                    "Open editor",
                    identifier="OpenFloatingEditor",
                    mouse_pressed_fn=open_editor,
                )
            await ui_test.human_delay(1)
            button = ui_test.find("FloatingEditorLauncher//Frame/Button[*].identifier=='OpenFloatingEditor'")
            launch_position = button.center
            await ui_test.input.emulate_mouse(MouseEventType.MOVE, launch_position)
            try:
                await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, launch_position)
                await ui_test.human_delay(1)
                self.assertIsInstance(self._editor, ui.Window)
                self.assertTrue(self._editor.is_open)
                self.assertEqual(0, self._released)
            finally:
                await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP, launch_position)
            await ui_test.human_delay(1)
            window = self._editor
            original_window = window
            self.assertTrue(window.is_open)
            self.assertTrue(window.title.startswith("Roughness - Curve Editor###PropertyPanelFloatingEditor_"))
            self.assertEqual(
                ui.WINDOW_FLAGS_NO_DOCKING | ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_SCROLLBAR,
                window.flags,
            )
            centered_position = (
                (ui.Workspace.get_main_window_width() - window.width) / 2,
                (ui.Workspace.get_main_window_height() - window.height) / 2,
            )
            self.assertEqual(centered_position, (window.position_x, window.position_y))
            self.assertEqual(_SIZE, (window.width, window.height))
            header_height = window.frame.screen_position_y - window.position_y
            self.assertGreater(header_height, 0)
            title = Vec2(window.position_x + window.width / 2, window.position_y + header_height / 2)
            await ui_test.input.emulate_mouse_move_and_click(title)
            await ui_test.human_delay(1)
            self.assertTrue(window.is_open)
            before_move = (window.position_x, window.position_y)
            await ui_test.input.emulate_mouse_drag_and_drop(title, title + Vec2(30, 20))
            await ui_test.human_delay(1)
            self.assertGreater(window.position_x, before_move[0])
            self.assertGreater(window.position_y, before_move[1])
            before_size = (window.width, window.height)
            grip = Vec2(window.position_x + window.width - 2, window.position_y + window.height - 2)
            await ui_test.input.emulate_mouse_drag_and_drop(grip, grip + Vec2(40, 30))
            await ui_test.human_delay(1)
            self.assertGreater(window.width, before_size[0])
            self.assertGreater(window.height, before_size[1])
            close = Vec2(window.position_x + window.width - header_height / 2, window.position_y + header_height / 2)
            await ui_test.input.emulate_mouse_move_and_click(close)
            await ui_test.human_delay(1)
            self.assertFalse(window.is_open)
            self.assertEqual(1, self._released)
            await ui_test.human_delay(1)
            self.assertEqual(1, self._released)

            launcher.position_x = ui.Workspace.get_main_window_width() - launcher.width - 8
            launcher.position_y = ui.Workspace.get_main_window_height() - launcher.height - 8
            await ui_test.human_delay(1)
            await button.click()
            await ui_test.human_delay(1)
            window = self._editor
            self.assertIsInstance(window, ui.Window)
            self.assertIsNot(window, original_window)
            self.assertTrue(window.is_open)
            self.assertEqual(launch_button.screen_position_x - 8 - window.width, window.position_x)
            self.assertEqual(ui.Workspace.get_main_window_height() - 8 - window.height, window.position_y)
            self.assertEqual(_SIZE, (window.width, window.height))
            await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
            await ui_test.human_delay(1)
            self.assertFalse(window.is_open)
            self.assertEqual(2, self._released)
            await ui_test.human_delay(1)
            self.assertEqual(2, self._released)

            # Any outside button must dismiss, including clicks that transfer focus without using the left button.
            outside = Vec2(launcher.position_x + launcher.width / 2, launcher.position_y + header_height / 2)
            for button_down, button_up in button_events:
                await button.click()
                await ui_test.human_delay(1)
                window = self._editor
                self.assertTrue(window.is_open)
                await ui_test.input.emulate_mouse(MouseEventType.MOVE, outside)
                await ui_test.input.emulate_mouse(button_down, outside)
                await ui_test.human_delay(1)
                self.assertFalse(window.is_open, button_down.name)
                await ui_test.input.emulate_mouse(button_up, outside)
                await ui_test.human_delay(1)
        finally:
            for _, button_up in button_events:
                await ui_test.input.emulate_mouse(button_up, Vec2(1, 1))
            launcher.destroy()
            await ui_test.human_delay(1)

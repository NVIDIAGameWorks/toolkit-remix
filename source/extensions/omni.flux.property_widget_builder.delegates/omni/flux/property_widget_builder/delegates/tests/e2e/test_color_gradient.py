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

__all__ = ("TestColorGradientField",)

import uuid

import omni.kit.ui_test as ui_test
import omni.ui as ui
from carb.input import KeyboardInput, MouseEventType
from omni.flux.utils.widget import InMemoryGroupedKeysModel
from omni.kit.renderer_capture import acquire_renderer_capture_interface, convert_raw_bytes_to_rgba_tuples
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test import Vec2
from omni.kit.ui_test.input import emulate_mouse, emulate_mouse_move_and_click

from ... import field_popup_window
from ...float_value.color_gradient import ColorGradientField, GradientFieldEditor

_GROUP_ID = "gradient"
_EDITOR_TITLE = "Gradient Editor###PropertyPanelFloatingEditor_"


def _find_gradient_editor_window():
    """Find the visible property-owned Gradient editor window."""
    return next(
        (window for window in ui.Workspace.get_windows() if window.title.startswith(_EDITOR_TITLE) and window.visible),
        None,
    )


def _payload_from_keyframes(keyframes):
    """Convert real gradient stops into their production model payload."""
    return {
        "times": [time for time, _color in keyframes],
        "values": [color for _time, color in keyframes],
    }


class _LoggingGroupedKeysModel(InMemoryGroupedKeysModel):
    """Observe edits while retaining the production in-memory model's behavior."""

    def __init__(self, payload=None):
        """Initialize the production gradient model and its commit log."""
        super().__init__(group_ids=[_GROUP_ID], payloads={_GROUP_ID: payload} if payload is not None else None)
        self.commit_log = []

    def commit_payload(self, group_id: str, payload: dict) -> None:
        """Record each committed payload after production storage accepts it."""
        super().commit_payload(group_id, payload)
        self.commit_log.append((group_id, payload))


class TestColorGradientField(AsyncTestCase):
    """Tests for the ColorGradientField delegate as a pure UI component."""

    async def setUp(self):
        self._window = ui.Window(
            f"TestGradientField_{uuid.uuid1()}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        self._field = None
        self._model = None
        self._widgets = None

    async def tearDown(self):
        try:
            if field_popup_window._ACTIVE_WINDOW is not None:
                field_popup_window._ACTIVE_WINDOW.close()
            await ui_test.human_delay(1)
            if self._field:
                self._field.destroy()
        finally:
            self._field = None
            if self._widgets:
                for widget in self._widgets:
                    widget.destroy()
                self._widgets = None
            if self._model:
                self._model.destroy()
                self._model = None
            if self._window:
                self._window.destroy()
                self._window = None
            await ui_test.human_delay(1)

    def _build_field(self, keyframes=None, default_color=None):
        """Build the ColorGradientField in the test window."""
        self._model = _LoggingGroupedKeysModel(_payload_from_keyframes(keyframes) if keyframes is not None else None)
        self._window.frame.clear()
        with self._window.frame:
            self._field = ColorGradientField(
                model=self._model,
                group_id=_GROUP_ID,
                default_color=default_color,
            )
            self._widgets = self._field.build_ui(None)

    async def _show_widget_popup(self):
        """Open the editor through its inline gradient control."""
        overlay = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'")
        await overlay.click()
        await ui_test.human_delay(5)

    async def _select_preset(self, name: str):
        """Select a preset or operation through the editor's native menu."""
        host = _find_gradient_editor_window()
        if host is None:
            await self._show_widget_popup()
            host = _find_gradient_editor_window()
        self.assertIsNotNone(host)
        await ui_test.find(f"{host.title}//Frame/**/Image[*].name=='MenuBurger'").click()
        await ui_test.human_delay()
        await ui_test.select_context_menu(name)
        await ui_test.human_delay()

    async def _click_for_update(self, position):
        """Hold a left mouse click across one UI update."""
        await emulate_mouse(MouseEventType.MOVE, position)
        try:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, position)
            await ui_test.human_delay(1)
        finally:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, position)
        await ui_test.human_delay(1)

    async def _read_preview_pixel(self, provider):
        """Read the center pixel of the gradient provider after its texture upload."""
        pixels = []

        def capture_pixel(buffer, size, width, height, pixel_format):
            """Copy the center pixel while the capture buffer is valid."""
            rgba = convert_raw_bytes_to_rgba_tuples(buffer, size, width, height, pixel_format)
            pixels.append(rgba[(height // 2) * width + width // 2])

        await ui_test.human_delay(1)
        capture = acquire_renderer_capture_interface()
        capture.capture_next_frame_rp_resource_callback(capture_pixel, provider.get_managed_resource())
        await ui_test.human_delay(1)
        capture.wait_async_capture()
        self.assertEqual(len(pixels), 1)
        return pixels[0]

    async def test_external_changes_closed_fields_refresh_preview_until_destroyed(self):
        """External changes refresh closed editable and read-only previews until field cleanup."""
        unrelated_group_id = "other"
        red = (1.0, 0.0, 0.0, 1.0)
        blue = (0.0, 0.0, 1.0, 1.0)
        green = (0.0, 1.0, 0.0, 1.0)

        for read_only in (False, True):
            with self.subTest(read_only=read_only):
                model = InMemoryGroupedKeysModel(
                    group_ids=[_GROUP_ID, unrelated_group_id],
                    payloads={_GROUP_ID: _payload_from_keyframes([(0.0, red)])},
                )
                field = None
                widgets = []
                try:
                    self._window.frame.clear()
                    with self._window.frame:
                        field = ColorGradientField(
                            model=model,
                            group_id=_GROUP_ID,
                            default_color=green,
                            read_only=read_only,
                        )
                        widgets = field.build_ui(None)
                    provider = field._preview.gradient_provider
                    self.assertEqual(await self._read_preview_pixel(provider), (255, 0, 0, 255))

                    # Dismiss the popup so subsequent checks exercise the inline field on its own.
                    if not read_only:
                        await self._show_widget_popup()
                        host = _find_gradient_editor_window()
                        self.assertIsNotNone(host)
                        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
                        await ui_test.human_delay()
                        self.assertFalse(host.visible)

                    # Closed and read-only fields must still follow changes to their own group.
                    model.simulate_external_change(_GROUP_ID, _payload_from_keyframes([(0.0, blue)]))
                    self.assertEqual(await self._read_preview_pixel(provider), (0, 0, 255, 255))

                    # Notifications from another group must leave this preview unchanged.
                    model.simulate_external_change(unrelated_group_id, _payload_from_keyframes([(0.0, red)]))
                    self.assertEqual(await self._read_preview_pixel(provider), (0, 0, 255, 255))

                    # An empty gradient must display the field's fallback color.
                    model.simulate_external_change(_GROUP_ID, _payload_from_keyframes([]))
                    self.assertEqual(await self._read_preview_pixel(provider), (0, 255, 0, 255))

                    # Destroyed fields must stop reacting to model notifications.
                    field.destroy()
                    model.simulate_external_change(_GROUP_ID, _payload_from_keyframes([(0.0, red)]))
                    self.assertEqual(await self._read_preview_pixel(provider), (0, 255, 0, 255))
                finally:
                    if field_popup_window._ACTIVE_WINDOW is not None:
                        field_popup_window._ACTIVE_WINDOW.close()
                        await ui_test.human_delay()
                    if field is not None:
                        field.destroy()
                    for widget in widgets:
                        widget.destroy()
                    model.destroy()
                    self._window.frame.clear()

    async def test_constant_preset_swatch_edit_commits_color_without_keys(self):
        """Choosing Constant and editing its swatch changes color without creating a key."""
        self._window.width = 160
        self._build_field(keyframes=[(0.0, (1.0, 0.0, 0.0, 1.0)), (1.0, (0.0, 0.0, 1.0, 1.0))])
        await ui_test.human_delay(3)
        inline = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'").widget
        inline_width = inline.computed_width
        await self._select_preset("Constant")
        editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(editor, GradientFieldEditor)
        content = editor._content
        self.assertEqual(content.get_keyframes(), [])
        self._model.commit_log.clear()

        host = _find_gradient_editor_window()
        self.assertIsNotNone(host)
        swatch = ui_test.find(f"{host.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'")
        await swatch.click()
        await ui_test.human_delay()
        for value in ("0.8", "0.5", "0.4"):
            await ui_test.emulate_keyboard_press(KeyboardInput.TAB)
            await ui_test.emulate_char_press(value)
        await emulate_mouse_move_and_click(swatch.offset(-3, -3))
        await ui_test.human_delay()

        self.assertEqual(content.get_keyframes(), [])
        for actual, expected in zip(content._preview.fallback_color, (0.8, 0.5, 0.4, 1.0)):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(self._model.commit_log[-1][1], {"times": [], "values": []})

        # Adding and deleting the only rendered key leaves the edited constant as the full-precision fallback.
        preview = self._field._preview
        color = preview.fallback_color
        provider = preview.gradient_provider
        checker_provider = preview.checker_provider
        self.assertIs(content._preview, preview)

        # Both views preserve square checkers when resized before inserting another stop.
        for view, width in ((self._window, 350), (host, 700)):
            view.width = width
            await ui_test.human_delay()
            checker = ui_test.find(
                f"{view.title}//Frame/**/ImageWithProvider[*].identifier=='GradientCheckerboard'"
            ).widget
            target = ui_test.find(f"{view.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'").widget
            self.assertAlmostEqual(
                checker.computed_width / checker_provider.width,
                checker.computed_height / checker_provider.height,
                places=5,
            )
            self.assertGreaterEqual(checker.computed_width, target.computed_width)
            self.assertGreaterEqual(checker.computed_height, target.computed_height)
        self.assertIs(preview.checker_provider, checker_provider)

        bar = ui_test.find(f"{host.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'").widget
        self.assertLess(inline_width, bar.computed_width)
        position = Vec2(
            round(bar.screen_position_x + bar.computed_width * 0.25),
            round(bar.screen_position_y + bar.computed_height / 2),
        )
        expected_time = round((position.x - bar.screen_position_x) / bar.computed_width, 5)
        self._model.commit_log.clear()
        await emulate_mouse_move_and_click(position)
        await ui_test.human_delay()
        expected = [(expected_time, color)]
        self.assertEqual(content.get_keyframes(), expected)
        self.assertEqual(self._model.commit_log, [(_GROUP_ID, _payload_from_keyframes(expected))])
        self.assertTrue(host.visible)
        await ui_test.find(f"{host.title}//Frame/**/Image[*].name=='TrashCan'").click()
        await ui_test.human_delay()
        self.assertEqual(content.get_keyframes(), [])
        self.assertEqual(self._model.get_payload(_GROUP_ID), {"times": [], "values": []})
        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
        await ui_test.human_delay()
        await self._show_widget_popup()
        editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(editor, GradientFieldEditor)
        self.assertIsNot(content, editor._content)
        self.assertIs(preview, editor._content._preview)
        self.assertEqual(color, preview.fallback_color)
        self.assertIs(provider, preview.gradient_provider)
        swatch_model = editor._content._color_widget.model
        self.assertEqual(
            tuple(
                swatch_model.get_item_value_model(child).get_value_as_float()
                for child in swatch_model.get_item_children()
            ),
            color,
        )

    async def test_popup_stays_open_during_child_popups(self):
        """Child interactions preserve the editor; clicking outside the whole group dismisses it."""
        self._build_field(keyframes=[(0.0, (1.0, 0.0, 0.0, 1.0))])
        await ui_test.human_delay(10)
        await self._show_widget_popup()

        host = _find_gradient_editor_window()
        self.assertIsNotNone(host)
        # Choosing a real preset must not dismiss the parent editor.
        await self._select_preset("Grayscale")
        self.assertTrue(host.visible)
        editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(editor, GradientFieldEditor)
        self.assertEqual(editor._content.get_keyframes()[0][1], (0.0, 0.0, 0.0, 1.0))

        outside = Vec2(1.0, 1.0)
        parent_title = Vec2(host.position_x + host.width / 2, host.position_y + 5)
        swatch = ui_test.find(f"{host.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'")
        picker_closures = []
        picker_subscription = swatch.widget.model.subscribe_end_edit_fn(lambda *_: picker_closures.append(True))
        try:
            # Returning to the parent dismisses the picker, not the editor.
            await swatch.click()
            await ui_test.human_delay()
            await self._click_for_update(parent_title)
            self.assertEqual(picker_closures, [True])
            self.assertTrue(host.visible)

            # A single click outside both windows dismisses the picker and editor together.
            await swatch.click()
            await ui_test.human_delay()
            await self._click_for_update(outside)
            self.assertEqual(picker_closures, [True, True])
            self.assertFalse(host.visible)
        finally:
            del picker_subscription

        await self._show_widget_popup()
        host = _find_gradient_editor_window()
        self.assertIsNotNone(host)
        editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(editor, GradientFieldEditor)
        await ui_test.find(f"{host.title}//Frame/**/Image[*].name=='MenuBurger'").click()
        await ui_test.human_delay()
        menu = editor._content._presets_menu
        self.assertTrue(menu.shown)
        await self._click_for_update(parent_title)
        self.assertFalse(menu.shown)
        self.assertTrue(host.visible)

        await ui_test.find(f"{host.title}//Frame/**/Image[*].name=='MenuBurger'").click()
        await ui_test.human_delay()
        menu = editor._content._presets_menu
        self.assertTrue(menu.shown)
        await self._click_for_update(outside)
        self.assertFalse(menu.shown)
        self.assertFalse(host.visible)

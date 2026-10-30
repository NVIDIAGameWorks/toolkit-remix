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

__all__ = ("TestColorPickerWindow",)

import colorsys

import omni.ui as ui
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardEventType, KeyboardInput, MouseEventType
from omni.flux.property_widget_builder.delegates.float_value.color import _ChannelModel
from omni.flux.property_widget_builder.delegates.float_value.color_picker import ColorPickerWindow
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test.input import emulate_keyboard, emulate_mouse


class TestColorPickerWindow(AsyncTestCase):
    """Exercise color controls and complete gesture events without a property or USD model."""

    async def setUp(self):
        """Retain real native models until their windows finish closing."""
        self.picker = None
        self.models = []
        self.windows = []
        self.retained_models = []
        self.events = []
        self.colors = []
        self.subscriptions = []
        self.mouse_held = False

    async def tearDown(self):
        """Release held input and native windows even after a failed assertion."""
        if self.mouse_held:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await ui_test.human_delay()
        for window in self.windows:
            window.cancel()
            window.edit_started.clear()
            window.edit_finished.clear()
        await ui_test.human_delay(2)
        self.subscriptions.clear()
        self.picker = None
        self.windows = self.models = self.retained_models = []

    async def _open(self, values=None):
        """Open a fresh native window, optionally replacing its real channel fixture."""
        if values is not None:
            self.models = [_ChannelModel(value) for value in values]
            self.retained_models.append(self.models)
        self.events, self.colors = [], []
        self.picker = ColorPickerWindow(self.models, title="Color picker workflow", context_name=None)
        self.windows.append(self.picker)
        self.picker.edit_started.add(lambda: self.events.append("begin"))
        self.picker.edit_finished.add(lambda: self.events.append("end"))
        self.picker.open(preferred_size=(ColorPickerWindow.WINDOW_WIDTH, ColorPickerWindow.WINDOW_HEIGHT))
        await ui_test.human_delay()
        self.subscriptions = [model.subscribe_value_changed_fn(self._record_color) for model in self.models]

    def _record_color(self, _model):
        """Observe complete normalized colors after every component has updated."""
        if not self.picker._gesture_depth:
            return
        values = self._values()
        if self.colors and self.colors[-1] == values:
            return
        self.assertTrue(all(0 <= value <= 1 for value in values))
        self.colors.append(values)
        self.events.append(values)

    def _values(self):
        """Read the fixture's authoritative channel values."""
        return tuple(model.get_value_as_float() for model in self.models)

    def _control(self, identifier, widget_type="FloatDrag"):
        """Find a live editor by its production identifier."""
        return ui_test.find(f"{self.picker.title}//Frame/**/{widget_type}[*].identifier=='color_picker_{identifier}'")

    async def _edit(self, identifier, text):
        """Type and commit through the actual numeric or hexadecimal control."""
        field = self._control(identifier, "StringField" if identifier == "hex" else "FloatDrag")
        if identifier == "hex":
            await field.double_click()
            await ui_test.human_delay()
        else:
            await field.click()
            await ui_test.human_delay()
            await emulate_keyboard(
                KeyboardEventType.KEY_PRESS, KeyboardInput.LEFT_CONTROL, KEYBOARD_MODIFIER_FLAG_CONTROL
            )
            await ui_test.human_delay()
            try:
                await field.click()
                await ui_test.human_delay()
            finally:
                await emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.LEFT_CONTROL, 0)
                await ui_test.human_delay()
        self.assertEqual(self.events[-1], "begin")
        beginning = len(self.events) - 1
        await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        await ui_test.emulate_char_press(str(text))
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await ui_test.human_delay()
        self._assert_gesture(self.events[beginning:])

    def _assert_gesture(self, events):
        """Require one begin and one end around all complete color previews."""
        self.assertEqual(events[0], "begin")
        self.assertEqual(events[-1], "end")
        self.assertEqual(events.count("begin"), 1)
        self.assertEqual(events.count("end"), 1)

    async def _drag(self, identifier, start, end, widget_type="ImageWithProvider"):
        """Hold and release a real control while checking live complete-color notifications."""
        control = self._control(identifier, widget_type)
        first = control.position + ui_test.Vec2(control.size.x * start[0], control.size.y * start[1])
        last = control.position + ui_test.Vec2(control.size.x * end[0], control.size.y * end[1])
        beginning = len(self.events)
        await emulate_mouse(MouseEventType.MOVE, first)
        await ui_test.human_delay()
        self.mouse_held = True
        await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
        await ui_test.human_delay()
        await emulate_mouse(MouseEventType.MOVE, last)
        await ui_test.human_delay()
        held_events = self.events[beginning:]
        self.assertEqual(held_events[0], "begin")
        self.assertNotIn("end", held_events)
        self.assertTrue(any(isinstance(event, tuple) for event in held_events))
        await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
        self.mouse_held = False
        await ui_test.human_delay()
        self._assert_gesture(self.events[beginning:])

    def _assert_display(self, text):
        """Check that dynamic preview colors use the same bytes as the hexadecimal readout."""
        self.assertEqual(self._control("hex", "StringField").model.get_value_as_string(), text)
        channels = [int(text[index : index + 2], 16) for index in range(1, len(text), 2)]
        expected = sum(channel << (8 * index) for index, channel in enumerate(channels))
        self.assertEqual(self.picker._current_opaque.style["background_color"], expected | 0xFF000000)
        if len(channels) == 4:
            self.assertEqual(self.picker._current_alpha.style["background_color"], expected)

    def _assert_selectors(self):
        """Check that reopened selectors track the preserved channel color."""
        hue, saturation, value = colorsys.rgb_to_hsv(*self._values()[:3])
        plane, bar = self._control("sv", "ImageWithProvider"), self._control("hue", "ImageWithProvider")
        marker = ui_test.find(f"{self.picker.title}//Frame/**/Image[*].name=='ColorPickerHandle'")
        self.assertAlmostEqual(marker.center.x, plane.position.x + saturation * plane.size.x, delta=1)
        self.assertAlmostEqual(marker.center.y, plane.position.y + (1 - value) * plane.size.y, delta=1)
        marker = ui_test.find(f"{self.picker.title}//Frame/**/Image[*].name=='ColorPickerHueHandle'")
        self.assertAlmostEqual(marker.center.y, bar.position.y + hue * bar.size.y, delta=1)

    async def _close(self):
        """Close normally and wait for native teardown before reopening."""
        self.picker.close()
        await ui_test.human_delay(2)
        self.assertFalse(self.picker.is_open)

    async def test_edit_rgb_rgba_text_rejects_invalid_values_and_matches_display_bytes(self):
        """Hexadecimal and tuple edits share validation, byte rounding, and complete-color events."""
        for alpha in ((), (0.5,)):
            with self.subTest(components=3 + len(alpha)):
                await self._open((0.5, 0.25, 0.125, *alpha))
                self._assert_display("#804020" + ("80" if alpha else ""))
                await self._edit("hex", "4080c0" + ("80" if alpha else ""))
                self.assertEqual(self._values(), (64 / 255, 128 / 255, 192 / 255, *((128 / 255,) if alpha else ())))
                self._assert_display("#4080C0" + ("80" if alpha else ""))
                await self._edit("hex", "(.3,.5,1" + (",.5)" if alpha else ")"))
                self.assertEqual(self._values(), (77 / 255, 128 / 255, 1.0, *((128 / 255,) if alpha else ())))
                self._assert_display("#4D80FF" + ("80" if alpha else ""))
                await self._edit("red", 0.7)
                canonical = "#B380FF" + ("80" if alpha else "")
                self._assert_display(canonical)

                # Invalid submissions restore canonical text without publishing a replacement color.
                original, emitted = self._values(), len(self.colors)
                rest = ",".join(".5" for _ in self.models[1:])
                invalid = [
                    "#GG0000",
                    "#" + "1" * (len(self.models) * 2 - 1),
                    "(1,1,1)" if alpha else "(1,1,1,1)",
                    "(.5,,.5)",
                    "[1,0,0]",
                ]
                invalid += [f"({token},{rest})" for token in ("nan", "inf", "-inf", "-.1", "1.1", "red")]
                for text in invalid:
                    with self.subTest(text=text):
                        await self._edit("hex", text)
                        self.assertEqual(self._values(), original)
                        self.assertEqual(len(self.colors), emitted)
                        self._assert_display(canonical)
                await self._close()

    async def test_edit_rgba_channels_clamps_input_and_sync_preserves_authored_hdr(self):
        """Native RGB, HSV, and both alpha fields normalize edits while external synchronization preserves HDR."""
        authored = (2.0, 0.5, -0.25, 1.5)
        await self._open(authored)
        self.assertEqual(self._values(), authored)
        self._assert_display("#FF8000FF")
        for identifier, value, channel in (
            ("red", 3.5, 0),
            ("red", -0.5, 0),
            ("green", 3.5, 1),
            ("blue", -0.5, 2),
            ("alpha", -0.5, 3),
            ("alpha", 1.5, 3),
        ):
            with self.subTest(control=identifier, value=value):
                await self._edit(identifier, value)
                self.assertEqual(self._values()[channel], min(1.0, max(0.0, value)))
                self.assertTrue(all(0 <= component <= 1 for component in self._values()))
        for identifier in ("hue_value", "saturation", "value", "alpha_hsv"):
            for value in (-0.5, 1.5):
                with self.subTest(control=identifier, value=value):
                    await self._edit(identifier, value)
                    self.assertEqual(self._control(identifier).model.get_value_as_float(), 0 if value < 0 else 1)
                    self.assertTrue(all(0 <= component <= 1 for component in self._values()))
        emitted = len(self.colors)
        _ChannelModel.mirror_values(self.models, authored)
        await ui_test.human_delay()
        self.assertEqual(self._values(), authored)
        self.assertEqual(len(self.colors), emitted)
        self._assert_display("#FF8000FF")

    async def test_edit_achromatic_hsv_preserves_chosen_selectors_across_authoritative_sync(self):
        """Hue and saturation selected on black remain useful after white and black synchronization."""
        await self._open((0.0, 0.0, 0.0))
        await self._edit("hue_value", 0.5)
        await self._edit("saturation", 0.75)
        self.assertEqual(self.colors, [])
        _ChannelModel.mirror_values(self.models, (0.0, 0.0, 0.0))
        await ui_test.human_delay()
        self.assertEqual(self._control("hue_value").model.get_value_as_float(), 0.5)
        self.assertEqual(self._control("saturation").model.get_value_as_float(), 0.75)
        await self._edit("value", 0.8)
        for actual, expected in zip(self._values(), (0.2, 0.8, 0.8)):
            self.assertAlmostEqual(actual, expected)
        await self._edit("saturation", 0.0)
        await self._edit("hue_value", 0.75)
        emitted = len(self.colors)
        for color in ((1.0, 1.0, 1.0), (0.0, 0.0, 0.0)):
            _ChannelModel.mirror_values(self.models, color)
            await ui_test.human_delay()
            self.assertEqual(self._values(), color)
            self.assertEqual(self._control("hue_value").model.get_value_as_float(), 0.75)
            self.assertEqual(len(self.colors), emitted)
        await self._edit("saturation", 0.75)
        await self._edit("value", 0.8)
        for actual, expected in zip(self._values(), (0.5, 0.2, 0.8)):
            self.assertAlmostEqual(actual, expected)

    async def test_drag_rgb_rgba_controls_emits_complete_gestures_and_reopens_preserved_color(self):
        """Plane, hue, and native drags publish complete colors that survive reopening."""
        for alpha in ((), (0.4,)):
            with self.subTest(components=3 + len(alpha)):
                await self._open((0.2, 0.2, 0.8, *alpha))
                await self._drag("sv", (0.3, 0.3), (0.5, 0.5))
                await self._drag("hue", (0.5, 0.8), (0.5, 1.0))
                for actual, expected in zip(self._values()[:3], (0.5, 0.25, 0.25)):
                    self.assertAlmostEqual(actual, expected, places=5)
                await self._drag("red", (0.25, 0.5), (0.75, 0.5), "FloatDrag")
                preserved = self._values()
                await self._close()
                await self._open()
                self.assertEqual(self._values(), preserved)
                self.assertEqual(self.colors, [])
                self._assert_selectors()
                await self._close()

    async def test_wheel_over_overflowing_picker_preserves_control_positions_and_color(self):
        """Native wheel input leaves overflowing picker content and its color unchanged."""
        await self._open((0.2, 0.2, 0.8, 0.4))
        plane = self._control("sv", "ImageWithProvider")
        # A fixed-height plane creates a scroll range even when the workspace can fit the normal picker.
        plane.widget.height = ui.Pixel(ColorPickerWindow.WINDOW_HEIGHT)
        self.picker.height = ColorPickerWindow.WINDOW_HEIGHT / 2
        await ui_test.human_delay()
        self.assertGreater(plane.size.y, self.picker.height)
        controls = (plane, self._control("hue", "ImageWithProvider"), self._control("red"))
        positions = [(control.position.x, control.position.y) for control in controls]
        preserved, emitted = self._values(), len(self.colors)
        await ui_test.emulate_mouse_move(plane.position + ui_test.Vec2(4, 4))
        await ui_test.human_delay()
        await ui_test.input.emulate_mouse_scroll(ui_test.Vec2(0, -1200))
        await ui_test.human_delay()
        self.assertEqual([(control.position.x, control.position.y) for control in controls], positions)
        self.assertEqual(self._values(), preserved)
        self.assertEqual(len(self.colors), emitted)

    async def test_close_during_first_numeric_hex_notification_preserves_complete_color(self):
        """Normal dismissal during a channel notification completes the input before native teardown."""
        for identifier, text, expected in (
            ("red", 0.9, (0.9, 0.2, 0.2)),
            ("hex", "#4080C0", (64 / 255, 128 / 255, 192 / 255)),
        ):
            with self.subTest(control=identifier):
                await self._open((0.2, 0.2, 0.2))
                observed = []

                def close_on_first_change(_model, observed=observed):
                    observed.append(self._values())
                    self.picker.close()

                subscription = self.models[0].subscribe_value_changed_fn(close_on_first_change)
                try:
                    await self._edit(identifier, text)
                    await ui_test.human_delay(2)
                    self.assertFalse(self.picker.is_open)
                    for actual, wanted in zip(self._values(), expected):
                        self.assertAlmostEqual(actual, wanted)
                    self.assertEqual(self.colors[-1], self._values())
                    for actual, wanted in zip(observed[0], expected):
                        self.assertAlmostEqual(actual, wanted)
                finally:
                    del subscription

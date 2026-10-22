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

E2E tests for CurveEditorToolbar.

Tests toolbar button interactions simulating user clicks, asserting both
UI state (button styling) and model state.
"""

from collections.abc import Callable

import carb.input
import carb.settings
import omni.appwindow
import omni.kit.app
import omni.kit.commands
import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.kit.undo
from carb.input import KeyboardEventType, KeyboardInput
from omni import ui

from omni.flux.fcurve.widget import CurveBounds, FCurve, FCurveKey, KeyReference, TangentType
from omni.flux.curve_editor.widget import CurveEditorWidget
from omni.flux.curve_editor.widget.payload import curve_to_payload, payload_to_curve
from omni.flux.utils.widget import InMemoryGroupedKeysModel

__all__ = ["TestToolbar"]

_COLOR_ALPHA_MASK = 0xFF000000


def _commit_payload(model, curve_id: str, curve: FCurve) -> None:
    model.commit_payload(curve_id, curve_to_payload(curve))


def _get_curve(model, curve_id: str) -> FCurve | None:
    return payload_to_curve(curve_id, model.get_payload(curve_id))


class ModifierKeyDownScope:
    """Context manager for holding a modifier key down during operations.

    IMPORTANT: The __aexit__ waits for a full frame after releasing the key to ensure
    the buffered KEY_RELEASE event is processed by the input system. Without this,
    subsequent tests may see the modifier key as still held.
    """

    def __init__(self, key: KeyboardInput, human_delay_speed: int = 2):
        self._key = key
        self._human_delay_speed = human_delay_speed

    async def __aenter__(self):
        await self._emulate_keyboard(KeyboardEventType.KEY_PRESS, self._key, self._key)
        await ui_test.human_delay(self._human_delay_speed)

    async def __aexit__(self, *args):
        await self._emulate_keyboard(KeyboardEventType.KEY_RELEASE, self._key)
        # Frame wait ensures the buffered KEY_RELEASE is processed by the input system.
        # Without this, subsequent operations may interpret the modifier as still held.
        await omni.kit.app.get_app().next_update_async()

    async def _emulate_keyboard(self, event_type: KeyboardEventType, key: KeyboardInput, modifier: KeyboardInput = 0):
        keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        carb.input.acquire_input_provider().buffer_keyboard_key_event(keyboard, event_type, key, modifier)


class TestToolbar(omni.kit.test.AsyncTestCase):
    """Tests for CurveEditorToolbar button interactions."""

    async def setUp(self):
        """Initialize model - widget is created lazily after curves are set up."""
        await omni.kit.app.get_app().next_update_async()
        self._model = InMemoryGroupedKeysModel()
        self._widget = None
        self.window = None
        await omni.kit.app.get_app().next_update_async()

    async def tearDown(self):
        # Clear selection first to prevent dangling references
        if self._widget and self._widget.fcurve_widget:
            self._widget.fcurve_widget.clear_selection()

        # Allow widget destruction to complete
        await omni.kit.app.get_app().next_update_async()

        # Now destroy window
        if self.window:
            self.window.visible = False
            self.window.destroy()
            self.window = None

        # Clear model
        if self._model:
            self._model.destroy()
        self._model = None

        # Multiple frame waits to ensure full cleanup
        for _ in range(3):
            await omni.kit.app.get_app().next_update_async()

    async def _build_widget(self, *, on_change: Callable[[], None] | None = None) -> None:
        """Build the widget after curves are committed to the model.

        Args:
            on_change: Optional callback invoked when the editor changes a curve.
        """
        self.window = ui.Window(
            "Toolbar Test",
            width=700,
            height=500,
            flags=ui.WINDOW_FLAGS_NO_SCROLLBAR,
        )

        with self.window.frame:
            with ui.ZStack():
                # Widget builds automatically in constructor (omni.ui pattern)
                # Use padded ranges to ensure keyframes at edges are fully visible/clickable
                self._widget = CurveEditorWidget(
                    model=self._model,
                    time_range=(-0.1, 1.1),
                    value_range=(-0.1, 1.1),
                    show_toolbar=True,
                    on_change=on_change,
                )

        # Wait for UI to fully initialize
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_simple_curve(
        self,
        in_type: TangentType = TangentType.LINEAR,
        out_type: TangentType = TangentType.LINEAR,
        broken: bool = True,
    ) -> None:
        """Setup a simple 3-key curve with specified tangent types."""
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.5,
                    in_tangent_type=in_type,
                    out_tangent_type=out_type,
                    tangent_broken=broken,
                ),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=in_type,
                    out_tangent_type=out_type,
                    tangent_broken=broken,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.3,
                    in_tangent_type=in_type,
                    out_tangent_type=out_type,
                    tangent_broken=broken,
                ),
            ],
            color=0xFF3560FF,
        )
        _commit_payload(self._model, "test", curve)

    def _setup_two_curves(self) -> None:
        """Setup two curves for multi-curve tests."""
        curve1 = FCurve(
            id="curve1",
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.3,
                    in_tangent_type=TangentType.LINEAR,
                    out_tangent_type=TangentType.LINEAR,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=0.5,
                    value=0.7,
                    in_tangent_type=TangentType.LINEAR,
                    out_tangent_type=TangentType.LINEAR,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.5,
                    in_tangent_type=TangentType.LINEAR,
                    out_tangent_type=TangentType.LINEAR,
                    tangent_broken=True,
                ),
            ],
            color=0xFF3560FF,
        )
        curve2 = FCurve(
            id="curve2",
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.7,
                    in_tangent_type=TangentType.AUTO,
                    out_tangent_type=TangentType.AUTO,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=0.5,
                    value=0.3,
                    in_tangent_type=TangentType.AUTO,
                    out_tangent_type=TangentType.AUTO,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.6,
                    in_tangent_type=TangentType.AUTO,
                    out_tangent_type=TangentType.AUTO,
                    tangent_broken=True,
                ),
            ],
            color=0xFF60FF35,
        )
        _commit_payload(self._model, "curve1", curve1)
        _commit_payload(self._model, "curve2", curve2)

    @property
    def _toolbar(self):
        """Get the toolbar instance."""
        return self._widget._toolbar

    @property
    def _fcurve_widget(self):
        """Get the inner FCurveWidget."""
        return self._widget._canvas._fcurve_widget

    def _get_key_screen_pos(self, curve_id: str, key_index: int) -> tuple[float, float]:
        """Get screen position of a keyframe."""
        mgr = self._fcurve_widget._managers.get(curve_id)
        if mgr and key_index < len(mgr.key_handles):
            return mgr.key_handles[key_index].screen_center
        return (0.0, 0.0)

    async def _click_key(self, curve_id: str, key_index: int) -> None:
        """Click on a keyframe to select it."""
        x, y = self._get_key_screen_pos(curve_id, key_index)
        pos = ui_test.Vec2(x, y)

        await ui_test.input.emulate_mouse_move(pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

    async def _shift_click_key(self, curve_id: str, key_index: int) -> None:
        """Shift+click on a keyframe to add to selection."""
        x, y = self._get_key_screen_pos(curve_id, key_index)
        pos = ui_test.Vec2(x, y)
        await ui_test.input.emulate_mouse_move(pos)
        await ui_test.human_delay(3)
        async with ModifierKeyDownScope(key=KeyboardInput.LEFT_SHIFT):
            await ui_test.emulate_mouse_click()
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

    async def _click_button(self, btn: ui.Button) -> None:
        """Click a toolbar button."""
        # Get button center position
        x = btn.screen_position_x + btn.computed_width / 2
        y = btn.screen_position_y + btn.computed_height / 2
        pos = ui_test.Vec2(x, y)
        await ui_test.input.emulate_mouse_move(pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

    async def _click_away(self) -> None:
        """Click on empty area to deselect."""
        canvas = ui_test.find("Toolbar Test//Frame/**/Frame[*].identifier=='CurveEditorCanvas'").widget
        await ui_test.input.emulate_mouse_move(
            ui_test.Vec2(
                canvas.screen_position_x + canvas.computed_width * 0.75,
                canvas.screen_position_y + canvas.computed_height * 0.90,
            )
        )
        await ui_test.human_delay()
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay()

    def _is_button_active(self, btn: ui.Button) -> bool:
        """Check if button has active styling via its name suffix."""
        return btn.name.endswith("Active")

    def _get_model_key(self, curve_id: str, key_index: int) -> FCurveKey:
        """Get a key from the model."""
        curve = _get_curve(self._model, curve_id)
        return curve.keys[key_index]

    def _assert_viewport_ranges(self, time_range: tuple[float, float], value_range: tuple[float, float]) -> None:
        """Verify fitted bounds and exact synchronization between the canvas and curve viewport."""
        viewport = self._widget._canvas._viewport
        self.assertEqual((viewport.time_min, viewport.time_max), self._fcurve_widget.time_range)
        self.assertEqual((viewport.value_min, viewport.value_max), self._fcurve_widget.value_range)
        for actual, expected in zip(self._fcurve_widget.time_range, time_range):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(self._fcurve_widget.value_range, value_range):
            self.assertAlmostEqual(actual, expected)

    # ─────────────────────────────────────────────────────────────────────────
    # Tests: Button Initial State
    # ─────────────────────────────────────────────────────────────────────────

    async def test_buttons_initializes_inactive_without_selection(self):
        """All tangent buttons should be inactive when no selection exists."""
        self._setup_simple_curve()
        await self._build_widget()

        # No selection yet - all tangent type buttons should be inactive
        for ttype, btn in self._toolbar._left_tangent_btns.items():
            self.assertFalse(
                self._is_button_active(btn), f"Left {ttype.name} button should be inactive without selection"
            )
        for ttype, btn in self._toolbar._right_tangent_btns.items():
            self.assertFalse(
                self._is_button_active(btn), f"Right {ttype.name} button should be inactive without selection"
            )

        # A disabled toggle cannot modify curves without selected editable keys.
        self.assertFalse(
            self._is_button_active(self._toolbar._link_tangents_btn), "Link button should be inactive without selection"
        )
        self.assertFalse(self._toolbar._link_tangents_btn.checked)
        self.assertFalse(self._toolbar._link_tangents_btn.enabled)
        before = self._model.get_payload("test")
        toggle = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnLink'")
        await toggle.click()
        await ui_test.human_delay()
        self.assertEqual(self._model.get_payload("test"), before)

    async def test_buttons_become_active_when_selection_is_made(self):
        """Tangent buttons should show active state when keyframe is selected."""
        self._setup_simple_curve(in_type=TangentType.AUTO, out_type=TangentType.LINEAR, broken=True)
        await self._build_widget()

        # Select middle keyframe
        await self._click_key("test", 1)

        # Assert correct tangent type buttons are active
        self.assertTrue(
            self._is_button_active(self._toolbar._left_tangent_btns[TangentType.AUTO]),
            "Left AUTO button should be active",
        )
        self.assertTrue(
            self._is_button_active(self._toolbar._right_tangent_btns[TangentType.LINEAR]),
            "Right LINEAR button should be active",
        )

        # Other tangent buttons should be inactive
        self.assertFalse(
            self._is_button_active(self._toolbar._left_tangent_btns[TangentType.LINEAR]),
            "Left LINEAR button should be inactive",
        )

        # An unlocked selection enables the toggle without pressing it.
        self.assertTrue(self._toolbar._link_tangents_btn.enabled)
        self.assertFalse(self._toolbar._link_tangents_btn.checked)
        self.assertEqual(self._toolbar._link_tangents_btn.name, "CurveEditorBtnBroken")
        self.assertFalse(
            self._is_button_active(self._toolbar._link_tangents_btn),
            "Link button should be inactive for broken tangent",
        )

    async def test_buttons_become_inactive_when_selection_is_cleared(self):
        """Buttons should return to inactive when selection is cleared."""
        self._setup_simple_curve(in_type=TangentType.SMOOTH, out_type=TangentType.SMOOTH)
        await self._build_widget()

        # Select then deselect
        await self._click_key("test", 1)
        await self._click_away()

        # All buttons should be inactive again
        for ttype, btn in self._toolbar._left_tangent_btns.items():
            self.assertFalse(
                self._is_button_active(btn), f"Left {ttype.name} button should be inactive after deselection"
            )

        self.assertFalse(
            self._is_button_active(self._toolbar._link_tangents_btn), "Link button should be inactive after deselection"
        )
        self.assertFalse(self._toolbar._link_tangents_btn.checked)
        self.assertFalse(self._toolbar._link_tangents_btn.enabled)

    # ─────────────────────────────────────────────────────────────────────────
    # Tests: Selection Updates
    # ─────────────────────────────────────────────────────────────────────────

    async def test_tangent_type_buttons_update_to_the_newly_selected_keyframe(self):
        """Selecting different keyframes should update toolbar to show their tangent types."""
        # Setup curve with different tangent types per key
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.5,
                    in_tangent_type=TangentType.LINEAR,
                    out_tangent_type=TangentType.LINEAR,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.AUTO,
                    out_tangent_type=TangentType.SMOOTH,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.3,
                    in_tangent_type=TangentType.FLAT,
                    out_tangent_type=TangentType.STEP,
                    tangent_broken=True,
                ),
            ],
        )
        _commit_payload(self._model, "test", curve)
        await self._build_widget()
        await omni.kit.app.get_app().next_update_async()

        # Select key 0 - LINEAR/LINEAR
        await self._click_key("test", 0)
        self.assertTrue(self._is_button_active(self._toolbar._left_tangent_btns[TangentType.LINEAR]))
        self.assertTrue(self._is_button_active(self._toolbar._right_tangent_btns[TangentType.LINEAR]))

        # Select key 1 - AUTO/SMOOTH
        await self._click_key("test", 1)
        self.assertTrue(self._is_button_active(self._toolbar._left_tangent_btns[TangentType.AUTO]))
        self.assertTrue(self._is_button_active(self._toolbar._right_tangent_btns[TangentType.SMOOTH]))

        # Select key 2 - FLAT/STEP
        await self._click_key("test", 2)
        self.assertTrue(self._is_button_active(self._toolbar._left_tangent_btns[TangentType.FLAT]))
        self.assertTrue(self._is_button_active(self._toolbar._right_tangent_btns[TangentType.STEP]))

    async def test_toggle_mixed_selection_locks_all_then_unlocks_all(self):
        """The toggle refreshes from selected keys and locks a mixed selection on its first click."""
        # Setup: key 0 = broken, key 1 = linked
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.5, tangent_broken=True),
                FCurveKey(time=0.5, value=0.8, tangent_broken=False),
                FCurveKey(time=1.0, value=0.3, tangent_broken=True),
            ],
        )
        _commit_payload(self._model, "test", curve)
        await self._build_widget()

        # Select broken key
        await self._click_key("test", 0)
        self.assertFalse(self._toolbar._link_tangents_btn.checked)
        self.assertEqual(self._toolbar._link_tangents_btn.name, "CurveEditorBtnBroken")
        self.assertFalse(self._is_button_active(self._toolbar._link_tangents_btn))

        # Select linked key
        await self._click_key("test", 1)
        self.assertTrue(self._is_button_active(self._toolbar._link_tangents_btn))
        self.assertTrue(self._toolbar._link_tangents_btn.checked)
        self.assertEqual(self._toolbar._link_tangents_btn.name, "CurveEditorBtnLinkActive")

        # Expanding a linked selection must discard the previous all-linked state.
        await self._shift_click_key("test", 0)
        toggle = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnLink'")
        self.assertFalse(toggle.widget.checked)
        self.assertEqual(toggle.widget.name, "CurveEditorBtnBroken")
        self.assertIn("Mixed", toggle.widget.tooltip)
        await toggle.click()
        await ui_test.human_delay()
        self.assertTrue(toggle.widget.checked)
        self.assertEqual(toggle.widget.name, "CurveEditorBtnLinkActive")
        self.assertEqual(self._model.get_payload("test")["tangentBrokens"], [False, False, True])

        # Clicking the same control again unlocks both selected keys.
        await toggle.click()
        await ui_test.human_delay()
        self.assertFalse(toggle.widget.checked)
        self.assertEqual(toggle.widget.name, "CurveEditorBtnBroken")
        self.assertEqual(self._model.get_payload("test")["tangentBrokens"], [True, True, True])

    async def test_toggle_on_change_clears_selection_disables_lock_button(self):
        """A change callback clearing selection leaves the lock control disabled and unchecked."""

        def clear_selection() -> None:
            """Clear the editor's key selection after an edit."""
            self._widget.fcurve_widget.clear_selection()

        self._setup_simple_curve(broken=True)
        await self._build_widget(on_change=clear_selection)
        await self._click_key("test", 1)

        # The edit callback clears selection before the click finishes updating its presentation.
        toggle = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnLink'")
        await toggle.click()
        await ui_test.human_delay()

        self.assertEqual(self._model.get_payload("test")["tangentBrokens"], [True, False, True])
        self.assertEqual(
            [key.tangent_broken for key in self._widget.fcurve_widget.curves["test"].keys], [True, False, True]
        )
        self.assertEqual(self._widget.fcurve_widget.selected_keys, [])
        self.assertFalse(toggle.widget.enabled)
        self.assertFalse(toggle.widget.checked)
        self.assertEqual(toggle.widget.name, "CurveEditorBtnBroken")
        self.assertEqual(toggle.widget.tooltip, "Select editable keys to lock or unlock tangents.")

    async def test_toggle_on_change_selects_other_broken_key_refreshes_lock_button(self):
        """A change callback selecting another broken key leaves the lock control ready to lock it."""
        self._setup_simple_curve(broken=True)
        await self._build_widget(on_change=lambda: self._widget.fcurve_widget.select_keys([KeyReference("test", 1)]))
        await self._click_key("test", 0)

        # The completed edit locks the original key while the callback changes which key the toolbar represents.
        toggle = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnLink'")
        await toggle.click()
        await ui_test.human_delay()

        self.assertEqual(self._model.get_payload("test")["tangentBrokens"], [False, True, True])
        self.assertEqual(
            [key.tangent_broken for key in self._widget.fcurve_widget.curves["test"].keys], [False, True, True]
        )
        self.assertEqual(self._widget.fcurve_widget.selected_keys, [KeyReference("test", 1)])
        self.assertTrue(toggle.widget.enabled)
        self.assertFalse(toggle.widget.checked)
        self.assertEqual(toggle.widget.name, "CurveEditorBtnBroken")
        self.assertEqual(toggle.widget.tooltip, "Tangents unlocked — click to lock.")

    # ─────────────────────────────────────────────────────────────────────────
    # Tests: Link/Broken Tangent Actions
    # ─────────────────────────────────────────────────────────────────────────

    async def test_link_button_mirrors_tangents_and_updates_model(self):
        """Clicking Link button should mirror tangents and update model."""
        # Setup with broken tangents and different types
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.5, tangent_broken=True),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.AUTO,
                    out_tangent_type=TangentType.LINEAR,
                    in_tangent_x=-0.1,
                    in_tangent_y=0.1,
                    out_tangent_x=0.1,
                    out_tangent_y=0.2,
                    tangent_broken=True,
                ),
                FCurveKey(time=1.0, value=0.3, tangent_broken=True),
            ],
        )
        _commit_payload(self._model, "test", curve)
        await self._build_widget()

        # Select key 1 and click Link button
        await self._click_key("test", 1)
        await self._click_button(self._toolbar._link_tangents_btn)

        # Assert UI: Link button active
        self.assertTrue(self._is_button_active(self._toolbar._link_tangents_btn))
        self.assertTrue(self._toolbar._link_tangents_btn.checked)

        # Assert model: tangent_broken = False
        key = self._get_model_key("test", 1)
        self.assertFalse(key.tangent_broken, "Model should have tangent_broken=False")

    async def test_toggle_linked_key_preserves_tangent_types_and_positions(self):
        """Unlocking a linked key preserves its tangent types and positions."""
        # Setup with linked tangents
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.5),
                FCurveKey(
                    time=0.5,
                    value=0.7,
                    in_tangent_type=TangentType.SMOOTH,
                    out_tangent_type=TangentType.SMOOTH,
                    in_tangent_x=-0.1,
                    in_tangent_y=-0.05,
                    out_tangent_x=0.1,
                    out_tangent_y=0.05,
                    tangent_broken=False,
                ),
                FCurveKey(time=1.0, value=0.3),
            ],
        )
        _commit_payload(self._model, "test", curve)
        await self._build_widget()

        # Get original tangent values before making changes
        orig_key = self._get_model_key("test", 1)
        orig_in_type = orig_key.in_tangent_type
        orig_out_type = orig_key.out_tangent_type

        # Unlock the selected linked key through the same toggle used for locking.
        await self._click_key("test", 1)
        await self._click_button(self._toolbar._link_tangents_btn)

        self.assertFalse(self._toolbar._link_tangents_btn.checked)
        self.assertEqual(self._toolbar._link_tangents_btn.name, "CurveEditorBtnBroken")
        self.assertFalse(self._is_button_active(self._toolbar._link_tangents_btn))

        # Assert model: tangent_broken = True, types preserved
        key = self._get_model_key("test", 1)
        self.assertTrue(key.tangent_broken, "Model should have tangent_broken=True")
        self.assertEqual(key.in_tangent_type, orig_in_type, "In tangent type should be preserved")
        self.assertEqual(key.out_tangent_type, orig_out_type, "Out tangent type should be preserved")

    # ─────────────────────────────────────────────────────────────────────────
    # Tests: Tangent Type Changes
    # ─────────────────────────────────────────────────────────────────────────

    async def test_linked_keyframe_tangent_type_change_affects_both_sides(self):
        """With linked tangents, changing type should affect BOTH in and out."""
        # Setup with linked tangents (broken=False)
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.5),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.LINEAR,
                    out_tangent_type=TangentType.LINEAR,
                    tangent_broken=False,
                ),
                FCurveKey(time=1.0, value=0.3),
            ],
        )
        _commit_payload(self._model, "test", curve)
        await self._build_widget()

        # Select key 1
        await self._click_key("test", 1)

        # Click LEFT AUTO button (should set BOTH tangents to AUTO since linked)
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.AUTO])

        # Assert UI: Both AUTO buttons active
        self.assertTrue(self._is_button_active(self._toolbar._left_tangent_btns[TangentType.AUTO]))
        self.assertTrue(self._is_button_active(self._toolbar._right_tangent_btns[TangentType.AUTO]))

        # Assert model: Both tangent types are AUTO
        key = self._get_model_key("test", 1)
        self.assertEqual(key.in_tangent_type, TangentType.AUTO, "In tangent should be AUTO")
        self.assertEqual(key.out_tangent_type, TangentType.AUTO, "Out tangent should be AUTO")

    async def test_broken_keyframe_tangent_type_change_affects_one_side(self):
        """With broken tangents, changing type should only affect the clicked side."""
        # Setup with broken tangents
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.5),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.LINEAR,
                    out_tangent_type=TangentType.LINEAR,
                    tangent_broken=True,
                ),
                FCurveKey(time=1.0, value=0.3),
            ],
        )
        _commit_payload(self._model, "test", curve)
        await self._build_widget()

        # Select key 1
        await self._click_key("test", 1)

        # Click LEFT SMOOTH button (should ONLY change in tangent)
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.SMOOTH])

        # Assert UI: Only left SMOOTH active, right still LINEAR
        self.assertTrue(self._is_button_active(self._toolbar._left_tangent_btns[TangentType.SMOOTH]))
        self.assertTrue(self._is_button_active(self._toolbar._right_tangent_btns[TangentType.LINEAR]))

        # Assert model: Only in tangent changed
        key = self._get_model_key("test", 1)
        self.assertEqual(key.in_tangent_type, TangentType.SMOOTH, "In tangent should be SMOOTH")
        self.assertEqual(key.out_tangent_type, TangentType.LINEAR, "Out tangent should still be LINEAR")

    # ─────────────────────────────────────────────────────────────────────────
    # Tests: Multi-Selection
    # ─────────────────────────────────────────────────────────────────────────

    async def test_multiselect_mixed_tangent_types_shows_mixed_label(self):
        """Multi-selecting keys with different types should show MIXED label."""
        # Setup with different tangent types per key
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.5,
                    in_tangent_type=TangentType.AUTO,
                    out_tangent_type=TangentType.AUTO,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.LINEAR,
                    out_tangent_type=TangentType.LINEAR,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.3,
                    in_tangent_type=TangentType.SMOOTH,
                    out_tangent_type=TangentType.SMOOTH,
                    tangent_broken=True,
                ),
            ],
        )
        _commit_payload(self._model, "test", curve)
        await self._build_widget()

        # Select key 0, then ctrl+click key 1 to multi-select
        await self._click_key("test", 0)
        await self._shift_click_key("test", 1)

        # Assert UI: No tangent type button should be active (mixed)
        for ttype, btn in self._toolbar._left_tangent_btns.items():
            self.assertFalse(self._is_button_active(btn), f"Left {ttype.name} should be inactive for mixed selection")

        # Assert labels show "MIXED"
        self.assertIn("MIXED", self._toolbar._left_tangent_label.text)
        self.assertIn("MIXED", self._toolbar._right_tangent_label.text)

    async def test_multiselect_same_tangent_types_shows_shared_type(self):
        """Multi-selecting keys with same types should show that type as active."""
        # Setup with same tangent types (FLAT)
        self._setup_simple_curve(in_type=TangentType.FLAT, out_type=TangentType.FLAT, broken=True)
        await self._build_widget()

        # Multi-select keys 0 and 1
        await self._click_key("test", 0)
        await self._shift_click_key("test", 1)

        # Assert UI: FLAT buttons should be active
        self.assertTrue(self._is_button_active(self._toolbar._left_tangent_btns[TangentType.FLAT]))
        self.assertTrue(self._is_button_active(self._toolbar._right_tangent_btns[TangentType.FLAT]))

        # Assert labels show "FLAT"
        self.assertIn("FLAT", self._toolbar._left_tangent_label.text)
        self.assertIn("FLAT", self._toolbar._right_tangent_label.text)

    # ─────────────────────────────────────────────────────────────────────────
    # Tests: Multi-Curve Selection
    # ─────────────────────────────────────────────────────────────────────────

    async def test_multi_curve_selection_setting_tangent_type(self):
        """Setting tangent type with keys from multiple curves should update all."""
        self._setup_two_curves()
        await self._build_widget()

        # Select key from curve1, then ctrl+click key from curve2
        await self._click_key("curve1", 1)
        await self._shift_click_key("curve2", 1)

        # Click SMOOTH button
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.SMOOTH])

        # Assert model: Both curves' key 1 should have SMOOTH in tangent
        key1 = self._get_model_key("curve1", 1)
        key2 = self._get_model_key("curve2", 1)
        self.assertEqual(key1.in_tangent_type, TangentType.SMOOTH)
        self.assertEqual(key2.in_tangent_type, TangentType.SMOOTH)

    async def test_multi_curve_selection_setting_link_and_broken_tangents(self):
        """Setting link/broken with keys from multiple curves should update all."""
        self._setup_two_curves()
        await self._build_widget()

        # Select keys from both curves
        await self._click_key("curve1", 1)
        await self._shift_click_key("curve2", 1)

        # Click Link button
        await self._click_button(self._toolbar._link_tangents_btn)

        # Assert model: Both keys should have tangent_broken=False
        key1 = self._get_model_key("curve1", 1)
        key2 = self._get_model_key("curve2", 1)
        self.assertFalse(key1.tangent_broken)
        self.assertFalse(key2.tangent_broken)

        # The same button unlocks both channels on its next click.
        await self._click_button(self._toolbar._link_tangents_btn)
        self.assertTrue(self._get_model_key("curve1", 1).tangent_broken)
        self.assertTrue(self._get_model_key("curve2", 1).tangent_broken)
        self.assertFalse(self._toolbar._link_tangents_btn.checked)

    async def test_toggle_ineligible_selection_ignores_keys_and_preserves_their_payloads(self):
        """Hidden, locked, missing, and invalid keys cannot determine or receive a toggle edit."""
        for curve_id, value, broken in (("editable", 0.2, False), ("locked", 0.5, True), ("hidden", 0.8, True)):
            keys = [FCurveKey(time=0.5, value=value, tangent_broken=broken)]
            if curve_id == "editable":
                keys.append(FCurveKey(time=0.75, value=0.3, tangent_broken=True))
            _commit_payload(
                self._model,
                curve_id,
                FCurve(id=curve_id, keys=keys),
            )
        await self._build_widget()
        widget = self._fcurve_widget
        widget.curves["locked"].locked = True
        widget.set_curve_visible("hidden", False)
        ineligible = [
            KeyReference("locked", 0),
            KeyReference("hidden", 0),
            KeyReference("missing", 0),
            KeyReference("editable", -1),
            KeyReference("editable", 10),
        ]
        widget.select_keys([KeyReference("editable", 0), *ineligible])
        await ui_test.human_delay()
        before = {curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}

        # Only the linked editable key contributes to the current state and the next click.
        toggle = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnLink'")
        self.assertTrue(toggle.widget.enabled)
        self.assertTrue(toggle.widget.checked)
        await toggle.click()
        await ui_test.human_delay()
        self.assertTrue(self._get_model_key("editable", 0).tangent_broken)
        for curve_id in ("locked", "hidden"):
            self.assertEqual(self._model.get_payload(curve_id), before[curve_id])

        # A negative stale index must not be interpreted as the editable curve's last key.
        await toggle.click()
        await ui_test.human_delay()
        self.assertEqual(self._model.get_payload("editable")["tangentBrokens"], [False, True])
        for curve_id in ("locked", "hidden"):
            self.assertEqual(self._model.get_payload(curve_id), before[curve_id])

        # Stale references alone must leave the toggle disabled and every payload untouched.
        widget.select_keys(ineligible)
        await ui_test.human_delay()
        before = {curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}
        self.assertFalse(toggle.widget.enabled)
        self.assertFalse(toggle.widget.checked)
        await toggle.click()
        await ui_test.human_delay()
        self.assertEqual({curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}, before)

    async def test_frame_buttons_displayed_curves_fit_independently_and_preserve_data(self):
        """Frame each axis across displayed keys, preserving the other axis, selection, and payloads."""
        for curve_id, positions in (
            ("editable", ((0.3, 0.4), (0.5, 0.5), (0.6, 0.6))),
            ("locked", ((0.2, 0.1), (0.8, 0.9))),
            ("hidden", ((-5.0, -5.0), (5.0, 5.0))),
        ):
            _commit_payload(
                self._model,
                curve_id,
                FCurve(id=curve_id, keys=[FCurveKey(time=time, value=value) for time, value in positions]),
            )
        await self._build_widget()
        self._fcurve_widget.curves["locked"].locked = True
        self._fcurve_widget.set_curve_visible("hidden", False)
        await ui_test.human_delay()
        await self._click_key("editable", 1)
        selection = self._fcurve_widget.selected_keys
        self.assertEqual(selection, [KeyReference("editable", 1)])
        before = {curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}
        time_button = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnFrameTime'")
        value_button = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnFrameValue'")
        self.assertIsNotNone(time_button)
        self.assertIsNotNone(value_button)
        self.assertTrue(time_button.widget.enabled)
        self.assertTrue(value_button.widget.enabled)

        # Narrowing the view leaves the extreme keys offscreen; selection must not restrict fitting.
        self._widget.set_time_range(0.4, 0.6)
        self._widget.set_value_range(0.4, 0.6)
        await ui_test.human_delay()
        original_value_range = self._fcurve_widget.value_range
        await time_button.click()
        await ui_test.human_delay()
        self._assert_viewport_ranges((0.14, 0.86), original_value_range)
        self.assertEqual(self._fcurve_widget.value_range, original_value_range)
        fitted_time_range = self._fcurve_widget.time_range
        await time_button.click()
        await ui_test.human_delay()
        self.assertEqual(self._fcurve_widget.time_range, fitted_time_range)
        self.assertEqual(self._fcurve_widget.value_range, original_value_range)

        await value_button.click()
        await ui_test.human_delay()
        self._assert_viewport_ranges((0.14, 0.86), (0.02, 0.98))
        self.assertEqual(self._fcurve_widget.time_range, fitted_time_range)
        fitted_value_range = self._fcurve_widget.value_range
        await value_button.click()
        await ui_test.human_delay()
        self.assertEqual(self._fcurve_widget.value_range, fitted_value_range)
        self.assertEqual(self._fcurve_widget.time_range, fitted_time_range)

        # Reversing the order must give the same full view without disturbing the untouched axis.
        self._widget.set_time_range(0.45, 0.55)
        self._widget.set_value_range(0.45, 0.55)
        await ui_test.human_delay()
        original_time_range = self._fcurve_widget.time_range
        await value_button.click()
        await ui_test.human_delay()
        self._assert_viewport_ranges(original_time_range, fitted_value_range)
        self.assertEqual(self._fcurve_widget.time_range, original_time_range)
        await time_button.click()
        await ui_test.human_delay()
        self.assertEqual(self._fcurve_widget.time_range, fitted_time_range)
        self.assertEqual(self._fcurve_widget.value_range, fitted_value_range)

        self.assertEqual(self._fcurve_widget.time_range, fitted_time_range)
        self.assertEqual(self._fcurve_widget.value_range, fitted_value_range)
        self.assertEqual(self._fcurve_widget.selected_keys, selection)
        self.assertEqual({curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}, before)

        # A channel filter excludes unloaded curves even though their payloads remain in the model.
        self._widget._canvas.set_selected_curve_ids({"editable"})
        await ui_test.human_delay()
        self.assertEqual(set(self._fcurve_widget.curves), {"editable"})
        self.assertEqual(self._fcurve_widget.selected_keys, selection)
        await time_button.click()
        await ui_test.human_delay()
        self._assert_viewport_ranges((0.27, 0.63), fitted_value_range)
        await value_button.click()
        await ui_test.human_delay()
        self._assert_viewport_ranges((0.27, 0.63), (0.38, 0.62))
        self.assertEqual(self._fcurve_widget.selected_keys, selection)
        self.assertEqual({curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}, before)

    async def test_frame_buttons_singleton_curve_pad_both_axes(self):
        """A single key receives nonzero padding when each axis is framed without selection."""
        _commit_payload(self._model, "test", FCurve(id="test", keys=[FCurveKey(time=0.5, value=0.25)]))
        await self._build_widget()
        time_button = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnFrameTime'")
        value_button = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnFrameValue'")

        # Axis controls remain usable even though no key has been selected.
        await time_button.click()
        await ui_test.human_delay()
        self._assert_viewport_ranges((0.4, 0.6), (-0.1, 1.1))
        await value_button.click()
        await ui_test.human_delay()
        self._assert_viewport_ranges((0.4, 0.6), (0.15, 0.35))
        self.assertEqual(self._fcurve_widget.selected_keys, [])

    async def test_frame_buttons_constant_value_curve_preserve_nonzero_value_span(self):
        """Framing a flat curve pads its constant value while fitting the full time extent."""
        _commit_payload(
            self._model,
            "test",
            FCurve(id="test", keys=[FCurveKey(time=0.2, value=0.5), FCurveKey(time=0.8, value=0.5)]),
        )
        await self._build_widget()
        # A zero value span must not collapse the value viewport.
        for identifier in ("CurveEditorBtnFrameValue", "CurveEditorBtnFrameTime"):
            button = ui_test.find(f"Toolbar Test//Frame/**/Button[*].identifier=='{identifier}'")
            await button.click()
            await ui_test.human_delay()
        self._assert_viewport_ranges((0.14, 0.86), (0.4, 0.6))

    async def test_frame_buttons_empty_data_preserve_viewport(self):
        """Both frame controls leave the viewport unchanged when there are no keys."""
        await self._build_widget()
        self._widget.set_time_range(0.2, 0.7)
        self._widget.set_value_range(-0.4, 0.8)
        await ui_test.human_delay()
        before = (self._fcurve_widget.time_range, self._fcurve_widget.value_range)

        # Empty-editor framing has no fallback range that could unexpectedly reset the view.
        for identifier in ("CurveEditorBtnFrameTime", "CurveEditorBtnFrameValue"):
            button = ui_test.find(f"Toolbar Test//Frame/**/Button[*].identifier=='{identifier}'")
            await button.click()
            await ui_test.human_delay()
            self._assert_viewport_ranges(*before)
            self.assertEqual((self._fcurve_widget.time_range, self._fcurve_widget.value_range), before)

    async def test_multi_curve_selection_deleting_a_keyframe(self):
        """Deleting a multi-curve selection removes each selected key once."""
        self._setup_two_curves()
        await self._build_widget()

        # Select middle keys from both curves
        await self._click_key("curve1", 1)
        await self._shift_click_key("curve2", 1)

        # Public selections may repeat a reference; Delete must still remove each key only once.
        selected = self._fcurve_widget.selected_keys
        self._fcurve_widget.select_keys([*selected, selected[0]])
        await ui_test.human_delay()
        self.assertEqual(self._fcurve_widget.selected_keys, [*selected, selected[0]])

        # Click delete button
        await self._click_button(self._toolbar._delete_key_btn)

        # Assert model: Both curves now have 2 keys
        curve1 = _get_curve(self._model, "curve1")
        curve2 = _get_curve(self._model, "curve2")
        self.assertEqual(len(curve1.keys), 2, "curve1 should have 2 keys after delete")
        self.assertEqual(len(curve2.keys), 2, "curve2 should have 2 keys after delete")

    async def test_clicking_key_on_other_curve_deselects_first_curve(self):
        """Clicking a keyframe on curve2 without shift should deselect curve1's selection."""
        self._setup_two_curves()
        await self._build_widget()

        fw = self._fcurve_widget

        # Select key 1 on curve1
        await self._click_key("curve1", 1)
        sel = fw.selected_keys
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0].curve_id, "curve1")

        # Click key 1 on curve2 (no shift) — should deselect curve1
        await self._click_key("curve2", 1)
        sel = fw.selected_keys
        self.assertEqual(len(sel), 1, "Only one key should be selected after non-shift click on another curve")
        self.assertEqual(sel[0].curve_id, "curve2", "Selected key should be from curve2")
        self.assertEqual(sel[0].key_index, 1)

    async def test_shift_clicking_key_on_other_curve_keeps_both_selected(self):
        """Shift+clicking a keyframe on curve2 should keep curve1's selection."""
        self._setup_two_curves()
        await self._build_widget()

        fw = self._fcurve_widget

        # Select key 1 on curve1
        await self._click_key("curve1", 1)
        self.assertEqual(len(fw.selected_keys), 1)

        # Shift+click key 1 on curve2 — should ADD to selection
        await self._shift_click_key("curve2", 1)
        sel = fw.selected_keys
        self.assertEqual(len(sel), 2, "Both keys should be selected after shift-click")
        curve_ids = {s.curve_id for s in sel}
        self.assertEqual(curve_ids, {"curve1", "curve2"})

    # ─────────────────────────────────────────────────────────────────────────
    # Tests: Add Keyframe
    # ─────────────────────────────────────────────────────────────────────────

    async def test_add_keyframe_inserts_after_selected_key(self):
        """Add keyframe should insert between selected key and next key."""
        self._setup_simple_curve()
        await self._build_widget()

        # Original key times: 0.0, 0.5, 1.0
        orig_curve = _get_curve(self._model, "test")
        self.assertEqual(len(orig_curve.keys), 3)

        # Select key 0 (time=0.0) and click add
        await self._click_key("test", 0)
        await self._click_button(self._toolbar._add_key_btn)

        # Assert: New key added between key 0 and key 1
        curve = _get_curve(self._model, "test")
        self.assertEqual(len(curve.keys), 4, "Should have 4 keys after add")
        # New key should be at time ~0.25 (midpoint between 0.0 and 0.5)
        self.assertAlmostEqual(curve.keys[1].time, 0.25, delta=0.01)

    async def test_add_keyframe_multiple_curves_uses_shared_time_and_selects_new_keys(self):
        """Add samples every displayed curve at the first curve's shared time."""
        for curve_id, keys in {
            "first": [(0.0, 0.0), (1.0, 1.0)],
            "second": [(0.0, 0.8), (0.25, 0.6), (1.0, 0.0)],
        }.items():
            _commit_payload(self._model, curve_id, FCurve(id=curve_id, keys=[FCurveKey(*key) for key in keys]))
        await self._build_widget()

        # One click inserts on both curves even without selecting existing keys.
        await self._click_button(self._toolbar._add_key_btn)

        self.assertEqual(self._fcurve_widget.selected_keys, [KeyReference("first", 1), KeyReference("second", 2)])
        self.assertAlmostEqual(_get_curve(self._model, "first").keys[1].time, 0.5)
        self.assertAlmostEqual(_get_curve(self._model, "first").keys[1].value, 0.5)
        self.assertAlmostEqual(_get_curve(self._model, "second").keys[2].time, 0.5)
        self.assertAlmostEqual(_get_curve(self._model, "second").keys[2].value, 0.4)

    async def test_add_keyframe_existing_shared_time_reuses_and_selects_key(self):
        """An exact-time key on another curve is reused without changing its payload."""
        for curve_id, times in {"first": [0.0, 1.0], "second": [0.0, 0.5, 1.0]}.items():
            _commit_payload(self._model, curve_id, FCurve(id=curve_id, keys=[FCurveKey(time, 0.5) for time in times]))
        await self._build_widget()
        previous_payload = self._model.get_payload("second")

        # Add inserts on the first curve while selecting the existing shared-time key on the second.
        await self._click_button(self._toolbar._add_key_btn)

        self.assertEqual(self._fcurve_widget.selected_keys, [KeyReference("first", 1), KeyReference("second", 1)])
        self.assertEqual(self._model.get_payload("second"), previous_payload)
        self.assertEqual(len(_get_curve(self._model, "first").keys), 3)

    async def test_add_keyframe_spacing_conflict_preserves_all_curves_and_selection(self):
        """A nearby key prevents the shared insertion without partially editing curves."""
        for curve_id, times in {"first": [0.0, 1.0], "second": [0.0, 0.5005, 1.0]}.items():
            _commit_payload(self._model, curve_id, FCurve(id=curve_id, keys=[FCurveKey(time, 0.5) for time in times]))
        await self._build_widget()
        self._fcurve_widget.select_keys([KeyReference("first", 0)])
        previous_payloads = {curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}

        # The disabled native Add control must preserve both curves and the current key selection.
        await self._click_button(self._toolbar._add_key_btn)

        self.assertFalse(self._toolbar._add_key_btn.enabled)
        self.assertIn("close", self._toolbar._add_key_btn.tooltip)
        self.assertEqual(self._fcurve_widget.selected_keys, [KeyReference("first", 0)])
        self.assertEqual(
            {curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}, previous_payloads
        )

    async def test_add_keyframe_target_bounds_conflict_preserves_all_curves(self):
        """A shared time outside one target's bounds prevents all insertion."""
        self._setup_two_curves()
        await self._build_widget()
        self._fcurve_widget.set_curve_bounds("curve2", CurveBounds(time_max=0.2))
        previous_payloads = {curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}

        # Changed bounds are rechecked when the user presses Add, before either curve can be edited.
        self.assertTrue(self._toolbar._add_key_btn.enabled)
        await self._click_button(self._toolbar._add_key_btn)

        self.assertFalse(self._toolbar._add_key_btn.enabled)
        self.assertIn("bounds", self._toolbar._add_key_btn.tooltip)
        self.assertEqual(
            {curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}, previous_payloads
        )

    async def test_add_keyframe_without_selection_inserts_after_first(self):
        """Add keyframe with no selection should add after first key."""
        self._setup_simple_curve()
        await self._build_widget()

        # Ensure no selection
        await self._click_away()

        # Click add
        await self._click_button(self._toolbar._add_key_btn)

        # Assert: New key added after key 0
        curve = _get_curve(self._model, "test")
        self.assertEqual(len(curve.keys), 4, "Should have 4 keys after add")
        # New key should be at time ~0.25 (midpoint between 0.0 and 0.5)
        self.assertAlmostEqual(curve.keys[1].time, 0.25, delta=0.01)

    async def test_add_keyframe_after_last_key_extends_curve(self):
        """Add keyframe after last key should extend beyond the last key time."""
        self._setup_simple_curve()
        await self._build_widget()
        self._fcurve_widget.set_curve_bounds("test", CurveBounds(time_max=1.1))

        # Select last key (time=1.0)
        await self._click_key("test", 2)
        await self._click_button(self._toolbar._add_key_btn)

        # Assert: New key added after last key
        curve = _get_curve(self._model, "test")
        self.assertEqual(len(curve.keys), 4, "Should have 4 keys after add")
        # New key should be at time ~1.1 (0.1 offset from last key)
        self.assertAlmostEqual(curve.keys[3].time, 1.1, delta=0.01)

    async def test_add_keyframe_in_memory_preserves_existing_kit_redo(self):
        """Editing standalone in-memory data leaves unrelated Kit redo history intact."""
        self._setup_simple_curve()
        await self._build_widget()
        setting_path = "/tests/curveEditor/standaloneRedo"
        settings = carb.settings.get_settings()
        settings.set(setting_path, False)
        omni.kit.undo.clear_stack()
        omni.kit.commands.execute("ChangeSetting", path=setting_path, value=True)
        omni.kit.undo.undo()
        redo_before = list(omni.kit.undo.get_redo_stack())
        try:
            # A standalone edit must leave the user's unrelated Kit redo action available.
            await self._click_button(self._toolbar._add_key_btn)

            self.assertEqual(len(_get_curve(self._model, "test").keys), 4)
            self.assertEqual(list(omni.kit.undo.get_redo_stack()), redo_before)
            omni.kit.undo.redo()
            self.assertTrue(settings.get(setting_path))
        finally:
            omni.kit.undo.clear_stack()
            settings.destroy_item(setting_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Tests: Delete Keyframe
    # ─────────────────────────────────────────────────────────────────────────

    async def test_delete_keyframe_after_display_rebuild_preserves_highlights_and_hidden_payload(self):
        """Curve-colored selections survive display changes without affecting hidden data."""
        self._setup_two_curves()
        await self._build_widget()
        widget = self._widget.fcurve_widget
        colors = {"curve1": 0xFFDDA844, "curve2": 0x8060FF35}
        selected_colors = {"curve1": 0xFFF9EECD, "curve2": 0x80D9FFC4}
        for curve_id, color in colors.items():
            widget.set_curve_color(curve_id, color)
            await ui_test.human_delay()

        def assert_selected_styles():
            """Check curve-derived fills and native selection borders on the visible middle keys."""
            self.assertEqual(set(widget._managers), set(colors))
            for curve_id, manager in widget._managers.items():
                self.assertEqual([handle.selected for handle in manager.key_handles], [False, True, False])
                rectangle = manager.key_handles[1]._drag_rect
                self.assertTrue(rectangle.selected)
                style = rectangle.style
                self.assertEqual(int(style["background_color"]), selected_colors[curve_id])
                outline = style["Rectangle::FCurveKey:selected"]
                self.assertEqual(outline["border_width"], 1.0)
                self.assertEqual(int(outline["border_color"]), colors[curve_id] & _COLOR_ALPHA_MASK)

        # The user selects the middle key on each displayed curve.
        await self._click_key("curve1", 1)
        await self._shift_click_key("curve2", 1)
        assert_selected_styles()
        before = {curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}
        changed_curves = []
        selection_events = []
        self._display_test_subscriptions = (
            widget.subscribe_curve_changed(changed_curves.append),
            widget.subscribe_selection_changed(selection_events.append),
        )
        try:
            # Recoloring must preserve the visible handles' selection without editing storage.
            colors["curve1"] = 0x404480CC
            selected_colors["curve1"] = 0x40CDE3F6
            widget.set_curve_color("curve1", colors["curve1"])
            await ui_test.human_delay()
            assert_selected_styles()
            self.assertEqual(selection_events, [])

            # Hiding the second curve must leave the visible selected handle highlighted.
            widget.set_curve_visible("curve2", False)
            await ui_test.human_delay()
            self.assertEqual(
                [handle.selected for handle in widget._managers["curve1"].key_handles], [False, True, False]
            )
            self.assertEqual(
                {curve_id: self._model.get_payload(curve_id) for curve_id in self._model.group_ids}, before
            )
            self.assertEqual(changed_curves, [])
            self.assertEqual(len(selection_events), 1)
            self.assertEqual(
                selection_events[0].selected_keys,
                (KeyReference("curve1", 1), KeyReference("curve2", 1)),
            )
            # Visibility refreshes numeric eligibility while preserving the selected key references.
            value_field = ui_test.find("Toolbar Test//Frame/**/FloatDrag[*].identifier=='CurveEditorValueDrag'")
            self.assertAlmostEqual(value_field.model.as_float, 0.7)

            # Delete acts on the highlighted visible key, preserving the hidden channel's complete payload.
            delete = ui_test.find("Toolbar Test//Frame/**/Button[*].identifier=='CurveEditorBtnDeleteKey'")
            self.assertTrue(delete.widget.enabled)
            await delete.click()
            await ui_test.human_delay()
            self.assertEqual([key.time for key in _get_curve(self._model, "curve1").keys], [0.0, 1.0])
            self.assertEqual(self._model.get_payload("curve2"), before["curve2"])
            self.assertEqual(changed_curves, ["curve1"])
            self.assertEqual([handle.selected for handle in widget._managers["curve1"].key_handles], [False, False])
        finally:
            self._display_test_subscriptions = None

    async def test_delete_keyframe_removes_from_model_and_clears_selection(self):
        """Deleting a keyframe should remove it and clear selection state."""
        self._setup_simple_curve()
        await self._build_widget()
        await ui_test.human_delay(50)  # TODO: Investigate why there are vestigial widgets corrupting mouse clicks.

        # Select middle key and delete
        await self._click_key("test", 1)
        await self._click_button(self._toolbar._delete_key_btn)

        # Assert model: Only 2 keys remain
        curve = _get_curve(self._model, "test")
        self.assertEqual(len(curve.keys), 2, "Should have 2 keys after delete")
        # Keys should be at 0.0 and 1.0 (middle key removed)
        self.assertAlmostEqual(curve.keys[0].time, 0.0, delta=0.01)
        self.assertAlmostEqual(curve.keys[1].time, 1.0, delta=0.01)

        # Assert UI: No selection, buttons inactive
        self.assertFalse(self._toolbar._has_selection, "Should have no selection after delete")

    async def test_deleting_last_keyframe_is_forbidden_and_results_in_nop(self):
        """Cannot delete the last keyframe - curve must have at least 1 key."""
        # Setup with only 2 keys (minimum viable curve for deletion test)
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.5),
                FCurveKey(time=1.0, value=0.5),
            ],
        )
        _commit_payload(self._model, "test", curve)
        await self._build_widget()

        # Select first key and delete - should work
        await self._click_key("test", 0)
        await self._click_button(self._toolbar._delete_key_btn)

        curve = _get_curve(self._model, "test")
        self.assertEqual(len(curve.keys), 1, "Should have 1 key after first delete")

        # Select the remaining key and try to delete - should be no-op
        await self._click_key("test", 0)
        await self._click_button(self._toolbar._delete_key_btn)

        curve = _get_curve(self._model, "test")
        self.assertEqual(len(curve.keys), 1, "Should still have 1 key - cannot delete last")

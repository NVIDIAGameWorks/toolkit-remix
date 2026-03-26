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

import carb.input
import omni.appwindow
import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
from carb.input import KeyboardEventType, KeyboardInput
from omni import ui

from omni.flux.fcurve.widget import FCurve, FCurveKey, TangentType
from omni.flux.curve_editor.widget import CurveEditorWidget, InMemoryCurveModel

__all__ = ["TestToolbar"]


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
        self._model = InMemoryCurveModel()
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

    async def _build_widget(self):
        """Build the widget AFTER curves are committed to model."""
        self.window = ui.Window(
            "Toolbar Test",
            width=900,
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
        self._model.commit_curve("test", curve)

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
        self._model.commit_curve("curve1", curve1)
        self._model.commit_curve("curve2", curve2)

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
        # Use FCurveWidget's clear_selection directly for reliability
        # (clicking empty area can fail if position calculation is off)
        self._fcurve_widget.clear_selection()
        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()

    def _is_button_active(self, btn: ui.Button) -> bool:
        """Check if button has active styling via its name suffix."""
        return btn.name.endswith("Active")

    def _get_model_key(self, curve_id: str, key_index: int) -> FCurveKey:
        """Get a key from the model."""
        curve = self._model.get_curve(curve_id)
        return curve.keys[key_index]

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

        # Link/broken buttons should both be inactive
        self.assertFalse(
            self._is_button_active(self._toolbar._link_tangents_btn), "Link button should be inactive without selection"
        )
        self.assertFalse(
            self._is_button_active(self._toolbar._broken_tangents_btn),
            "Broken button should be inactive without selection",
        )

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

        # Broken button should be active (tangent_broken=True)
        self.assertTrue(
            self._is_button_active(self._toolbar._broken_tangents_btn),
            "Broken button should be active for broken tangent",
        )
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
        self.assertFalse(
            self._is_button_active(self._toolbar._broken_tangents_btn),
            "Broken button should be inactive after deselection",
        )

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
        self._model.commit_curve("test", curve)
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

    async def test_link_and_broken_tangents_button_updates_to_the_newly_selected_keyframe(self):
        """Link/broken buttons should reflect the selected keyframe's state."""
        # Setup: key 0 = broken, key 1 = linked
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.5, tangent_broken=True),
                FCurveKey(time=0.5, value=0.8, tangent_broken=False),
                FCurveKey(time=1.0, value=0.3, tangent_broken=True),
            ],
        )
        self._model.commit_curve("test", curve)
        await self._build_widget()

        # Select broken key
        await self._click_key("test", 0)
        self.assertTrue(self._is_button_active(self._toolbar._broken_tangents_btn))
        self.assertFalse(self._is_button_active(self._toolbar._link_tangents_btn))

        # Select linked key
        await self._click_key("test", 1)
        self.assertTrue(self._is_button_active(self._toolbar._link_tangents_btn))
        self.assertFalse(self._is_button_active(self._toolbar._broken_tangents_btn))

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
        self._model.commit_curve("test", curve)
        await self._build_widget()

        # Select key 1 and click Link button
        await self._click_key("test", 1)
        await self._click_button(self._toolbar._link_tangents_btn)

        # Assert UI: Link button active
        self.assertTrue(self._is_button_active(self._toolbar._link_tangents_btn))
        self.assertFalse(self._is_button_active(self._toolbar._broken_tangents_btn))

        # Assert model: tangent_broken = False
        key = self._get_model_key("test", 1)
        self.assertFalse(key.tangent_broken, "Model should have tangent_broken=False")

    async def test_broken_button_preserves_tangent_types_and_positions(self):
        """Clicking Broken button should set broken=True while preserving tangent data."""
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
        self._model.commit_curve("test", curve)
        await self._build_widget()

        # Get original tangent values before making changes
        orig_key = self._get_model_key("test", 1)
        orig_in_type = orig_key.in_tangent_type
        orig_out_type = orig_key.out_tangent_type

        # Select key 1 and click Broken button
        await self._click_key("test", 1)
        await self._click_button(self._toolbar._broken_tangents_btn)

        # Assert UI: Broken button active
        self.assertTrue(self._is_button_active(self._toolbar._broken_tangents_btn))
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
        self._model.commit_curve("test", curve)
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
        self._model.commit_curve("test", curve)
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
        self._model.commit_curve("test", curve)
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

    async def test_multi_curve_selection_deleting_a_keyframe(self):
        """Deleting with multi-curve selection should remove keys from all curves."""
        self._setup_two_curves()
        await self._build_widget()

        # Select middle keys from both curves
        await self._click_key("curve1", 1)
        await self._shift_click_key("curve2", 1)

        # Click delete button
        await self._click_button(self._toolbar._delete_key_btn)

        # Assert model: Both curves now have 2 keys
        curve1 = self._model.get_curve("curve1")
        curve2 = self._model.get_curve("curve2")
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
        orig_curve = self._model.get_curve("test")
        self.assertEqual(len(orig_curve.keys), 3)

        # Select key 0 (time=0.0) and click add
        await self._click_key("test", 0)
        await self._click_button(self._toolbar._add_key_btn)

        # Assert: New key added between key 0 and key 1
        curve = self._model.get_curve("test")
        self.assertEqual(len(curve.keys), 4, "Should have 4 keys after add")
        # New key should be at time ~0.25 (midpoint between 0.0 and 0.5)
        self.assertAlmostEqual(curve.keys[1].time, 0.25, delta=0.01)

    async def test_add_keyframe_without_selection_inserts_after_first(self):
        """Add keyframe with no selection should add after first key."""
        self._setup_simple_curve()
        await self._build_widget()

        # Ensure no selection
        await self._click_away()

        # Click add
        await self._click_button(self._toolbar._add_key_btn)

        # Assert: New key added after key 0
        curve = self._model.get_curve("test")
        self.assertEqual(len(curve.keys), 4, "Should have 4 keys after add")
        # New key should be at time ~0.25 (midpoint between 0.0 and 0.5)
        self.assertAlmostEqual(curve.keys[1].time, 0.25, delta=0.01)

    async def test_add_keyframe_after_last_key_extends_curve(self):
        """Add keyframe after last key should extend beyond the last key time."""
        self._setup_simple_curve()
        await self._build_widget()

        # Select last key (time=1.0)
        await self._click_key("test", 2)
        await self._click_button(self._toolbar._add_key_btn)

        # Assert: New key added after last key
        curve = self._model.get_curve("test")
        self.assertEqual(len(curve.keys), 4, "Should have 4 keys after add")
        # New key should be at time ~1.1 (0.1 offset from last key)
        self.assertAlmostEqual(curve.keys[3].time, 1.001, delta=0.01)

    # ─────────────────────────────────────────────────────────────────────────
    # Tests: Delete Keyframe
    # ─────────────────────────────────────────────────────────────────────────

    async def test_delete_keyframe_removes_from_model_and_clears_selection(self):
        """Deleting a keyframe should remove it and clear selection state."""
        self._setup_simple_curve()
        await self._build_widget()
        await ui_test.human_delay(50)  # TODO: Investigate why there are vestigial widgets corrupting mouse clicks.

        # Select middle key and delete
        await self._click_key("test", 1)
        await self._click_button(self._toolbar._delete_key_btn)

        # Assert model: Only 2 keys remain
        curve = self._model.get_curve("test")
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
        self._model.commit_curve("test", curve)
        await self._build_widget()

        # Select first key and delete - should work
        await self._click_key("test", 0)
        await self._click_button(self._toolbar._delete_key_btn)

        curve = self._model.get_curve("test")
        self.assertEqual(len(curve.keys), 1, "Should have 1 key after first delete")

        # Select the remaining key and try to delete - should be no-op
        await self._click_key("test", 0)
        await self._click_button(self._toolbar._delete_key_btn)

        curve = self._model.get_curve("test")
        self.assertEqual(len(curve.keys), 1, "Should still have 1 key - cannot delete last")

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

E2E tests for PrimvarCurveModel + CurveEditorWidget integration.

Tests that user interactions in the visual editor (dragging keyframes,
changing tangent types via toolbar, adding/deleting keys) are correctly
persisted as USD primvars on the backing prim.

Every test is BLACK-BOX: simulate mouse interactions on the widget,
then assert primvar values directly on the USD prim.

Every test asserts against the expected primvar naming format:
    primvars:{curve_id}:{property}
"""

import carb.input
import os

import omni.appwindow
import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.kit.undo
import omni.usd
from carb.input import KeyboardEventType, KeyboardInput
from omni import ui
from pxr import UsdGeom

from omni.flux.fcurve.widget import FCurve, FCurveKey, TangentType
from omni.flux.curve_editor.widget import CurveEditorWidget, PrimvarCurveModel

__all__ = ["TestPrimvarIntegration"]


# ─────────────────────────────────────────────────────────────────────────────
# Primvar naming constants
# ─────────────────────────────────────────────────────────────────────────────

#: Per-key array suffixes (all arrays must have the same length)
ARRAY_SUFFIXES = (
    "times",
    "values",
    "inTangentTimes",
    "inTangentValues",
    "inTangentTypes",
    "outTangentTimes",
    "outTangentValues",
    "outTangentTypes",
    "tangentBrokens",
)

#: Scalar (non-array) suffixes
SCALAR_SUFFIXES = (
    "preInfinity",
    "postInfinity",
)

#: All primvar suffixes for a curve
ALL_SUFFIXES = ARRAY_SUFFIXES + SCALAR_SUFFIXES


def _approx_equal_tuples(a, b, tol=1e-3):
    """Check if two tuples of floats are approximately equal."""
    if a is None or b is None:
        return a is b
    if len(a) != len(b):
        return False
    return all(abs(float(x) - float(y)) < tol for x, y in zip(a, b))


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

    async def _emulate_keyboard(self, event_type: KeyboardEventType, key: KeyboardInput, modifier: KeyboardInput = 0):
        keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        carb.input.acquire_input_provider().buffer_keyboard_key_event(keyboard, event_type, key, modifier)


class TestPrimvarIntegration(omni.kit.test.AsyncTestCase):
    """E2E tests: CurveEditorWidget + PrimvarCurveModel -> USD primvars."""

    # ─────────────────────────────────────────────────────────────────────────
    # Setup / Teardown
    # ─────────────────────────────────────────────────────────────────────────

    async def setUp(self):
        # Create a fresh USD stage with a prim to hold curve primvars
        await omni.usd.get_context().new_stage_async()
        self._stage = omni.usd.get_context().get_stage()
        self._prim_path = "/World/TestCurve"
        UsdGeom.Xform.Define(self._stage, self._prim_path)

        self._model = None
        self._widget = None
        self._window = None

    async def tearDown(self):
        # Clear selection first to prevent dangling references
        if self._widget and self._widget.fcurve_widget:
            self._widget.fcurve_widget.clear_selection()

        if self._window:
            self._window.visible = False
            self._window.destroy()
            self._window = None

        if self._model:
            self._model.destroy()
            self._model = None

        await omni.usd.get_context().close_stage_async()

    # ─────────────────────────────────────────────────────────────────────────
    # Model / Widget helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _create_model(self, curve_ids: list[str]) -> PrimvarCurveModel:
        """Create a PrimvarCurveModel for the given curve_ids."""
        self._model = PrimvarCurveModel(
            prim_path=self._prim_path,
            curve_ids=curve_ids,
            usd_context_name="",
        )
        return self._model

    async def _build_widget(self):
        """Build the CurveEditorWidget AFTER curves are committed."""
        self._window = ui.Window(
            "Primvar Integration Test",
            width=900,
            height=500,
            flags=ui.WINDOW_FLAGS_NO_SCROLLBAR,
        )
        with self._window.frame:
            with ui.ZStack():
                self._widget = CurveEditorWidget(
                    model=self._model,
                    time_range=(-0.1, 1.1),
                    value_range=(-0.1, 1.1),
                    show_toolbar=True,
                )

        # CurveEditorWidget needs 2 frames: frame 1 computes canvas layout and
        # triggers set_viewport_size via computed_content_size_changed_fn;
        # frame 2 applies the repositioned Placer offsets so screen_position is valid.
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()

    # ─────────────────────────────────────────────────────────────────────────
    # Widget accessors
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def _fcurve_widget(self):
        return self._widget._canvas._fcurve_widget

    @property
    def _toolbar(self):
        return self._widget._toolbar

    # ─────────────────────────────────────────────────────────────────────────
    # Screen-position helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_key_screen_pos(self, curve_id: str, key_index: int) -> tuple[float, float]:
        """Get screen position of a keyframe."""
        mgr = self._fcurve_widget._managers.get(curve_id)
        if mgr and key_index < len(mgr.key_handles):
            return mgr.key_handles[key_index].screen_center
        return (0.0, 0.0)

    def _get_tangent_screen_pos(self, curve_id: str, key_index: int, is_in_tangent: bool) -> tuple[float, float]:
        """Get screen position of a tangent handle."""
        mgr = self._fcurve_widget._managers.get(curve_id)
        if mgr and key_index < len(mgr._groups):
            g = mgr._groups[key_index]
            handle = g.in_h if is_in_tangent else g.out_h
            if handle:
                return handle.screen_center
        return (0.0, 0.0)

    def _model_to_screen(self, time: float, value: float) -> tuple[float, float]:
        """Convert model coordinates to screen position."""
        fw = self._fcurve_widget
        px, py = fw.viewport.model_to_pixel(time, value)
        stack = fw._stack
        return stack.screen_position_x + px, stack.screen_position_y + py

    # ─────────────────────────────────────────────────────────────────────────
    # Interaction helpers (all pixel-level, black-box)
    # ─────────────────────────────────────────────────────────────────────────

    async def _click_key(self, curve_id: str, key_index: int) -> None:
        """Click on a keyframe to select it."""
        x, y = self._get_key_screen_pos(curve_id, key_index)
        pos = ui_test.Vec2(x, y)
        await ui_test.input.emulate_mouse_move(pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay(3)

    async def _shift_click_key(self, curve_id: str, key_index: int) -> None:
        """Shift+click on a keyframe to add to selection."""
        x, y = self._get_key_screen_pos(curve_id, key_index)
        pos = ui_test.Vec2(x, y)
        await ui_test.input.emulate_mouse_move(pos)
        await ui_test.human_delay(3)
        async with ModifierKeyDownScope(key=KeyboardInput.LEFT_SHIFT):
            await ui_test.emulate_mouse_click()
        await ui_test.human_delay(3)

    async def _click_button(self, btn: ui.Button) -> None:
        """Click a toolbar button."""
        x = btn.screen_position_x + btn.computed_width / 2
        y = btn.screen_position_y + btn.computed_height / 2
        pos = ui_test.Vec2(x, y)
        await ui_test.input.emulate_mouse_move(pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay(3)

    async def _drag(self, from_pos: tuple[float, float], to_pos: tuple[float, float]) -> None:
        """Emulate a mouse drag from one screen position to another."""
        start = ui_test.Vec2(*from_pos)
        end = ui_test.Vec2(*to_pos)
        await ui_test.input.emulate_mouse_move(start)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_drag_and_drop(start, end)
        await ui_test.human_delay(3)

    async def _click_away(self) -> None:
        """Click on empty area to deselect."""
        self._fcurve_widget.clear_selection()

    # ─────────────────────────────────────────────────────────────────────────
    # Primvar assertion helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _prim(self):
        """Get the USD prim."""
        return self._stage.GetPrimAtPath(self._prim_path)

    def _read_primvar(self, curve_id: str, suffix: str):
        """Read a single primvar attribute value."""
        attr = self._prim().GetAttribute(f"primvars:{curve_id}:{suffix}")
        self.assertTrue(
            attr and attr.IsValid(),
            f"Primvar primvars:{curve_id}:{suffix} should exist on prim",
        )
        return attr.Get()

    def _assert_primvar_format(self, curve_id: str) -> None:
        """Assert all 11 expected primvar attributes exist with correct naming."""
        prim = self._prim()
        for suffix in ALL_SUFFIXES:
            attr_name = f"primvars:{curve_id}:{suffix}"
            attr = prim.GetAttribute(attr_name)
            self.assertTrue(
                attr and attr.IsValid(),
                f"Expected primvar '{attr_name}' to exist on prim",
            )
            self.assertIsNotNone(
                attr.Get(),
                f"Expected primvar '{attr_name}' to have a value",
            )

    def _assert_primvar_arrays_consistent(self, curve_id: str) -> None:
        """Assert all per-key array primvars have the same length."""
        lengths = {}
        for suffix in ARRAY_SUFFIXES:
            val = self._read_primvar(curve_id, suffix)
            lengths[suffix] = len(val)

        first_len = lengths["times"]
        for suffix, length in lengths.items():
            self.assertEqual(
                length,
                first_len,
                f"primvars:{curve_id}:{suffix} has {length} elements, expected {first_len} (same as :times)",
            )

    def _read_all_primvar_values(self, curve_id: str) -> dict:
        """Read all primvar values for a curve into a dict keyed by suffix."""
        result = {}
        for suffix in ALL_SUFFIXES:
            result[suffix] = self._read_primvar(curve_id, suffix)
        return result

    def _get_model_key(self, curve_id: str, key_index: int) -> FCurveKey:
        """Get a key from the model (reads from USD)."""
        curve = self._model.get_curve(curve_id)
        return curve.keys[key_index]

    def _snapshot_all_primvars(self, curve_id: str) -> dict:
        """Take a snapshot of all primvar values for a curve (for undo comparison).

        Returns a dict keyed by suffix. Array values are converted to plain
        Python lists/tuples so comparisons are value-based, not identity-based.
        """
        result = {}
        prim = self._prim()
        for suffix in ALL_SUFFIXES:
            attr = prim.GetAttribute(f"primvars:{curve_id}:{suffix}")
            if attr and attr.IsValid():
                val = attr.Get()
                # Convert Vt arrays to tuples for stable equality comparison
                if hasattr(val, "__len__") and not isinstance(val, str):
                    result[suffix] = tuple(val)
                else:
                    result[suffix] = val
            else:
                result[suffix] = None
        return result

    def _assert_primvars_match_snapshot(
        self,
        curve_id: str,
        snapshot: dict,
        msg_prefix: str = "",
    ) -> None:
        """Assert every primvar value matches the given snapshot.

        Uses approximate comparison for float values (tolerance 1e-6) since
        USD round-trips can introduce tiny floating-point discrepancies.
        Token and bool arrays are compared exactly.
        """
        current = self._snapshot_all_primvars(curve_id)
        for suffix in ALL_SUFFIXES:
            cur_val = current[suffix]
            snap_val = snapshot[suffix]

            if cur_val is None and snap_val is None:
                continue

            # For token arrays and scalar tokens, compare exactly
            if suffix.endswith("Types") or suffix.endswith("Infinity"):
                self.assertEqual(
                    cur_val,
                    snap_val,
                    f"{msg_prefix}primvars:{curve_id}:{suffix} does not match snapshot",
                )
                continue

            # For bool arrays, compare exactly
            if suffix == "tangentBrokens":
                self.assertEqual(
                    cur_val,
                    snap_val,
                    f"{msg_prefix}primvars:{curve_id}:{suffix} does not match snapshot",
                )
                continue

            # For double arrays, compare with tolerance
            if isinstance(cur_val, tuple) and isinstance(snap_val, tuple):
                self.assertEqual(
                    len(cur_val),
                    len(snap_val),
                    f"{msg_prefix}primvars:{curve_id}:{suffix} array length mismatch",
                )
                for i, (c, s) in enumerate(zip(cur_val, snap_val)):
                    self.assertAlmostEqual(
                        float(c),
                        float(s),
                        places=5,
                        msg=f"{msg_prefix}primvars:{curve_id}:{suffix}[{i}] does not match snapshot",
                    )
            else:
                self.assertEqual(
                    cur_val,
                    snap_val,
                    f"{msg_prefix}primvars:{curve_id}:{suffix} does not match snapshot",
                )

    async def _undo(self) -> None:
        """Perform a single undo and wait for the USD change to propagate."""
        omni.kit.undo.undo()

    async def _undo_until_snapshot(
        self,
        curve_id: str,
        snapshot: dict,
        max_undos: int = 20,
    ) -> None:
        """Undo repeatedly until the primvars match the snapshot (or max_undos reached).

        A single mouse drag may generate multiple undo entries (one per
        intermediate mouse position). This helper undoes enough times to
        fully reverse such operations.
        """
        for _i in range(max_undos):
            omni.kit.undo.undo()

            current = self._snapshot_all_primvars(curve_id)
            # Check if times array matches (sufficient indicator for drag reversal)
            if _approx_equal_tuples(current.get("times"), snapshot.get("times")):
                # Give extra frames for full settle
                return

        self.fail(f"Failed to reach target snapshot after {max_undos} undos")

    # ─────────────────────────────────────────────────────────────────────────
    # Curve setup helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _make_curve(
        self,
        curve_id: str,
        in_type: TangentType = TangentType.LINEAR,
        out_type: TangentType = TangentType.LINEAR,
        broken: bool = True,
        color: int = 0xFF3560FF,
        key_positions: list[tuple[float, float]] | None = None,
    ) -> FCurve:
        """Create a 3-key curve in the 0..1 range.

        Args:
            key_positions: Optional list of (time, value) tuples for each key.
                Defaults to [(0.0, 0.5), (0.5, 0.8), (1.0, 0.3)].
                Use different positions in multi-curve tests to avoid keyframe
                overlap (overlapping keys cause drags/clicks to hit all curves).
        """
        positions = key_positions or [(0.0, 0.5), (0.5, 0.8), (1.0, 0.3)]
        return FCurve(
            id=curve_id,
            keys=[
                FCurveKey(
                    time=t,
                    value=v,
                    in_tangent_type=in_type,
                    out_tangent_type=out_type,
                    tangent_broken=broken,
                )
                for t, v in positions
            ],
            color=color,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # Group 1: Primvar Format Validation
    # ═════════════════════════════════════════════════════════════════════════

    async def test_committed_curve_creates_all_expected_primvar_attributes(self):
        """Committing a curve should create all 11 primvar attributes with correct naming."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        curve = self._make_curve(curve_id)
        model.commit_curve(curve_id, curve)

        self._assert_primvar_format(curve_id)

        prim = self._prim()
        expected_names = [f"primvars:{curve_id}:{s}" for s in ALL_SUFFIXES]
        for name in expected_names:
            attr = prim.GetAttribute(name)
            self.assertTrue(attr and attr.IsValid(), f"Missing: {name}")

        for suffix in ARRAY_SUFFIXES:
            val = self._read_primvar(curve_id, suffix)
            self.assertEqual(len(val), 3, f"primvars:{curve_id}:{suffix} should have 3 elements")

    async def test_primvar_array_lengths_stay_consistent_after_multiple_edits(self):
        """After add/delete/edit, all per-key arrays must have the same length."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id))
        await self._build_widget()

        # Initial: 3 keys
        self._assert_primvar_arrays_consistent(curve_id)

        # Add a keyframe (click key 0, click add)
        await self._click_key(curve_id, 0)
        await self._click_button(self._toolbar._add_key_btn)
        self._assert_primvar_arrays_consistent(curve_id)
        self.assertEqual(len(self._read_primvar(curve_id, "times")), 4)

        # Delete a keyframe (click key 1, click delete)
        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._delete_key_btn)
        self._assert_primvar_arrays_consistent(curve_id)
        self.assertEqual(len(self._read_primvar(curve_id, "times")), 3)

        # Change tangent type on key 1
        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.AUTO])
        self._assert_primvar_arrays_consistent(curve_id)

    # ═════════════════════════════════════════════════════════════════════════
    # Group 2: Moving Keyframes
    # ═════════════════════════════════════════════════════════════════════════

    async def test_drag_keyframe_updates_times_and_values_primvars(self):
        """Dragging a keyframe should update the times and values primvar arrays."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id))
        await self._build_widget()

        orig_times = list(self._read_primvar(curve_id, "times"))
        orig_values = list(self._read_primvar(curve_id, "values"))

        # Drag middle keyframe to a new position
        from_pos = self._get_key_screen_pos(curve_id, 1)
        to_pos = self._model_to_screen(0.6, 0.9)
        await self._drag(from_pos, to_pos)

        new_times = list(self._read_primvar(curve_id, "times"))
        new_values = list(self._read_primvar(curve_id, "values"))

        self.assertAlmostEqual(new_times[0], orig_times[0], delta=0.01, msg="Key 0 time unchanged")
        self.assertAlmostEqual(new_times[2], orig_times[2], delta=0.01, msg="Key 2 time unchanged")
        self.assertNotAlmostEqual(new_times[1], orig_times[1], delta=0.01, msg="Key 1 time should change")
        self.assertNotAlmostEqual(new_values[1], orig_values[1], delta=0.01, msg="Key 1 value should change")
        self._assert_primvar_format(curve_id)

    async def test_drag_keyframe_preserves_tangent_type_primvars(self):
        """Dragging a keyframe must not change the tangent type primvars."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id, in_type=TangentType.SMOOTH, out_type=TangentType.FLAT))
        await self._build_widget()

        orig_in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        orig_out_types = list(self._read_primvar(curve_id, "outTangentTypes"))

        from_pos = self._get_key_screen_pos(curve_id, 1)
        to_pos = self._model_to_screen(0.6, 0.7)
        await self._drag(from_pos, to_pos)

        new_in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        new_out_types = list(self._read_primvar(curve_id, "outTangentTypes"))

        self.assertEqual(new_in_types, orig_in_types, "In tangent types must not change on drag")
        self.assertEqual(new_out_types, orig_out_types, "Out tangent types must not change on drag")

    async def test_drag_keyframe_recomputes_auto_tangent_handle_primvars(self):
        """Dragging a keyframe with AUTO tangents must recompute tangent handles in primvars."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id, in_type=TangentType.AUTO, out_type=TangentType.AUTO))
        await self._build_widget()

        orig_in_times = list(self._read_primvar(curve_id, "inTangentTimes"))
        orig_in_values = list(self._read_primvar(curve_id, "inTangentValues"))
        orig_out_times = list(self._read_primvar(curve_id, "outTangentTimes"))
        orig_out_values = list(self._read_primvar(curve_id, "outTangentValues"))

        # Drag middle key downward significantly
        from_pos = self._get_key_screen_pos(curve_id, 1)
        to_pos = self._model_to_screen(0.5, 0.2)
        await self._drag(from_pos, to_pos)

        new_in_times = list(self._read_primvar(curve_id, "inTangentTimes"))
        new_in_values = list(self._read_primvar(curve_id, "inTangentValues"))
        new_out_times = list(self._read_primvar(curve_id, "outTangentTimes"))
        new_out_values = list(self._read_primvar(curve_id, "outTangentValues"))

        tangent_data_changed = (
            new_in_times != orig_in_times
            or new_in_values != orig_in_values
            or new_out_times != orig_out_times
            or new_out_values != orig_out_values
        )
        self.assertTrue(tangent_data_changed, "AUTO tangent handles should recompute after keyframe drag")
        self._assert_primvar_format(curve_id)

    # ═════════════════════════════════════════════════════════════════════════
    # Group 3: Adding and Removing Keyframes
    # ═════════════════════════════════════════════════════════════════════════

    async def test_add_keyframe_grows_all_primvar_arrays(self):
        """Adding a keyframe should grow every per-key primvar array by 1."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id))
        await self._build_widget()

        self.assertEqual(len(self._read_primvar(curve_id, "times")), 3)

        await self._click_key(curve_id, 0)
        await self._click_button(self._toolbar._add_key_btn)

        for suffix in ARRAY_SUFFIXES:
            val = self._read_primvar(curve_id, suffix)
            self.assertEqual(
                len(val),
                4,
                f"primvars:{curve_id}:{suffix} should have 4 elements after add",
            )
        self._assert_primvar_format(curve_id)

    async def test_delete_keyframe_shrinks_all_primvar_arrays(self):
        """Deleting a keyframe should shrink every per-key primvar array by 1."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id))
        await self._build_widget()

        self.assertEqual(len(self._read_primvar(curve_id, "times")), 3)

        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._delete_key_btn)

        for suffix in ARRAY_SUFFIXES:
            val = self._read_primvar(curve_id, suffix)
            self.assertEqual(
                len(val),
                2,
                f"primvars:{curve_id}:{suffix} should have 2 elements after delete",
            )
        self._assert_primvar_format(curve_id)

    async def test_add_keyframe_tangent_type_stored_in_primvars(self):
        """A new keyframe's tangent type should be stored correctly in primvars."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id))
        await self._build_widget()

        await self._click_key(curve_id, 0)
        await self._click_button(self._toolbar._add_key_btn)

        in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        out_types = list(self._read_primvar(curve_id, "outTangentTypes"))

        self.assertEqual(len(in_types), 4, "Should have 4 in-tangent types after add")
        self.assertIn(
            in_types[1],
            ("linear", "auto", "smooth", "flat", "step", "custom"),
            "New key's in-tangent type should be a valid token in primvars",
        )
        self.assertIn(
            out_types[1],
            ("linear", "auto", "smooth", "flat", "step", "custom"),
            "New key's out-tangent type should be a valid token in primvars",
        )

    # ═════════════════════════════════════════════════════════════════════════
    # Group 4: Moving Tangent Handles
    # ═════════════════════════════════════════════════════════════════════════

    async def test_drag_custom_out_tangent_updates_out_tangent_primvars(self):
        """Dragging a CUSTOM out-tangent handle should update outTangentTimes/Values primvars."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        curve = FCurve(
            id=curve_id,
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.5,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    tangent_broken=True,
                    out_tangent_x=0.15,
                    out_tangent_y=0.1,
                ),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    tangent_broken=True,
                    in_tangent_x=-0.15,
                    in_tangent_y=-0.1,
                    out_tangent_x=0.15,
                    out_tangent_y=0.1,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.3,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    tangent_broken=True,
                    in_tangent_x=-0.15,
                    in_tangent_y=-0.1,
                ),
            ],
            color=0xFF3560FF,
        )
        model.commit_curve(curve_id, curve)
        await self._build_widget()

        orig_out_times = list(self._read_primvar(curve_id, "outTangentTimes"))

        # Click the key first to make tangent handles visible, then drag the out-tangent
        await self._click_key(curve_id, 1)
        from_pos = self._get_tangent_screen_pos(curve_id, 1, is_in_tangent=False)
        to_pos = self._model_to_screen(0.5 + 0.25, 0.8 + 0.2)
        await self._drag(from_pos, to_pos)

        new_out_times = list(self._read_primvar(curve_id, "outTangentTimes"))

        self.assertNotAlmostEqual(
            float(new_out_times[1]),
            float(orig_out_times[1]),
            delta=0.01,
            msg="outTangentTimes[1] should change after drag",
        )
        self._assert_primvar_format(curve_id)

    async def test_drag_custom_in_tangent_updates_in_tangent_primvars(self):
        """Dragging a CUSTOM in-tangent handle should update inTangentTimes/Values primvars."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        curve = FCurve(
            id=curve_id,
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.5,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    tangent_broken=True,
                    out_tangent_x=0.15,
                    out_tangent_y=0.1,
                ),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    tangent_broken=True,
                    in_tangent_x=-0.15,
                    in_tangent_y=-0.1,
                    out_tangent_x=0.15,
                    out_tangent_y=0.1,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.3,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    tangent_broken=True,
                    in_tangent_x=-0.15,
                    in_tangent_y=-0.1,
                ),
            ],
            color=0xFF3560FF,
        )
        model.commit_curve(curve_id, curve)
        await self._build_widget()

        orig_in_times = list(self._read_primvar(curve_id, "inTangentTimes"))

        # Click key to make handles visible, then drag in-tangent
        await self._click_key(curve_id, 1)
        from_pos = self._get_tangent_screen_pos(curve_id, 1, is_in_tangent=True)
        to_pos = self._model_to_screen(0.5 - 0.25, 0.8 - 0.2)
        await self._drag(from_pos, to_pos)

        new_in_times = list(self._read_primvar(curve_id, "inTangentTimes"))

        self.assertNotAlmostEqual(
            float(new_in_times[1]),
            float(orig_in_times[1]),
            delta=0.01,
            msg="inTangentTimes[1] should change after drag",
        )
        self._assert_primvar_format(curve_id)

    async def test_drag_smooth_tangent_stores_halfway_length_in_primvars(self):
        """SMOOTH tangent handle X in primvars should equal half the distance to neighbor."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        # Pre-compute SMOOTH halfway tangent values so USD and widget agree on
        # handle positions (SMOOTH auto-computes X = halfway to neighbor).
        curve = FCurve(
            id=curve_id,
            keys=[
                FCurveKey(
                    time=0.0, value=0.5, out_tangent_type=TangentType.SMOOTH, out_tangent_x=0.25, tangent_broken=True
                ),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.SMOOTH,
                    out_tangent_type=TangentType.SMOOTH,
                    tangent_broken=True,
                    in_tangent_x=-0.25,
                    out_tangent_x=0.25,
                ),
                FCurveKey(
                    time=1.0, value=0.3, in_tangent_type=TangentType.SMOOTH, in_tangent_x=-0.25, tangent_broken=True
                ),
            ],
            color=0xFF3560FF,
        )
        model.commit_curve(curve_id, curve)
        await self._build_widget()

        # Click key, then drag its out-tangent to change angle
        await self._click_key(curve_id, 1)
        from_pos = self._get_tangent_screen_pos(curve_id, 1, is_in_tangent=False)
        to_pos = self._model_to_screen(0.75, 0.95)
        await self._drag(from_pos, to_pos)

        # SMOOTH rule: out_tangent_x == (next_key.time - this_key.time) / 2
        out_tangent_times = list(self._read_primvar(curve_id, "outTangentTimes"))
        key1_time = float(self._read_primvar(curve_id, "times")[1])
        key2_time = float(self._read_primvar(curve_id, "times")[2])
        expected_x = (key2_time - key1_time) / 2.0

        self.assertAlmostEqual(
            float(out_tangent_times[1]),
            expected_x,
            delta=0.05,
            msg=f"SMOOTH out tangent X should be halfway to neighbor: {expected_x}",
        )
        self._assert_primvar_format(curve_id)

    # ═════════════════════════════════════════════════════════════════════════
    # Group 5: Changing Tangent Types
    # ═════════════════════════════════════════════════════════════════════════

    async def test_set_linear_tangent_type_updates_type_and_handle_primvars(self):
        """Setting LINEAR via toolbar should store 'linear' type and midpoint handles."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id, in_type=TangentType.AUTO, out_type=TangentType.AUTO))
        await self._build_widget()

        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.LINEAR])

        in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        self.assertEqual(in_types[1], "linear", "In tangent type should be 'linear' in primvars")

        in_tangent_times = list(self._read_primvar(curve_id, "inTangentTimes"))
        key0_time = float(self._read_primvar(curve_id, "times")[0])
        key1_time = float(self._read_primvar(curve_id, "times")[1])
        expected_in_x = -(key1_time - key0_time) / 2.0
        self.assertAlmostEqual(
            float(in_tangent_times[1]),
            expected_in_x,
            delta=0.02,
            msg="LINEAR in tangent X should be at midpoint to previous key",
        )
        self._assert_primvar_format(curve_id)

    async def test_set_auto_tangent_type_recomputes_handles_in_primvars(self):
        """Setting AUTO via toolbar should store 'auto' and recompute handle positions."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(
            curve_id, self._make_curve(curve_id, in_type=TangentType.LINEAR, out_type=TangentType.LINEAR)
        )
        await self._build_widget()

        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._right_tangent_btns[TangentType.AUTO])

        out_types = list(self._read_primvar(curve_id, "outTangentTypes"))
        self.assertEqual(out_types[1], "auto", "Out tangent type should be 'auto' in primvars")

        out_tangent_values = list(self._read_primvar(curve_id, "outTangentValues"))
        self.assertNotAlmostEqual(
            float(out_tangent_values[1]),
            0.0,
            delta=0.001,
            msg="AUTO out tangent Y should be non-zero (computed from neighbors)",
        )
        self._assert_primvar_format(curve_id)

    async def test_set_flat_tangent_type_zeroes_slope_in_primvars(self):
        """Setting FLAT via toolbar should store 'flat' and set tangent Y to 0 (horizontal)."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id, in_type=TangentType.AUTO, out_type=TangentType.AUTO))
        await self._build_widget()

        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.FLAT])

        in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        self.assertEqual(in_types[1], "flat", "In tangent type should be 'flat' in primvars")

        in_tangent_values = list(self._read_primvar(curve_id, "inTangentValues"))
        self.assertAlmostEqual(
            float(in_tangent_values[1]),
            0.0,
            delta=0.001,
            msg="FLAT tangent Y should be 0.0 in primvars",
        )
        self._assert_primvar_format(curve_id)

    async def test_set_step_tangent_type_stored_in_primvars(self):
        """Setting STEP via toolbar should store 'step' in outTangentTypes primvar."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id))
        await self._build_widget()

        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._right_tangent_btns[TangentType.STEP])

        out_types = list(self._read_primvar(curve_id, "outTangentTypes"))
        self.assertEqual(out_types[1], "step", "Out tangent type should be 'step' in primvars")
        self._assert_primvar_format(curve_id)

    async def test_set_custom_tangent_type_preserves_handle_positions_in_primvars(self):
        """Switching to CUSTOM should store 'custom' type with non-default handle positions."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(curve_id, self._make_curve(curve_id, in_type=TangentType.AUTO, out_type=TangentType.AUTO))
        await self._build_widget()

        # Click key, switch in-tangent to CUSTOM
        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.CUSTOM])

        in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        self.assertEqual(in_types[1], "custom")

        # CUSTOM should preserve the AUTO-computed handle (non-default, non-zero X)
        in_tangent_times = list(self._read_primvar(curve_id, "inTangentTimes"))
        self.assertNotAlmostEqual(
            float(in_tangent_times[1]),
            0.0,
            delta=0.001,
            msg="CUSTOM should have non-zero tangent X (preserved from AUTO)",
        )
        self._assert_primvar_format(curve_id)

    async def test_link_tangents_mirrors_handles_and_updates_broken_primvar(self):
        """Clicking Link should set tangentBrokens to false and mirror tangent types."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        curve = FCurve(
            id=curve_id,
            keys=[
                FCurveKey(time=0.0, value=0.5, tangent_broken=True),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.AUTO,
                    out_tangent_type=TangentType.LINEAR,
                    tangent_broken=True,
                ),
                FCurveKey(time=1.0, value=0.3, tangent_broken=True),
            ],
            color=0xFF3560FF,
        )
        model.commit_curve(curve_id, curve)
        await self._build_widget()

        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._link_tangents_btn)

        broken_arr = list(self._read_primvar(curve_id, "tangentBrokens"))
        self.assertFalse(broken_arr[1], "tangentBrokens[1] should be false after Link")

        in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        out_types = list(self._read_primvar(curve_id, "outTangentTypes"))
        self.assertEqual(
            in_types[1],
            out_types[1],
            "Linked tangent types should be mirrored (both same type)",
        )
        self._assert_primvar_format(curve_id)

    async def test_break_tangents_updates_broken_primvar_preserving_data(self):
        """Clicking Broken should set tangentBrokens to true and preserve tangent data."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        curve = FCurve(
            id=curve_id,
            keys=[
                FCurveKey(time=0.0, value=0.5),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.SMOOTH,
                    out_tangent_type=TangentType.SMOOTH,
                    tangent_broken=False,
                ),
                FCurveKey(time=1.0, value=0.3),
            ],
            color=0xFF3560FF,
        )
        model.commit_curve(curve_id, curve)
        await self._build_widget()

        orig_in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        orig_out_types = list(self._read_primvar(curve_id, "outTangentTypes"))

        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._broken_tangents_btn)

        broken_arr = list(self._read_primvar(curve_id, "tangentBrokens"))
        self.assertTrue(broken_arr[1], "tangentBrokens[1] should be true after Break")

        new_in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        new_out_types = list(self._read_primvar(curve_id, "outTangentTypes"))
        self.assertEqual(new_in_types[1], orig_in_types[1], "In tangent type preserved after break")
        self.assertEqual(new_out_types[1], orig_out_types[1], "Out tangent type preserved after break")
        self._assert_primvar_format(curve_id)

    # ═════════════════════════════════════════════════════════════════════════
    # Group 6: Multi-Curve - Different Attributes
    # ═════════════════════════════════════════════════════════════════════════

    async def test_different_attribute_curves_stored_in_independent_primvar_namespaces(self):
        """Curves for different attributes should have independent primvar namespaces."""
        cid_opacity = "opacity:x"
        cid_size = "size:x"
        model = self._create_model([cid_opacity, cid_size])

        model.commit_curve(cid_opacity, self._make_curve(cid_opacity, color=0xFF3560FF))
        model.commit_curve(cid_size, self._make_curve(cid_size, color=0xFF60FF35))

        self._assert_primvar_format(cid_opacity)
        self._assert_primvar_format(cid_size)

        prim = self._prim()
        opacity_times = prim.GetAttribute(f"primvars:{cid_opacity}:times")
        size_times = prim.GetAttribute(f"primvars:{cid_size}:times")
        self.assertTrue(opacity_times.IsValid())
        self.assertTrue(size_times.IsValid())
        self.assertNotEqual(opacity_times.GetPath(), size_times.GetPath())

    async def test_edit_one_attribute_curve_does_not_affect_other_attribute_primvars(self):
        """Editing one attribute's curve should not change another attribute's primvars."""
        cid_opacity = "opacity:x"
        cid_size = "size:x"
        model = self._create_model([cid_opacity, cid_size])

        # Use distinct key positions so keyframes don't overlap on screen
        model.commit_curve(
            cid_opacity,
            self._make_curve(
                cid_opacity,
                color=0xFF3560FF,
                key_positions=[(0.0, 0.3), (0.5, 0.9), (1.0, 0.5)],
            ),
        )
        model.commit_curve(
            cid_size,
            self._make_curve(
                cid_size,
                color=0xFF60FF35,
                key_positions=[(0.0, 0.7), (0.5, 0.2), (1.0, 0.6)],
            ),
        )
        await self._build_widget()

        size_before = self._read_all_primvar_values(cid_size)

        # Edit opacity: drag its middle keyframe (at value=0.9, far from size's 0.2)
        from_pos = self._get_key_screen_pos(cid_opacity, 1)
        to_pos = self._model_to_screen(0.6, 0.85)
        await self._drag(from_pos, to_pos)

        size_after = self._read_all_primvar_values(cid_size)
        for suffix in ALL_SUFFIXES:
            self.assertEqual(
                size_after[suffix],
                size_before[suffix],
                f"primvars:{cid_size}:{suffix} should not change when editing {cid_opacity}",
            )

    async def test_simultaneous_tangent_type_change_across_different_attributes(self):
        """Multi-selecting keys from different attribute curves and changing type updates both."""
        cid_opacity = "opacity:x"
        cid_size = "size:x"
        model = self._create_model([cid_opacity, cid_size])

        # Use distinct value positions so ctrl+click targets don't overlap
        model.commit_curve(
            cid_opacity,
            self._make_curve(
                cid_opacity,
                color=0xFF3560FF,
                key_positions=[(0.0, 0.3), (0.5, 0.9), (1.0, 0.5)],
            ),
        )
        model.commit_curve(
            cid_size,
            self._make_curve(
                cid_size,
                color=0xFF60FF35,
                key_positions=[(0.0, 0.7), (0.5, 0.2), (1.0, 0.6)],
            ),
        )
        await self._build_widget()

        # Multi-select middle keys from both curves via Ctrl+click
        await self._click_key(cid_opacity, 1)
        await self._shift_click_key(cid_size, 1)

        # Change in-tangent to FLAT
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.FLAT])

        opacity_in_types = list(self._read_primvar(cid_opacity, "inTangentTypes"))
        size_in_types = list(self._read_primvar(cid_size, "inTangentTypes"))
        self.assertEqual(opacity_in_types[1], "flat")
        self.assertEqual(size_in_types[1], "flat")

    # ═════════════════════════════════════════════════════════════════════════
    # Group 7: Multi-Curve - Same Attribute, Different Channels
    # ═════════════════════════════════════════════════════════════════════════

    async def test_xyzw_channels_stored_in_independent_primvar_namespaces(self):
        """X/Y/Z channel curves on the same prim should have independent primvar namespaces."""
        cid_x = "translate:x"
        cid_y = "translate:y"
        cid_z = "translate:z"
        model = self._create_model([cid_x, cid_y, cid_z])

        model.commit_curve(cid_x, self._make_curve(cid_x, color=0xFFFF0000))
        model.commit_curve(cid_y, self._make_curve(cid_y, color=0xFF00FF00))
        model.commit_curve(cid_z, self._make_curve(cid_z, color=0xFF0000FF))

        for cid in (cid_x, cid_y, cid_z):
            self._assert_primvar_format(cid)

        prim = self._prim()
        x_times = prim.GetAttribute(f"primvars:{cid_x}:times")
        y_times = prim.GetAttribute(f"primvars:{cid_y}:times")
        z_times = prim.GetAttribute(f"primvars:{cid_z}:times")
        self.assertTrue(x_times.IsValid())
        self.assertTrue(y_times.IsValid())
        self.assertTrue(z_times.IsValid())

        paths = {str(x_times.GetPath()), str(y_times.GetPath()), str(z_times.GetPath())}
        self.assertEqual(len(paths), 3, "XYZ channels should have distinct primvar attribute paths")

    async def test_edit_one_channel_does_not_affect_sibling_channel_primvars(self):
        """Editing one channel should not change sibling channel primvars."""
        cid_x = "translate:x"
        cid_y = "translate:y"
        cid_z = "translate:z"
        model = self._create_model([cid_x, cid_y, cid_z])

        # Use distinct value positions so keyframes don't overlap on screen
        model.commit_curve(
            cid_x,
            self._make_curve(
                cid_x,
                color=0xFFFF0000,
                key_positions=[(0.0, 0.9), (0.5, 0.85), (1.0, 0.8)],
            ),
        )
        model.commit_curve(
            cid_y,
            self._make_curve(
                cid_y,
                color=0xFF00FF00,
                key_positions=[(0.0, 0.5), (0.5, 0.5), (1.0, 0.5)],
            ),
        )
        model.commit_curve(
            cid_z,
            self._make_curve(
                cid_z,
                color=0xFF0000FF,
                key_positions=[(0.0, 0.1), (0.5, 0.15), (1.0, 0.2)],
            ),
        )
        await self._build_widget()

        y_before = self._read_all_primvar_values(cid_y)
        z_before = self._read_all_primvar_values(cid_z)

        # Edit X: drag its middle key (at value=0.85, far from Y=0.5 and Z=0.15)
        from_pos = self._get_key_screen_pos(cid_x, 1)
        to_pos = self._model_to_screen(0.6, 0.9)
        await self._drag(from_pos, to_pos)

        y_after = self._read_all_primvar_values(cid_y)
        z_after = self._read_all_primvar_values(cid_z)
        for suffix in ALL_SUFFIXES:
            self.assertEqual(
                y_after[suffix],
                y_before[suffix],
                f"primvars:{cid_y}:{suffix} should not change when editing {cid_x}",
            )
            self.assertEqual(
                z_after[suffix],
                z_before[suffix],
                f"primvars:{cid_z}:{suffix} should not change when editing {cid_x}",
            )

    # ═════════════════════════════════════════════════════════════════════════
    # Group 8: Undo Solo
    # ═════════════════════════════════════════════════════════════════════════

    async def test_undo_drag_keyframe_restores_full_curve_state(self):
        """Drag a keyframe, undo, assert all primvars match the original snapshot.

        Uses CUSTOM tangent curves so tangent handle values are preserved exactly
        through widget load/reload cycles (auto-computed types like LINEAR recompute
        boundary handles, making exact snapshot comparison impossible).

        A mouse drag generates multiple intermediate commits (one per mouse move
        step), so we undo repeatedly until the state matches the original.
        """
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(
            curve_id,
            self._make_curve(
                curve_id,
                in_type=TangentType.CUSTOM,
                out_type=TangentType.CUSTOM,
            ),
        )
        await self._build_widget()

        snapshot_before = self._snapshot_all_primvars(curve_id)

        # Drag middle keyframe
        from_pos = self._get_key_screen_pos(curve_id, 1)
        to_pos = self._model_to_screen(0.6, 0.9)
        await self._drag(from_pos, to_pos)

        # Verify something actually changed
        snapshot_after_drag = self._snapshot_all_primvars(curve_id)
        self.assertNotEqual(snapshot_after_drag["times"], snapshot_before["times"], "Drag should have changed times")

        # Undo all intermediate drag steps
        await self._undo_until_snapshot(curve_id, snapshot_before)
        self._assert_primvars_match_snapshot(curve_id, snapshot_before, "After undo: ")

    async def test_undo_add_keyframe_restores_full_curve_state(self):
        """Add a keyframe, undo, assert all primvars match the original snapshot."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(
            curve_id,
            self._make_curve(
                curve_id,
                in_type=TangentType.CUSTOM,
                out_type=TangentType.CUSTOM,
            ),
        )
        await self._build_widget()

        snapshot_before = self._snapshot_all_primvars(curve_id)
        # Add keyframe
        await self._click_key(curve_id, 0)
        await self._click_button(self._toolbar._add_key_btn)

        # Verify key count changed
        self.assertEqual(len(self._read_primvar(curve_id, "times")), 4)

        # Undo
        await self._undo()
        self._assert_primvars_match_snapshot(curve_id, snapshot_before, "After undo: ")

    async def test_undo_delete_keyframe_restores_full_curve_state(self):
        """Delete a keyframe, undo, assert all primvars match the original snapshot."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(
            curve_id,
            self._make_curve(
                curve_id,
                in_type=TangentType.CUSTOM,
                out_type=TangentType.CUSTOM,
            ),
        )
        await self._build_widget()

        snapshot_before = self._snapshot_all_primvars(curve_id)

        # Delete middle key
        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._delete_key_btn)

        # Verify key count changed
        self.assertEqual(len(self._read_primvar(curve_id, "times")), 2)

        # Undo
        await self._undo()
        self._assert_primvars_match_snapshot(curve_id, snapshot_before, "After undo: ")

    async def test_undo_tangent_type_change_restores_full_curve_state(self):
        """Change tangent type, undo, assert all primvars match the original snapshot."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(
            curve_id,
            self._make_curve(
                curve_id,
                in_type=TangentType.CUSTOM,
                out_type=TangentType.CUSTOM,
            ),
        )
        await self._build_widget()

        snapshot_before = self._snapshot_all_primvars(curve_id)

        # Change key 1 in-tangent to FLAT
        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.FLAT])

        # Verify type changed
        in_types = list(self._read_primvar(curve_id, "inTangentTypes"))
        self.assertEqual(in_types[1], "flat")

        # Undo
        await self._undo()
        self._assert_primvars_match_snapshot(curve_id, snapshot_before, "After undo: ")

    async def test_undo_link_tangents_restores_full_curve_state(self):
        """Link tangents, undo, assert all primvars match the original snapshot."""
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        curve = FCurve(
            id=curve_id,
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.5,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    in_tangent_x=-0.15,
                    in_tangent_y=0.0,
                    out_tangent_x=0.15,
                    out_tangent_y=0.1,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=0.5,
                    value=0.8,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    in_tangent_x=-0.15,
                    in_tangent_y=-0.1,
                    out_tangent_x=0.15,
                    out_tangent_y=0.1,
                    tangent_broken=True,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.3,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    in_tangent_x=-0.15,
                    in_tangent_y=-0.1,
                    out_tangent_x=0.15,
                    out_tangent_y=0.0,
                    tangent_broken=True,
                ),
            ],
            color=0xFF3560FF,
        )
        model.commit_curve(curve_id, curve)
        await self._build_widget()

        snapshot_before = self._snapshot_all_primvars(curve_id)

        # Link tangents on key 1
        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._link_tangents_btn)

        # Verify broken changed
        broken_arr = list(self._read_primvar(curve_id, "tangentBrokens"))
        self.assertFalse(broken_arr[1])

        # Undo
        await self._undo()
        self._assert_primvars_match_snapshot(curve_id, snapshot_before, "After undo: ")

    # ═════════════════════════════════════════════════════════════════════════
    # Group 9: Chained Undo
    # ═════════════════════════════════════════════════════════════════════════

    async def test_undo_chain_restores_each_step_exactly(self):
        """Perform a sequence of different actions, then undo each one.

        At each undo step, assert the ENTIRE curve state matches the
        expected snapshot from before that action was performed.

        Uses CUSTOM tangent curves so handle values are preserved exactly.
        """
        curve_id = "opacity:x"
        model = self._create_model([curve_id])
        model.commit_curve(
            curve_id,
            self._make_curve(
                curve_id,
                in_type=TangentType.CUSTOM,
                out_type=TangentType.CUSTOM,
            ),
        )
        await self._build_widget()

        snapshot_0 = self._snapshot_all_primvars(curve_id)

        # Step 1: drag key 1
        from_pos = self._get_key_screen_pos(curve_id, 1)
        to_pos = self._model_to_screen(0.6, 0.7)
        await self._drag(from_pos, to_pos)
        snapshot_1 = self._snapshot_all_primvars(curve_id)
        self.assertNotEqual(snapshot_1["times"], snapshot_0["times"])

        # Step 2: change key 1 in-tangent to FLAT
        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._left_tangent_btns[TangentType.FLAT])
        snapshot_2 = self._snapshot_all_primvars(curve_id)
        self.assertNotEqual(snapshot_2["inTangentTypes"], snapshot_1["inTangentTypes"])

        # Step 3: add key
        await self._click_key(curve_id, 0)
        await self._click_button(self._toolbar._add_key_btn)
        snapshot_3 = self._snapshot_all_primvars(curve_id)
        self.assertNotEqual(len(snapshot_3["times"]), len(snapshot_2["times"]))

        # Step 4: delete key 2
        await self._click_key(curve_id, 2)
        await self._click_button(self._toolbar._delete_key_btn)
        snapshot_4 = self._snapshot_all_primvars(curve_id)
        self.assertNotEqual(len(snapshot_4["times"]), len(snapshot_3["times"]))

        # Step 5: change key 1 out-tangent to STEP
        await self._click_key(curve_id, 1)
        await self._click_button(self._toolbar._right_tangent_btns[TangentType.STEP])
        self._snapshot_all_primvars(curve_id)

        # Undo each step; verify full curve state at each point
        await self._undo()
        self._assert_primvars_match_snapshot(curve_id, snapshot_4, "After undo step 5→4: ")

        await self._undo()
        self._assert_primvars_match_snapshot(curve_id, snapshot_3, "After undo step 4→3: ")

        await self._undo()
        self._assert_primvars_match_snapshot(curve_id, snapshot_2, "After undo step 3→2: ")

        await self._undo()
        self._assert_primvars_match_snapshot(curve_id, snapshot_1, "After undo step 2→1: ")

        # Step 1 was a drag — undo all intermediate commits
        await self._undo_until_snapshot(curve_id, snapshot_0)
        self._assert_primvars_match_snapshot(curve_id, snapshot_0, "After undo step 1→0: ")

    # ═════════════════════════════════════════════════════════════════════════
    # Group 10: Load .usda Fixture
    # ═════════════════════════════════════════════════════════════════════════

    async def _open_fixture_stage(self) -> None:
        """Open the .usda fixture stage and wait for it to be fully loaded."""

        ext_manager = omni.kit.app.get_app().get_extension_manager()
        ext_path = ext_manager.get_extension_path_by_module("omni.flux.curve_editor.widget")
        usda_path = os.path.join(ext_path, "data", "tests", "usd", "primvar_curve_test_fixture.usda")
        self.assertTrue(os.path.isfile(usda_path), f"Fixture file not found: {usda_path}")

        result, _error = await omni.usd.get_context().open_stage_async(usda_path)
        self.assertTrue(result, f"Failed to open fixture stage: {usda_path}")

        self._stage = omni.usd.get_context().get_stage()
        self.assertIsNotNone(self._stage, "Stage should not be None after open_stage_async")
        self._prim_path = "/World/CurveHost"

    async def test_load_usda_fixture_primvars_match_expected_values(self):
        """Open a .usda fixture file, read primvars, assert exact values match."""
        await self._open_fixture_stage()

        curve_id = "opacity:x"

        # Assert all primvar attributes exist
        self._assert_primvar_format(curve_id)

        # Assert exact values from the hand-written fixture
        times = tuple(self._read_primvar(curve_id, "times"))
        values = tuple(self._read_primvar(curve_id, "values"))
        in_tangent_types = tuple(self._read_primvar(curve_id, "inTangentTypes"))
        out_tangent_types = tuple(self._read_primvar(curve_id, "outTangentTypes"))
        tangent_brokens = tuple(self._read_primvar(curve_id, "tangentBrokens"))
        pre_infinity = self._read_primvar(curve_id, "preInfinity")
        post_infinity = self._read_primvar(curve_id, "postInfinity")

        self.assertEqual(times, (0.0, 0.5, 1.0))
        self.assertEqual(values, (0.0, 1.0, 0.5))
        self.assertEqual(in_tangent_types, ("linear", "smooth", "linear"))
        self.assertEqual(out_tangent_types, ("linear", "smooth", "linear"))
        self.assertEqual(tangent_brokens, (False, True, False))
        self.assertEqual(pre_infinity, "constant")
        self.assertEqual(post_infinity, "constant")

    async def test_load_usda_fixture_fcurve_widget_model_matches_primvars(self):
        """Open a .usda fixture, build widget, assert FCurveWidget model matches primvar data."""
        await self._open_fixture_stage()

        curve_id = "opacity:x"
        self._create_model([curve_id])
        await self._build_widget()

        # Read curve from widget
        curves = self._fcurve_widget.curves
        self.assertIn(curve_id, curves)
        curve = curves[curve_id]
        self.assertEqual(len(curve.keys), 3)

        # Assert key data matches fixture
        key0 = curve.keys[0]
        self.assertAlmostEqual(key0.time, 0.0, delta=0.001)
        self.assertAlmostEqual(key0.value, 0.0, delta=0.001)
        self.assertEqual(key0.in_tangent_type, TangentType.LINEAR)
        self.assertEqual(key0.out_tangent_type, TangentType.LINEAR)
        self.assertFalse(key0.tangent_broken)

        key1 = curve.keys[1]
        self.assertAlmostEqual(key1.time, 0.5, delta=0.001)
        self.assertAlmostEqual(key1.value, 1.0, delta=0.001)
        self.assertEqual(key1.in_tangent_type, TangentType.SMOOTH)
        self.assertEqual(key1.out_tangent_type, TangentType.SMOOTH)
        self.assertTrue(key1.tangent_broken)

        key2 = curve.keys[2]
        self.assertAlmostEqual(key2.time, 1.0, delta=0.001)
        self.assertAlmostEqual(key2.value, 0.5, delta=0.001)
        self.assertEqual(key2.in_tangent_type, TangentType.LINEAR)
        self.assertEqual(key2.out_tangent_type, TangentType.LINEAR)
        self.assertFalse(key2.tangent_broken)

    async def test_load_usda_fixture_key_widget_screen_positions_match_model(self):
        """Open a .usda fixture, build widget, assert key screen positions match model coords."""
        await self._open_fixture_stage()

        curve_id = "opacity:x"
        self._create_model([curve_id])
        await self._build_widget()

        # Read key positions from the model (USD)
        curve = self._model.get_curve(curve_id)
        self.assertIsNotNone(curve)

        # For each key, verify the screen position computed from model coords
        # matches by round-tripping: model -> screen -> verify it's within the canvas
        frame = self._fcurve_widget._stack

        for i, key in enumerate(curve.keys):
            sx, sy = self._get_key_screen_pos(curve_id, i)

            # Screen position should be within the canvas frame bounds
            self.assertGreaterEqual(
                sx,
                frame.screen_position_x,
                f"Key {i} screen X should be within canvas (left)",
            )
            self.assertLessEqual(
                sx,
                frame.screen_position_x + frame.computed_width,
                f"Key {i} screen X should be within canvas (right)",
            )
            self.assertGreaterEqual(
                sy,
                frame.screen_position_y,
                f"Key {i} screen Y should be within canvas (top)",
            )
            self.assertLessEqual(
                sy,
                frame.screen_position_y + frame.computed_height,
                f"Key {i} screen Y should be within canvas (bottom)",
            )

            # Verify the model-to-screen mapping is consistent:
            # convert key time/value to screen and compare with _get_key_screen_pos
            expected_sx, expected_sy = self._model_to_screen(key.time, key.value)
            self.assertAlmostEqual(sx, expected_sx, delta=1.0, msg=f"Key {i} screen X should match model_to_screen")
            self.assertAlmostEqual(sy, expected_sy, delta=1.0, msg=f"Key {i} screen Y should match model_to_screen")

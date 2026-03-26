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

from __future__ import annotations

from unittest.mock import MagicMock, patch

import omni.kit.app
import omni.kit.commands
import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.kit.undo
import omni.usd
from omni import ui
from omni.flux.property_widget_builder.model.usd.field_builders.gradient import (
    UsdColorGradientWidget,
    _snapshot_gradient,
)
from pxr import Gf, Sdf, Tf, Usd, Vt

_GRADIENT_MODULE = "omni.flux.property_widget_builder.model.usd.field_builders.gradient"

_INITIAL_TIMES = Vt.DoubleArray([0.0, 1.0])
_INITIAL_VALUES = Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)])

_NEW_TIMES = Vt.DoubleArray([0.0, 0.5, 1.0])
_NEW_VALUES = Vt.Vec4fArray([Gf.Vec4f(0, 1, 0, 1), Gf.Vec4f(1, 1, 0, 1), Gf.Vec4f(0, 0, 1, 1)])


async def _wait(frames: int = 2):
    for _ in range(frames):
        await omni.kit.app.get_app().next_update_async()


# ============================================================================
# Unit tests: SetGradientPrimvarsCommand
# ============================================================================


class TestSetGradientPrimvarsCommand(omni.kit.test.AsyncTestCase):
    """Unit tests for the SetGradientPrimvars Kit command (do/undo/redo)."""

    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()

        self._prim_path = "/World/TestGradient"
        prim = self._stage.DefinePrim(self._prim_path, "Xform")
        prim.CreateAttribute("primvars:test:times", Sdf.ValueTypeNames.DoubleArray).Set(_INITIAL_TIMES)
        prim.CreateAttribute("primvars:test:values", Sdf.ValueTypeNames.Color4fArray).Set(_INITIAL_VALUES)

        self._base_name = "primvars:test"

        self._listener_patcher = patch(f"{_GRADIENT_MODULE}._get_usd_listener_instance", return_value=MagicMock())
        self._block_patcher = patch(f"{_GRADIENT_MODULE}._DisableAllListenersBlock", MagicMock)
        self._listener_patcher.start()
        self._block_patcher.start()

    async def tearDown(self):
        self._block_patcher.stop()
        self._listener_patcher.stop()
        await self._context.close_stage_async()

    def _read_times(self) -> list[float]:
        prim = self._stage.GetPrimAtPath(self._prim_path)
        return list(prim.GetAttribute(f"{self._base_name}:times").Get())

    def _read_values(self) -> list[tuple[float, ...]]:
        prim = self._stage.GetPrimAtPath(self._prim_path)
        return [tuple(float(c) for c in v) for v in prim.GetAttribute(f"{self._base_name}:values").Get()]

    def _execute(self, times=None, values=None, old_values=None):
        kwargs = {
            "prim_path": self._prim_path,
            "base_name": self._base_name,
            "times": times if times is not None else _NEW_TIMES,
            "values": values if values is not None else _NEW_VALUES,
            "usd_context_name": "",
        }
        if old_values is not None:
            kwargs["old_values"] = old_values
        omni.kit.commands.execute("SetGradientPrimvars", **kwargs)

    async def test_do_writes_correct_values(self):
        """Executing the command writes new times and values to USD."""
        self._execute()

        times = self._read_times()
        values = self._read_values()
        self.assertEqual(times, [0.0, 0.5, 1.0])
        self.assertEqual(len(values), 3)
        self.assertAlmostEqual(values[0][1], 1.0, places=5)
        self.assertAlmostEqual(values[1][0], 1.0, places=5)

    async def test_undo_restores_previous_values(self):
        """Undo restores the original gradient values snapshotted by do()."""
        self._execute()
        omni.kit.undo.undo()

        times = self._read_times()
        values = self._read_values()
        self.assertEqual(times, [0.0, 1.0])
        self.assertEqual(len(values), 2)
        self.assertAlmostEqual(values[0][0], 1.0, places=5)
        self.assertAlmostEqual(values[1][2], 1.0, places=5)

    async def test_redo_reapplies_values(self):
        """Redo re-applies the new gradient values after an undo."""
        self._execute()
        omni.kit.undo.undo()
        omni.kit.undo.redo()

        times = self._read_times()
        values = self._read_values()
        self.assertEqual(times, [0.0, 0.5, 1.0])
        self.assertEqual(len(values), 3)

    async def test_snapshot_captures_current_state(self):
        """_snapshot_gradient returns the current times and values from USD."""
        snapshot = _snapshot_gradient("", self._prim_path, self._base_name)

        self.assertIn("times", snapshot)
        self.assertIn("values", snapshot)
        self.assertEqual(len(snapshot["times"]), 2)
        self.assertEqual(len(snapshot["values"]), 2)
        self.assertAlmostEqual(float(snapshot["times"][0]), 0.0, places=5)
        self.assertAlmostEqual(float(snapshot["times"][1]), 1.0, places=5)

    async def test_precaptured_old_values_used_for_undo(self):
        """When old_values is pre-captured (drag pattern), undo restores to that snapshot."""
        drag_snapshot = _snapshot_gradient("", self._prim_path, self._base_name)

        # Simulate intermediate direct writes during drag
        prim = self._stage.GetPrimAtPath(self._prim_path)
        prim.GetAttribute(f"{self._base_name}:times").Set(Vt.DoubleArray([0.0, 0.3, 1.0]))
        prim.GetAttribute(f"{self._base_name}:values").Set(
            Vt.Vec4fArray([Gf.Vec4f(0.5, 0.5, 0, 1), Gf.Vec4f(1, 0, 1, 1), Gf.Vec4f(0, 1, 1, 1)])
        )

        final_times = Vt.DoubleArray([0.0, 0.3, 1.0])
        final_values = Vt.Vec4fArray([Gf.Vec4f(0.5, 0.5, 0, 1), Gf.Vec4f(1, 0, 1, 1), Gf.Vec4f(0, 1, 1, 1)])

        self._execute(times=final_times, values=final_values, old_values=drag_snapshot)
        omni.kit.undo.undo()

        times = self._read_times()
        values = self._read_values()
        self.assertEqual(times, [0.0, 1.0])
        self.assertEqual(len(values), 2)
        self.assertAlmostEqual(values[0][0], 1.0, places=5)

    async def test_undo_fires_tf_notice(self):
        """Undo triggers Tf.Notice.ObjectsChanged so the UI can react."""
        notices_received: list[Usd.Notice.ObjectsChanged] = []

        def _on_notice(notice, _stage):
            notices_received.append(notice)

        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, _on_notice, self._stage)
        self._execute()
        notices_received.clear()

        omni.kit.undo.undo()

        self.assertGreater(len(notices_received), 0, "Tf.Notice should fire on undo")
        del listener


# ============================================================================
# E2E tests: UsdColorGradientWidget with simulated user interactions
# ============================================================================


class TestGradientEditorUndo(omni.kit.test.AsyncTestCase):
    """E2E: click the gradient bar to add/delete keyframes, verify USD and UI update on undo."""

    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()

        self._prim_path = "/World/GradientPrim"
        prim = self._stage.DefinePrim(self._prim_path, "Xform")
        prim.CreateAttribute("primvars:color:times", Sdf.ValueTypeNames.DoubleArray).Set(Vt.DoubleArray([0.0, 1.0]))
        prim.CreateAttribute("primvars:color:values", Sdf.ValueTypeNames.Color4fArray).Set(
            Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
        )
        self._base_name = "primvars:color"
        self._window = None
        self._widget: UsdColorGradientWidget | None = None

    async def tearDown(self):
        if self._widget:
            self._widget._hide_popup()
        if self._window:
            self._window.visible = False
            self._window.destroy()
            self._window = None
        self._widget = None
        await self._context.close_stage_async()

    def _read_times(self):
        prim = self._stage.GetPrimAtPath(self._prim_path)
        val = prim.GetAttribute(f"{self._base_name}:times").Get()
        return list(val) if val else []

    def _read_values(self):
        prim = self._stage.GetPrimAtPath(self._prim_path)
        val = prim.GetAttribute(f"{self._base_name}:values").Get()
        return [tuple(float(c) for c in v) for v in val] if val else []

    def _build_widget(self):
        self._window = ui.Window("GradientUndoTest", width=600, height=200)
        with self._window.frame:
            self._widget = UsdColorGradientWidget("", self._prim_path, self._base_name)

    def _popup_title(self) -> str:
        assert self._widget and self._widget._popup_window
        return self._widget._popup_window.title

    def _find_overlay(self) -> ui_test.WidgetRef | None:
        """Find the popup gradient bar overlay (click target for adding keyframes)."""
        return ui_test.find(f"{self._popup_title()}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'")

    def _find_markers(self) -> list[ui_test.WidgetRef]:
        """Find all marker images in the popup."""
        return ui_test.find_all(f"{self._popup_title()}//Frame/**/Image[*].identifier=='GradientKeyframeMarker'")

    def _click_overlay_at(self, fraction: float):
        """Simulate a left-click on the popup bar at a horizontal fraction [0..1].

        Calls the bar's mouse_released_fn with coordinates that place the click
        at *fraction* along the bar width.
        """
        bar = self._widget._popup_gradient_overlay
        assert bar is not None, "Popup overlay not built"
        x = bar.screen_position_x + bar.computed_width * fraction
        y = bar.screen_position_y + bar.computed_height * 0.5
        bar.call_mouse_released_fn(x, y, 0, 0)

    def _right_click_marker(self, index: int):
        """Right-click the Nth marker to delete it."""
        markers = self._find_markers()
        assert index < len(markers), f"Marker index {index} out of range ({len(markers)} markers)"
        markers[index].widget.call_mouse_pressed_fn(0, 0, 1, 0)

    async def _open_popup(self):
        """Open the popup by clicking the inline gradient bar."""
        overlay = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'")
        assert overlay is not None, "Inline gradient bar overlay not found"
        overlay.widget.call_mouse_released_fn(0, 0, 0, 0)
        await _wait(3)

    async def test_add_keyframe_via_bar_click(self):
        """Click the gradient bar to add a keyframe, verify USD has 3 entries."""
        self._build_widget()
        await _wait(3)
        await self._open_popup()

        self.assertEqual(len(self._read_times()), 2)
        self.assertEqual(len(self._find_markers()), 2)

        self._click_overlay_at(0.5)
        await _wait()

        self.assertEqual(len(self._read_times()), 3, "USD should have 3 keyframes after click-to-add")
        self.assertEqual(len(self._find_markers()), 3, "Popup should show 3 markers")

    async def test_add_keyframe_then_undo(self):
        """Click-to-add, then undo: USD and widget both revert to 2 keyframes."""
        self._build_widget()
        await _wait(3)
        await self._open_popup()

        self.assertEqual(len(self._read_times()), 2)

        self._click_overlay_at(0.5)
        await _wait()
        self.assertEqual(len(self._read_times()), 3)

        omni.kit.undo.undo()
        await _wait(3)

        self.assertEqual(len(self._read_times()), 2, "USD: back to 2 after undo")
        self.assertEqual(len(self._find_markers()), 2, "UI markers: back to 2 after undo")

    async def test_delete_keyframe_via_right_click(self):
        """Right-click a marker to delete it, verify USD drops to 1 keyframe."""
        self._build_widget()
        await _wait(3)
        await self._open_popup()

        self.assertEqual(len(self._read_times()), 2)

        self._right_click_marker(1)
        await _wait()

        self.assertEqual(len(self._read_times()), 1, "USD: 1 keyframe after right-click delete")
        self.assertEqual(len(self._find_markers()), 1, "UI: 1 marker after delete")

    async def test_delete_keyframe_then_undo(self):
        """Right-click delete, then undo: both USD and UI revert."""
        self._build_widget()
        await _wait(3)
        await self._open_popup()

        self._right_click_marker(1)
        await _wait()
        self.assertEqual(len(self._read_times()), 1)

        omni.kit.undo.undo()
        await _wait(3)

        self.assertEqual(len(self._read_times()), 2, "USD: back to 2 after undo")
        self.assertEqual(len(self._find_markers()), 2, "UI markers: back to 2 after undo")

    async def test_multiple_adds_then_undo_chain(self):
        """Two click-to-add edits, each individually undoable."""
        self._build_widget()
        await _wait(3)
        await self._open_popup()

        # Add first keyframe
        self._click_overlay_at(0.3)
        await _wait()
        self.assertEqual(len(self._read_times()), 3)

        # Add second keyframe
        self._click_overlay_at(0.7)
        await _wait()
        self.assertEqual(len(self._read_times()), 4)
        self.assertEqual(len(self._find_markers()), 4)

        # Undo second add
        omni.kit.undo.undo()
        await _wait(3)
        self.assertEqual(len(self._read_times()), 3, "USD: 3 after first undo")
        self.assertEqual(len(self._find_markers()), 3, "UI: 3 after first undo")

        # Undo first add
        omni.kit.undo.undo()
        await _wait(3)
        self.assertEqual(len(self._read_times()), 2, "USD: 2 after second undo")
        self.assertEqual(len(self._find_markers()), 2, "UI: 2 after second undo")

    async def test_redo_restores_added_keyframe(self):
        """Undo then redo re-creates the keyframe in both USD and UI."""
        self._build_widget()
        await _wait(3)
        await self._open_popup()

        self._click_overlay_at(0.5)
        await _wait()
        self.assertEqual(len(self._read_times()), 3)

        omni.kit.undo.undo()
        await _wait(3)
        self.assertEqual(len(self._read_times()), 2)

        omni.kit.undo.redo()
        await _wait(3)
        self.assertEqual(len(self._read_times()), 3, "USD: 3 after redo")
        self.assertEqual(len(self._find_markers()), 3, "UI: 3 markers after redo")

    async def test_marker_drag_produces_single_undo_entry(self):
        """Dragging a marker (press -> move -> release) creates exactly one undo entry."""
        self._build_widget()
        await _wait(3)
        await self._open_popup()

        original_times = self._read_times()
        self.assertEqual(len(original_times), 2)

        # Simulate full drag cycle via widget callbacks
        markers = self._find_markers()
        self.assertGreaterEqual(len(markers), 2)
        # Left-press the second marker (starts drag, captures snapshot)
        markers[1].widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await _wait()

        # Simulate placer offset change (the marker moves)
        uid = self._widget._keyframes[-1].uid
        placer = self._widget._marker_placers.get(uid)
        if placer:
            placer.offset_x = ui.Percent(80.0)
        await _wait()

        # Release (commits command + fires changed)
        markers = self._find_markers()
        markers[-1].widget.call_mouse_released_fn(0, 0, 0, 0)
        await _wait()

        moved_times = self._read_times()
        self.assertNotEqual(original_times, moved_times, "Times should change after drag")

        # Single undo should restore to original
        omni.kit.undo.undo()
        await _wait(3)
        self.assertEqual(self._read_times(), original_times, "Single undo should restore original times")


# ============================================================================
# RAII lifecycle tests: notice registration tied to popup open/close
# ============================================================================


class TestUsdGradientWidgetLifecycle(omni.kit.test.AsyncTestCase):
    """Verify that Tf.Notice registration follows the popup lifecycle."""

    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()

        self._prim_path = "/World/LifecyclePrim"
        prim = self._stage.DefinePrim(self._prim_path, "Xform")
        prim.CreateAttribute("primvars:color:times", Sdf.ValueTypeNames.DoubleArray).Set(Vt.DoubleArray([0.0, 1.0]))
        prim.CreateAttribute("primvars:color:values", Sdf.ValueTypeNames.Color4fArray).Set(
            Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
        )
        self._base_name = "primvars:color"
        self._window = None
        self._widget: UsdColorGradientWidget | None = None

    async def tearDown(self):
        if self._widget:
            self._widget._hide_popup()
        if self._window:
            self._window.visible = False
            self._window.destroy()
            self._window = None
        self._widget = None
        await self._context.close_stage_async()

    def _build_widget(self):
        self._window = ui.Window("GradientLifecycleTest", width=600, height=200)
        with self._window.frame:
            self._widget = UsdColorGradientWidget("", self._prim_path, self._base_name)

    def _read_times(self):
        prim = self._stage.GetPrimAtPath(self._prim_path)
        val = prim.GetAttribute(f"{self._base_name}:times").Get()
        return list(val) if val else []

    async def test_no_listener_before_popup_open(self):
        """Before the popup is opened, no Tf.Notice listener is registered."""
        self._build_widget()
        await _wait(3)

        self.assertIsNone(self._widget._usd_listener, "No listener before popup opens")

    async def test_listener_registered_on_popup_open(self):
        """Opening the popup registers a Tf.Notice listener."""
        self._build_widget()
        await _wait(3)

        self._widget._show_popup()
        await _wait(3)

        self.assertIsNotNone(self._widget._usd_listener, "Listener should exist after popup opens")

    async def test_listener_revoked_on_popup_close(self):
        """Closing the popup revokes the Tf.Notice listener."""
        self._build_widget()
        await _wait(3)

        self._widget._show_popup()
        await _wait(3)
        self.assertIsNotNone(self._widget._usd_listener)

        self._widget._hide_popup()
        await _wait()

        self.assertIsNone(self._widget._usd_listener, "Listener should be revoked after popup closes")

    async def test_reopen_popup_re_registers_listener(self):
        """Open -> close -> reopen cycle re-registers the listener correctly."""
        self._build_widget()
        await _wait(3)

        self._widget._show_popup()
        await _wait(3)
        first_listener = self._widget._usd_listener
        self.assertIsNotNone(first_listener)

        self._widget._hide_popup()
        await _wait()
        self.assertIsNone(self._widget._usd_listener)

        self._widget._show_popup()
        await _wait(3)
        self.assertIsNotNone(self._widget._usd_listener, "Listener re-registered after reopen")

    async def test_external_usd_edit_refreshes_widget_while_popup_open(self):
        """An external USD edit while the popup is open updates the widget's keyframes."""
        self._build_widget()
        await _wait(3)

        self._widget._show_popup()
        await _wait(3)
        self.assertEqual(len(self._widget._keyframes), 2)

        # External edit: add a third keyframe directly to USD
        prim = self._stage.GetPrimAtPath(self._prim_path)
        prim.GetAttribute(f"{self._base_name}:times").Set(Vt.DoubleArray([0.0, 0.5, 1.0]))
        prim.GetAttribute(f"{self._base_name}:values").Set(
            Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 1, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
        )
        await _wait(3)

        self.assertEqual(len(self._widget._keyframes), 3, "Widget should reflect external USD edit via Tf.Notice")

    async def test_external_usd_edit_ignored_while_popup_closed(self):
        """An external USD edit while the popup is closed does NOT update the widget."""
        self._build_widget()
        await _wait(3)

        self.assertIsNone(self._widget._usd_listener)
        self.assertEqual(len(self._widget._keyframes), 2)

        # External edit without popup open
        prim = self._stage.GetPrimAtPath(self._prim_path)
        prim.GetAttribute(f"{self._base_name}:times").Set(Vt.DoubleArray([0.0, 0.5, 1.0]))
        prim.GetAttribute(f"{self._base_name}:values").Set(
            Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 1, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
        )
        await _wait(3)

        self.assertEqual(len(self._widget._keyframes), 2, "Widget should NOT update when popup is closed (no listener)")

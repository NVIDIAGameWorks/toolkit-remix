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

from unittest.mock import patch

import omni.kit.commands
import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.kit.undo
import omni.usd
from omni import ui
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardEventType, KeyboardInput, MouseEventType
from omni.flux.property_widget_builder.delegates import ColorGradientField, field_popup_window
from omni.flux.property_widget_builder.delegates.float_value.color_gradient import GradientFieldEditor
from omni.flux.utils.common.interactive_usd_notices import register_objects_changed_listener as _register_listener
from omni.flux.utils.widget.color_gradient import GradientPreview
from omni.kit.actions.core import get_action_registry
from omni.kit.hotkeys.core import HotkeyFilter, get_hotkey_context, get_hotkey_registry
from omni.kit.ui_test import Vec2
from omni.kit.ui_test.input import (
    emulate_keyboard,
    emulate_mouse,
    emulate_mouse_drag_and_drop,
    emulate_mouse_move_and_click,
    emulate_mouse_slow_move,
)
from pxr import Gf, Sdf, Tf, Usd, Vt

from ... import USDAttributeItem
from ...field_builders.gradient import _claim_gradients
from ...grouped_keys_primvar import PropertyGroupedKeysModel

_INITIAL_TIMES = Vt.DoubleArray([0.0, 1.0])
_INITIAL_VALUES = Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)])

_NEW_TIMES = Vt.DoubleArray([0.0, 0.5, 1.0])
_NEW_VALUES = Vt.Vec4fArray([Gf.Vec4f(0, 1, 0, 1), Gf.Vec4f(1, 1, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
_EDITOR_IDENTITY = "###PropertyPanelFloatingEditor_"


def _find_gradient_editor_window():
    """Find the active native Gradient editor window."""
    title = f"Gradient Editor{_EDITOR_IDENTITY}"
    return next(
        (window for window in ui.Workspace.get_windows() if window.title.startswith(title) and window.visible), None
    )


def _attr_path(prim_path: str, name: str) -> Sdf.Path:
    return Sdf.Path(f"{prim_path}.{name}")


def _make_gradient_item(context_name: str, prim_paths: list[str], base_name: str) -> USDAttributeItem:
    times_item = USDAttributeItem(
        context_name,
        [_attr_path(path, f"{base_name}:times") for path in prim_paths],
        value_type_name=Sdf.ValueTypeNames.DoubleArray,
    )
    values_item = USDAttributeItem(
        context_name,
        [_attr_path(path, f"{base_name}:values") for path in prim_paths],
        value_type_name=Sdf.ValueTypeNames.Color4fArray,
    )
    _claim_gradients([times_item, values_item])
    return values_item


def _make_gradient_model(context_name: str, prim_paths: list[str], base_name: str) -> PropertyGroupedKeysModel:
    return PropertyGroupedKeysModel.from_item(_make_gradient_item(context_name, prim_paths, base_name))


# ============================================================================
# Kit/USD API integration tests: SetDataPrimvarsCommand
# ============================================================================


class TestSetDataPrimvarsCommand(omni.kit.test.AsyncTestCase):
    """Kit/USD API integration tests for the SetDataPrimvars command."""

    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()

        self._prim_path = "/World/TestGradient"
        prim = self._stage.DefinePrim(self._prim_path, "Xform")
        prim.CreateAttribute("primvars:test:times", Sdf.ValueTypeNames.DoubleArray).Set(_INITIAL_TIMES)
        prim.CreateAttribute("primvars:test:values", Sdf.ValueTypeNames.Color4fArray).Set(_INITIAL_VALUES)

        self._other_prim_path = "/World/OtherGradient"
        other_prim = self._stage.DefinePrim(self._other_prim_path, "Xform")
        other_prim.CreateAttribute("primvars:test:times", Sdf.ValueTypeNames.DoubleArray).Set(
            Vt.DoubleArray([0.0, 0.25, 1.0])
        )
        other_prim.CreateAttribute("primvars:test:values", Sdf.ValueTypeNames.Color4fArray).Set(
            Vt.Vec4fArray(
                [
                    Gf.Vec4f(0.2, 0.2, 0.2, 1),
                    Gf.Vec4f(0.4, 0.4, 0.4, 1),
                    Gf.Vec4f(0.6, 0.6, 0.6, 1),
                ]
            )
        )

        self._base_name = "primvars:test"

    async def tearDown(self):
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()
        await self._context.close_stage_async()

    def _read_gradient_payload(self, prim_path: str | None = None) -> tuple[list[float], list[tuple[float, ...]]]:
        prim_path = prim_path or self._prim_path
        prim = self._stage.GetPrimAtPath(prim_path)
        times = list(prim.GetAttribute(f"{self._base_name}:times").Get())
        values = [tuple(float(c) for c in v) for v in prim.GetAttribute(f"{self._base_name}:values").Get()]
        return times, values

    def _execute(self, times=None, values=None, old_values=None):
        kwargs = {
            "prim_paths": [self._prim_path],
            "group_id": self._base_name,
            "payload": {
                "times": times if times is not None else _NEW_TIMES,
                "values": values if values is not None else _NEW_VALUES,
            },
            "usd_context_name": "",
        }
        if old_values is not None:
            kwargs["old_values"] = old_values
        omni.kit.commands.execute("SetDataPrimvars", **kwargs)

    def _snapshot_gradient(self, prim_path: str | None = None) -> dict:
        prim_path = prim_path or self._prim_path
        prim = self._stage.GetPrimAtPath(prim_path)
        return {
            "times": prim.GetAttribute(f"{self._base_name}:times").Get(),
            "values": prim.GetAttribute(f"{self._base_name}:values").Get(),
        }

    async def test_command_do_writes_expected_payloads(self):
        """Executing the command writes the expected gradient payload."""
        self._execute()

        times, values = self._read_gradient_payload()
        self.assertEqual(times, list(_NEW_TIMES))
        self.assertEqual(values, [tuple(value) for value in _NEW_VALUES])

    async def test_command_undo_restores_initial_payloads(self):
        """Undo restores the initial gradient payload."""
        self._execute()

        omni.kit.undo.undo()

        times, values = self._read_gradient_payload()
        self.assertEqual(times, list(_INITIAL_TIMES))
        self.assertEqual(values, [tuple(value) for value in _INITIAL_VALUES])

    async def test_command_redo_reapplies_expected_payloads(self):
        """Redo reapplies the expected gradient payload."""
        self._execute()
        omni.kit.undo.undo()

        omni.kit.undo.redo()

        times, values = self._read_gradient_payload()
        self.assertEqual(times, list(_NEW_TIMES))
        self.assertEqual(values, [tuple(value) for value in _NEW_VALUES])

    async def test_precaptured_old_values_used_for_undo(self):
        """When old_values is pre-captured (drag pattern), undo restores to that snapshot."""
        drag_snapshot = self._snapshot_gradient()

        # Simulate intermediate direct writes during drag
        prim = self._stage.GetPrimAtPath(self._prim_path)
        prim.GetAttribute(f"{self._base_name}:times").Set(Vt.DoubleArray([0.0, 0.3, 1.0]))
        prim.GetAttribute(f"{self._base_name}:values").Set(
            Vt.Vec4fArray([Gf.Vec4f(0.5, 0.5, 0, 1), Gf.Vec4f(1, 0, 1, 1), Gf.Vec4f(0, 1, 1, 1)])
        )

        final_times = Vt.DoubleArray([0.0, 0.3, 1.0])
        final_values = Vt.Vec4fArray([Gf.Vec4f(0.5, 0.5, 0, 1), Gf.Vec4f(1, 0, 1, 1), Gf.Vec4f(0, 1, 1, 1)])

        self._execute(times=final_times, values=final_values, old_values={self._prim_path: drag_snapshot})
        omni.kit.undo.undo()

        times, values = self._read_gradient_payload()
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

    async def test_multi_target_command_undo_restores_each_target_payload(self):
        """Undo restores each selected prim to its own pre-edit gradient payload."""
        first_before = self._read_gradient_payload(self._prim_path)
        second_before = self._read_gradient_payload(self._other_prim_path)

        omni.kit.commands.execute(
            "SetDataPrimvars",
            prim_paths=[self._prim_path, self._other_prim_path],
            group_id=self._base_name,
            payload={"times": _NEW_TIMES, "values": _NEW_VALUES},
            usd_context_name="",
        )

        self.assertEqual(self._read_gradient_payload(self._prim_path)[0], [0.0, 0.5, 1.0])
        self.assertEqual(self._read_gradient_payload(self._other_prim_path)[0], [0.0, 0.5, 1.0])

        omni.kit.undo.undo()

        self.assertEqual(self._read_gradient_payload(self._prim_path), first_before)
        self.assertEqual(self._read_gradient_payload(self._other_prim_path), second_before)

    async def test_multi_target_command_undo_skips_deleted_targets(self):
        """Undo restores surviving targets when another edited gradient target was deleted."""
        first_before = self._read_gradient_payload(self._prim_path)

        omni.kit.commands.execute(
            "SetDataPrimvars",
            prim_paths=[self._prim_path, self._other_prim_path],
            group_id=self._base_name,
            payload={"times": _NEW_TIMES, "values": _NEW_VALUES},
            usd_context_name="",
        )
        self._stage.RemovePrim(self._other_prim_path)

        self.assertFalse(self._stage.GetPrimAtPath(self._other_prim_path).IsValid())

        omni.kit.undo.undo()

        self.assertEqual(self._read_gradient_payload(self._prim_path), first_before)
        self.assertFalse(self._stage.GetPrimAtPath(self._other_prim_path).IsValid())

    async def test_scalar_times_values_payload_infers_scalar_curve_shape(self):
        """Scalar values use the two-suffix curve shape instead of color gradient storage."""
        prim_path = "/World/ScalarCurve"
        base_name = "primvars:scalarCurve"
        prim = self._stage.DefinePrim(prim_path, "Xform")
        prim.CreateAttribute(f"{base_name}:times", Sdf.ValueTypeNames.DoubleArray).Set(Vt.DoubleArray([0.0, 1.0]))
        prim.CreateAttribute(f"{base_name}:values", Sdf.ValueTypeNames.DoubleArray).Set(Vt.DoubleArray([1.0, 2.0]))

        omni.kit.commands.execute(
            "SetDataPrimvars",
            prim_paths=[prim_path],
            group_id=base_name,
            payload={"times": [0.0, 0.5, 1.0], "values": [3.0, 4.0, 5.0]},
            usd_context_name="",
        )

        self.assertEqual(list(prim.GetAttribute(f"{base_name}:times").Get()), [0.0, 0.5, 1.0])
        self.assertEqual(list(prim.GetAttribute(f"{base_name}:values").Get()), [3.0, 4.0, 5.0])

    async def test_noop_drag_end_preserves_payload_and_undo_history(self):
        """Ending an unchanged model edit leaves the payload and public undo state untouched."""
        for paths in ([self._prim_path], [self._prim_path, self._other_prim_path]):
            with self.subTest(paths=paths):
                model = _make_gradient_model("", paths, self._base_name)
                try:
                    payloads_before = [self._read_gradient_payload(path) for path in paths]
                    history_before = omni.kit.undo.get_history().copy()
                    undo_stack_before = tuple(omni.kit.undo.get_undo_stack())

                    model.begin_edit(self._base_name)
                    model.end_edit(self._base_name)

                    self.assertEqual([self._read_gradient_payload(path) for path in paths], payloads_before)
                    self.assertEqual(omni.kit.undo.get_history(), history_before)
                    self.assertEqual(tuple(omni.kit.undo.get_undo_stack()), undo_stack_before)
                finally:
                    model.destroy()

    async def test_mixed_discrete_edit_preserves_distinct_undo_payloads(self):
        """A discrete edit creates one command and restores each selected gradient."""
        model = _make_gradient_model("", [self._prim_path, self._other_prim_path], self._base_name)
        try:
            first_before = self._read_gradient_payload(self._prim_path)
            second_before = self._read_gradient_payload(self._other_prim_path)
            undo_count = len(omni.kit.undo.get_undo_stack())
            expected = (list(_NEW_TIMES), [tuple(value) for value in _NEW_VALUES])

            model.commit_payload(self._base_name, {"times": _NEW_TIMES, "values": _NEW_VALUES})

            self.assertEqual(self._read_gradient_payload(self._prim_path), expected)
            self.assertEqual(self._read_gradient_payload(self._other_prim_path), expected)
            self.assertEqual(len(omni.kit.undo.get_undo_stack()), undo_count + 1)
            omni.kit.undo.undo()
            self.assertEqual(self._read_gradient_payload(self._prim_path), first_before)
            self.assertEqual(self._read_gradient_payload(self._other_prim_path), second_before)
            self.assertNotEqual(first_before, second_before)
            omni.kit.undo.redo()
            self.assertEqual(self._read_gradient_payload(self._prim_path), expected)
            self.assertEqual(self._read_gradient_payload(self._other_prim_path), expected)
        finally:
            model.destroy()

    async def test_mixed_continuous_edit_creates_history_only_at_end(self):
        """A gesture writes both gradients live and commits one undo command on release."""
        model = _make_gradient_model("", [self._prim_path, self._other_prim_path], self._base_name)
        try:
            first_before = self._read_gradient_payload(self._prim_path)
            second_before = self._read_gradient_payload(self._other_prim_path)
            history_before = omni.kit.undo.get_history().copy()
            undo_count = len(omni.kit.undo.get_undo_stack())
            expected = (list(_NEW_TIMES), [tuple(value) for value in _NEW_VALUES])

            model.begin_edit(self._base_name)
            self.assertEqual(self._read_gradient_payload(self._prim_path), first_before)
            self.assertEqual(self._read_gradient_payload(self._other_prim_path), second_before)
            model.commit_payload(self._base_name, {"times": _NEW_TIMES, "values": _NEW_VALUES})
            self.assertEqual(self._read_gradient_payload(self._prim_path), expected)
            self.assertEqual(self._read_gradient_payload(self._other_prim_path), expected)
            self.assertEqual(omni.kit.undo.get_history(), history_before)
            self.assertEqual(len(omni.kit.undo.get_undo_stack()), undo_count)
            model.end_edit(self._base_name)

            self.assertEqual(len(omni.kit.undo.get_undo_stack()), undo_count + 1)
            omni.kit.undo.undo()
            self.assertEqual(self._read_gradient_payload(self._prim_path), first_before)
            self.assertEqual(self._read_gradient_payload(self._other_prim_path), second_before)
            omni.kit.undo.redo()
            self.assertEqual(self._read_gradient_payload(self._prim_path), expected)
            self.assertEqual(self._read_gradient_payload(self._other_prim_path), expected)
        finally:
            model.destroy()


# ============================================================================
# E2E tests: ColorGradientField with simulated user interactions
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
        self._model = None
        self._widget: ColorGradientField | None = None

        self._context.get_selection().set_selected_prim_paths([self._prim_path], False)
        await ui_test.human_delay()

        actions = get_action_registry()
        hotkeys = get_hotkey_registry()
        context = get_hotkey_context()
        self.addCleanup(actions.deregister_all_actions_for_extension, __name__)
        self.addCleanup(hotkeys.deregister_all_hotkeys_for_extension, __name__)
        for key, action, callback in (
            ("CTRL+Z", "undo", omni.kit.undo.undo),
            ("CTRL+Y", "redo", omni.kit.undo.redo),
            ("ESCAPE", "clear_selection", lambda: self._context.get_selection().clear_selected_prim_paths()),
        ):
            actions.register_action(__name__, action, callback)
            self.assertIsNotNone(
                hotkeys.register_hotkey(__name__, key, __name__, action, filter=HotkeyFilter(context=__name__))
            )
        context.push(__name__)
        self.addCleanup(context.pop)

    async def tearDown(self):
        try:
            try:
                await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, Vec2(0, 0))
            finally:
                for key in (KeyboardInput.Z, KeyboardInput.Y, KeyboardInput.LEFT_CONTROL):
                    await emulate_keyboard(KeyboardEventType.KEY_RELEASE, key)
        finally:
            try:
                if field_popup_window._ACTIVE_WINDOW is not None:
                    field_popup_window._ACTIVE_WINDOW.close()
                await ui_test.human_delay(1)
                if self._widget:
                    self._widget.destroy()
                if self._window:
                    self._window.visible = False
                    self._window.destroy()
            finally:
                try:
                    if self._model is not None:
                        self._model.destroy()
                finally:
                    self._window = self._widget = self._model = None
                    omni.kit.undo.clear_stack()
                    omni.kit.undo.clear_history()
                    await self._context.close_stage_async()

    def _read_times(self):
        prim = self._stage.GetPrimAtPath(self._prim_path)
        val = prim.GetAttribute(f"{self._base_name}:times").Get()
        return list(val) if val else []

    def _build_widget(self):
        self._window = ui.Window("GradientUndoTest", width=600, height=200)
        with self._window.frame:
            self._model = _make_gradient_model("", [self._prim_path], self._base_name)
            self._widget = ColorGradientField(self._model, self._base_name, context_name="")
            self._widget.build_ui(None)

    def _find_markers(self) -> list[ui_test.WidgetRef]:
        """Find all marker images in the popup."""
        host = _find_gradient_editor_window()
        self.assertIsNotNone(host)
        return ui_test.find_all(f"{host.title}//Frame/**/Image[*].identifier=='GradientKeyframeMarker'")

    async def _click_overlay_at(self, fraction: float):
        """Click the popup bar at a horizontal fraction of its rendered bounds."""
        editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(editor, GradientFieldEditor)
        bar = editor._content._popup_gradient_overlay
        assert bar is not None, "Popup overlay not built"
        x = bar.screen_position_x + bar.computed_width * fraction
        y = bar.screen_position_y + bar.computed_height * 0.5
        await emulate_mouse_move_and_click(Vec2(x, y))

    async def _right_click_marker(self, index: int):
        """Right-click the Nth marker to delete it."""
        markers = self._find_markers()
        assert index < len(markers), f"Marker index {index} out of range ({len(markers)} markers)"
        await markers[index].click(right_click=True)

    async def _open_popup(self):
        """Open the popup by clicking the inline gradient bar."""
        overlay = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'")
        assert overlay is not None, "Inline gradient bar overlay not found"
        await overlay.click()
        await ui_test.human_delay(3)

    async def test_add_keyframe_via_bar_click(self):
        """Click the gradient bar to add a keyframe, verify USD has 3 entries."""
        self._build_widget()
        await ui_test.human_delay(3)
        await self._open_popup()

        self.assertEqual(len(self._read_times()), 2)
        self.assertEqual(len(self._find_markers()), 2)
        notices = []
        subscription = _register_listener(self._stage, lambda notice, stage: notices.append((notice, stage)))

        try:
            await self._click_overlay_at(0.5)
            await ui_test.human_delay()

            self.assertEqual(len(self._read_times()), 3, "USD should have 3 keyframes after click-to-add")
            self.assertEqual(len(self._find_markers()), 3, "Popup should show 3 markers")
            self.assertEqual(len(notices), 0)

            await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
            await ui_test.human_delay(3)

            self.assertIsNone(field_popup_window._ACTIVE_WINDOW)
            self.assertEqual(self._context.get_selection().get_selected_prim_paths(), [self._prim_path])
            self.assertEqual(len(notices), 1)

            # Once the editor is closed, Escape resumes the scene's normal selection action.
            await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
            await ui_test.human_delay()
            self.assertEqual(self._context.get_selection().get_selected_prim_paths(), [])
        finally:
            subscription.Revoke()

    async def test_delete_keyframe_then_undo(self):
        """Right-click delete, then undo: both USD and UI revert."""
        self._build_widget()
        await ui_test.human_delay(3)
        await self._open_popup()

        self.assertEqual(len(self._read_times()), 2)
        self.assertEqual(len(self._find_markers()), 2)

        await self._right_click_marker(1)
        await ui_test.human_delay()
        self.assertEqual(len(self._read_times()), 1, "USD: 1 keyframe after right-click delete")
        self.assertEqual(len(self._find_markers()), 1, "UI: 1 marker after delete")

        omni.kit.undo.undo()
        await ui_test.human_delay(3)

        self.assertEqual(len(self._read_times()), 2, "USD: back to 2 after undo")
        self.assertEqual(len(self._find_markers()), 2, "UI markers: back to 2 after undo")

    async def test_multiple_adds_then_undo_chain(self):
        """Two click-to-add edits, each individually undoable."""
        self._build_widget()
        await ui_test.human_delay(3)
        await self._open_popup()

        # Add first keyframe
        await self._click_overlay_at(0.3)
        await ui_test.human_delay()
        self.assertEqual(len(self._read_times()), 3)

        # Add second keyframe
        await self._click_overlay_at(0.7)
        await ui_test.human_delay()
        self.assertEqual(len(self._read_times()), 4)
        self.assertEqual(len(self._find_markers()), 4)

        # Undo second add
        omni.kit.undo.undo()
        await ui_test.human_delay(3)
        self.assertEqual(len(self._read_times()), 3, "USD: 3 after first undo")
        self.assertEqual(len(self._find_markers()), 3, "UI: 3 after first undo")

        # Undo first add
        omni.kit.undo.undo()
        await ui_test.human_delay(3)
        self.assertEqual(len(self._read_times()), 2, "USD: 2 after second undo")
        self.assertEqual(len(self._find_markers()), 2, "UI: 2 after second undo")

    async def test_add_keyframe_undo_redo_updates_usd_and_markers(self):
        """Keyboard history updates authored data and controls, including an open native picker."""
        self._build_widget()
        await ui_test.human_delay(3)
        await self._open_popup()

        editor = field_popup_window._ACTIVE_WINDOW
        content = editor._content
        original = content.get_keyframes()
        self.assertEqual(len(self._read_times()), 2)
        self.assertEqual(len(self._find_markers()), 2)

        await self._click_overlay_at(0.5)
        await ui_test.human_delay()
        self.assertEqual(len(self._read_times()), 3)
        self.assertEqual(len(self._find_markers()), 3)

        await ui_test.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay(3)
        self.assertEqual(len(self._read_times()), 2)
        self.assertEqual(len(self._find_markers()), 2)

        await ui_test.emulate_keyboard_press(KeyboardInput.Y, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay(3)
        self.assertEqual(len(self._read_times()), 3, "USD: 3 after redo")
        self.assertEqual(len(self._find_markers()), 3, "UI: 3 markers after redo")
        added = content.get_keyframes()

        # Opening an untouched picker must not capture a stale edit when scene history changes.
        swatch = ui_test.find(f"{editor.title}//Frame/**/ColorWidget[*]")
        title_bar = Vec2(editor.position_x + editor.width / 2, editor.position_y + 5)
        await swatch.click()
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay(3)
        self.assertEqual(content.get_keyframes(), original)
        self.assertTrue(content._color_picker_active)
        history = (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack()))
        await emulate_mouse_move_and_click(title_bar)
        await ui_test.human_delay()
        self.assertFalse(content._color_picker_active)
        self.assertEqual(history, (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack())))

        # Multiple live picker changes are one command, completed when its native popup closes.
        await swatch.click()
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.Y, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay(3)
        self.assertEqual(content.get_keyframes(), added)
        undo_count = len(omni.kit.undo.get_undo_stack())
        for start, end in ((Vec2(80, 140), Vec2(180, 80)), (Vec2(160, 110), Vec2(120, 150))):
            before = self._model.get_payload(self._base_name)
            await emulate_mouse_drag_and_drop(swatch.center + start, swatch.center + end)
            await ui_test.human_delay()
            self.assertNotEqual(self._model.get_payload(self._base_name), before)
            self.assertEqual(len(omni.kit.undo.get_undo_stack()), undo_count)
        colored = content.get_keyframes()
        await emulate_mouse_move_and_click(title_bar)
        await ui_test.human_delay()
        self.assertEqual(len(omni.kit.undo.get_undo_stack()), undo_count + 1)

        # History reloads data without replacing the swatch or dismissing its picker.
        await swatch.click()
        await ui_test.human_delay()
        for key, expected in (
            (KeyboardInput.Z, added),
            (KeyboardInput.Y, colored),
            (KeyboardInput.Z, added),
            (KeyboardInput.Z, original),
        ):
            await ui_test.emulate_keyboard_press(key, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay(3)
            self.assertTrue(editor.is_open)
            self.assertTrue(content._color_picker_active)
            self.assertIs(content._color_widget, swatch.widget)
            self.assertEqual(content.get_keyframes(), expected)
            self.assertEqual(self._read_times(), [time for time, _color in expected])
            self.assertEqual(len(self._find_markers()), len(expected))
            self.assertEqual(
                ui_test.find(f"{editor.title}//Frame/**/FloatDrag[*]").widget.model.get_value_as_float(), expected[0][0]
            )
            self.assertEqual(
                tuple(
                    swatch.widget.model.get_item_value_model(child).get_value_as_float()
                    for child in swatch.widget.model.get_item_children()
                ),
                expected[0][1],
            )

        # Editing after Undo uses the restored keys; finalizing for Undo cannot add another command on close.
        await emulate_mouse_drag_and_drop(swatch.center + Vec2(80, 140), swatch.center + Vec2(160, 90))
        await ui_test.human_delay()
        self.assertEqual(self._read_times(), [time for time, _color in original])
        self.assertNotEqual(content.get_keyframes(), original)
        await ui_test.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay(3)
        self.assertEqual(content.get_keyframes(), original)
        history = (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack()))
        await emulate_mouse_move_and_click(title_bar)
        await ui_test.human_delay()
        self.assertEqual(history, (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack())))

        # Native numeric text consumes its own Undo/Redo rather than invoking scene history.
        await swatch.click()
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await ui_test.emulate_char_press("0.37")
        await ui_test.human_delay(3)
        typed = content.get_keyframes()
        self.assertNotEqual(typed, original)
        await ui_test.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay(3)
        self.assertNotEqual(content.get_keyframes(), typed)
        self.assertEqual(history, (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack())))
        await ui_test.emulate_keyboard_press(KeyboardInput.Y, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay(3)
        self.assertEqual(content.get_keyframes(), typed)
        self.assertEqual(history, (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack())))
        await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await ui_test.human_delay()
        self.assertTrue(editor.is_open)
        self.assertTrue(content._color_picker_active)
        payload = self._model.get_payload(self._base_name)
        # The native picker must follow its control's lifetime, not a test-held WidgetRef.
        swatch = None

        # Escape commits the open native picker and closes the editor before scene deselection can run.
        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
        await ui_test.human_delay()
        self.assertFalse(editor.is_open)
        self.assertIsNone(field_popup_window._ACTIVE_WINDOW)
        self.assertFalse(content._color_picker_active)
        self.assertIsNone(content._model_sub)
        self.assertIsNone(self._model.usd_listener)
        self.assertIsNone(self._model.usd_notice_token)
        self.assertEqual(self._model.get_payload(self._base_name), payload)
        self.assertEqual(len(omni.kit.undo.get_undo_stack()), len(history[0]) + 1)
        self.assertEqual(self._context.get_selection().get_selected_prim_paths(), [self._prim_path])

        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
        await ui_test.human_delay()
        self.assertEqual(self._context.get_selection().get_selected_prim_paths(), [])

    async def test_resized_editor_edge_drag_preserves_payload_and_undo(self):
        """Marker and numeric drags ignore held Undo/Redo and commit one undoable payload on release."""
        prim = self._stage.GetPrimAtPath(self._prim_path)
        initial = [
            (0.0, (1.0, 0.0, 0.0, 1.0)),
            (0.5, (0.0, 1.0, 0.0, 1.0)),
            (1.0, (0.0, 0.0, 1.0, 1.0)),
        ]
        # Both shortcuts need a real change to this gradient available in scene history.
        for middle_time in (0.5, 0.75):
            omni.kit.commands.execute(
                "SetDataPrimvars",
                prim_paths=[self._prim_path],
                group_id=self._base_name,
                payload={"times": [0.0, middle_time, 1.0], "values": [color for _time, color in initial]},
                usd_context_name="",
            )
        self._build_widget()
        await ui_test.human_delay(3)
        await self._open_popup()
        await ui_test.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        self.assertEqual(self._read_times(), [time for time, _color in initial])
        self.assertTrue(omni.kit.undo.get_undo_stack())
        self.assertTrue(omni.kit.undo.get_redo_stack())

        editor_window = _find_gradient_editor_window()
        self.assertIsNotNone(editor_window)
        previous_width = editor_window.width
        grip = Vec2(
            editor_window.position_x + editor_window.width - 2,
            editor_window.position_y + editor_window.height - 2,
        )
        await emulate_mouse_drag_and_drop(grip, grip + Vec2(80, 30))
        await ui_test.human_delay()
        self.assertGreater(editor_window.width, previous_width)

        editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(editor, GradientFieldEditor)
        content = editor._content
        key = content._keyframes[0]
        marker = content._marker_widgets[key.uid]
        bar = content._popup_gradient_overlay
        marker_start = Vec2(
            marker.screen_position_x + marker.computed_width / 2,
            marker.screen_position_y + marker.computed_height / 2,
        )
        marker_target = Vec2(bar.screen_position_x + bar.computed_width * 0.25, marker_start.y)
        expected_time = (marker_target.x - bar.screen_position_x) / bar.computed_width
        undo_stack_before = tuple(omni.kit.undo.get_undo_stack())
        notices = []
        subscription = _register_listener(self._stage, lambda notice, stage: notices.append((notice, stage)))

        try:
            await emulate_mouse(MouseEventType.MOVE, marker_start)
            try:
                await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, marker_start)
                await ui_test.human_delay()
                self.assertEqual(len(notices), 0)
                await emulate_mouse_slow_move(marker_start, marker_target)
                await ui_test.human_delay()
                self.assertEqual(len(notices), 0)
                held = content.get_keyframes()
                self.assertAlmostEqual(held[0][0], expected_time, delta=0.01)
                self.assertEqual(
                    held,
                    list(
                        zip(
                            self._read_times(),
                            [tuple(value) for value in prim.GetAttribute(f"{self._base_name}:values").Get()],
                        )
                    ),
                )
                self.assertEqual(len(omni.kit.undo.get_undo_stack()), len(undo_stack_before))
                held_payload = self._model.get_payload(self._base_name)
                held_history = (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack()))
                for shortcut in (KeyboardInput.Z, KeyboardInput.Y):
                    await ui_test.emulate_keyboard_press(shortcut, KEYBOARD_MODIFIER_FLAG_CONTROL)
                    await ui_test.human_delay()
                    self.assertEqual(self._model.get_payload(self._base_name), held_payload)
                    self.assertEqual(content.get_keyframes(), held)
                    self.assertEqual(
                        (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack())), held_history
                    )
            finally:
                await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, marker_target)
                await ui_test.human_delay()

            current = content.get_keyframes()
            usd_times = self._read_times()
            usd_values = [tuple(value) for value in prim.GetAttribute(f"{self._base_name}:values").Get()]
            self.assertTrue(editor_window.visible)
            self.assertAlmostEqual(current[0][0], expected_time, delta=0.01)
            self.assertEqual(current[1:], initial[1:])
            self.assertEqual([color for _time, color in current], [color for _time, color in initial])
            self.assertEqual(current, list(zip(usd_times, usd_values)))
            self.assertEqual(len(omni.kit.undo.get_undo_stack()), len(undo_stack_before) + 1)
            self.assertEqual(len(notices), 0)

            # Two numeric drags create two entries, not one entry per intermediate value.
            numeric_payloads = []
            for index in range(2):
                time_field = ui_test.find(f"{editor.title}//Frame/**/FloatDrag[*]")
                start, end = time_field.center, time_field.center + Vec2(6, 0)
                before = content.get_keyframes()
                try:
                    await emulate_mouse(MouseEventType.MOVE, start)
                    await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, start)
                    await ui_test.human_delay()
                    await emulate_mouse_slow_move(start, end)
                    await ui_test.human_delay()
                    self.assertEqual(len(omni.kit.undo.get_undo_stack()), len(undo_stack_before) + 1 + index)
                    held_payload = self._model.get_payload(self._base_name)
                    held_history = (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack()))
                    for shortcut in (KeyboardInput.Z, KeyboardInput.Y):
                        await ui_test.emulate_keyboard_press(shortcut, KEYBOARD_MODIFIER_FLAG_CONTROL)
                        await ui_test.human_delay()
                        self.assertEqual(self._model.get_payload(self._base_name), held_payload)
                        self.assertEqual(
                            (tuple(omni.kit.undo.get_undo_stack()), tuple(omni.kit.undo.get_redo_stack())), held_history
                        )
                finally:
                    await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, end)
                    await ui_test.human_delay()
                numeric_payloads.append(content.get_keyframes())
                self.assertNotEqual(numeric_payloads[-1], before)
                self.assertEqual(numeric_payloads[-1][1:], initial[1:])
                self.assertEqual([color for _time, color in numeric_payloads[-1]], [color for _time, color in initial])
                self.assertEqual(self._read_times(), [time for time, _color in numeric_payloads[-1]])
                self.assertEqual(len(omni.kit.undo.get_undo_stack()), len(undo_stack_before) + 2 + index)
                self.assertEqual(len(notices), 0)

            for expected in (numeric_payloads[0], current):
                await ui_test.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
                await ui_test.human_delay(3)
                self.assertTrue(editor.is_open)
                self.assertEqual(content.get_keyframes(), expected)
            self.assertEqual(len(notices), 0)

            await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
            await ui_test.human_delay(3)

            self.assertFalse(editor_window.visible)
            self.assertEqual(len(notices), 1)
        finally:
            subscription.Revoke()

        omni.kit.undo.undo()
        await ui_test.human_delay(3)
        self.assertEqual(
            (
                self._read_times(),
                [tuple(value) for value in prim.GetAttribute(f"{self._base_name}:values").Get()],
            ),
            ([time for time, _color in initial], [color for _time, color in initial]),
        )

    async def test_escape_during_marker_drag_flushes_notice_once(self):
        """Escaping the popup during a drag finalizes one undo entry and deferred USD notice."""
        self._build_widget()
        await ui_test.human_delay(3)
        await self._open_popup()

        original_times = self._read_times()
        undo_stack_before = tuple(omni.kit.undo.get_undo_stack())
        notices = []
        subscription = _register_listener(self._stage, lambda notice, stage: notices.append((notice, stage)))
        try:
            markers = self._find_markers()
            self.assertGreaterEqual(len(markers), 2)
            marker_start = markers[1].center
            marker_target = marker_start - Vec2(60, 0)
            editor_window = _find_gradient_editor_window()
            self.assertIsNotNone(editor_window)
            await emulate_mouse(MouseEventType.MOVE, marker_start)
            try:
                await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, marker_start)
                await ui_test.human_delay()
                await emulate_mouse_slow_move(marker_start, marker_target)
                await ui_test.human_delay()
                self.assertNotEqual(self._read_times(), original_times)
                self.assertEqual(len(notices), 0)

                await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
                self.assertFalse(editor_window.visible)
                await ui_test.human_delay(1)
                self.assertIsNone(self._model.usd_notice_token)
                self.assertEqual(len(notices), 1)
                self.assertEqual(self._context.get_selection().get_selected_prim_paths(), [self._prim_path])
            finally:
                await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, marker_target)
                await ui_test.human_delay(1)

            self.assertEqual(len(notices), 1)
            self.assertEqual(len(omni.kit.undo.get_undo_stack()), len(undo_stack_before) + 1)
        finally:
            subscription.Revoke()


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
        self._model = None
        self._widget: ColorGradientField | None = None

    async def tearDown(self):
        if field_popup_window._ACTIVE_WINDOW is not None:
            field_popup_window._ACTIVE_WINDOW.close()
        await ui_test.human_delay(1)
        if self._widget:
            self._widget.destroy()
        if self._window:
            self._window.visible = False
            self._window.destroy()
            self._window = None
        self._widget = None
        if self._model is not None:
            self._model.destroy()
            self._model = None
        await self._context.close_stage_async()

    def _build_widget(self):
        """Build a Gradient field borrowing the fixture's model."""
        self._window = ui.Window("GradientLifecycleTest", width=600, height=200)
        with self._window.frame:
            item = _make_gradient_item("", [self._prim_path], self._base_name)
            self._model = PropertyGroupedKeysModel.from_item(item)
            self._widget = ColorGradientField(self._model, self._base_name, context_name="")
            self._widget.build_ui(None)

    async def _open_widget(self):
        """Open the Gradient using its rendered inline control."""
        await ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'").click()
        await ui_test.human_delay()

    async def test_close_reopen_and_launcher_destroy_preserve_preview_and_session(self):
        """Closing, reopening, and launcher destruction preserve preview ownership and the editing session."""
        keyframes = [(0.0, (1.0, 0.0, 0.0, 1.0)), (1.0, (0.0, 0.0, 1.0, 1.0))]
        with patch.object(GradientPreview, "render", autospec=True, side_effect=GradientPreview.render) as render:
            self._build_widget()
            self.assertEqual(render.call_args.args, (self._widget._preview, keyframes))

        widget = self._widget
        self.assertIsNone(field_popup_window._ACTIVE_WINDOW)
        preview = widget._preview
        gradient_provider = preview.gradient_provider
        checker_provider = preview.checker_provider
        model = self._model
        payload = model.get_payload(self._base_name)
        self.assertIsNone(model.usd_listener)
        self.assertIsNone(model.usd_notice_token)
        self.assertEqual(len(model._on_change), 1)

        await self._open_widget()
        editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(editor, GradientFieldEditor)
        content = editor._content
        self.assertTrue(editor.is_open)
        self.assertIs(content._preview, preview)
        self.assertIs(content._preview.gradient_provider, gradient_provider)
        self.assertIs(content._preview.checker_provider, checker_provider)
        self.assertIsNotNone(model.usd_listener)
        self.assertIsNotNone(model.usd_notice_token)
        self.assertEqual(len(model._on_change), 2)

        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
        await ui_test.human_delay(1)
        self.assertFalse(editor.is_open)
        self.assertIsNone(field_popup_window._ACTIVE_WINDOW)
        self.assertIs(widget._preview, preview)
        self.assertIs(preview.gradient_provider, gradient_provider)
        self.assertIs(preview.checker_provider, checker_provider)
        self.assertIsNone(content._model_sub)
        self.assertIsNone(model.usd_listener)
        self.assertIsNone(model.usd_notice_token)
        self.assertEqual(len(model._on_change), 1)
        self.assertEqual(model.get_payload(self._base_name), payload)

        overlay = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'")
        await overlay.click()
        await overlay.click()
        await ui_test.human_delay(1)
        self.assertIsNot(editor, field_popup_window._ACTIVE_WINDOW)
        editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(editor, GradientFieldEditor)
        self.assertIsNot(content, editor._content)
        content = editor._content
        self.assertTrue(editor.is_open)
        self.assertIs(content._preview, preview)
        self.assertIs(content._preview.gradient_provider, gradient_provider)
        self.assertIs(content._preview.checker_provider, checker_provider)
        self.assertIsNotNone(model.usd_listener)
        self.assertIsNotNone(model.usd_notice_token)
        self.assertEqual(len(model._on_change), 2)
        self.assertEqual(
            sum(
                1
                for candidate in ui.Workspace.get_windows()
                if candidate.title.startswith(f"Gradient Editor{_EDITOR_IDENTITY}") and candidate.visible
            ),
            1,
        )

        widget.destroy()
        self._widget = None
        self.assertTrue(editor.is_open)
        self.assertIs(content._model, model)
        self.assertIsNotNone(model.usd_listener)
        self.assertIsNotNone(model.usd_notice_token)
        self.assertEqual(len(model._on_change), 1)

        await ui_test.find(f"{editor.title}//Frame/**/Image[*].name=='MenuBurger'").click()
        await ui_test.human_delay()
        await ui_test.select_context_menu("Grayscale")
        await ui_test.human_delay()
        expected = [(0.0, (0.0, 0.0, 0.0, 1.0)), (1.0, (1.0, 1.0, 1.0, 1.0))]
        self.assertEqual(content.get_keyframes(), expected)
        payload = model.get_payload(self._base_name)
        self.assertEqual(list(payload["times"]), [time for time, _color in expected])
        self.assertEqual([tuple(value) for value in payload["values"]], [color for _time, color in expected])

        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
        await ui_test.human_delay(1)
        self.assertFalse(editor.is_open)
        self.assertIsNone(field_popup_window._ACTIVE_WINDOW)
        self.assertIsNone(content._model_sub)
        self.assertIsNone(model.usd_listener)
        self.assertIsNone(model.usd_notice_token)
        self.assertEqual(len(model._on_change), 0)
        self.assertEqual(model.get_payload(self._base_name), payload)

        await ui_test.human_delay(1)
        self.assertIsNone(model.usd_listener)
        self.assertIsNone(model.usd_notice_token)
        self.assertEqual(len(model._on_change), 0)

    async def test_external_usd_edit_refreshes_widget_while_popup_open(self):
        """An external USD edit while the popup is open updates the widget's keyframes."""
        self._build_widget()
        await ui_test.human_delay(3)

        await self._open_widget()
        await ui_test.human_delay(3)
        editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(editor, GradientFieldEditor)
        content = editor._content
        self.assertEqual(len(content._keyframes), 2)

        # External edit: add a third keyframe directly to USD
        prim = self._stage.GetPrimAtPath(self._prim_path)
        prim.GetAttribute(f"{self._base_name}:times").Set(Vt.DoubleArray([0.0, 0.5, 1.0]))
        prim.GetAttribute(f"{self._base_name}:values").Set(
            Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 1, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
        )
        await ui_test.human_delay(3)

        self.assertEqual(len(content._keyframes), 3, "Widget should reflect external USD edit via Tf.Notice")

    async def test_external_usd_edit_without_active_session_reloads_on_open(self):
        """A preview without an active edit session reloads external USD edits on open."""
        self._build_widget()
        await ui_test.human_delay(3)

        self.assertIsNone(self._model.usd_listener)
        self.assertIsNone(field_popup_window._ACTIVE_WINDOW)
        self.assertEqual(len(self._model._on_change), 1)
        preview = self._widget._preview
        with patch.object(preview, "render", wraps=preview.render) as render:
            # The field listener remains, but no active editing session listens for USD notices.
            prim = self._stage.GetPrimAtPath(self._prim_path)
            prim.GetAttribute(f"{self._base_name}:times").Set(Vt.DoubleArray([0.0, 0.5, 1.0]))
            prim.GetAttribute(f"{self._base_name}:values").Set(
                Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 1, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
            )
            await ui_test.human_delay(3)
            render.assert_not_called()
            self.assertIsNone(self._model.usd_listener)
            self.assertIsNone(self._model.usd_notice_token)
            self.assertEqual(len(self._model._on_change), 1)

            await self._open_widget()
            editor = field_popup_window._ACTIVE_WINDOW
            self.assertIsInstance(editor, GradientFieldEditor)
            self.assertIs(editor._content._preview, preview)
            self.assertEqual(
                editor._content.get_keyframes(),
                [(0.0, (1.0, 0.0, 0.0, 1.0)), (0.5, (0.0, 1.0, 0.0, 1.0)), (1.0, (0.0, 0.0, 1.0, 1.0))],
            )
            render.assert_called()

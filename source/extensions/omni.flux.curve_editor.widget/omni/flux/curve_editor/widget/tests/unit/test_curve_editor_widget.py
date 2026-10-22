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

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, Mock, patch

import omni.kit.test
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput
from omni import ui
from omni.flux.curve_editor.widget import curve_editor_widget
from omni.flux.curve_editor.widget.curve_editor_widget import CurveEditorWidget
from omni.flux.fcurve.widget import FCurve, FCurveKey, KeyReference

__all__ = ["TestCurveEditorWidget"]


def _editor(curves, references, events):
    """Build callback state without constructing the visual editor."""

    @contextmanager
    def edit_context():
        events.append("group begin")
        try:
            yield
        finally:
            events.append("group end")

    @contextmanager
    def edit_curves(curve_ids):
        events.append(("curves begin", tuple(curve_ids)))
        try:
            yield
        finally:
            events.append("curves end")

    with patch.object(CurveEditorWidget, "_build_ui"):
        editor = CurveEditorWidget(Mock(), edit_context_factory=edit_context)
    fcurve_widget = Mock(
        curves=curves, editable_selected_keys=tuple(references), time_range=(0.0, 1.0), value_range=(0.0, 10.0)
    )
    editor._canvas = Mock(fcurve_widget=fcurve_widget)
    editor._canvas.edit_curves = edit_curves
    editor._position_fields = {axis: Mock(model=ui.SimpleFloatModel()) for axis in ("time", "value")}
    editor._position_offset_labels = {axis: Mock() for axis in ("time", "value")}
    editor._position_pointer_edit = False

    def prepare(baseline, selected_keys, *, time_offset=0.0, value_offset=0.0):
        return {
            reference: (
                baseline[reference.curve_id][reference.key_index].time + time_offset,
                baseline[reference.curve_id][reference.key_index].value + value_offset,
            )
            for reference in selected_keys
        }

    def apply(positions, *, baseline):
        del baseline
        for reference, (time, value) in positions.items():
            key = curves[reference.curve_id].keys[reference.key_index]
            key.time, key.value = time, value
        events.append("write")

    fcurve_widget.prepare_key_offset.side_effect = prepare
    fcurve_widget.set_key_positions.side_effect = apply
    return editor


class TestCurveEditorWidget(omni.kit.test.AsyncTestCase):
    """Verify numeric edit targeting and gesture lifetime."""

    async def test_delete_selected_keys_destroyed_editor_does_not_open_an_edit(self):
        """Deletion after canvas cleanup leaves the edit context untouched."""
        # Arrange
        editor = CurveEditorWidget.__new__(CurveEditorWidget)
        editor._canvas = None
        editor._edit_context_factory = Mock()

        # Act
        editor.delete_selected_keys()

        # Assert
        editor._edit_context_factory.assert_not_called()

    async def setUp(self):
        """Isolate native device state and deferred update subscriptions."""
        self._patches = ExitStack()
        self.addCleanup(self._patches.close)
        self._patches.enter_context(
            patch.object(
                curve_editor_widget,
                "acquire_input_interface",
                return_value=Mock(get_modifier_flags=Mock(return_value=0), get_mouse_value=Mock(return_value=1.0)),
            )
        )
        self._patches.enter_context(patch.object(curve_editor_widget, "get_default_app_window"))
        self._patches.enter_context(patch.object(curve_editor_widget, "get_app"))

    async def test_change_after_key_replacement_leaves_replacement_untouched(self):
        """Stale index references cannot write into replacement key objects."""
        # Arrange
        curve = FCurve(id="x", keys=[FCurveKey(time=0.25, value=2.0)])
        events = []
        editor = _editor({"x": curve}, [KeyReference("x", 0)], events)
        model = editor._position_fields["value"].model
        editor._on_position_edit_begin("value", model)
        curve.keys[0] = FCurveKey(time=0.75, value=9.0)
        model.set_value(4.0)

        # Act
        editor._on_position_value_changed("value", model)

        # Assert
        self.assertEqual(curve.keys[0].value, 9.0)
        self.assertEqual(events, [])

    async def test_model_notice_during_edit_invalidates_before_deferred_finalization(self):
        """An external notice disables input while leaving model finalization deferred."""
        # Arrange
        editor, _, _, events = self._active_editor()

        # Act
        editor._on_model_changed("x")

        # Assert
        self.assertTrue(editor._position_edit_invalidated)
        self.assertFalse(editor._position_fields["value"].enabled)
        self.assertEqual(events, [("curves begin", ("x",)), "write"])
        self.assertIsNotNone(editor._deferred_reload_sub)

    async def test_value_change_after_model_notice_does_not_write(self):
        """Pending external reload rejects subsequent native value callbacks."""
        # Arrange
        editor, model, curve, events = self._active_editor()
        editor._on_model_changed("x")
        model.set_value(8.0)
        editor.fcurve_widget.set_key_positions.reset_mock()

        # Act
        editor._on_position_value_changed("value", model)

        # Assert
        self.assertEqual(curve.keys[0].value, 4.0)
        editor.fcurve_widget.set_key_positions.assert_not_called()
        self.assertNotIn("curves end", events)

    async def test_deferred_reload_finalizes_once_before_reloading_storage(self):
        """The deferred callback finalizes the invalidated edit before authoritative reload."""
        # Arrange
        editor, model, _, events = self._active_editor()
        editor._on_model_changed("x")
        begin_edit = Mock(side_effect=lambda: editor._on_position_edit_begin("value", model))
        editor._position_edit_stack.callback(begin_edit)
        editor._canvas.reload_from_storage.side_effect = lambda: events.append("reload")

        # Act
        editor._finish_external_reload(None)

        # Assert
        self.assertEqual(
            events, [("curves begin", ("x",)), "write", "group begin", "curves end", "group end", "reload"]
        )
        begin_edit.assert_called_once_with()
        self.assertIsNone(editor._deferred_reload_sub)
        self.assertIsNone(editor._position_axis)
        self.assertIsNone(editor._position_edit_stack)

    async def test_destroy_after_model_notice_discards_stale_value_and_finalizes_once(self):
        """Destruction releases a pending reload without applying the invalidated field value."""
        # Arrange
        editor, model, curve, events = self._active_editor()
        editor._on_model_changed("x")
        model.set_value(8.0)
        widget = editor.fcurve_widget
        widget.set_key_positions.reset_mock()

        # Act
        editor.destroy()

        # Assert
        widget.set_key_positions.assert_not_called()
        self.assertEqual(curve.keys[0].value, 4.0)
        self.assertEqual(events, [("curves begin", ("x",)), "write", "group begin", "curves end", "group end"])
        self.assertIsNone(editor._deferred_reload_sub)
        self.assertIsNone(editor._position_axis)
        self.assertIsNone(editor._position_edit_stack)
        self.assertFalse(editor._position_pointer_edit)
        self.assertEqual(editor._position_keys, ())
        self.assertEqual(editor._position_baseline, {})
        self.assertEqual(editor._position_curves, {})
        self.assertEqual(editor._position_key_objects, {})
        self.assertTrue(editor._destroyed)

    async def test_position_undo_after_model_notice_leaves_deferred_finalization_pending(self):
        """An invalidated drag cannot finalize or undo inside the pending reload window."""
        # Arrange
        editor, _, _, events = self._active_editor()
        editor._on_model_changed("x")
        with patch.object(curve_editor_widget, "undo") as undo:
            # Act
            editor._on_position_key_pressed(int(KeyboardInput.Z), KEYBOARD_MODIFIER_FLAG_CONTROL, True)

            # Assert
            self.assertIsNotNone(editor._position_edit_stack)
            self.assertIsNotNone(editor._deferred_reload_sub)
            self.assertNotIn("curves end", events)
            undo.assert_not_called()

    async def test_finish_with_undo_context_entry_failure_closes_edits_and_reloads(self):
        """A failed undo-group entry still closes the model edit and restores authoritative data."""
        # Arrange
        editor, model, curve, events = self._active_editor()
        edit_context = MagicMock()
        edit_context.__enter__.side_effect = ValueError("group entry failed")
        editor._edit_context_factory = lambda: edit_context
        editor._finalization_context_factory = editor._edit_context_factory
        editor._canvas.reload_from_storage.side_effect = lambda: setattr(curve.keys[0], "value", 2.0)

        # Act
        with self.assertRaisesRegex(ValueError, "group entry failed"):
            editor._finish_position_edit()

        # Assert
        self.assertEqual(events.count("curves end"), 1)
        self.assertEqual(model.as_float, 2.0)
        self.assertIsNone(editor._position_edit_stack)
        self.assertIsNone(editor._position_axis)
        self.assertFalse(editor._position_pointer_edit)
        self.assertEqual(editor._position_keys, ())
        self.assertEqual(editor._position_baseline, {})
        self.assertEqual(editor._position_curves, {})
        self.assertEqual(editor._position_key_objects, {})

    async def test_finish_with_model_finalizer_failure_clears_state_and_finishes_remaining_edits(self):
        """One failing model finalizer cannot retain active state or strand later callbacks."""
        # Arrange
        editor, model, curve, events = self._active_editor()
        states = []

        def fail_finalization():
            """Record cleared interaction state before raising a finalization error."""
            states.append(
                (
                    editor._position_axis,
                    editor._position_edit_stack,
                    editor._position_pointer_edit,
                    editor._position_keys,
                    dict(editor._position_baseline),
                    dict(editor._position_curves),
                    dict(editor._position_key_objects),
                )
            )
            raise ValueError("model finalization failed")

        editor._position_edit_stack.callback(fail_finalization)
        editor._canvas.reload_from_storage.side_effect = lambda: setattr(curve.keys[0], "value", 2.0)

        # Act
        with self.assertRaisesRegex(ValueError, "model finalization failed"):
            editor._finish_position_edit()

        # Assert
        self.assertEqual(states, [(None, None, False, (), {}, {}, {})])
        self.assertEqual(events.count("curves end"), 1)
        self.assertEqual(events[-2:], ["curves end", "group end"])
        self.assertEqual(model.as_float, 2.0)

    async def test_unchanged_native_float_representation_does_not_write_double_key(self):
        """An untouched field must not quantize a stored key merely when focus leaves."""
        for axis in ("time", "value"):
            with self.subTest(title=axis):
                # Arrange
                events = []
                original_value = 0.12345678912345678
                curve = FCurve(id="x", keys=[FCurveKey(time=original_value, value=original_value)])
                editor = _editor({"x": curve}, [KeyReference("x", 0)], events)
                self._patches.callback(editor.destroy)
                editor._refresh_position_fields()
                model = editor._position_fields[axis].model
                editor._on_position_edit_begin(axis, model)

                # Act
                editor._on_position_edit_end(axis, model)

                # Assert
                self.assertEqual((curve.keys[0].time, curve.keys[0].value), (original_value, original_value))
                self.assertEqual(events, [])

    async def test_rejected_numeric_input_unwinds_and_refreshes_fields(self):
        """Failed writes restore the displayed storage value and release the edit scope."""
        # Arrange
        events = []
        curve = FCurve(id="x", keys=[FCurveKey(time=0.25, value=2.0)])
        editor = _editor({"x": curve}, [KeyReference("x", 0)], events)
        editor._refresh_position_fields()
        model = editor._position_fields["value"].model
        editor._on_position_edit_begin("value", model)
        editor.fcurve_widget.set_key_positions.side_effect = ValueError("cannot write")
        model.set_value(7.0)

        # Act
        with self.assertRaisesRegex(ValueError, "cannot write"):
            editor._on_position_value_changed("value", model)

        # Assert
        self.assertEqual(events[-2:], ["curves end", "group end"])
        self.assertEqual(model.as_float, 2.0)
        self.assertIsNone(editor._position_axis)

    async def test_late_value_callback_after_end_does_not_start_another_edit(self):
        """Callbacks delivered after native end cannot reuse a completed gesture."""
        # Arrange
        events = []
        curve = FCurve(id="x", keys=[FCurveKey(time=0.25, value=2.0)])
        editor = _editor({"x": curve}, [KeyReference("x", 0)], events)
        editor._refresh_position_fields()
        model = editor._position_fields["value"].model
        editor._on_position_edit_begin("value", model)
        editor._on_position_edit_end("value", model)
        model.set_value(7.0)

        # Act
        editor._on_position_value_changed("value", model)

        # Assert
        self.assertEqual(events, [])
        self.assertEqual(curve.keys[0].value, 2.0)

    async def test_destroy_with_canvas_failure_still_releases_other_children(self):
        """A failed canvas teardown cannot strand the tree, frame, or their references."""
        # Arrange
        editor = _editor({}, [], [])
        destroyed = []

        def destroy_canvas():
            destroyed.append("canvas")
            raise ValueError("canvas cleanup failed")

        editor._canvas.destroy.side_effect = destroy_canvas
        editor._curve_tree = Mock(destroy=lambda: destroyed.append("tree"))
        editor._frame = Mock(destroy=lambda: destroyed.append("frame"))
        fields = list(editor._position_fields.values())

        # Act
        with self.assertRaisesRegex(ValueError, "canvas cleanup failed"):
            editor.destroy()

        # Assert
        self.assertEqual(destroyed, ["canvas", "tree", "frame"])
        self.assertIsNone(editor._canvas)
        self.assertIsNone(editor._curve_tree)
        self.assertIsNone(editor._frame)
        for field in fields:
            field.set_key_pressed_fn.assert_called_once_with(None)

    async def test_destroy_after_canvas_failure_does_not_repeat_child_cleanup(self):
        """A second destruction leaves already-released children untouched."""
        # Arrange
        editor = _editor({}, [], [])
        canvas = editor._canvas
        canvas.destroy.side_effect = ValueError("canvas cleanup failed")
        tree = editor._curve_tree = Mock()
        frame = editor._frame = Mock()
        with self.assertRaisesRegex(ValueError, "canvas cleanup failed"):
            editor.destroy()

        # Act
        editor.destroy()

        # Assert
        canvas.destroy.assert_called_once_with()
        tree.destroy.assert_called_once_with()
        frame.destroy.assert_called_once_with()

    def _active_editor(self):
        """Start a numeric edit that changes one key and register editor cleanup."""
        events = []
        curve = FCurve(id="x", keys=[FCurveKey(time=0.25, value=2.0)])
        editor = _editor({"x": curve}, [KeyReference("x", 0)], events)
        self._patches.callback(editor.destroy)
        model = editor._position_fields["value"].model
        editor._on_position_edit_begin("value", model)
        model.set_value(4.0)
        editor._on_position_value_changed("value", model)
        return editor, model, curve, events

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

from contextlib import nullcontext
from unittest.mock import Mock

import omni.kit.test
from omni.flux.curve_editor.widget.canvas import CurveEditorCanvas
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.fcurve.widget import FCurve, FCurveKey, FCurveWidget, KeyReference, SelectionInfo
from omni.flux.utils.widget import GroupedKeysModel

__all__ = ["TestCurveEditorCanvas"]


def _canvas(selected_keys: list[KeyReference] | None = None) -> CurveEditorCanvas:
    """Create canvas selection and edit lifecycle state without constructing UI."""
    payloads = {
        "x": curve_to_payload(FCurve(id="x", keys=[FCurveKey(0.0, 0.0), FCurveKey(1.0, 1.0)])),
        "y": curve_to_payload(FCurve(id="y", keys=[FCurveKey()])),
    }
    model = Mock(spec=GroupedKeysModel)
    model.group_ids = list(payloads)
    model.get_payload.side_effect = payloads.get

    widget = Mock(spec=FCurveWidget)
    widget.selection = SelectionInfo(keys=list(selected_keys or []))

    def set_curves(curves: dict[str, FCurve]) -> None:
        """Model the renderer's replacement and selection-reset boundary."""
        widget.curves = curves
        widget.selection = SelectionInfo()

    widget.set_curves.side_effect = set_curves

    canvas = CurveEditorCanvas.__new__(CurveEditorCanvas)
    canvas._model = model
    canvas._fcurve_widget = widget
    canvas._curve_colors = {}
    canvas._selected_curve_ids = {"x"}
    canvas._dragging_curve_ids = set()
    canvas._drag_has_changes = False
    canvas._edit_context_factory = nullcontext
    canvas._on_model_changed_callback = None
    return canvas


class TestCurveEditorCanvas(omni.kit.test.AsyncTestCase):
    """Test channel filtering and continuous-edit ownership without constructing UI."""

    async def test_set_selected_curve_ids_retains_only_valid_refs_on_loaded_curves(self):
        """Discard hidden, missing, negative, and out-of-range key references."""
        # Arrange
        canvas = _canvas(
            [
                KeyReference("x", 0),
                KeyReference("x", 1),
                KeyReference("y", 0),
                KeyReference("missing", 0),
                KeyReference("x", -1),
                KeyReference("x", 2),
            ]
        )

        # Act
        canvas.set_selected_curve_ids({"x"})

        # Assert
        self.assertEqual({"x"}, set(canvas._fcurve_widget.curves))
        canvas._fcurve_widget.select_keys.assert_called_once_with([KeyReference("x", 0), KeyReference("x", 1)])
        canvas._model.commit_payload.assert_not_called()

    async def test_set_selected_curve_ids_with_none_loads_all_curves(self):
        """Remove the channel filter while retaining valid selected keys."""
        # Arrange
        canvas = _canvas([KeyReference("x", 1)])

        # Act
        canvas.set_selected_curve_ids(None)

        # Assert
        self.assertEqual({"x", "y"}, set(canvas._fcurve_widget.curves))
        canvas._fcurve_widget.select_keys.assert_called_once_with([KeyReference("x", 1)])
        canvas._model.commit_payload.assert_not_called()

    async def test_edit_curves_brackets_each_distinct_target_once(self):
        """Distinct targets begin in order and finalize in reverse order."""
        # Arrange
        canvas = _canvas()
        states = []
        canvas._model.begin_edit.side_effect = lambda curve_id: states.append(("begin", curve_id))
        canvas._model.end_edit.side_effect = lambda curve_id: states.append(("end", curve_id))

        # Act
        with canvas.edit_curves(("x", "y", "x")):
            pass

        # Assert
        self.assertEqual(
            states,
            [
                ("begin", "x"),
                ("begin", "y"),
                ("end", "y"),
                ("end", "x"),
            ],
        )

    async def test_edit_curves_failed_begin_finishes_successful_predecessors(self):
        """An exception opening one backend edit cannot leave earlier edits open."""
        # Arrange
        canvas = _canvas()
        canvas._model.begin_edit.side_effect = [None, ValueError("cannot start")]

        # Act
        with self.assertRaisesRegex(ValueError, "cannot start"):
            with canvas.edit_curves(("x", "y")):
                pass

        # Assert
        canvas._model.end_edit.assert_called_once_with("x")

    async def test_edit_curves_failed_end_still_finishes_other_curves(self):
        """A backend end failure does not strand another curve's edit scope."""
        # Arrange
        canvas = _canvas()
        ended = []

        def end_edit(curve_id):
            ended.append(curve_id)
            if curve_id == "y":
                raise ValueError("cannot finish")

        canvas._model.end_edit.side_effect = end_edit

        # Act
        with self.assertRaisesRegex(ValueError, "cannot finish"):
            with canvas.edit_curves(("x", "y")):
                pass

        # Assert
        self.assertEqual(ended, ["y", "x"])

    async def test_model_notices_during_numeric_edit_reach_owner(self):
        """Numeric editing forwards model notices for participating and other curves."""
        for curve_id in ("x", "other"):
            with self.subTest(title=curve_id):
                # Arrange
                canvas = _canvas()
                notices = []
                canvas._on_model_changed_callback = notices.append

                # Act
                with canvas.edit_curves(("x",)):
                    canvas._on_model_changed(curve_id)

                    # Assert
                    self.assertEqual(notices, [curve_id])
                    self.assertEqual(canvas._dragging_curve_ids, set())

    async def test_destroy_with_viewport_end_failure_finishes_every_curve_once(self):
        """Every viewport edit and child widget closes even if the first backend end fails."""
        # Arrange
        canvas = _canvas()
        canvas._dragging_curve_ids = {"x", "y"}
        ended = []
        destroyed = []

        def end_edit(curve_id):
            ended.append(curve_id)
            if len(ended) == 1:
                raise ValueError("viewport end failed")

        canvas._model.end_edit.side_effect = end_edit

        def destroy_fcurve():
            canvas._on_drag_ended("x")
            destroyed.append("fcurve")

        canvas._fcurve_widget = Mock(destroy=destroy_fcurve)
        canvas._frame = Mock(destroy=lambda: destroyed.append("frame"))

        # Act
        with self.assertRaisesRegex(ValueError, "viewport end failed"):
            canvas.destroy()

        # Assert
        self.assertEqual(set(ended), {"x", "y"})
        self.assertEqual(len(ended), 2)
        self.assertEqual(destroyed, ["fcurve", "frame"])
        self.assertEqual(canvas._dragging_curve_ids, set())
        self.assertIsNone(canvas._fcurve_widget)
        self.assertIsNone(canvas._frame)

    async def test_destroy_with_fcurve_failure_still_destroys_frame(self):
        """A child widget exception leaves no frame or retained child reference."""
        # Arrange
        canvas = _canvas()
        destroyed = []

        def destroy_fcurve():
            destroyed.append("fcurve")
            raise ValueError("fcurve cleanup failed")

        canvas._fcurve_widget = Mock(destroy=destroy_fcurve)
        canvas._frame = Mock(destroy=lambda: destroyed.append("frame"))

        # Act
        with self.assertRaisesRegex(ValueError, "fcurve cleanup failed"):
            canvas.destroy()

        # Assert
        self.assertEqual(destroyed, ["fcurve", "frame"])
        self.assertIsNone(canvas._fcurve_widget)
        self.assertIsNone(canvas._frame)

    async def test_destroy_after_failure_does_not_repeat_model_or_child_cleanup(self):
        """Failed destruction releases ownership before a later destroy call."""
        for failing_boundary in ("model", "fcurve"):
            with self.subTest(title=failing_boundary):
                # Arrange
                canvas = _canvas()
                canvas._dragging_curve_ids = {"x", "y"}
                fcurve_widget = canvas._fcurve_widget = Mock()
                frame = canvas._frame = Mock()
                if failing_boundary == "model":
                    canvas._model.end_edit.side_effect = [ValueError("cleanup failed"), None]
                else:
                    fcurve_widget.destroy.side_effect = ValueError("cleanup failed")
                with self.assertRaisesRegex(ValueError, "cleanup failed"):
                    canvas.destroy()

                # Act
                canvas.destroy()

                # Assert
                self.assertEqual(canvas._model.end_edit.call_count, 2)
                fcurve_widget.destroy.assert_called_once_with()
                frame.destroy.assert_called_once_with()

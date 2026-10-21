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

from unittest.mock import Mock, patch

import omni.kit.test

from omni.flux.curve_editor.widget import toolbar as toolbar_module
from omni.flux.curve_editor.widget.toolbar import CurveEditorToolbar
from omni.flux.fcurve.widget import CurveBounds, FCurve, FCurveKey, KeyReference

__all__ = ["TestCurveEditorToolbar"]

_BOUNDS = CurveBounds(time_min=-2e308, time_max=2e308, value_min=-1.0, value_max=1.0)


def _toolbar(curves: dict[str, FCurve], editable_selected_keys: tuple[KeyReference, ...] = ()) -> CurveEditorToolbar:
    """Create a toolbar without constructing its UI."""
    widget = Mock()
    widget.curves = curves
    widget.editable_selected_keys = editable_selected_keys
    widget.keyframe_clamp_threshold = 0.001
    widget.bounds_for.return_value = _BOUNDS
    edit_context_factory = Mock(side_effect=AssertionError("edit context should not be entered"))
    with patch.object(CurveEditorToolbar, "_build_ui"):
        return CurveEditorToolbar(widget, edit_context_factory=edit_context_factory)


class TestCurveEditorToolbar(omni.kit.test.AsyncTestCase):
    """Test toolbar curve targeting without building UI controls."""

    async def test_prepare_add_keys_with_nonfinite_shared_time_returns_reason(self):
        """An overflowing anchor midpoint should make Add unavailable."""
        # Arrange
        curve = FCurve(id="curve", keys=[FCurveKey(time=1e308), FCurveKey(time=1.7e308)])
        toolbar = _toolbar({curve.id: curve}, (KeyReference(curve.id, 0),))

        # Act
        prepared, reason = toolbar._prepare_add_keys()

        # Assert
        self.assertEqual(prepared, [])
        self.assertEqual(reason, "The shared key time must be finite.")

    async def test_prepare_add_keys_with_nonfinite_sample_returns_reason(self):
        """A nonfinite evaluated value should make Add unavailable."""
        # Arrange
        curve = FCurve(id="curve", keys=[FCurveKey(time=0.0), FCurveKey(time=1.0)])
        toolbar = _toolbar({curve.id: curve}, (KeyReference(curve.id, 0),))

        # Act
        with patch.object(toolbar_module, "evaluate_curve", return_value=float("inf")):
            prepared, reason = toolbar._prepare_add_keys()

        # Assert
        self.assertEqual(prepared, [])
        self.assertEqual(reason, "The sampled value is outside a selected curve's bounds or is not finite.")

    async def test_prepare_add_keys_with_no_eligible_curves_returns_reason(self):
        """Locked, hidden, and empty curves should not be Add targets."""
        # Arrange
        curves = {
            "locked": FCurve(id="locked", locked=True, keys=[FCurveKey()]),
            "hidden": FCurve(id="hidden", visible=False, keys=[FCurveKey()]),
            "empty": FCurve(id="empty"),
        }
        toolbar = _toolbar(curves)

        # Act
        prepared, reason = toolbar._prepare_add_keys()

        # Assert
        self.assertEqual(prepared, [])
        self.assertEqual(reason, "Select an unlocked channel with curve data. Use Create for empty channels.")

    async def test_on_add_key_reused_key_outside_value_bounds_rejects_all_targets(self):
        """Recheck reused-key bounds at click time before opening an edit group."""
        # Arrange
        curves = {
            "first": FCurve(id="first", keys=[FCurveKey(time=0.0), FCurveKey(time=1.0)]),
            "second": FCurve(id="second", keys=[FCurveKey(time=0.5, value=2.0)]),
        }
        toolbar = _toolbar(curves)
        toolbar._add_key_btn = Mock(enabled=True)

        # Act
        toolbar._on_add_key()

        # Assert
        self.assertFalse(toolbar._add_key_btn.enabled)
        self.assertEqual(
            toolbar._add_key_btn.tooltip, "The sampled value is outside a selected curve's bounds or is not finite."
        )
        toolbar._edit_context_factory.assert_not_called()
        toolbar._fcurve_widget.add_key.assert_not_called()
        toolbar._fcurve_widget.clear_selection.assert_not_called()
        toolbar._fcurve_widget.select_keys.assert_not_called()

    async def test_prepare_add_keys_uses_first_eligible_selected_key_as_anchor(self):
        """The first eligible selected key determines the shared time for all displayed targets."""
        # Arrange
        curves = {
            "first": FCurve(id="first", keys=[FCurveKey(time=0.0), FCurveKey(time=20.0)]),
            "selected": FCurve(id="selected", keys=[FCurveKey(time=10.0), FCurveKey(time=14.0)]),
            "locked": FCurve(id="locked", locked=True, keys=[FCurveKey(time=50.0)]),
        }
        toolbar = _toolbar(
            curves,
            (KeyReference("selected", 0), KeyReference("first", 0)),
        )

        # Act
        with patch.object(toolbar_module, "evaluate_curve", return_value=0.5):
            prepared, reason = toolbar._prepare_add_keys()

        # Assert
        self.assertEqual(reason, "")
        self.assertEqual(
            [(curve_id, time) for curve_id, time, _value, _index in prepared], [("first", 12.0), ("selected", 12.0)]
        )

    async def test_on_add_key_when_large_time_reuses_all_keys_without_edit_context(self):
        """A rounded singleton offset should select existing keys without opening an edit group."""
        # Arrange
        curves = {
            "first": FCurve(id="first", keys=[FCurveKey(time=1e16, value=0.25)]),
            "second": FCurve(id="second", keys=[FCurveKey(time=1e16, value=0.75)]),
        }
        toolbar = _toolbar(curves, (KeyReference("first", 0),))

        # Act
        toolbar._on_add_key()

        # Assert
        toolbar._edit_context_factory.assert_not_called()
        toolbar._fcurve_widget.add_key.assert_not_called()
        toolbar._fcurve_widget.select_keys.assert_called_once_with(
            [KeyReference("first", 0), KeyReference("second", 0)]
        )

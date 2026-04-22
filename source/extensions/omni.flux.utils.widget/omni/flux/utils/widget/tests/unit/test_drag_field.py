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

from typing import Any, cast
from unittest.mock import patch

import omni.kit.test
from omni.flux.utils.widget.drag_field import IntBoundedDrag, _HardLimitDragMixin


class _MockModel:
    def __init__(self):
        self.supports_batch_edit = False
        self.is_batch_editing = False
        self._callback = None
        self.last_value = None

    def set_callback_pre_set_value(self, callback):
        self._callback = callback

    def apply(self, value):
        if self._callback is None:
            self.last_value = value
            return
        self._callback(self._set, value)

    def _set(self, value):
        self.last_value = value


class _MockWidgetBase:
    def __init__(self, model=None, **kwargs):
        del kwargs
        self.model = model
        self._pressed_fn = None
        self._released_fn = None

    def set_mouse_pressed_fn(self, callback):
        self._pressed_fn = callback

    def set_mouse_released_fn(self, callback):
        self._released_fn = callback

    def emit_mouse_pressed(self, button=0):
        if self._pressed_fn is not None:
            self._pressed_fn(0.0, 0.0, button, 0)

    def emit_mouse_released(self, button=0):
        if self._released_fn is not None:
            self._released_fn(0.0, 0.0, button, 0)


class _MockDrag(_HardLimitDragMixin, _MockWidgetBase):
    pass


class _BatchModel(_MockModel):
    def __init__(self):
        super().__init__()
        self.supports_batch_edit = True
        self.is_batch_editing = False
        self.begin_count = 0
        self.end_count = 0

    def begin_batch_edit(self):
        self.begin_count += 1
        self.is_batch_editing = True

    def end_batch_edit(self):
        self.end_count += 1
        self.is_batch_editing = False


class _ModelWithoutBatchFlag:
    def __init__(self):
        self._callback = None
        self.last_value = None

    def set_callback_pre_set_value(self, callback):
        self._callback = callback

    def apply(self, value):
        if self._callback is None:
            self.last_value = value
            return
        self._callback(self._set, value)

    def _set(self, value):
        self.last_value = value


class TestHardClampedDragMixin(omni.kit.test.AsyncTestCase):
    async def test_clamps_to_hard_bounds(self):
        # Arrange
        model = _MockModel()
        _MockDrag(model=model, hard_min_value=0.0, hard_max_value=10.0)

        # Act
        model.apply(-5.0)

        # Assert
        self.assertEqual(model.last_value, 0.0)

    async def test_preserves_input_type(self):
        # Arrange
        model = _MockModel()
        _MockDrag(model=model, hard_min_value=0, hard_max_value=10)

        # Act
        model.apply(12)

        # Assert
        self.assertIsInstance(model.last_value, int)
        self.assertEqual(model.last_value, 10)

    async def test_drag_int_normalizes_fractional_hard_min_with_ceiling(self):
        # Arrange
        value = 0

        # Act
        result = IntBoundedDrag._clamp_numeric_value(value, hard_min=cast(Any, 0.5), hard_max=None)

        # Assert
        self.assertIsInstance(result, int)
        self.assertEqual(result, 1)

    async def test_drag_int_normalizes_fractional_hard_max_with_floor(self):
        # Arrange
        value = 10

        # Act
        result = IntBoundedDrag._clamp_numeric_value(value, hard_min=None, hard_max=cast(Any, 3.7))

        # Assert
        self.assertIsInstance(result, int)
        self.assertEqual(result, 3)

    async def test_drag_int_clamps_with_integer_hard_limits(self):
        # Arrange
        value = 10

        # Act
        result = IntBoundedDrag._clamp_numeric_value(value, hard_min=0, hard_max=3)

        # Assert
        self.assertIsInstance(result, int)
        self.assertEqual(result, 3)

    async def test_drag_int_ignores_inverted_bounds_after_integer_normalization(self):
        # Arrange
        value = 5

        # Act
        with patch("omni.flux.utils.widget.drag_field.carb.log_warn") as mock_log_warn:
            result = IntBoundedDrag._clamp_numeric_value(value, hard_min=cast(Any, 0.3), hard_max=cast(Any, 0.7))

        # Assert
        self.assertIsInstance(result, int)
        self.assertEqual(result, 5)
        mock_log_warn.assert_called_once()

    async def test_drag_int_non_numeric_passthrough(self):
        # Arrange
        value = cast(Any, "abc")

        # Act
        result = IntBoundedDrag._clamp_numeric_value(value, hard_min=0, hard_max=10)

        # Assert
        self.assertEqual(result, "abc")

    async def test_ignores_non_numeric_values(self):
        # Arrange
        model = _MockModel()
        _MockDrag(model=model, hard_min_value=0.0, hard_max_value=1.0)

        # Act
        model.apply("abc")

        # Assert
        self.assertEqual(model.last_value, "abc")

    async def test_drag_starts_batch_edit_before_setting_value(self):
        # Arrange
        model = _BatchModel()
        widget = _MockDrag(model=model, hard_min_value=0.0, hard_max_value=10.0)
        widget.emit_mouse_pressed(button=0)

        # Act
        model.apply(5.0)

        # Assert
        self.assertEqual(model.begin_count, 1)
        self.assertTrue(model.is_batch_editing)
        self.assertEqual(model.last_value, 5.0)

    async def test_mouse_release_ends_active_batch_edit(self):
        # Arrange
        model = _BatchModel()
        widget = _MockDrag(model=model, hard_min_value=0.0, hard_max_value=10.0)
        widget.emit_mouse_pressed(button=0)
        model.apply(7.0)

        # Act
        widget.emit_mouse_released(button=0)

        # Assert
        self.assertEqual(model.end_count, 1)
        self.assertFalse(model.is_batch_editing)

    async def test_missing_batch_flag_logs_warning_and_disables_batch_behavior(self):
        # Arrange
        model = _ModelWithoutBatchFlag()
        widget = _MockDrag(model=model, hard_min_value=0.0, hard_max_value=10.0, enable_batch_edit=True)

        # Act
        with patch("omni.flux.utils.widget.drag_field.carb.log_warn") as mock_log_warn:
            widget._sync_hard_clamp_callback()
            widget._sync_hard_clamp_callback()
            model.apply(5.0)

            # Assert
            self.assertEqual(model.last_value, 5.0)
            self.assertGreaterEqual(mock_log_warn.call_count, 1)

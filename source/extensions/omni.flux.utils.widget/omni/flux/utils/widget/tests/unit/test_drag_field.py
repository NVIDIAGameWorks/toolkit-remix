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

from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

import carb
import omni.kit.test
from omni.flux.utils.widget.drag_field import (
    FloatBoundedDrag,
    IntBoundedDrag,
    _BoundedNumericDragBase,
    _safe_eval_numeric_expression,
)


class _MockModel:
    def __init__(self, value=0.0, string_value=None):
        self.supports_batch_edit = False
        self.is_batch_editing = False
        self._callback = None
        self.last_value = value
        self.string_value = string_value

    def set_callback_pre_set_value(self, callback):
        self._callback = callback

    def apply(self, value):
        if self._callback is None:
            self.last_value = value
            return
        self._callback(self._set, value)

    def _set(self, value):
        self.last_value = value

    def set_value(self, value):
        self.apply(value)

    def get_value_as_float(self):
        return float(self.last_value)

    def get_value_as_string(self):
        return self.string_value if self.string_value is not None else str(self.last_value)


class _MockWidgetBase:
    def __init__(self, model=None, **kwargs):
        self.model = model
        self.step = kwargs.pop("step", None)
        self.kwargs = kwargs
        self.min = kwargs.get("min")
        self.max = kwargs.get("max")
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

    def destroy(self):
        pass


class _MockDrag(_BoundedNumericDragBase, _MockWidgetBase):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("enable_numeric_edit", False)
        super().__init__(*args, **kwargs)


class _MockFloatDrag(_MockDrag):
    _NUMERIC_VALUE_TYPE = float
    _KEYBOARD_STEP_VALUE_TYPE = float


class _MockIntDrag(_MockDrag):
    _NUMERIC_VALUE_TYPE = int
    _KEYBOARD_STEP_VALUE_TYPE = int
    _MIN_KEYBOARD_STEP = 1


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


class _ReentrantEndBatchModel(_BatchModel):
    def end_batch_edit(self):
        super().end_batch_edit()
        self.apply(4.0)


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


class TestBoundedNumericDragBase(omni.kit.test.AsyncTestCase):
    async def test_concrete_drag_widgets_reuse_shared_numeric_edit_hooks(self):
        # Arrange
        shared_methods = {
            "__init__",
            "_coerce_numeric_value",
            "_get_keyboard_step",
            "begin_deferred_numeric_undo_group",
            "begin_numeric_text_edit",
            "set_numeric_expression_value",
            "set_numeric_edit_widgets",
            "step_keyboard_value",
        }

        # Act
        duplicated_methods = {
            cls.__name__: sorted(shared_methods.intersection(cls.__dict__))
            for cls in (FloatBoundedDrag, IntBoundedDrag)
        }

        # Assert
        self.assertTrue(issubclass(FloatBoundedDrag, _BoundedNumericDragBase))
        self.assertTrue(issubclass(IntBoundedDrag, _BoundedNumericDragBase))
        self.assertEqual(duplicated_methods, {"FloatBoundedDrag": [], "IntBoundedDrag": []})

    async def test_clamps_to_hard_bounds(self):
        # Arrange
        model = _MockModel()
        _MockDrag(model=model, hard_min_value=0.0, hard_max_value=10.0)

        # Act
        model.apply(-5.0)

        # Assert
        self.assertEqual(model.last_value, 0.0)

    async def test_hard_min_fills_missing_drag_min(self):
        # Arrange / Act
        widget = _MockDrag(model=_MockModel(), hard_min_value=0.0, max=10.0)

        # Assert
        self.assertEqual(widget.min, 0.0)
        self.assertEqual(widget.max, 10.0)

    async def test_hard_max_fills_missing_drag_max(self):
        # Arrange / Act
        widget = _MockDrag(model=_MockModel(), min=0.0, hard_max_value=10.0)

        # Assert
        self.assertEqual(widget.min, 0.0)
        self.assertEqual(widget.max, 10.0)

    async def test_explicit_drag_bounds_are_not_overridden_by_hard_bounds(self):
        # Arrange / Act
        widget = _MockDrag(model=_MockModel(), min=0.0, max=10.0, hard_min_value=5.0, hard_max_value=8.0)

        # Assert
        self.assertEqual(widget.min, 0.0)
        self.assertEqual(widget.max, 10.0)

    async def test_invalid_hard_bound_drag_fallback_is_ignored(self):
        # Arrange / Act
        with patch("omni.flux.utils.widget.drag_field.carb.log_warn") as mock_log_warn:
            widget = _MockDrag(model=_MockModel(), hard_min_value=20.0, max=10.0)

        # Assert
        self.assertIsNone(widget.min)
        self.assertEqual(widget.max, 10.0)
        mock_log_warn.assert_called_once()

    async def test_preserves_input_type(self):
        # Arrange
        model = _MockModel()
        _MockDrag(model=model, hard_min_value=0, hard_max_value=10)

        # Act
        model.apply(12)

        # Assert
        self.assertIsInstance(model.last_value, int)
        self.assertEqual(model.last_value, 10)

    async def test_float_drag_does_not_coerce_bool_as_number(self):
        # Arrange
        drag = _MockFloatDrag(model=_MockModel())

        # Act
        result = drag._coerce_numeric_value(True)

        # Assert
        self.assertIs(result, True)

    async def test_drag_int_normalizes_fractional_hard_min_with_ceiling(self):
        # Arrange
        value = 0

        # Act
        result = IntBoundedDrag._clamp_numeric_value(value, hard_min=cast(Any, 0.5), hard_max=None)

        # Assert
        self.assertIsInstance(result, int)
        self.assertEqual(result, 1)

    async def test_numeric_expression_parser_accepts_basic_arithmetic(self):
        # Arrange
        expressions = ("2*100", "-(5 + 3) / 2")

        # Act
        results = [_safe_eval_numeric_expression(expression) for expression in expressions]

        # Assert
        self.assertEqual(results, [200, -4.0])

    async def test_numeric_expression_parser_preserves_large_integer_precision(self):
        # Arrange
        expression = "9007199254740993 + 1"

        # Act
        result = _safe_eval_numeric_expression(expression)

        # Assert
        self.assertEqual(result, 9007199254740994)

    async def test_numeric_expression_parser_rejects_unsafe_input(self):
        # Arrange
        unsafe_expressions = ("__import__('os').system('echo unsafe')", "2**10", "1e999")

        # Act
        for expression in unsafe_expressions:
            with self.subTest(expression=expression):
                # Assert
                with self.assertRaises(ValueError):
                    _safe_eval_numeric_expression(expression)

    async def test_numeric_expression_parser_rejects_deep_expressions(self):
        # Arrange
        expression = "+" * 25 + "1"

        # Act
        with self.assertRaises(ValueError):
            # Assert
            _safe_eval_numeric_expression(expression)

    async def test_arrow_up_evaluates_expression_and_adds_widget_step(self):
        # Arrange
        model = _MockModel(value=0.0, string_value="2*100")
        widget = _MockDrag(model=model, step=0.1)

        # Act
        widget.step_keyboard_value(model, int(carb.input.KeyboardInput.UP))

        # Assert
        self.assertAlmostEqual(model.last_value, 200.1)

    async def test_numeric_expression_value_sets_evaluated_number_on_model(self):
        # Arrange
        model = _MockModel()
        widget = _MockFloatDrag(model=model)

        # Act
        with patch.object(model, "set_value", wraps=model.set_value) as set_value:
            widget.set_numeric_expression_value(model, "2*100")

        # Assert
        set_value.assert_called_once_with(200.0)
        self.assertEqual(model.last_value, 200.0)

    async def test_repeated_arrow_steps_do_not_propagate_float_rounding_errors(self):
        # Arrange
        model = _MockModel(value=0.0)
        widget = _MockDrag(model=model, step=0.1)

        # Act
        for _ in range(84):
            widget.step_keyboard_value(model, int(carb.input.KeyboardInput.UP))

        # Assert
        self.assertEqual(model.last_value, 8.4)

    async def test_arrow_step_snaps_existing_float_noise_to_step_grid(self):
        # Arrange
        model = _MockModel(value=8.399999999999988)
        widget = _MockDrag(model=model, step=0.1)

        # Act
        widget.step_keyboard_value(model, int(carb.input.KeyboardInput.UP))

        # Assert
        self.assertEqual(model.last_value, 8.5)

    async def test_arrow_step_handles_large_decimal_values(self):
        # Arrange
        value = Decimal("1e100")

        # Act
        result = _MockDrag._calculate_keyboard_step_value(value, 0.1, 1)

        # Assert
        self.assertEqual(result, 1e100)

    async def test_arrow_step_preserves_value_precision_when_not_float_noise(self):
        # Arrange
        model = _MockModel(value=0.015)
        widget = _MockDrag(model=model, step=0.1)

        # Act
        widget.step_keyboard_value(model, int(carb.input.KeyboardInput.UP))

        # Assert
        self.assertEqual(model.last_value, 0.115)

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

    async def test_drag_int_rejects_fractional_value_without_truncating(self):
        # Arrange
        model = _MockModel(value=5)
        _MockIntDrag(model=model)

        # Act
        model.apply("3/2")

        # Assert
        self.assertEqual(model.last_value, 5)

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

    async def test_rejects_non_numeric_string_values(self):
        # Arrange
        model = _MockModel()
        _MockDrag(model=model, hard_min_value=0.0, hard_max_value=1.0)

        # Act
        model.apply("abc")

        # Assert
        self.assertEqual(model.last_value, 0.0)

    async def test_rejects_empty_numeric_string_values(self):
        # Arrange
        model = _MockModel(value=3.0)
        _MockDrag(model=model, hard_min_value=0.0, hard_max_value=10.0)

        # Act
        model.apply(" ")

        # Assert
        self.assertEqual(model.last_value, 3.0)

    async def test_float_drag_accepts_integer_text(self):
        # Arrange
        model = _MockModel()
        _MockFloatDrag(model=model, hard_min_value=0.0, hard_max_value=100.0)

        # Act
        model.apply("12")

        # Assert
        self.assertEqual(model.last_value, 12.0)

    async def test_float_drag_ignores_incomplete_expression(self):
        # Arrange
        model = _MockModel(value=3.0)
        _MockFloatDrag(model=model, hard_min_value=0.0, hard_max_value=100.0)

        # Act
        model.apply("2*")

        # Assert
        self.assertEqual(model.last_value, 3.0)

    async def test_float_drag_ignores_leading_decimal_prefix(self):
        # Arrange
        expressions = (".", "+.", "-.")

        # Act
        for expression in expressions:
            with self.subTest(expression=expression):
                model = _MockModel(value=3.0)
                _MockFloatDrag(model=model, hard_min_value=-100.0, hard_max_value=100.0)
                model.apply(expression)

                # Assert
                self.assertEqual(model.last_value, 3.0)

    async def test_float_drag_ignores_incomplete_exponent(self):
        # Arrange
        expressions = ("1e", "1e+", "1e-")

        # Act
        for expression in expressions:
            with self.subTest(expression=expression):
                model = _MockModel(value=3.0)
                _MockFloatDrag(model=model, hard_min_value=0.0, hard_max_value=100.0)
                model.apply(expression)

                # Assert
                self.assertEqual(model.last_value, 3.0)

    async def test_float_drag_ignores_complete_invalid_expression(self):
        # Arrange
        invalid_expressions = ("1/0", "2**10", "1e999", "2*/3")

        # Act
        for expression in invalid_expressions:
            with self.subTest(expression=expression):
                model = _MockModel(value=3.0)
                _MockFloatDrag(model=model, hard_min_value=0.0, hard_max_value=100.0)
                model.apply(expression)

                # Assert
                self.assertEqual(model.last_value, 3.0)

    async def test_float_drag_rejects_oversized_numeric_string_values(self):
        # Arrange
        model = _MockModel(value=3.0)
        _MockFloatDrag(model=model, hard_min_value=0.0, hard_max_value=100.0)

        # Act
        model.apply("9" * 400)

        # Assert
        self.assertEqual(model.last_value, 3.0)

    async def test_arrow_step_falls_back_when_expression_overflows_float(self):
        # Arrange
        model = _MockModel(value=1.0, string_value="9" * 400)
        widget = _MockFloatDrag(model=model, step=0.1)

        # Act
        widget.step_keyboard_value(model, int(carb.input.KeyboardInput.UP))

        # Assert
        self.assertEqual(model.last_value, 1.1)

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

    async def test_destroy_clears_mouse_pressed_before_ending_batch_edit(self):
        # Arrange
        model = _ReentrantEndBatchModel()
        widget = _MockDrag(model=model, hard_min_value=0.0, hard_max_value=10.0)
        widget.emit_mouse_pressed(button=0)
        model.apply(7.0)

        # Act
        widget.destroy()

        # Assert
        self.assertEqual(model.end_count, 1)
        self.assertFalse(model.is_batch_editing)
        self.assertEqual(model.last_value, 4.0)

    async def test_non_left_mouse_release_keeps_active_batch_edit_open(self):
        # Arrange
        model = _BatchModel()
        widget = _MockDrag(model=model, hard_min_value=0.0, hard_max_value=10.0)
        widget.emit_mouse_pressed(button=0)
        model.apply(7.0)

        # Act
        widget.emit_mouse_released(button=1)

        # Assert
        self.assertEqual(model.end_count, 0)
        self.assertTrue(model.is_batch_editing)

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

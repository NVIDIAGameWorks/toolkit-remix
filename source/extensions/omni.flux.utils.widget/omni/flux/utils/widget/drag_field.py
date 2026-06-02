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

__all__ = ("FloatBoundedDrag", "IntBoundedDrag")

import ast
import math
import operator
from contextlib import suppress
from decimal import Decimal, localcontext
from typing import Any, ClassVar, Protocol, cast

import carb
import omni.appwindow
import omni.kit.undo
import omni.ui as ui


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_PENDING_EXPRESSION_CHARS = frozenset("0123456789.eE+-*/() ")
_KEYBOARD_STEP_DIRECTIONS = {
    int(carb.input.KeyboardInput.UP): 1,
    int(carb.input.KeyboardInput.DOWN): -1,
}
_STEP_KEYS = frozenset(_KEYBOARD_STEP_DIRECTIONS)
_ENTER_KEY = int(carb.input.KeyboardInput.ENTER)
_ESCAPE_KEY = int(carb.input.KeyboardInput.ESCAPE)
_END_KEYS = frozenset((_ENTER_KEY, _ESCAPE_KEY))
_TAB_KEY = int(carb.input.KeyboardInput.TAB)
_BACKSPACE_KEY = int(carb.input.KeyboardInput.BACKSPACE)
_CONTROL_MODIFIER_FLAG = int(carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
_STEP_GRID_TOLERANCE = Decimal("1e-12")
_MAX_NUMERIC_EXPRESSION_DEPTH = 20


def _safe_eval_numeric_expression(expression: str) -> float | int:
    """Evaluate a numeric expression limited to arithmetic operators."""

    try:
        tree = ast.parse(expression.strip(), mode="eval")
        value = _eval_numeric_ast(tree.body)
        if isinstance(value, int):
            return value
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"Non-finite numeric expression: {expression}")
        return value
    except (ArithmeticError, RecursionError, SyntaxError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric expression: {expression}") from exc


def _eval_numeric_ast(node: ast.AST, depth: int = 0) -> float | int:
    if depth > _MAX_NUMERIC_EXPRESSION_DEPTH:
        raise ValueError("Numeric expression is too deeply nested")
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_eval_numeric_ast(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        return _BINARY_OPERATORS[type(node.op)](
            _eval_numeric_ast(node.left, depth + 1), _eval_numeric_ast(node.right, depth + 1)
        )
    raise ValueError(f"Unsupported numeric expression node: {type(node).__name__}")


class _DragModelProtocol(Protocol):
    """Static typing contract for drag widget value models.

    Why this exists:
        ``_BoundedNumericDragBase`` is reused by concrete UI drag widgets, but the
        mixin itself does not declare model APIs like ``set_callback_pre_set_value``
        or batch-edit hooks. This protocol documents the required model surface
        so static type checkers can validate direct attribute access.
    """

    supports_batch_edit: bool
    is_batch_editing: bool

    def begin_batch_edit(self) -> None: ...
    def end_batch_edit(self) -> None: ...
    def set_callback_pre_set_value(self, callback: Any) -> None: ...
    def subscribe_value_changed_fn(self, callback: Any) -> Any: ...
    def subscribe_begin_edit_fn(self, callback: Any) -> Any: ...
    def subscribe_end_edit_fn(self, callback: Any) -> Any: ...
    def subscribe_property_edit_cancel_fn(self, callback: Any) -> Any: ...
    def begin_edit(self) -> None: ...
    def end_edit(self) -> None: ...
    def get_value(self) -> Any: ...
    def get_value_as_float(self) -> float: ...
    def get_value_as_string(self) -> str: ...
    def set_value(self, value: Any) -> None: ...


class _DragWidgetProtocol(Protocol):
    """Static typing contract for widgets that host ``_BoundedNumericDragBase``.

    Why this exists:
        The mixin assumes concrete drag widgets provide a ``model`` plus mouse
        callback registration APIs. This protocol captures that required widget
        interface for lint/type-check correctness while the implementation keeps
        direct calls to the typed model and widget contracts.
    """

    model: _DragModelProtocol
    step: Any
    enabled: bool

    def set_mouse_pressed_fn(self, callback: Any) -> None: ...
    def set_mouse_released_fn(self, callback: Any) -> None: ...
    def set_mouse_double_clicked_fn(self, callback: Any) -> None: ...
    def set_numeric_expression_value(self, model: _DragModelProtocol, expression: str) -> None: ...
    def step_keyboard_value(self, model: _DragModelProtocol, key: int, expression: str | None = None) -> None: ...
    def begin_numeric_text_edit(
        self, *, clear_value: bool = True, from_tab_transfer: bool = False, begin_undo_group: bool = True
    ) -> None: ...
    def begin_deferred_numeric_undo_group(self) -> None: ...


class _NumericEditController:
    active_controller: ClassVar["_NumericEditController | None"] = None

    def __init__(
        self,
        *,
        value_model: _DragModelProtocol,
        drag_widget: _DragWidgetProtocol,
        style_type_name_override: str,
    ) -> None:
        self._value_model = value_model
        self._drag_widget = drag_widget
        self._edit_widgets: dict[int, _DragWidgetProtocol] = {}
        self._index = 0
        self._updating = False
        self._applying = False
        self._editing = False
        self._transfer_key_active = False
        self._replace_expression_text = True
        self._keyboard_subscription: int | None = None
        self._undo_group_open = False
        self._destroyed = False
        self._initial_value: Any = None
        self._cancel_subscription = self._value_model.subscribe_property_edit_cancel_fn(self._cancel_edit)
        self._expression_model = ui.SimpleStringModel()
        self._expression_field = ui.StringField(
            model=self._expression_model,
            visible=False,
            enabled=False,
            read_only=True,
            width=ui.Fraction(1),
            style_type_name_override=style_type_name_override,
        )
        self._subs = [
            self._expression_model.subscribe_value_changed_fn(self._apply_expression),
            self._value_model.subscribe_value_changed_fn(self._sync_expression_from_target),
            self._expression_model.subscribe_begin_edit_fn(self._begin_edit),
            self._expression_model.subscribe_end_edit_fn(self._end_edit),
        ]
        self._expression_field.set_key_pressed_fn(self._on_key_pressed)
        self._drag_widget.set_mouse_double_clicked_fn(self.begin_text_edit)

    def set_edit_widgets(self, widgets: dict[int, _DragWidgetProtocol], index: int) -> None:
        self._edit_widgets = widgets
        self._index = index

    @classmethod
    def end_active_controller_except(cls, controller: "_NumericEditController | None") -> None:
        """End any active numeric text edit controller except ``controller``."""
        active_controller = cls.active_controller
        if active_controller is None or active_controller is controller:
            return
        if active_controller._destroyed:  # noqa: SLF001 - same-class active controller lifecycle.
            cls.active_controller = None
            return
        active_controller._transfer_key_active = False  # noqa: SLF001 - same-class active controller lifecycle.
        active_controller._end_edit()  # noqa: SLF001 - same-class active controller lifecycle.

    def _clear_active_controller(self) -> None:
        """Clear the active controller when this controller owns it."""
        if type(self).active_controller is self:
            type(self).active_controller = None

    def refocus(self) -> None:
        if not self._editing:
            return
        self._expression_field.visible = True
        self._expression_field.selected = True
        self._expression_field.focus_keyboard(True)

    def _set_expression_value(self, value: str) -> None:
        self._updating = True
        try:
            self._expression_model.set_value(value)
        finally:
            self._updating = False

    def focus(
        self, *, clear_value: bool = True, from_tab_transfer: bool = False, begin_undo_group: bool = True
    ) -> None:
        if self._destroyed:
            return
        if not from_tab_transfer:
            type(self).end_active_controller_except(self)
        self._transfer_key_active = from_tab_transfer
        self._initial_value = self._value_model.get_value()
        if clear_value:
            expression_value = ""
        else:
            expression_value = self._value_model.get_value_as_string()
        self._expression_field.visible = True
        self._expression_field.enabled = True
        self._begin_edit(begin_undo_group=begin_undo_group)
        self._drag_widget.enabled = False
        self._set_expression_value(expression_value)
        self._replace_expression_text = True
        type(self).active_controller = self
        self.refocus()

    def begin_text_edit(self, _x, _y, button, _modifier) -> bool:
        if self._destroyed:
            return False
        if button != 0:
            return False
        self.focus(clear_value=False)
        return True

    def _apply_expression(self, model) -> None:
        if self._updating:
            return
        self._transfer_key_active = False
        self._applying = True
        try:
            self._drag_widget.set_numeric_expression_value(self._value_model, model.get_value_as_string())
        finally:
            self._applying = False

    def _sync_expression_from_target(self, _model) -> None:
        if not self._editing or self._applying:
            return
        self._set_expression_value(self._value_model.get_value_as_string())
        self.refocus()

    def begin_deferred_undo_group(self) -> None:
        if self._editing and self._value_model.supports_batch_edit and not self._undo_group_open:
            omni.kit.undo.begin_group()
            self._undo_group_open = True

    def _begin_edit(self, _model=None, *, begin_undo_group: bool = True) -> None:
        if not self._expression_field.visible:
            return
        if self._editing:
            return
        self._editing = True
        self._start_keyboard_subscription()
        edit_started = False
        try:
            self._value_model.begin_edit()
            edit_started = True
            if begin_undo_group:
                self.begin_deferred_undo_group()
        except Exception:
            self._transfer_key_active = False
            self._editing = False
            if edit_started:
                with suppress(Exception):
                    self._value_model.end_edit()
            self._expression_field.visible = False
            self._drag_widget.enabled = True
            if self._undo_group_open:
                self._undo_group_open = False
                omni.kit.undo.end_group()
            self._stop_keyboard_subscription()
            raise

    def _end_edit(self, _model=None, *, commit: bool = True) -> None:
        if self._transfer_key_active and self._editing:
            self.refocus()
            return
        self._transfer_key_active = False
        self._expression_field.visible = False
        self._expression_field.enabled = False
        self._drag_widget.enabled = True
        if not self._editing:
            return
        self._editing = False
        try:
            if not commit:
                self._value_model.set_value(self._initial_value)
        finally:
            try:
                self._value_model.end_edit()
            finally:
                self._initial_value = None
                if self._undo_group_open:
                    self._undo_group_open = False
                    omni.kit.undo.end_group()
                self._stop_keyboard_subscription()
                self._clear_active_controller()

    def _on_key_pressed(self, key, modifier, down) -> bool:
        del modifier
        if key == _TAB_KEY:
            return len(self._edit_widgets) > 1 and self._index in self._edit_widgets
        if key in _END_KEYS or key in _STEP_KEYS:
            return True
        if down:
            self._transfer_key_active = False
        return False

    def _set_expression_from_keyboard(self, text: str) -> None:
        self._transfer_key_active = False
        self._replace_expression_text = False
        self._expression_model.set_value(text)

    def _append_expression_text(self, text: str) -> bool:
        if not text or any(character not in _PENDING_EXPRESSION_CHARS for character in text):
            return False
        if self._replace_expression_text:
            self._set_expression_from_keyboard(text)
            return True
        self._set_expression_from_keyboard(self._expression_model.get_value_as_string() + text)
        return True

    def _backspace_expression_character(self) -> bool:
        if self._replace_expression_text:
            self._set_expression_from_keyboard("")
            return True
        self._set_expression_from_keyboard(self._expression_model.get_value_as_string()[:-1])
        return True

    def _on_keyboard_event(self, event: carb.input.KeyboardEvent) -> bool:
        if event.type == carb.input.KeyboardEventType.CHAR:
            if isinstance(event.input, str):
                return self._append_expression_text(event.input)
            try:
                return self._append_expression_text(chr(int(event.input)))
            except (OverflowError, TypeError, ValueError):
                return False
        if event.type not in (
            carb.input.KeyboardEventType.KEY_PRESS,
            carb.input.KeyboardEventType.KEY_RELEASE,
            carb.input.KeyboardEventType.KEY_REPEAT,
        ):
            return False
        key = int(event.input)
        if key == _BACKSPACE_KEY and event.type in (
            carb.input.KeyboardEventType.KEY_PRESS,
            carb.input.KeyboardEventType.KEY_REPEAT,
        ):
            return self._backspace_expression_character()
        if key not in _STEP_KEYS and key not in _END_KEYS and key != _TAB_KEY:
            if event.type == carb.input.KeyboardEventType.KEY_PRESS:
                self._transfer_key_active = False
            return False
        if event.type == carb.input.KeyboardEventType.KEY_REPEAT and key not in _STEP_KEYS:
            return True
        if event.type == carb.input.KeyboardEventType.KEY_RELEASE:
            if key == _TAB_KEY and self._transfer_key_active:
                self._transfer_key_active = False
                self.refocus()
            return True
        if key in _END_KEYS:
            self._end_edit(commit=key != _ESCAPE_KEY)
            return True
        if key == _TAB_KEY:
            return self._transfer_to_next(event.modifiers)
        self._drag_widget.step_keyboard_value(self._value_model, key, self._expression_model.get_value_as_string())
        self._set_expression_value(self._value_model.get_value_as_string())
        self.refocus()
        return True

    def _on_input_event(self, event: carb.input.InputEvent) -> bool:
        if event.deviceType == carb.input.DeviceType.KEYBOARD:
            return self._on_keyboard_event(cast(carb.input.KeyboardEvent, event.event))
        return False

    def _start_keyboard_subscription(self) -> None:
        if self._keyboard_subscription is not None:
            return
        app_window = omni.appwindow.get_default_app_window()
        if app_window is None:
            return
        keyboard = app_window.get_keyboard()
        if keyboard is None:
            return
        self._keyboard_subscription = carb.input.acquire_input_interface().subscribe_to_input_events(
            self._on_input_event, device=keyboard, order=0
        )

    def _stop_keyboard_subscription(self) -> None:
        if self._keyboard_subscription is None:
            return
        with suppress(RuntimeError):
            carb.input.acquire_input_interface().unsubscribe_to_input_events(self._keyboard_subscription)
        self._keyboard_subscription = None

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        with suppress(RuntimeError):
            self._drag_widget.set_mouse_double_clicked_fn(None)
        try:
            if self._editing:
                self._transfer_key_active = False
                self._end_edit(commit=False)
        finally:
            cancel_subscription = self._cancel_subscription
            self._cancel_subscription = None
            if cancel_subscription is not None:
                cancel_subscription()
            self._transfer_key_active = False
            self._expression_field.visible = False
            self._expression_field.enabled = False
            self._drag_widget.enabled = True
            if self._undo_group_open:
                self._undo_group_open = False
                omni.kit.undo.end_group()
            self._subs.clear()
            self._stop_keyboard_subscription()
            self._clear_active_controller()
            with suppress(RuntimeError):
                self._expression_field.destroy()

    def _cancel_edit(self) -> None:
        try:
            if self._editing:
                self._transfer_key_active = False
                self._end_edit(commit=False)
        finally:
            self.destroy()

    def _transfer_to_next(self, modifier: int) -> bool:
        if len(self._edit_widgets) <= 1:
            return False
        direction = -1 if bool(int(modifier) & int(carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT)) else 1
        widget_indices = sorted(self._edit_widgets)
        if self._index not in self._edit_widgets:
            return False
        current_position = widget_indices.index(self._index)
        target_position = (current_position + direction) % len(widget_indices)
        target_index = widget_indices[target_position]
        target_widget = self._edit_widgets.get(target_index)
        if target_widget is None:
            return False
        target_widget.begin_numeric_text_edit(clear_value=False, from_tab_transfer=True, begin_undo_group=False)
        try:
            self._end_edit()
        finally:
            target_widget.begin_deferred_numeric_undo_group()
        return True

    def __del__(self):
        with suppress(Exception):
            self.destroy()


class _BoundedNumericDragBase:
    """Shared hard-limit and numeric-edit behavior for drag widgets.

    Why this exists:
        ``omni.ui`` drag widgets expose soft ``min``/``max`` for drag interaction,
        but typed values can bypass those bounds. This mixin attaches a model
        pre-set callback that clamps any numeric input to optional hard bounds.
        It also owns the shared expression editing and Arrow Up/Down stepping
        behavior used by float and int bounded drags.
    """

    _DEFAULT_KEYBOARD_STEP = 0.1
    _NUMERIC_VALUE_TYPE: type[float] | type[int] | None = None
    _KEYBOARD_STEP_VALUE_TYPE: type[float] | type[int] | None = None
    _MIN_KEYBOARD_STEP: float | int | None = None

    def __init__(
        self,
        *args,
        hard_min_value: float | int | None = None,
        hard_max_value: float | int | None = None,
        enable_batch_edit: bool = True,
        enable_numeric_edit: bool = True,
        **kwargs,
    ):
        read_only = bool(kwargs.get("read_only", False))
        style_type_name_override = kwargs.get("style_type_name_override", "")
        self._apply_hard_bounds_to_missing_drag_bounds(kwargs, hard_min_value, hard_max_value)
        super().__init__(*args, **kwargs)
        self._hard_min_value: float | int | None = None
        self._hard_max_value: float | int | None = None
        self._enable_batch_edit = enable_batch_edit
        self._mouse_pressed = False
        self._pending_numeric_text_edit_from_mouse_press = False
        self._numeric_edit_controller: _NumericEditController | None = None

        if self._enable_batch_edit or (enable_numeric_edit and not read_only):
            self._install_mouse_callbacks()
        self.set_hard_limits(hard_min_value, hard_max_value)
        if enable_numeric_edit and not read_only:
            widget = cast(_DragWidgetProtocol, self)
            self._numeric_edit_controller = _NumericEditController(
                value_model=widget.model,
                drag_widget=widget,
                style_type_name_override=style_type_name_override,
            )

    @property
    def hard_min_value(self) -> float | int | None:
        """Lower hard clamp bound."""
        return self._hard_min_value

    @hard_min_value.setter
    def hard_min_value(self, value: float | int | None) -> None:
        self._hard_min_value = value if isinstance(value, (int, float)) else None
        self._sync_hard_clamp_callback()

    @property
    def hard_max_value(self) -> float | int | None:
        """Upper hard clamp bound."""
        return self._hard_max_value

    @hard_max_value.setter
    def hard_max_value(self, value: float | int | None) -> None:
        self._hard_max_value = value if isinstance(value, (int, float)) else None
        self._sync_hard_clamp_callback()

    def set_hard_limits(self, hard_min_value: float | int | None, hard_max_value: float | int | None) -> None:
        """Set hard bounds and refresh model callback."""
        self._hard_min_value = hard_min_value if isinstance(hard_min_value, (int, float)) else None
        self._hard_max_value = hard_max_value if isinstance(hard_max_value, (int, float)) else None
        self._sync_hard_clamp_callback()

    @staticmethod
    def _apply_hard_bounds_to_missing_drag_bounds(
        kwargs: dict[str, Any], hard_min_value: float | int | None, hard_max_value: float | int | None
    ) -> None:
        """Use hard bounds as drag bounds when the matching soft side is omitted."""
        has_soft_min = kwargs.get("min") is not None
        has_soft_max = kwargs.get("max") is not None
        has_hard_min = isinstance(hard_min_value, (int, float))
        has_hard_max = isinstance(hard_max_value, (int, float))
        should_fill_min = not has_soft_min and has_hard_min
        should_fill_max = not has_soft_max and has_hard_max
        if not should_fill_min and not should_fill_max:
            return

        drag_min = hard_min_value if should_fill_min else kwargs.get("min")
        drag_max = hard_max_value if should_fill_max else kwargs.get("max")
        if isinstance(drag_min, (int, float)) and isinstance(drag_max, (int, float)) and drag_min >= drag_max:
            carb.log_warn(f"Drag bounds ignored: min ({drag_min}) must be less than max ({drag_max}).")
            return

        if should_fill_min:
            kwargs["min"] = hard_min_value
        if should_fill_max:
            kwargs["max"] = hard_max_value

    def _sync_hard_clamp_callback(self) -> None:
        """Install hard-clamp pre-set callback on the widget model."""
        # Cast narrows ``self`` (a mixin instance) to the concrete widget contract
        # so static analysis can validate direct model/callback member access.
        widget = cast(_DragWidgetProtocol, self)
        model = widget.model
        hard_min, hard_max = self._validate_hard_bounds()
        has_batch_behavior = self._enable_batch_edit and self._supports_batch_edit(model)

        def _clamp(set_fn, value):
            if has_batch_behavior and self._mouse_pressed and not model.is_batch_editing:
                model.begin_batch_edit()
            try:
                value = self._coerce_and_clamp_numeric_value(value, hard_min, hard_max)
            except (OverflowError, ValueError):
                return
            set_fn(value)

        model.set_callback_pre_set_value(_clamp)

    @staticmethod
    def _is_potential_numeric_expression(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        stripped_value = value.strip()
        return bool(stripped_value) and all(char in _PENDING_EXPRESSION_CHARS for char in stripped_value)

    def _validate_hard_bounds(self) -> tuple[float | int | None, float | int | None]:
        """Validate hard-bounds ordering and normalize invalid combinations."""
        hard_min = self._hard_min_value
        hard_max = self._hard_max_value
        if hard_min is not None and hard_max is not None and hard_min >= hard_max:
            carb.log_warn(f"Hard bounds ignored: hard_min ({hard_min}) must be less than hard_max ({hard_max}).")
            return None, None
        return hard_min, hard_max

    @classmethod
    def _clamp_numeric_value(cls, value: Any, hard_min: float | int | None, hard_max: float | int | None) -> Any:
        """Clamp numeric values while preserving original numeric type.

        Non-numeric values are passed through unchanged.
        """
        if not isinstance(value, (int, float)):
            return value
        clamped = value
        if hard_min is not None and clamped < hard_min:
            clamped = hard_min
        if hard_max is not None and clamped > hard_max:
            clamped = hard_max
        return type(value)(clamped)

    def _supports_batch_edit(self, model) -> bool:
        """Return True when model exposes batch-edit hooks used by drag interactions.

        If the attached model does not provide ``supports_batch_edit``, this
        returns False and logs a warning instructing callers to either disable
        batch-edit mode or provide a batch-edit-capable model.
        """
        try:
            return bool(model.supports_batch_edit)
        except AttributeError:
            carb.log_warn(
                "Batch edit requested for drag widget, but attached model does not expose "
                "'supports_batch_edit'. Set enable_batch_edit=False or provide a batch-edit-capable model."
            )
            return False

    def _parse_numeric_value(self, value: Any) -> Any:
        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                raise ValueError(f"Empty numeric value: {value}")
            if not any(char.isdigit() for char in stripped_value):
                if self._is_potential_numeric_expression(value):
                    raise ValueError(f"Incomplete numeric expression: {value}")
                raise ValueError(f"Invalid numeric value: {value}")
            return _safe_eval_numeric_expression(stripped_value)
        return value

    def _coerce_numeric_value(self, value: Any) -> Any:
        numeric_type = self._NUMERIC_VALUE_TYPE
        if numeric_type is None or not isinstance(value, (int, float)) or isinstance(value, bool):
            return value
        if numeric_type is int and isinstance(value, float) and not value.is_integer():
            raise ValueError(f"Non-integer value not allowed for {type(self).__name__}: {value}")
        return numeric_type(value)

    def _coerce_and_clamp_numeric_value(
        self, value: Any, hard_min: float | int | None, hard_max: float | int | None
    ) -> Any:
        value = self._coerce_numeric_value(self._parse_numeric_value(value))
        return self._coerce_numeric_value(self._clamp_numeric_value(value, hard_min, hard_max))

    def _get_keyboard_base_value(self, model: _DragModelProtocol, expression: str | None = None) -> float | int:
        if expression is not None:
            try:
                return self._coerce_numeric_value(_safe_eval_numeric_expression(expression))
            except (OverflowError, ValueError):
                pass
        try:
            return self._coerce_numeric_value(_safe_eval_numeric_expression(model.get_value_as_string()))
        except (OverflowError, ValueError):
            return self._coerce_numeric_value(model.get_value_as_float())

    def _get_keyboard_step(self) -> float | int:
        widget = cast(_DragWidgetProtocol, self)
        step = widget.step
        if isinstance(step, (int, float)):
            step = abs(step)
        else:
            step = self._DEFAULT_KEYBOARD_STEP
        min_step = self._MIN_KEYBOARD_STEP
        if min_step is not None:
            step = max(min_step, step)
        step_type = self._KEYBOARD_STEP_VALUE_TYPE
        return step_type(step) if step_type is not None else step

    @staticmethod
    def _calculate_keyboard_step_value(value: Decimal | float | int, step: float | int, direction: int) -> float | int:
        if not step:
            return value
        if isinstance(value, int) and isinstance(step, int):
            return value + (direction * step)
        step_decimal = Decimal(str(abs(step)))
        value_decimal = Decimal(str(value))
        step_exponent = min(step_decimal.as_tuple().exponent, 0)
        snapped_value = _BoundedNumericDragBase._quantize_decimal(value_decimal, step_exponent)
        if abs(value_decimal - snapped_value) <= _STEP_GRID_TOLERANCE:
            value_decimal = snapped_value
        stepped_value = value_decimal + (step_decimal * Decimal(direction))
        exponent = min(value_decimal.as_tuple().exponent, step_exponent, 0)
        return float(_BoundedNumericDragBase._quantize_decimal(stepped_value, exponent))

    @staticmethod
    def _quantize_decimal(value: Decimal, exponent: int) -> Decimal:
        with localcontext() as context:
            context.prec = max(28, len(value.as_tuple().digits), value.adjusted() - exponent + 1)
            return value.quantize(Decimal(1).scaleb(exponent))

    def step_keyboard_value(self, model, key: int, expression: str | None = None) -> None:
        if key not in _KEYBOARD_STEP_DIRECTIONS:
            return
        hard_min, hard_max = self._validate_hard_bounds()
        value = self._calculate_keyboard_step_value(
            self._get_keyboard_base_value(model, expression),
            self._get_keyboard_step(),
            _KEYBOARD_STEP_DIRECTIONS[key],
        )
        value = self._coerce_numeric_value(self._clamp_numeric_value(value, hard_min, hard_max))
        model.set_value(value)

    def set_numeric_expression_value(self, model, expression: str) -> None:
        hard_min, hard_max = self._validate_hard_bounds()
        try:
            value = self._coerce_and_clamp_numeric_value(expression, hard_min, hard_max)
        except (OverflowError, ValueError):
            return
        model.set_value(value)

    def set_numeric_edit_widgets(self, widgets: dict[int, _DragWidgetProtocol], index: int) -> None:
        if self._numeric_edit_controller is not None:
            self._numeric_edit_controller.set_edit_widgets(widgets, index)

    def begin_numeric_text_edit(
        self, *, clear_value: bool = True, from_tab_transfer: bool = False, begin_undo_group: bool = True
    ) -> None:
        if self._numeric_edit_controller is not None:
            self._numeric_edit_controller.focus(
                clear_value=clear_value,
                from_tab_transfer=from_tab_transfer,
                begin_undo_group=begin_undo_group,
            )

    def begin_deferred_numeric_undo_group(self) -> None:
        if self._numeric_edit_controller is not None:
            self._numeric_edit_controller.begin_deferred_undo_group()

    def _install_mouse_callbacks(self) -> None:
        """Install mouse handlers that drive drag and numeric-edit lifecycles."""
        # Cast narrows ``self`` to the concrete widget contract for static typing.
        widget = cast(_DragWidgetProtocol, self)

        def _on_mouse_pressed(_x, _y, button, modifier):
            if button != 0:
                return
            has_control_modifier = bool(int(modifier) & _CONTROL_MODIFIER_FLAG)
            self._pending_numeric_text_edit_from_mouse_press = (
                self._numeric_edit_controller is not None and has_control_modifier
            )
            _NumericEditController.end_active_controller_except(self._numeric_edit_controller)
            self._mouse_pressed = not self._pending_numeric_text_edit_from_mouse_press

        def _on_mouse_released(_x, _y, button, _m):
            if button != 0:
                return
            pending_numeric_text_edit = self._pending_numeric_text_edit_from_mouse_press
            self._pending_numeric_text_edit_from_mouse_press = False
            self._mouse_pressed = False
            if pending_numeric_text_edit:
                self.begin_numeric_text_edit(clear_value=False)
                return
            if not self._enable_batch_edit:
                return
            model = widget.model
            if not self._supports_batch_edit(model):
                return
            if model.is_batch_editing:
                model.end_batch_edit()

        widget.set_mouse_pressed_fn(_on_mouse_pressed)
        widget.set_mouse_released_fn(_on_mouse_released)

    def _cleanup_registered_callbacks(self) -> None:
        """Best-effort callback cleanup to break widget/model reference cycles."""
        # Cast narrows ``self`` to the concrete widget contract for static typing.
        widget = cast(_DragWidgetProtocol, self)
        widget.model.set_callback_pre_set_value(None)
        widget.set_mouse_pressed_fn(None)
        widget.set_mouse_released_fn(None)

    def _end_batch_edit_if_needed(self) -> None:
        widget = cast(_DragWidgetProtocol, self)
        model = widget.model
        self._pending_numeric_text_edit_from_mouse_press = False
        self._mouse_pressed = False
        if self._enable_batch_edit and self._supports_batch_edit(model) and model.is_batch_editing:
            model.end_batch_edit()

    def destroy(self) -> None:
        if self._numeric_edit_controller is not None:
            self._numeric_edit_controller.destroy()
            self._numeric_edit_controller = None
        self._end_batch_edit_if_needed()
        self._cleanup_registered_callbacks()
        super().destroy()

    def __del__(self):
        """Clear callbacks on object teardown.

        This keeps teardown robust even if native/UI lifetimes delay Python GC,
        and avoids leaving closures registered on external model/widget objects.
        """
        with suppress(Exception):
            if self._numeric_edit_controller is not None:
                self._numeric_edit_controller.destroy()
                self._numeric_edit_controller = None
            self._end_batch_edit_if_needed()
            self._cleanup_registered_callbacks()


class FloatBoundedDrag(_BoundedNumericDragBase, ui.FloatDrag):
    """Float drag widget with optional hard-clamp behavior."""

    _NUMERIC_VALUE_TYPE = float
    _KEYBOARD_STEP_VALUE_TYPE = float


class IntBoundedDrag(_BoundedNumericDragBase, ui.IntDrag):
    """Int drag widget with optional hard-clamp behavior."""

    _DEFAULT_KEYBOARD_STEP = 1
    _NUMERIC_VALUE_TYPE = int
    _KEYBOARD_STEP_VALUE_TYPE = int
    _MIN_KEYBOARD_STEP = 1

    @classmethod
    def _clamp_numeric_value(cls, value: Any, hard_min: float | int | None, hard_max: float | int | None) -> Any:
        """Clamp ``IntBoundedDrag`` values in integer domain.

        Float hard bounds are normalized before clamping using:
        - ``ceil`` for minimum bounds
        - ``floor`` for maximum bounds
        """
        if isinstance(hard_min, float):
            hard_min = math.ceil(hard_min)
        if isinstance(hard_max, float):
            hard_max = math.floor(hard_max)
        if hard_min is not None and hard_max is not None and hard_min > hard_max:
            carb.log_warn(
                "IntBoundedDrag hard bounds ignored after integer normalization: "
                f"hard_min ({hard_min}) must be <= hard_max ({hard_max})."
            )
            hard_min = None
            hard_max = None

        result = super()._clamp_numeric_value(value, hard_min, hard_max)
        return int(result) if isinstance(result, (int, float)) else result

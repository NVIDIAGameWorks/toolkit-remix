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

import math
from contextlib import suppress
from typing import Any, Protocol, cast

import carb
import omni.ui as ui


class _DragModelProtocol(Protocol):
    """Static typing contract for drag widget value models."""

    supports_batch_edit: bool
    is_batch_editing: bool

    def begin_batch_edit(self) -> None: ...
    def end_batch_edit(self) -> None: ...
    def set_callback_pre_set_value(self, callback: Any) -> None: ...
    def subscribe_begin_edit_fn(self, callback: Any) -> Any: ...
    def subscribe_end_edit_fn(self, callback: Any) -> Any: ...


class _DragWidgetProtocol(Protocol):
    """Static typing contract for widgets that host ``_BoundedNumericDragBase``."""

    model: _DragModelProtocol

    def set_mouse_pressed_fn(self, callback: Any) -> None: ...
    def set_mouse_released_fn(self, callback: Any) -> None: ...


class _BoundedNumericDragBase:
    """Shared hard-limit and batch-edit behavior for drag widgets.

    ``omni.ui`` drag widgets expose soft ``min``/``max`` for drag interaction,
    but typed values can bypass those bounds. This base attaches a model pre-set
    callback that clamps numeric values to optional hard bounds without owning
    custom text editing or expression parsing.
    """

    _NUMERIC_VALUE_TYPE: type[float] | type[int] | None = None

    def __init__(
        self,
        *args,
        hard_min_value: float | int | None = None,
        hard_max_value: float | int | None = None,
        enable_batch_edit: bool = True,
        **kwargs,
    ):
        self._apply_hard_bounds_to_missing_drag_bounds(kwargs, hard_min_value, hard_max_value)
        super().__init__(*args, **kwargs)
        self._hard_min_value: float | int | None = None
        self._hard_max_value: float | int | None = None
        self._enable_batch_edit = enable_batch_edit
        self._mouse_pressed = False
        self._model_editing = False
        self._model_edit_subs: list[Any] = []

        if self._enable_batch_edit:
            self._install_batch_mouse_callbacks()
            self._install_batch_model_callbacks()
        self.set_hard_limits(hard_min_value, hard_max_value)

    @property
    def hard_min_value(self) -> float | int | None:
        """Lower hard clamp bound."""
        return self._hard_min_value

    @hard_min_value.setter
    def hard_min_value(self, value: float | int | None) -> None:
        self._hard_min_value = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        self._sync_hard_clamp_callback()

    @property
    def hard_max_value(self) -> float | int | None:
        """Upper hard clamp bound."""
        return self._hard_max_value

    @hard_max_value.setter
    def hard_max_value(self, value: float | int | None) -> None:
        self._hard_max_value = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        self._sync_hard_clamp_callback()

    def set_hard_limits(self, hard_min_value: float | int | None, hard_max_value: float | int | None) -> None:
        """Set hard bounds and refresh model callback."""
        self._hard_min_value = (
            hard_min_value
            if isinstance(hard_min_value, (int, float)) and not isinstance(hard_min_value, bool)
            else None
        )
        self._hard_max_value = (
            hard_max_value
            if isinstance(hard_max_value, (int, float)) and not isinstance(hard_max_value, bool)
            else None
        )
        self._sync_hard_clamp_callback()

    @staticmethod
    def _apply_hard_bounds_to_missing_drag_bounds(
        kwargs: dict[str, Any], hard_min_value: float | int | None, hard_max_value: float | int | None
    ) -> None:
        """Use hard bounds as drag bounds when the matching soft side is omitted."""
        has_soft_min = kwargs.get("min") is not None
        has_soft_max = kwargs.get("max") is not None
        has_hard_min = isinstance(hard_min_value, (int, float)) and not isinstance(hard_min_value, bool)
        has_hard_max = isinstance(hard_max_value, (int, float)) and not isinstance(hard_max_value, bool)
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
        widget = cast(_DragWidgetProtocol, self)
        model = widget.model
        hard_min, hard_max = self._validate_hard_bounds()
        has_batch_behavior = self._enable_batch_edit and self._supports_batch_edit(model)

        def _clamp(set_fn, value):
            is_interactive_edit = self._mouse_pressed or self._model_editing
            if has_batch_behavior and is_interactive_edit and not model.is_batch_editing:
                model.begin_batch_edit()
            try:
                value = self._coerce_and_clamp_numeric_value(value, hard_min, hard_max)
            except (OverflowError, TypeError, ValueError):
                return
            set_fn(value)

        model.set_callback_pre_set_value(_clamp)

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
        """Clamp numeric values while preserving original numeric type."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return value
        clamped = value
        if hard_min is not None and clamped < hard_min:
            clamped = hard_min
        if hard_max is not None and clamped > hard_max:
            clamped = hard_max
        return type(value)(clamped)

    def _supports_batch_edit(self, model) -> bool:
        """Return True when model exposes batch-edit hooks used by drag interactions."""
        try:
            return bool(model.supports_batch_edit)
        except AttributeError:
            carb.log_warn(
                "Batch edit requested for drag widget, but attached model does not expose "
                "'supports_batch_edit'. Set enable_batch_edit=False or provide a batch-edit-capable model."
            )
            return False

    def _coerce_numeric_value(self, value: Any) -> Any:
        numeric_type = self._NUMERIC_VALUE_TYPE
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"Invalid numeric value for {type(self).__name__}: {value!r}")
        if numeric_type is None:
            return value
        if numeric_type is int and isinstance(value, float) and not value.is_integer():
            raise ValueError(f"Non-integer value not allowed for {type(self).__name__}: {value}")
        value = numeric_type(value)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Non-finite numeric value for {type(self).__name__}: {value}")
        return value

    def _coerce_and_clamp_numeric_value(
        self, value: Any, hard_min: float | int | None, hard_max: float | int | None
    ) -> Any:
        value = self._coerce_numeric_value(value)
        return self._coerce_numeric_value(self._clamp_numeric_value(value, hard_min, hard_max))

    def _install_batch_mouse_callbacks(self) -> None:
        """Install mouse handlers that drive drag batch-edit lifecycle."""
        widget = cast(_DragWidgetProtocol, self)

        def _on_mouse_pressed(_x, _y, button, _m):
            if button == 0:
                self._mouse_pressed = True

        def _on_mouse_released(_x, _y, button, _m):
            if button != 0:
                return
            self._mouse_pressed = False
            model = widget.model
            if self._supports_batch_edit(model) and model.is_batch_editing:
                model.end_batch_edit()

        widget.set_mouse_pressed_fn(_on_mouse_pressed)
        widget.set_mouse_released_fn(_on_mouse_released)

    def _install_batch_model_callbacks(self) -> None:
        """Track native model edit state when widget mouse callbacks are skipped."""
        widget = cast(_DragWidgetProtocol, self)
        begin_subscribe = getattr(widget.model, "subscribe_begin_edit_fn", None)
        end_subscribe = getattr(widget.model, "subscribe_end_edit_fn", None)
        if not callable(begin_subscribe) or not callable(end_subscribe):
            return
        self._model_edit_subs.extend(
            (
                begin_subscribe(self._on_model_begin_edit),
                end_subscribe(self._on_model_end_edit),
            )
        )

    def _on_model_begin_edit(self, _model: Any = None) -> None:
        """Mark native widget model edits as active."""
        del _model
        self._model_editing = True

    def _on_model_end_edit(self, _model: Any = None) -> None:
        """Clear native widget model edit state."""
        del _model
        self._model_editing = False

    def _cleanup_registered_callbacks(self) -> None:
        """Best-effort callback cleanup to break widget/model reference cycles."""
        widget = cast(_DragWidgetProtocol, self)
        widget.model.set_callback_pre_set_value(None)
        widget.set_mouse_pressed_fn(None)
        widget.set_mouse_released_fn(None)
        self._model_edit_subs.clear()

    def _end_batch_edit_if_needed(self) -> None:
        widget = cast(_DragWidgetProtocol, self)
        model = widget.model
        self._model_editing = False
        self._mouse_pressed = False
        if self._enable_batch_edit and self._supports_batch_edit(model) and model.is_batch_editing:
            model.end_batch_edit()

    def destroy(self) -> None:
        self._end_batch_edit_if_needed()
        self._cleanup_registered_callbacks()
        super().destroy()

    def __del__(self):
        """Clear callbacks on object teardown."""
        with suppress(Exception):
            self._end_batch_edit_if_needed()
            self._cleanup_registered_callbacks()


class FloatBoundedDrag(_BoundedNumericDragBase, ui.FloatDrag):
    """Float drag widget with optional hard-clamp behavior."""

    _NUMERIC_VALUE_TYPE = float


class IntBoundedDrag(_BoundedNumericDragBase, ui.IntDrag):
    """Int drag widget with optional hard-clamp behavior."""

    _NUMERIC_VALUE_TYPE = int

    @classmethod
    def _clamp_numeric_value(cls, value: Any, hard_min: float | int | None, hard_max: float | int | None) -> Any:
        """Clamp ``IntBoundedDrag`` values in integer domain."""
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
        return int(result) if isinstance(result, (int, float)) and not isinstance(result, bool) else result

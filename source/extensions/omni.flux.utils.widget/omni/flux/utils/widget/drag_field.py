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

from contextlib import suppress
from typing import Any, Protocol, cast
import math
import carb
import omni.ui as ui


class _DragModelProtocol(Protocol):
    """Static typing contract for drag widget value models.

    Why this exists:
        ``_HardLimitDragMixin`` is reused by concrete UI drag widgets, but the
        mixin itself does not declare model APIs like ``set_callback_pre_set_value``
        or batch-edit hooks. This protocol documents the required model surface
        so static type checkers can validate direct attribute access.
    """

    supports_batch_edit: bool
    is_batch_editing: bool

    def begin_batch_edit(self) -> None: ...
    def end_batch_edit(self) -> None: ...
    def set_callback_pre_set_value(self, callback: Any) -> None: ...


class _DragWidgetProtocol(Protocol):
    """Static typing contract for widgets that host ``_HardLimitDragMixin``.

    Why this exists:
        The mixin assumes concrete drag widgets provide a ``model`` plus mouse
        callback registration APIs. We intentionally use direct calls (instead of
        ``getattr``/``hasattr``), so this protocol captures that required widget
        interface for lint/type-check correctness.
    """

    model: _DragModelProtocol

    def set_mouse_pressed_fn(self, callback: Any) -> None: ...
    def set_mouse_released_fn(self, callback: Any) -> None: ...


class _HardLimitDragMixin:
    """Shared hard-limit behavior for drag widgets.

    Why this exists:
        ``omni.ui`` drag widgets expose soft ``min``/``max`` for drag interaction,
        but typed values can bypass those bounds. This mixin attaches a model
        pre-set callback that clamps any numeric input to optional hard bounds.
    """

    def __init__(
        self,
        *args,
        hard_min_value: float | int | None = None,
        hard_max_value: float | int | None = None,
        enable_batch_edit: bool = True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._hard_min_value: float | int | None = None
        self._hard_max_value: float | int | None = None
        self._enable_batch_edit = enable_batch_edit
        self._drag_state = {"mouse_pressed": False}

        if self._enable_batch_edit:
            self._install_batch_mouse_callbacks()
        self.set_hard_limits(hard_min_value, hard_max_value)

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

    def _sync_hard_clamp_callback(self) -> None:
        """Install hard-clamp pre-set callback on the widget model."""
        # Cast narrows ``self`` (a mixin instance) to the concrete widget contract
        # so static analysis can validate direct model/callback member access.
        widget = cast(_DragWidgetProtocol, self)
        model = widget.model
        hard_min, hard_max = self._validate_hard_bounds()
        has_hard_limits = hard_min is not None or hard_max is not None
        has_batch_behavior = self._enable_batch_edit and self._supports_batch_edit(model)
        if not has_hard_limits and not has_batch_behavior:
            model.set_callback_pre_set_value(None)
            return

        def _clamp(set_fn, value):
            if has_batch_behavior and self._drag_state["mouse_pressed"] and not model.is_batch_editing:
                model.begin_batch_edit()
            value = self._clamp_numeric_value(value, hard_min, hard_max)
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

    @staticmethod
    def _clamp_numeric_value(value: Any, hard_min: float | int | None, hard_max: float | int | None) -> Any:
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

    def _install_batch_mouse_callbacks(self) -> None:
        """Install mouse handlers that drive drag batch-edit lifecycle."""
        # Cast narrows ``self`` to the concrete widget contract for static typing.
        widget = cast(_DragWidgetProtocol, self)

        def _on_mouse_pressed(_x, _y, button, _m):
            if button == 0:
                self._drag_state["mouse_pressed"] = True

        def _on_mouse_released(_x, _y, button, _m):
            self._drag_state["mouse_pressed"] = False
            if button != 0:
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

    def __del__(self):
        """Clear callbacks on object teardown.

        This keeps teardown robust even if native/UI lifetimes delay Python GC,
        and avoids leaving closures registered on external model/widget objects.
        """
        with suppress(Exception):
            self._cleanup_registered_callbacks()


class FloatBoundedDrag(_HardLimitDragMixin, ui.FloatDrag):
    """Float drag widget with optional hard-clamp behavior."""

    def __init__(
        self,
        *args,
        hard_min_value: float | int | None = None,
        hard_max_value: float | int | None = None,
        enable_batch_edit: bool = True,
        **kwargs,
    ):
        super().__init__(
            *args,
            hard_min_value=hard_min_value,
            hard_max_value=hard_max_value,
            enable_batch_edit=enable_batch_edit,
            **kwargs,
        )


class IntBoundedDrag(_HardLimitDragMixin, ui.IntDrag):
    """Int drag widget with optional hard-clamp behavior."""

    def __init__(
        self,
        *args,
        hard_min_value: int | None = None,
        hard_max_value: int | None = None,
        enable_batch_edit: bool = True,
        **kwargs,
    ):
        super().__init__(
            *args,
            hard_min_value=hard_min_value,
            hard_max_value=hard_max_value,
            enable_batch_edit=enable_batch_edit,
            **kwargs,
        )

    @staticmethod
    def _clamp_numeric_value(value: Any, hard_min: float | int | None, hard_max: float | int | None) -> Any:
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

        result = super(IntBoundedDrag, IntBoundedDrag)._clamp_numeric_value(value, hard_min, hard_max)
        return int(result) if isinstance(result, (int, float)) else result

"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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


__all__ = ("AbstractDragFieldGroup", "AbstractField", "BoundsValue", "RealNumber")

import abc
from typing import TYPE_CHECKING, Generic, Protocol, TypeAlias, TypeVar, cast, overload

import carb
import omni.kit.undo
import omni.ui as ui


if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item
    from omni.flux.property_widget_builder.widget.tree.item_model import ItemModelBase


ItemT = TypeVar("ItemT", bound="Item")
RealNumber: TypeAlias = int | float


class _BoundsSequenceLike(Protocol):
    """Indexable bounds payload contract for per-channel scalar extraction."""

    def __getitem__(self, index: int) -> object: ...


BoundsValue: TypeAlias = RealNumber | _BoundsSequenceLike

_PRIMARY_FRAME_HEIGHT = 24
_PER_ELEMENT_SPACER_WIDTH = 8
_VSTACK_SPACER_HEIGHT = 2


class AbstractField(Generic[ItemT]):
    """
    AbstractField that stores a style_name attribute to be used within `build_ui` for styling widgets.
    """

    def __init__(self, style_name: str = "PropertiesWidgetField", identifier: None | str = None) -> None:
        self.style_name = style_name
        self.identifier = identifier

    def __call__(self, item: ItemT, **kwargs) -> ui.Widget | list[ui.Widget] | None:
        return self.build_ui(item, **kwargs)

    @abc.abstractmethod
    def build_ui(self, item: ItemT, **kwargs) -> ui.Widget | list[ui.Widget] | None:
        raise NotImplementedError

    @staticmethod
    def set_dynamic_tooltip_fn(widget: ui.Widget, item_value_model: ItemModelBase) -> None:
        """Helper method to set dynamic tooltip function on a built widget."""

        def update_tooltip(_hovered: bool):
            tool_tip = item_value_model.get_tool_tip()

            if tool_tip is not None:
                widget.tooltip = tool_tip

        widget.set_mouse_hovered_fn(update_tooltip)


class AbstractDragFieldGroup(AbstractField):
    """Abstract base for drag-style delegates with optional min/max bounds and step.

    Subclasses must implement :meth:`build_drag_widget` to create the actual
    drag widget instance. Edit events are grouped for undo via
    :meth:`begin_edit` and :meth:`end_edit`.

    When ``min_value`` and ``max_value`` are both provided the widget displays
    a bounded drag range.  Either (or both) may be ``None`` for an unbounded
    field; in that case the corresponding bound is simply not passed to the
    underlying ``omni.ui`` widget.

    Hard bounds (``hard_min_value`` / ``hard_max_value``) are forwarded to the
    widget, which is responsible for value clamping behavior.

    API note:
        This class was renamed from ``AbstractDragField`` to
        ``AbstractDragFieldGroup`` to make it explicit that it orchestrates one
        or more drag widgets (for scalar/vector channels) rather than being a
        single concrete drag widget itself.
    """

    def __init__(
        self,
        min_value: BoundsValue | None = None,
        max_value: BoundsValue | None = None,
        hard_min_value: BoundsValue | None = None,
        hard_max_value: BoundsValue | None = None,
        step: BoundsValue | None = None,
        **kwargs,
    ):
        """Initialize the drag field.

        Args:
            min_value: Soft minimum for the drag range. May be scalar or
                sequence-like for per-channel resolution. ``None`` = unbounded.
            max_value: Soft maximum for the drag range. May be scalar or
                sequence-like for per-channel resolution. ``None`` = unbounded.
            hard_min_value: Hard minimum bound forwarded to drag widgets for
                typed-value clamping via widget pre-set callbacks. May be scalar
                or sequence-like for per-channel resolution.
            hard_max_value: Hard maximum bound forwarded to drag widgets for
                typed-value clamping via widget pre-set callbacks. May be scalar
                or sequence-like for per-channel resolution.
            step: Optional step size; scalar or sequence-like values are
                resolved per channel in ``build_ui``.
            **kwargs: Passed to AbstractField (e.g. style_name, identifier).
        """
        super().__init__(**kwargs)
        self._subs: list[carb.Subscription] = []

        if isinstance(min_value, RealNumber) and isinstance(max_value, RealNumber) and min_value >= max_value:
            raise ValueError(f"min_value ({min_value}) must be less than max_value ({max_value})")

        self.min_value = min_value
        self.max_value = max_value

        self.hard_min_value = hard_min_value
        self.hard_max_value = hard_max_value

        self.step = step

    def begin_edit(self, model: ItemModelBase) -> None:
        """Start an undo group for non-batched edits.

        Typed edits use this begin/end pair directly. Drag edits on batch-capable
        models open and close their undo group from the widget mouse callbacks.
        """
        if model.supports_batch_edit:
            return
        omni.kit.undo.begin_group()

    def end_edit(self, model: ItemModelBase) -> None:
        """End the current edit.

        For batch-edit models, this closes any active drag batch if needed.
        For non-batch models, this closes the regular undo group.
        """
        if model.supports_batch_edit:
            if model.is_batch_editing:
                model.end_batch_edit()
            return
        omni.kit.undo.end_group()

    @abc.abstractmethod
    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: RealNumber | None,
        max_val: RealNumber | None,
        hard_min_val: RealNumber | None,
        hard_max_val: RealNumber | None,
        step: RealNumber | None,
    ) -> ui.Widget:
        """Build the drag widget for one value model.

        Args:
            model: Value model to bind to the widget.
            style_type_name_override: Style name for the widget (e.g. read-only variant).
            read_only: Whether the widget should be read-only.
            min_val: Minimum value for the widget, or ``None`` for unbounded.
            max_val: Maximum value for the widget, or ``None`` for unbounded.
            hard_min_val: Hard minimum value for typed-value clamping, or
                ``None`` for no lower hard bound.
            hard_max_val: Hard maximum value for typed-value clamping, or
                ``None`` for no upper hard bound.
            step: Step size for the widget, or ``None`` to omit.

        Returns:
            The built drag widget (typically ``FloatBoundedDrag``/``IntBoundedDrag`` wrappers
            or other ``ui.Widget``-compatible drag controls).
        """
        raise NotImplementedError

    @staticmethod
    @overload
    def _resolve_scalar_component(value: BoundsValue | None, scalar_index: None) -> BoundsValue | None: ...

    @staticmethod
    @overload
    def _resolve_scalar_component(value: BoundsValue | None, scalar_index: int) -> RealNumber | None: ...

    @staticmethod
    def _resolve_scalar_component(value: BoundsValue | None, scalar_index: int | None) -> BoundsValue | None:
        """Resolve a channel scalar from bounds/step, or return input when index is None."""
        if scalar_index is None:
            return value
        if isinstance(value, (int, float)):
            return value

        if value is None:
            return None

        try:
            # Keep panel rendering resilient: if one attribute provides malformed
            # bounds metadata, fail this component gracefully instead of crashing
            # the whole properties panel build.
            return cast(BoundsValue, value[scalar_index])
        except (IndexError, KeyError, TypeError):
            carb.log_error(f"Failed to resolve bounds component at index {scalar_index} from value {value!r}")
            return None

    def build_ui(self, item, **kwargs) -> list[ui.Widget]:  # PLW0221
        """Build drag widgets for each element of the item, with undo grouping and tooltips."""
        self._subs.clear()
        widgets = []
        with ui.HStack(height=ui.Pixel(_PRIMARY_FRAME_HEIGHT)):
            for i in range(item.element_count):
                value_model = item.value_models[i]
                self._subs.append(value_model.subscribe_begin_edit_fn(self.begin_edit))
                self._subs.append(value_model.subscribe_end_edit_fn(self.end_edit))

                min_value = self._resolve_scalar_component(self.min_value, i)
                max_value = self._resolve_scalar_component(self.max_value, i)
                hard_min_value = self._resolve_scalar_component(self.hard_min_value, i)
                hard_max_value = self._resolve_scalar_component(self.hard_max_value, i)
                step_value = self._resolve_scalar_component(self.step, i)

                if min_value is not None and max_value is not None and min_value >= max_value:
                    carb.log_warn(
                        f"Drag bounds ignored for channel {i}: min ({min_value}) must be less than max ({max_value})."
                    )
                    min_value = None
                    max_value = None

                if step_value is not None:
                    step_value = abs(step_value)

                effective_hard_min = hard_min_value if hard_min_value is not None else min_value
                effective_hard_max = hard_max_value if hard_max_value is not None else max_value
                if (
                    effective_hard_min is not None
                    and effective_hard_max is not None
                    and effective_hard_min >= effective_hard_max
                ):
                    carb.log_warn(
                        f"Hard bounds ignored for channel {i}: hard_min ({effective_hard_min}) "
                        f"must be less than hard_max ({effective_hard_max})."
                    )
                    effective_hard_min = None
                    effective_hard_max = None

                ui.Spacer(width=ui.Pixel(_PER_ELEMENT_SPACER_WIDTH))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(_VSTACK_SPACER_HEIGHT))
                    style_type_name_override = (
                        f"{self.style_name}Read" if item.value_models[i].read_only else self.style_name
                    )
                    widget = self.build_drag_widget(
                        value_model,
                        style_type_name_override,
                        value_model.read_only,
                        min_value,
                        max_value,
                        effective_hard_min,
                        effective_hard_max,
                        step_value,
                    )
                    self.set_dynamic_tooltip_fn(widget, value_model)
                    widgets.append(widget)
                    ui.Spacer(height=ui.Pixel(_VSTACK_SPACER_HEIGHT))
        return widgets

    def __del__(self):
        self._subs.clear()

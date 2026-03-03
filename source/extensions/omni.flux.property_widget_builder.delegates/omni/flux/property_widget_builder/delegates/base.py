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


__all__ = ("AbstractField", "AbstractSliderField", "AbstractValueField")

import abc
from typing import TYPE_CHECKING, Generic, TypeVar

import carb
import omni.kit.undo
import omni.ui as ui


if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item
    from omni.flux.property_widget_builder.widget.tree.item_model import ItemModelBase


ItemT = TypeVar("ItemT", bound="Item")

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


class AbstractSliderField(AbstractField):
    """Abstract base for slider-style delegates with min/max bounds and step.

    Subclasses must implement :meth:`build_drag_widget` to create the actual
    drag widget (e.g. :class:`omni.ui.FloatDrag` or :class:`omni.ui.IntDrag`).
    Slider edits are grouped for undo via :meth:`begin_edit` and :meth:`end_edit`.
    """

    def __init__(
        self,
        min_value: int | float = 0.0,
        max_value: int | float = 100.0,
        hard_min_value: int | float | None = None,
        hard_max_value: int | float | None = None,
        step: int | float | None = None,
        **kwargs,
    ):
        """Initialize the slider field.

        Args:
            min_value: Minimum value of the slider. Must be less than max_value.
            max_value: Maximum value of the slider.
            hard_min_value: Hard minimum bound for clamping. Both hard_min_value and
                hard_max_value must be provided for clamping to take effect.
            hard_max_value: Hard maximum bound for clamping. Both hard_min_value and
                hard_max_value must be provided for clamping to take effect.
            step: Optional step size; subclasses may compute a default when None.
            **kwargs: Passed to AbstractField (e.g. style_name, identifier).
        """
        super().__init__(**kwargs)
        self._subs: list[carb.Subscription] = []
        if min_value >= max_value:
            raise ValueError(f"min_value ({min_value}) must be less than max_value ({max_value})")

        self.min_value = min_value
        self.max_value = max_value

        self.hard_min_value = hard_min_value
        self.hard_max_value = hard_max_value

        self.step = step

    @abc.abstractmethod
    def _get_value_from_model(self, model) -> int | float:
        raise NotImplementedError("please implement this method")

    def _clamp_to_hard_bounds(self, model):
        """Clamp the model's value to hard min/max bounds if set."""
        if self.hard_min_value is None or self.hard_max_value is None:
            return

        val = self._get_value_from_model(model)
        clamped_val = None

        if val < self.hard_min_value:
            clamped_val = self.hard_min_value
        elif val > self.hard_max_value:
            clamped_val = self.hard_max_value

        if clamped_val is None:
            return

        model.set_value(clamped_val)

    def begin_edit(self, _) -> None:
        """Start an undo group for slider drag (called on begin edit)."""
        omni.kit.undo.begin_group()

    def end_edit(self, model) -> None:
        """End the undo group for slider drag (called on end edit)."""
        self._clamp_to_hard_bounds(model)
        omni.kit.undo.end_group()

    @abc.abstractmethod
    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: float | int,
        max_val: float | int,
        step: float | int,
    ) -> ui.Widget:
        """Build the drag widget for one value model.

        Args:
            model: Value model to bind to the widget.
            style_type_name_override: Style name for the widget (e.g. read-only variant).
            read_only: Whether the widget should be read-only.
            min_val: Minimum value for the widget.
            max_val: Maximum value for the widget.
            step: Step size for the widget.

        Returns:
            The built drag widget (e.g. ui.FloatDrag or ui.IntDrag).
        """
        raise NotImplementedError

    def build_ui(self, item, **kwargs) -> list[ui.Widget]:  # noqa PLW0221
        """Build slider widgets for each element of the item, with undo grouping and tooltips."""
        self._subs.clear()
        widgets = []
        with ui.HStack(height=ui.Pixel(_PRIMARY_FRAME_HEIGHT)):
            for i in range(item.element_count):
                # Create subscriptions on the begin/end edits so we can undo the slider changes all at once.
                value_model = item.value_models[i]
                self._subs.append(value_model.subscribe_begin_edit_fn(self.begin_edit))
                self._subs.append(value_model.subscribe_end_edit_fn(self.end_edit))

                ui.Spacer(width=ui.Pixel(_PER_ELEMENT_SPACER_WIDTH))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(_VSTACK_SPACER_HEIGHT))
                    style_type_name_override = (
                        f"{self.style_name}Read" if item.value_models[i].read_only else self.style_name
                    )
                    step = self.step
                    if step is None:
                        step = 1
                    widget = self.build_drag_widget(
                        value_model,
                        style_type_name_override,
                        value_model.read_only,
                        self.min_value,
                        self.max_value,
                        step,
                    )
                    self.set_dynamic_tooltip_fn(widget, value_model)
                    widgets.append(widget)
                    ui.Spacer(height=ui.Pixel(_VSTACK_SPACER_HEIGHT))
        return widgets

    def __del__(self):
        self._subs.clear()


class AbstractValueField(AbstractField):
    """General-purpose base for typed input fields with optional min/max clamping.

    Subclasses must implement :meth:`_get_value_from_model` so that the
    clamping logic knows how to read the current numeric value.  Set
    ``clamp_min`` and/or ``clamp_max`` to enable one- or two-sided clamping
    on end-edit; leave them as ``None`` for an unclamped field.
    """

    def __init__(
        self,
        widget_type: type[ui.Widget],
        clamp_min: int | float | None = None,
        clamp_max: int | float | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.widget_type = widget_type
        self.clamp_min = clamp_min
        self.clamp_max = clamp_max

        self._subs: list[carb.Subscription] = []

    @abc.abstractmethod
    def _get_value_from_model(self, model) -> int | float:
        raise NotImplementedError

    def _clamp(self, model) -> None:
        """Clamp the model value to whichever of clamp_min / clamp_max are set."""
        if self.clamp_min is None and self.clamp_max is None:
            return

        val = self._get_value_from_model(model)
        clamped_val = val

        if self.clamp_min is not None and val < self.clamp_min:
            clamped_val = self.clamp_min
        if self.clamp_max is not None and val > self.clamp_max:
            clamped_val = self.clamp_max

        if clamped_val != val:
            model.set_value(clamped_val)

    def begin_edit(self, _) -> None:
        omni.kit.undo.begin_group()

    def end_edit(self, model) -> None:
        self._clamp(model)
        omni.kit.undo.end_group()

    def build_ui(self, item, **kwargs) -> list[ui.Widget]:  # noqa PLW0221
        self._subs.clear()
        widgets = []
        with ui.HStack(height=ui.Pixel(_PRIMARY_FRAME_HEIGHT)):
            for i in range(item.element_count):
                value_model = item.value_models[i]
                self._subs.append(value_model.subscribe_begin_edit_fn(self.begin_edit))
                self._subs.append(value_model.subscribe_end_edit_fn(self.end_edit))

                ui.Spacer(width=ui.Pixel(_PER_ELEMENT_SPACER_WIDTH))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(_VSTACK_SPACER_HEIGHT))
                    style_name = f"{self.style_name}Read" if value_model.read_only else self.style_name
                    widget = self.widget_type(
                        model=value_model,
                        style_type_name_override=style_name,
                        read_only=value_model.read_only,
                        identifier=self.identifier or "",
                    )
                    self.set_dynamic_tooltip_fn(widget, value_model)
                    widgets.append(widget)
                    ui.Spacer(height=ui.Pixel(_VSTACK_SPACER_HEIGHT))
        return widgets

    def __del__(self):
        self._subs.clear()

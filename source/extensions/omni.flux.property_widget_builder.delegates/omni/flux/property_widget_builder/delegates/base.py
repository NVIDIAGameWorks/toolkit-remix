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


__all__ = ("AbstractField", "AbstractSliderField")

import abc
from typing import TYPE_CHECKING, Generic, TypeVar

import carb
import omni.kit.undo
import omni.ui as ui


if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item
    from omni.flux.property_widget_builder.widget.tree.item_model import ItemModelBase


ItemT = TypeVar("ItemT", bound="Item")


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
        step: int | float | None = None,
        **kwargs,
    ):
        """Initialize the slider field.

        Args:
            min_value: Minimum value of the slider. Must be less than max_value.
            max_value: Maximum value of the slider.
            step: Optional step size; subclasses may compute a default when None.
            **kwargs: Passed to AbstractField (e.g. style_name, identifier).
        """
        super().__init__(**kwargs)
        assert min_value < max_value, "Min value must be less than max value"
        self.min_value = min_value
        self.max_value = max_value

        self._step = step

        self._subs: list[carb.Subscription] = []

    def begin_edit(self, _) -> None:
        """Start an undo group for slider drag (called on begin edit)."""
        omni.kit.undo.begin_group()

    def end_edit(self, _) -> None:
        """End the undo group for slider drag (called on end edit)."""
        omni.kit.undo.end_group()

    @property
    def step(self) -> int | float | None:
        """Step size for the slider; may be None if subclass computes it."""
        return self._step

    @step.setter
    def step(self, value: int | float) -> None:
        self._step = value

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
        with ui.HStack(height=ui.Pixel(24)):
            for i in range(item.element_count):
                # Create subscriptions on the begin/end edits so we can undo the slider changes all at once.
                value_model = item.value_models[i]
                self._subs.append(value_model.subscribe_begin_edit_fn(self.begin_edit))
                self._subs.append(value_model.subscribe_end_edit_fn(self.end_edit))

                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
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
                    ui.Spacer(height=ui.Pixel(2))
        return widgets

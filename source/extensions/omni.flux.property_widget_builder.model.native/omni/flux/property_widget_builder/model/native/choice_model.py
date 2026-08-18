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

__all__ = ("NativeChoiceModel",)

import enum
from collections.abc import Callable
from typing import Any

import carb
import omni.ui as ui
from omni.flux.property_widget_builder.widget import ItemModel, ItemValueModel


class _ChoiceItem(ui.AbstractItem):
    """Represent one native choice shown in a ComboBox."""

    def __init__(self, value: Any):
        """Initialize a choice and its display model.

        Args:
            value: Typed value represented by the choice.
        """
        super().__init__()
        self.value = value
        label = value.value if isinstance(value, enum.Enum) else value
        self.model = ui.SimpleStringModel(str(label))


class NativeChoiceModel(ItemModel):
    """Adapt typed native choices to the ComboBox item-model contract."""

    def __init__(self, value_model: ItemValueModel, choices: tuple[Any, ...]):
        """Initialize a choice model around an existing editable value model.

        Args:
            value_model: Model that reads and writes the typed property value.
            choices: Allowed typed values in display order.

        Raises:
            ValueError: If choices are empty or omit the current property value.
        """
        super().__init__()
        if not choices:
            raise ValueError("Native choices cannot be empty")
        current_value = value_model.get_value()
        if current_value not in choices:
            raise ValueError(f"Current value {current_value!r} is not present in the declared choices")

        self._value_model = value_model
        self._choices = choices
        self._items = [_ChoiceItem(value) for value in choices]
        self._current_index = ui.SimpleIntModel(choices.index(current_value))
        self._current_index.add_value_changed_fn(self._on_index_changed)
        self._updating_index = False
        self._read_only = value_model.read_only

    def get_value(self) -> Any:
        """Return the current typed value.

        Returns:
            Value stored by the wrapped native property model.
        """
        return self._value_model.get_value()

    def get_item_children(self, item: _ChoiceItem | None = None) -> list[_ChoiceItem]:
        """Return the available choices for the model root.

        Args:
            item: Parent choice, or None for the model root.

        Returns:
            All choices for the root and no children for an option.
        """
        return self._items if item is None else []

    def get_item_value_model(self, item: _ChoiceItem | None = None, column_id: int = 0):
        """Return the selected-index model or an option label model.

        Args:
            item: Choice whose label is requested, or None for the selected index.
            column_id: Requested model column. Native choices expose one column.

        Returns:
            The current-index model for the root or the label model for a choice.
        """
        return self._current_index if item is None else item.model

    def get_item_value_model_count(self, item: _ChoiceItem | None = None) -> int:
        """Return the single value-model column exposed by native choices.

        Args:
            item: Item being queried. Native choices always expose one column.

        Returns:
            One value-model column.
        """
        return 1

    def subscribe_value_changed_fn(self, callback: Callable[[ui.SimpleIntModel], None]) -> carb.Subscription:
        """Subscribe to selected-choice changes.

        Args:
            callback: Function invoked with the selected-index model.

        Returns:
            Subscription that owns the callback lifetime.
        """
        return self._current_index.subscribe_value_changed_fn(callback)

    def refresh(self) -> None:
        """Synchronize the selected index with the underlying typed value."""
        current_value = self._value_model.get_value()
        if current_value not in self._choices:
            raise ValueError(f"Current value {current_value!r} is not present in the declared choices")
        selected_index = self._choices.index(current_value)
        if self._current_index.as_int == selected_index:
            return
        self._updating_index = True
        self._current_index.set_value(selected_index)
        self._updating_index = False
        self._item_changed(None)

    def get_tool_tip(self):
        """Return the tooltip from the wrapped property value model.

        Returns:
            Tooltip text supplied by the wrapped model.
        """
        return self._value_model.get_tool_tip()

    def _set_value(self, value: Any) -> None:
        """Write a declared typed choice to the wrapped value model.

        Args:
            value: Choice value to persist.

        Raises:
            ValueError: If value is not one of the declared choices.
        """
        if value not in self._choices:
            raise ValueError(f"Value {value!r} is not present in the declared choices")
        self._value_model.set_value(value)

    def _on_dirty(self) -> None:
        """Synchronize the ComboBox after an externally requested value change."""
        self.refresh()

    def _on_index_changed(self, model: ui.SimpleIntModel) -> None:
        """Persist a user-selected choice through the wrapped value model.

        Args:
            model: Integer model containing the selected choice index.
        """
        if self._updating_index:
            return
        if self.read_only:
            self.refresh()
            return
        selected_index = model.as_int
        if 0 <= selected_index < len(self._choices):
            self._value_model.set_value(self._choices[selected_index])
            self._item_changed(None)

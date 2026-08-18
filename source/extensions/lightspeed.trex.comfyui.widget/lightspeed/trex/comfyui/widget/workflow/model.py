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

__all__ = [
    "GetterValueModel",
    "SimpleComboModel",
]

import pathlib
from typing import Generic, TypeVar

from lightspeed.trex.comfyui.core.models import WorkflowInput
from lightspeed.trex.comfyui.core.resolvers import (
    ConstantResolver,
    ResolverParameter,
    create_resolver,
    get_resolver_rule,
)
from omni import ui
from omni.flux.property_widget_builder.widget import ItemValueModel

from .constants import get_native_constant_label

FieldValueT = TypeVar("FieldValueT")


class _ComboItem(ui.AbstractItem):
    """Represent one labeled ComboBox option."""

    def __init__(self, label: str):
        """Initialize an option with its display label.

        Args:
            label: Text displayed for the resolver option.
        """
        super().__init__()
        self.model = ui.SimpleStringModel(label)


class SimpleComboModel(ui.AbstractItemModel):
    """ComboBox model for a list of string options."""

    def __init__(self, options: list[str], selected_index: int = 0):
        """Initialize string options and the selected index.

        Args:
            options: Display strings exposed as ComboBox child items.
            selected_index: Index selected when the model is created.
        """
        super().__init__()
        self._items = [_ComboItem(label) for label in options]
        self._current_index = ui.SimpleIntModel(selected_index)
        self._current_index.add_value_changed_fn(self._on_index_changed)

    def get_item_children(self, item=None):
        """Return string options for the ComboBox root.

        Args:
            item: Parent item to query, or None for the model root.

        Returns:
            String options for the root, or an empty list for child items.
        """
        return self._items if item is None else []

    def get_item_value_model(self, item=None, column_id=-1):
        """Return the selected index or a child item's label model.

        Args:
            item: Item to query, or None for the root.
            column_id: Unused column index required by the model contract.

        Returns:
            Selected-index model for the root or label model for an option.
        """
        return self._current_index if item is None else item.model

    def get_item_value_model_count(self, item=None):
        """Return the single value-model column.

        Args:
            item: Item whose column count is queried.

        Returns:
            One value-model column.
        """
        return 1

    def _on_index_changed(self, _model: ui.SimpleIntModel) -> None:
        """Notify subscribers that the selected option changed.

        Args:
            _model: Updated selected-index model.
        """
        self._item_changed(None)


class GetterValueModel(SimpleComboModel):
    """ComboBox model for selecting the value resolver type of a workflow input.

    Populates its children from the available resolver types for the given
    input and updates the input's value when the selection changes.

    Args:
        workflow_input: The workflow input whose resolver this model controls.
        context_name: USD context passed to newly created resolver instances.
    """

    def __init__(self, workflow_input: WorkflowInput, context_name: str = ""):
        """Initialize resolver options for a workflow input and USD context.

        Args:
            workflow_input: Workflow input whose active resolver is selected.
            context_name: USD context passed to newly created resolver instances.

        Raises:
            ValueError: If the input's current resolver type is not an available option.
        """
        self._workflow_input = workflow_input
        self._context_name = context_name
        current_value = workflow_input.value
        resolver_rule = get_resolver_rule(workflow_input.remix_type, workflow_input.native_type)
        self._resolver_options = list(resolver_rule.options)
        labels = [
            get_native_constant_label(workflow_input.native_type) if cls is ConstantResolver else cls.label
            for cls in self._resolver_options
        ]

        initial_index = self._find_current_index()
        if initial_index is None:
            raise ValueError(
                f"Resolver {type(current_value).__name__} is not available for workflow input {workflow_input.port_id}"
            )
        super().__init__(labels, initial_index)

    def refresh(self) -> None:
        """Refresh the model state. Required by PropertyWidget's Model.refresh() call chain.

        Intentionally does NOT call _item_changed() to avoid infinite recursion:
        _item_changed -> ComboBox change -> _on_getter_changed -> model.refresh() -> repeat.
        """

    def _find_current_index(self) -> int | None:
        """Determine the index matching the input's current value type.

        Returns:
            The matching resolver-option index, or None when the type is unavailable.
        """
        current_value = self._workflow_input.value
        for index, resolver_class in enumerate(self._resolver_options):
            if type(current_value) is resolver_class:
                return index
        return None

    def _on_index_changed(self, model: ui.SimpleIntModel) -> None:
        """Create and assign the resolver selected by the ComboBox.

        Args:
            model: Integer model containing the selected resolver-option index.
        """
        index = model.as_int
        if 0 <= index < len(self._resolver_options):
            self._set_resolver(index)
            super()._on_index_changed(model)

    def _set_resolver(self, index: int) -> None:
        """Replace the workflow input value with the resolver at an index.

        Args:
            index: Valid index into the available resolver classes.
        """
        resolver_class = self._resolver_options[index]
        self._workflow_input.value = create_resolver(
            resolver_class,
            self._workflow_input.native_type,
            self._workflow_input.default_value,
            self._context_name,
        )


class _ResolverFieldValueModel(ItemValueModel, Generic[FieldValueT]):
    """Value model bound to a strongly typed resolver parameter.

    Args:
        parameter: The resolver parameter binding.
    """

    def __init__(self, parameter: ResolverParameter[FieldValueT], value_type: type):
        """Initialize a value model for one resolver field.

        Args:
            parameter: Typed resolver parameter read and written by this model.
            value_type: Declared workflow type used to normalize edited values.
        """
        super().__init__()
        self._parameter = parameter
        self._value_type = value_type
        self._read_only = False

    def get_value(self) -> FieldValueT:
        """Return the current field value from the resolver.

        Returns:
            The parameter's current typed value.
        """
        return self._parameter.get_value()

    def _set_value(self, value: FieldValueT) -> None:
        """Write a new value to the resolver field.

        Args:
            value: Typed value to persist when it differs from the current value.
        """
        if self._value_type is pathlib.Path and type(value) is str:
            value = pathlib.Path(value)
        current = self.get_value()
        if value != current:
            self._parameter.set_value(value)
            self._on_dirty()

    def _on_dirty(self) -> None:
        """Notify listeners that the value has changed."""
        self._value_changed()

    def refresh(self) -> None:
        """Re-read the field value and notify listeners."""
        self._value_changed()

    def _get_value_as_string(self) -> str:
        """Return the field value as a string.

        Returns:
            String representation of the current parameter value.
        """
        value = self.get_value()
        if self._value_type is pathlib.Path and value == pathlib.Path():
            return ""
        return str(value)

    def _get_value_as_float(self) -> float:
        """Return the field value as a float.

        Returns:
            The converted value, or zero when conversion fails.
        """
        try:
            return float(self.get_value())
        except (TypeError, ValueError):
            return 0.0

    def _get_value_as_bool(self) -> bool:
        """Return the field value as a Boolean.

        Returns:
            Truth value of the current parameter value.
        """
        return bool(self.get_value())

    def _get_value_as_int(self) -> int:
        """Return the field value as an integer.

        Returns:
            The converted value, or zero when conversion fails.
        """
        try:
            return int(self.get_value())
        except (TypeError, ValueError):
            return 0

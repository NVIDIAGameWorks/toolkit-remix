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

from __future__ import annotations

from typing import Any

import omni.ui as ui
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_ROW_SPACING = ui.Pixel(8)


class _SharedIntTarget(BaseModel):
    """Identify one top-level check-plugin integer field."""

    plugin: str
    field: str

    model_config = ConfigDict(extra="forbid")


class _SharedIntDeclaration(BaseModel):
    """Describe one shared integer control and all of its targets."""

    identifier: str = Field(alias="id")
    label: str
    label_width: int = Field(default=120, gt=0)
    tooltip: str
    value: int
    targets: list[_SharedIntTarget] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _SharedValueBinding:
    """Assign one value atomically to resolved Pydantic model fields."""

    def __init__(self, targets: list[tuple[BaseModel, str]], value: Any) -> None:
        """Initialize the resolved targets and last accepted value."""
        self._targets = tuple(targets)
        self._value = value

    def set_value(self, value: Any) -> bool:
        """Assign a candidate value to every target or restore every snapshot."""
        snapshots = [getattr(target, field_name) for target, field_name in self._targets]
        try:
            for target, field_name in self._targets:
                setattr(target, field_name, value)
        except ValidationError:
            for (target, field_name), snapshot in zip(self._targets, snapshots):
                setattr(target, field_name, snapshot)
            return False
        self._value = value
        return True

    @property
    def targets(self) -> tuple[BaseModel, ...]:
        """Return the resolved target data models."""
        return tuple(target for target, _field_name in self._targets)

    @property
    def value(self) -> Any:
        """Return the last value accepted by every target."""
        return self._value


class SharedIntField:
    """Bind one integer value to fields on multiple check-plugin data models."""

    def __init__(self, declaration: _SharedIntDeclaration, targets: list[tuple[BaseModel, str]]):
        """Initialize a resolved shared integer field.

        Args:
            declaration: Validated shared-field declaration.
            targets: Resolved Pydantic plugin data models and field names.
        """
        self._declaration = declaration
        self._binding = _SharedValueBinding(targets, declaration.value)
        self._model = None
        self._end_edit_subscription = None

    @classmethod
    def from_schema(cls, schema: Any, declaration: dict[str, Any]) -> SharedIntField:
        """Resolve a shared integer declaration against a validation schema.

        Args:
            schema: Validation schema containing the target check plugins.
            declaration: Raw declaration from the schema's mass UI metadata.

        Returns:
            The resolved shared integer field.

        Raises:
            ValueError: If a target plugin or integer field cannot be resolved uniquely.
        """
        parsed_declaration = _SharedIntDeclaration.model_validate(declaration)
        resolved_targets = []
        for target in parsed_declaration.targets:
            matching_plugins = [plugin for plugin in schema.check_plugins if plugin.name == target.plugin]
            if not matching_plugins:
                raise ValueError(f"Shared integer target plugin '{target.plugin}' was not found.")
            if len(matching_plugins) > 1:
                raise ValueError(f"Shared integer target plugin '{target.plugin}' occurs more than once.")

            target_data = matching_plugins[0].data
            model_field = target_data.__class__.model_fields.get(target.field)
            if model_field is None:
                raise ValueError(
                    f"Shared integer target field '{target.plugin}.{target.field}' was not found on the plugin data."
                )
            if model_field.annotation is not int:
                raise ValueError(f"Shared integer target field '{target.plugin}.{target.field}' must be an integer.")
            resolved_targets.append((target_data, target.field))

        shared_field = cls(parsed_declaration, resolved_targets)
        if not shared_field.set_value(parsed_declaration.value):
            raise ValueError(
                f"Shared integer field '{parsed_declaration.identifier}' value {parsed_declaration.value} "
                "was rejected by a target."
            )
        return shared_field

    def set_value(self, value: int) -> bool:
        """Assign a candidate value atomically to every target.

        Args:
            value: Candidate integer value.

        Returns:
            Whether every target accepted the value.
        """
        return self._binding.set_value(value)

    def build_ui(self) -> None:
        """Build the single editable row for this shared integer field."""
        self._end_edit_subscription = None
        with ui.HStack(spacing=_ROW_SPACING):
            ui.Label(
                self._declaration.label,
                width=ui.Pixel(self._declaration.label_width),
                name="PropertiesWidgetLabel",
                tooltip=self._declaration.tooltip,
            )
            int_field = ui.IntField(identifier=self._declaration.identifier)
            self._model = int_field.model
            self._model.set_value(self.value)
            self._end_edit_subscription = self._model.subscribe_end_edit_fn(self._on_edit_end)
            _InfoIconWidget(self._declaration.tooltip)

    def _on_edit_end(self, model: ui.AbstractValueModel) -> None:
        """Apply an edited model value or restore the last accepted value.

        Args:
            model: Integer field model whose edit just ended.
        """
        if not self.set_value(model.get_value_as_int()):
            model.set_value(self.value)

    def destroy(self) -> None:
        """Release the UI model and edit subscription."""
        self._end_edit_subscription = None
        self._model = None

    @property
    def targets(self) -> tuple[BaseModel, ...]:
        """Return the resolved target data models."""
        return self._binding.targets

    @property
    def value(self) -> int:
        """Return the last value accepted by every target."""
        return self._binding.value

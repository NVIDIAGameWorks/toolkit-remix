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

import asyncio
import weakref
from dataclasses import dataclass
from typing import Any, cast

import carb
import omni.kit.app

from .expression_evaluator import (
    evaluate_expression,
    extract_identifiers,
    normalize_expression,
)

__all__ = [
    "ConditionalVisibilityOrchestrator",
]


@dataclass(frozen=True)
class _ConditionalVisibilityAttributeEntry:
    """Attribute metadata consumed by the conditional visibility orchestrator.

    Args:
        attr_id: Stable attribute identifier used in condition expressions.
        condition: Optional condition expression that controls this attribute's visibility.
        metadata_source: Optional schema or metadata object associated with the attribute.
    """

    attr_id: str
    condition: str | None = None
    metadata_source: Any = None


@dataclass
class _ConditionalVisibilityConditionGroup:
    """Mutable accumulator for entries sharing one normalized condition expression."""

    condition: str
    driver_attr_ids: tuple[str, ...]
    affected_attr_ids: list[str]


@dataclass(frozen=True)
class _ConditionalVisibilityConditionBinding:
    """Normalized relationship between condition drivers and affected attributes.

    Args:
        condition: Original condition expression to evaluate.
        driver_attr_ids: Attribute identifiers read by the condition expression.
        affected_attr_ids: Attribute identifiers hidden when the condition evaluates false.
    """

    condition: str
    driver_attr_ids: tuple[str, ...]
    affected_attr_ids: tuple[str, ...]


class ConditionalVisibilityOrchestrator:
    """Shared conditional visibility lifecycle manager for opt-in property panels."""

    def __init__(self):
        """Initialize condition bindings and transient UI state."""
        self._attribute_entries: list[_ConditionalVisibilityAttributeEntry] = []
        self._condition_bindings: tuple[_ConditionalVisibilityConditionBinding, ...] = ()
        self._attribute_items_by_id: dict[str, tuple[Any, ...]] = {}
        self._value_model_subscriptions: list[Any] = []
        self._evaluation_task = None
        self._scheduled_driver_attr_ids: set[str] = set()
        self._active = True

    def __del__(self):
        """Release subscriptions and references held by the orchestrator."""
        self._active = False
        if self._evaluation_task is not None and not self._evaluation_task.done():
            self._evaluation_task.cancel()
        self._value_model_subscriptions.clear()
        self._scheduled_driver_attr_ids.clear()
        self._attribute_items_by_id.clear()
        self._attribute_entries.clear()
        self._condition_bindings = ()

    def _bind_items(self) -> None:
        """Bind rendered item objects so driver value edits can trigger re-evaluation."""
        self._value_model_subscriptions.clear()
        driver_attr_ids = self._get_bound_driver_attr_ids()

        for attr_id, items in self._attribute_items_by_id.items():
            if attr_id not in driver_attr_ids:
                continue
            for item in items:
                for value_model in item.value_models or ():
                    orchestrator_ref = weakref.ref(self)

                    def _on_driver_value_changed(
                        _value_model, driver_attr_id=attr_id, current_orchestrator_ref=orchestrator_ref
                    ):
                        orchestrator = current_orchestrator_ref()
                        if orchestrator is None or not orchestrator._active:  # noqa: SLF001
                            return
                        orchestrator._schedule_evaluate_bindings(driver_attr_id)  # noqa: SLF001

                    subscription = value_model.subscribe_value_changed_fn(_on_driver_value_changed)
                    self._value_model_subscriptions.append(subscription)

    def _schedule_evaluate_bindings(self, changed_driver_attr_id: str) -> None:
        """Schedule runtime visibility evaluation outside the value-model callback stack."""
        if changed_driver_attr_id not in self._get_bound_driver_attr_ids():
            return

        self._scheduled_driver_attr_ids.add(changed_driver_attr_id)
        if self._evaluation_task is not None and not self._evaluation_task.done():
            return

        self._evaluation_task = asyncio.ensure_future(self._do_scheduled_evaluate_bindings())

    async def _do_scheduled_evaluate_bindings(self) -> None:
        """Run one debounced runtime visibility evaluation on the next Kit update."""
        await cast(Any, omni.kit.app.get_app()).next_update_async()
        if not self._active:
            return

        scheduled_driver_attr_ids = set(self._scheduled_driver_attr_ids)
        self._scheduled_driver_attr_ids.clear()
        changed_driver_attr_id = next(iter(scheduled_driver_attr_ids)) if len(scheduled_driver_attr_ids) == 1 else None
        self._evaluate_bindings(changed_driver_attr_id=changed_driver_attr_id)

    def _get_enable_if_condition(self, attribute_entry: _ConditionalVisibilityAttributeEntry) -> str | None:
        """Read the condition expression from an attribute entry.

        Args:
            attribute_entry: Attribute-like record to inspect.

        Returns:
            Condition expression string, or ``None`` when the entry is unconditional.
        """
        return attribute_entry.condition

    def _get_attr_id(self, attribute_entry: _ConditionalVisibilityAttributeEntry) -> str | None:
        """Read the attribute identifier from an attribute entry.

        Args:
            attribute_entry: Attribute-like record to inspect.

        Returns:
            Attribute identifier, or ``None`` when unavailable.
        """
        return attribute_entry.attr_id

    def _normalize_attr_id(self, attr_id: str) -> str:
        """Normalize an attribute identifier for condition matching.

        Args:
            attr_id: Raw attribute identifier.

        Returns:
            Normalized attribute identifier.
        """
        return attr_id

    def _build_condition_bindings(self) -> tuple[_ConditionalVisibilityConditionBinding, ...]:
        """Create normalized bindings from entries that declare conditions.

        Returns:
            Tuple of condition bindings grouped by normalized condition expression.
        """
        available_attr_ids: set[str] = set()
        for entry in self._attribute_entries:
            attr_id = self._get_attr_id(entry)
            if attr_id:
                available_attr_ids.add(self._normalize_attr_id(attr_id))

        grouped: dict[str, _ConditionalVisibilityConditionGroup] = {}

        for entry in self._attribute_entries:
            affected_attr_id = self._get_attr_id(entry)
            if not affected_attr_id:
                continue
            affected_attr_id = self._normalize_attr_id(affected_attr_id)
            condition = self._get_enable_if_condition(entry)
            if not condition:
                continue

            driver_attr_ids = self._get_driver_attr_ids(condition, affected_attr_id, available_attr_ids)
            if not driver_attr_ids:
                continue

            group = grouped.setdefault(
                normalize_expression(condition),
                _ConditionalVisibilityConditionGroup(
                    condition=condition,
                    driver_attr_ids=driver_attr_ids,
                    affected_attr_ids=[],
                ),
            )
            group.affected_attr_ids.append(affected_attr_id)

        bindings: list[_ConditionalVisibilityConditionBinding] = []
        for group in grouped.values():
            bindings.append(
                _ConditionalVisibilityConditionBinding(
                    condition=group.condition,
                    driver_attr_ids=group.driver_attr_ids,
                    affected_attr_ids=tuple(dict.fromkeys(group.affected_attr_ids)),
                )
            )
        return tuple(bindings)

    def _get_driver_attr_ids(
        self,
        condition: str,
        affected_attr_id: str,
        available_attr_ids: set[str],
    ) -> tuple[str, ...]:
        """Extract valid driver IDs from a condition expression.

        Args:
            condition: Condition expression to inspect.
            affected_attr_id: Attribute ID controlled by the condition, used for diagnostics.
            available_attr_ids: Normalized attribute IDs available for driver references.

        Returns:
            Tuple of normalized driver IDs, or an empty tuple when binding is invalid.
        """
        try:
            driver_attr_ids = tuple(
                self._normalize_attr_id(identifier) for identifier in extract_identifiers(condition)
            )
        except ValueError as exc:
            carb.log_warn(f"Unable to parse enable-if condition for {affected_attr_id}: {condition!r}. {exc}")
            return ()
        driver_attr_ids = tuple(dict.fromkeys(driver_attr_ids))

        missing_driver_attr_ids = [attr_id for attr_id in driver_attr_ids if attr_id not in available_attr_ids]
        if missing_driver_attr_ids:
            carb.log_warn(
                "Unable to bind enable-if condition for "
                f"{affected_attr_id}: missing driver attribute(s) {missing_driver_attr_ids} in {condition!r}."
            )
            return ()

        return driver_attr_ids

    def _evaluate_binding(self, binding: _ConditionalVisibilityConditionBinding) -> bool | None:
        """Evaluate a single condition binding.

        Args:
            binding: Binding whose condition should be evaluated.

        Returns:
            ``True`` or ``False`` when evaluation succeeds, or ``None`` when it fails open.
        """
        values: dict[str, Any] = {}
        for driver_attr_id in binding.driver_attr_ids:
            values[driver_attr_id] = self._get_driver_value(driver_attr_id)

        try:
            return evaluate_expression(binding.condition, values)
        except ValueError as exc:
            carb.log_warn(f"Unable to evaluate enable-if condition {binding.condition!r}: {exc}")
            return None

    def _get_driver_value(self, attr_id: str) -> Any:
        """Read the current value for a driver attribute.

        Args:
            attr_id: Normalized driver attribute ID.

        Returns:
            Live item value when available, otherwise ``None``.
        """
        for item in self._attribute_items_by_id.get(attr_id, ()):
            value_models = item.value_models or ()
            if value_models:
                return value_models[0].get_value()

        return None

    @staticmethod
    def _normalize_bound_items(item_or_items: Any) -> tuple[Any, ...]:
        """Normalize a bound item value into a tuple of row items.

        Args:
            item_or_items: Rendered item object or a list/tuple of related rendered item objects.

        Returns:
            Tuple of non-null rendered item objects.
        """
        if isinstance(item_or_items, (list, tuple)):
            return tuple(item for item in item_or_items if item is not None)
        if item_or_items is None:
            return ()
        return (item_or_items,)

    def _get_bound_driver_attr_ids(self) -> frozenset[str]:
        """Return all driver attribute IDs referenced by bound conditions.

        Returns:
            Frozen set of normalized driver attribute IDs.
        """
        driver_attr_ids: set[str] = set()
        for binding in self._condition_bindings:
            driver_attr_ids.update(binding.driver_attr_ids)
        return frozenset(driver_attr_ids)

    def _evaluate_bindings(
        self,
        changed_driver_attr_id: str | None = None,
    ) -> None:
        """Evaluate visibility bindings and update cached state.

        Args:
            changed_driver_attr_id: Driver attribute ID that changed, or ``None`` to evaluate all bindings.
        """
        if changed_driver_attr_id is not None and changed_driver_attr_id not in self._get_bound_driver_attr_ids():
            return

        for binding in self._condition_bindings:
            if changed_driver_attr_id is not None and changed_driver_attr_id not in binding.driver_attr_ids:
                continue

            enabled = self._evaluate_binding(binding)
            if enabled is None:
                continue

            hidden = not enabled
            for affected_attr_id in binding.affected_attr_ids:
                for item in self._attribute_items_by_id.get(affected_attr_id, ()):
                    item.hidden = hidden

    def bind_attribute(
        self,
        *,
        attr_id: str | None = None,
        condition: str | None = None,
        metadata_source: Any = None,
        item_or_items: Any = None,
    ) -> None:
        """Bind one attribute entry and its rendered row item or companion row items.

        Args:
            attr_id: Stable attribute identifier used for condition matching.
            condition: Optional condition expression that controls this attribute's visibility.
            metadata_source: Optional schema or metadata object associated with the attribute.
            item_or_items: Rendered item object or related rendered item objects controlled by this entry.

        Each normalized attribute ID should be bound once per setup pass. Rebinding the same ID replaces its rendered
        item references rather than merging old and new rows.
        """
        if not attr_id:
            return

        attribute_entry = _ConditionalVisibilityAttributeEntry(
            attr_id=attr_id,
            condition=condition,
            metadata_source=metadata_source,
        )

        attr_id = self._get_attr_id(attribute_entry)
        if not attr_id:
            return

        normalized_attr_id = self._normalize_attr_id(attr_id)
        self._attribute_entries.append(attribute_entry)

        bound_items = self._normalize_bound_items(item_or_items)
        if bound_items:
            if normalized_attr_id in self._attribute_items_by_id:
                carb.log_warn(
                    f"Replacing conditional visibility item binding for duplicate attribute ID {normalized_attr_id!r}. "
                    "Each normalized attribute ID should be bound once per setup pass."
                )
            self._attribute_items_by_id[normalized_attr_id] = bound_items

    def can_bind_attribute(self, attr_id: str | None) -> bool:
        """Return whether an attribute identifier can participate in conditional visibility.

        Args:
            attr_id: Raw attribute identifier to inspect.

        Returns:
            Whether the attribute should be bound by the orchestrator.
        """
        return bool(attr_id and self._normalize_attr_id(attr_id))

    def sync_and_evaluate_bindings(self) -> None:
        """Build condition bindings, wire driver subscriptions, and apply initial visibility.

        Call this after all attributes and row items have been registered with
        :meth:`bind_attribute`.
        """
        self._condition_bindings = self._build_condition_bindings()
        self._bind_items()
        self._evaluate_bindings()

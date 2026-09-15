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

__all__ = ["StageManagerUtils"]

import asyncio
import threading
from collections import Counter
from collections.abc import Callable, Iterable

from omni.flux.utils.common.task_budget import WorkerYieldBudget

from .items import StageManagerItem
from .plugins.filter_plugin import FilterCategory as _FilterCategory
from .plugins.filter_plugin import StageManagerFilterPlugin as _StageManagerFilterPlugin

_FILTER_WORKER_YIELD_SECONDS = 0.004


def _filter_result_closed(
    universe: set[StageManagerItem],
    predicate: Callable[[StageManagerItem], bool],
    ancestor_universe: set[StageManagerItem] | None = None,
    cancel_event: threading.Event | None = None,
) -> set[StageManagerItem] | None:
    """
    Return the set of items that would be returned by filter_items with a single predicate
    (items passing the predicate plus all their ancestors that are in ancestor_universe).
    When narrowing (e.g. sequential AND), pass the same set for universe and ancestor_universe
    so ruled-out items are not added back.
    """
    if ancestor_universe is None:
        ancestor_universe = universe
    pass_set = set()
    for item in universe:
        if cancel_event and cancel_event.is_set():
            return None
        if predicate(item):
            pass_set.add(item)
    result = set(pass_set)
    for item in pass_set:
        if cancel_event and cancel_event.is_set():
            return None
        current = item.parent
        while current is not None:
            if cancel_event and cancel_event.is_set():
                return None
            if current in ancestor_universe:
                result.add(current)
            current = current.parent
    return result


class StageManagerUtils:
    """Filter Stage Manager items and prepare refresh-owned wrapper state."""

    @classmethod
    def get_unique_names(
        cls,
        items: Iterable[StageManagerItem],
        cancel_event: threading.Event | None = None,
    ) -> dict[StageManagerItem, tuple[str, str | None]] | None:
        """
        Get unique names from a list of prim paths.
        If the name is not unique, the name and parent name will be returned.

        Args:
            items: Stage Manager items wrapping USD prims.
            cancel_event: Signal set when this work has been superseded.

        Returns:
            A mapping from each Stage Manager item to its ``(leaf_name, parent_name_or_none)`` tuple, or ``None`` when
            cancelled.
        """
        return cls._get_unique_names(items, cancel_event=cancel_event)

    @staticmethod
    def _get_unique_names(
        items: Iterable[StageManagerItem],
        cancel_event: threading.Event | None = None,
        worker_yield_budget: WorkerYieldBudget | None = None,
    ) -> dict[StageManagerItem, tuple[str, str | None]] | None:
        """Build unique display names, optionally pacing an enclosing worker transaction."""
        items = list(items)
        default_names = {}
        for item in items:
            if cancel_event and cancel_event.is_set():
                return None
            default_names[item] = item.data.GetPath().name
            if worker_yield_budget:
                worker_yield_budget.checkpoint()

        # Count how many times each default name occurs.
        name_counts = Counter(default_names.values())

        # Build the result dictionary:
        result = {}
        for item in items:
            if cancel_event and cancel_event.is_set():
                return None
            # If the name is not unique, add the parent name to the list of names
            if name_counts[default_names[item]] == 1:
                result[item] = (default_names[item], None)
            else:
                result[item] = (default_names[item], item.data.GetPath().GetParentPath().name)
            if worker_yield_budget:
                worker_yield_budget.checkpoint()
        return result

    @classmethod
    def filter_items_by_category(
        cls,
        items: list[StageManagerItem],
        filter_plugins: list[_StageManagerFilterPlugin],
        cancel_event: threading.Event | None = None,
    ) -> list[StageManagerItem] | None:
        """Filter items using Stage Manager category combination rules.

        Active filters in named categories are combined with OR, filters in the OTHER category are combined with AND,
        and categories are applied with AND. Matching ancestors are retained to preserve the tree hierarchy.

        Args:
            items: Items to filter.
            filter_plugins: Filters grouped by their configured category.
            cancel_event: Signal set when this work has been superseded.

        Returns:
            Filtered items in input order, or ``None`` when cancelled.
        """
        if cancel_event and cancel_event.is_set():
            return None
        active_filters = [filter_obj for filter_obj in filter_plugins if filter_obj.filter_active]
        if not active_filters:
            return items

        filters_by_category = {category: [] for category in _FilterCategory}
        for filter_obj in active_filters:
            if cancel_event and cancel_event.is_set():
                return None
            filters_by_category[filter_obj.filter_category].append(filter_obj.build_filter_predicate())

        candidates = set(items)
        for category in _FilterCategory:
            if cancel_event and cancel_event.is_set():
                return None
            predicates = filters_by_category.get(category, [])
            if not predicates:
                continue

            if category.is_or:
                category_candidates = set()
                for predicate in predicates:
                    result = _filter_result_closed(candidates, predicate, cancel_event=cancel_event)
                    if result is None:
                        return None
                    category_candidates.update(result)
                candidates = category_candidates
                continue

            for predicate in predicates:
                filtered_candidates = _filter_result_closed(
                    candidates,
                    predicate,
                    ancestor_universe=candidates,
                    cancel_event=cancel_event,
                )
                if filtered_candidates is None:
                    return None
                candidates = filtered_candidates
                if not candidates:
                    break

        if cancel_event and cancel_event.is_set():
            return None
        return [item for item in items if item in candidates]

    @classmethod
    async def filter_items(
        cls,
        items: list[StageManagerItem],
        predicates: list[Callable[[StageManagerItem], bool]],
        include_invalid_parents: bool = True,
        cancel_event: threading.Event | None = None,
        include_display_name_ancestors: bool | None = None,
    ) -> list[StageManagerItem] | None:
        """
        Filter refresh-owned items in one cooperative worker transaction.

        Note:
            The supplied wrappers must be owned exclusively by the current context refresh. This method intentionally
            updates validity and may reparent surviving items before ownership transfers to the tree model.

        Args:
            items: Items to filter
            predicates: Predicates to execute on each item
            include_invalid_parents: Whether to include invalid parent items of valid items in the filtered list
            cancel_event: Signal set when this work has been superseded
            include_display_name_ancestors: Whether display-name candidates include source ancestors. Defaults to
                ``include_invalid_parents``.

        Returns:
            Filtered items, including invalid ancestors when requested or reparented to the nearest valid ancestor
            otherwise. The supplied wrappers are updated in place. Returns ``None`` when cancelled.
        """
        if cancel_event and cancel_event.is_set():
            return None
        if not items or not predicates:
            return items

        include_name_ancestors = (
            include_invalid_parents if include_display_name_ancestors is None else include_display_name_ancestors
        )

        def collect_items(worker_yield_budget: WorkerYieldBudget) -> list[StageManagerItem] | None:
            """Collect retained items, reconnecting sparse results when requested."""
            filtered_items = []
            if include_invalid_parents:
                for item in items:
                    if cancel_event and cancel_event.is_set():
                        return None
                    if item.is_valid or item.is_child_valid:
                        filtered_items.append(item)
                    worker_yield_budget.checkpoint()
                return filtered_items

            for item in items:
                if cancel_event and cancel_event.is_set():
                    return None
                if item.is_valid:
                    parent = item.parent
                    while parent and not parent.is_valid:
                        if cancel_event and cancel_event.is_set():
                            return None
                        parent = parent.parent
                    # Establish the hierarchy among surviving refresh-owned items before transferring them to the model.
                    item.parent = parent
                    filtered_items.append(item)
                worker_yield_budget.checkpoint()
            return filtered_items

        def filter_worker() -> list[StageManagerItem] | None:
            """Filter and prepare all refresh-owned items as one synchronous transaction."""
            worker_yield_budget = WorkerYieldBudget(yield_seconds=_FILTER_WORKER_YIELD_SECONDS)
            display_name_candidates = []
            for index in range(len(items)):
                if cancel_event and cancel_event.is_set():
                    return None
                item = items[index]
                item.set_filter_validity(
                    all(predicate(item) for predicate in predicates),
                    propagate_to_ancestors=include_invalid_parents,
                )
                if item.is_display_name_candidate:
                    display_name_candidates.append(item)
                worker_yield_budget.checkpoint()

            if not display_name_candidates:
                return collect_items(worker_yield_budget)

            naming_items = set(display_name_candidates)
            if include_name_ancestors:
                if cancel_event and cancel_event.is_set():
                    return None
                source_items = set(items)
                if cancel_event and cancel_event.is_set():
                    return None
                for item in display_name_candidates:
                    if cancel_event and cancel_event.is_set():
                        return None
                    parent = item.parent
                    while parent in source_items and parent not in naming_items:
                        if cancel_event and cancel_event.is_set():
                            return None
                        naming_items.add(parent)
                        parent = parent.parent
                    worker_yield_budget.checkpoint()
            display_names = cls._get_unique_names(
                naming_items,
                cancel_event=cancel_event,
                worker_yield_budget=worker_yield_budget,
            )
            if display_names is None:
                return None
            for item, name in display_names.items():
                if cancel_event and cancel_event.is_set():
                    return None
                item.prepare_display_name(name)
                worker_yield_budget.checkpoint()
            return collect_items(worker_yield_budget)

        filtered_items = await asyncio.to_thread(filter_worker)
        return None if cancel_event and cancel_event.is_set() else filtered_items

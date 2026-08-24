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
import time
from collections import Counter
from collections.abc import Callable, Iterable

from omni.flux.utils.common.task_budget import AdaptiveTaskBudget

from .items import StageManagerItem
from .plugins.filter_plugin import FilterCategory as _FilterCategory
from .plugins.filter_plugin import StageManagerFilterPlugin as _StageManagerFilterPlugin


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
    _task_budget = AdaptiveTaskBudget()

    @classmethod
    def get_unique_names(cls, items: Iterable[StageManagerItem]) -> dict[StageManagerItem, tuple[str, str | None]]:
        """
        Get unique names from a list of prim paths.
        If the name is not unique, the name and parent name will be returned.

        Args:
            items: Stage Manager items wrapping USD prims.

        Returns:
            A dict of { path: unique_name } where unique_name is a list of prim names that should identify the path
        """
        default_names = {item: item.data.GetPath().name for item in items}

        # Count how many times each default name occurs.
        name_counts = Counter(default_names.values())

        # Build the result dictionary:
        result = {}
        for item in items:
            # If the name is not unique, add the parent name to the list of names
            if name_counts[default_names[item]] == 1:
                result[item] = (default_names[item], None)
            else:
                result[item] = (default_names[item], item.data.GetPath().GetParentPath().name)
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
    ) -> list[StageManagerItem] | None:
        """
        Filter refresh-owned items in bounded worker chunks.

        Note:
            The supplied wrappers must be owned exclusively by the current context refresh. This method intentionally
            updates validity and may reparent surviving items before ownership transfers to the tree model.

        Args:
            items: Items to filter
            predicates: Predicates to execute on each item
            include_invalid_parents: Whether to include invalid parent items of valid items in the filtered list
            cancel_event: Signal set when this work has been superseded

        Returns:
            Filtered items, including invalid ancestors when requested or reparented to the nearest valid ancestor
            otherwise. The supplied wrappers are updated in place. Returns ``None`` when cancelled.
        """
        if cancel_event and cancel_event.is_set():
            return None
        if not items or not predicates:
            return items

        partition = cls._task_budget.compute_partition(len(items), len(predicates))
        chunk_size = partition.chunk_size

        async def run_chunks(callback) -> bool:
            for start_index in range(0, len(items), chunk_size):
                if cancel_event and cancel_event.is_set():
                    return False
                end_index = min(start_index + chunk_size, len(items))
                await asyncio.to_thread(callback, start_index, end_index)
            return not cancel_event or not cancel_event.is_set()

        def filter_chunk(start_index: int, end_index: int) -> float:
            started = time.perf_counter()
            for item in items[start_index:end_index]:
                if cancel_event and cancel_event.is_set():
                    break
                item.is_valid = all(predicate(item) for predicate in predicates)
            return (time.perf_counter() - started) * 1000.0

        loop = asyncio.get_event_loop()
        wait_started = loop.time()
        chunk_compute_ms = 0.0
        executed_chunks = 0
        for start_index in range(0, len(items), chunk_size):
            if cancel_event and cancel_event.is_set():
                return None
            end_index = min(start_index + chunk_size, len(items))
            chunk_compute_ms += await asyncio.to_thread(filter_chunk, start_index, end_index)
            executed_chunks += 1
        executor_wait_ms = (loop.time() - wait_started) * 1000.0

        if cancel_event and cancel_event.is_set():
            return None
        cls._task_budget.update_metrics(
            compute_ms=chunk_compute_ms,
            executor_wait_ms=executor_wait_ms,
            task_count=executed_chunks,
            item_count=len(items),
            predicate_count=len(predicates),
        )

        if include_invalid_parents:
            return await asyncio.to_thread(lambda: [item for item in items if item.is_valid or item.is_child_valid])

        filtered_items = []

        def collect_reparented_chunk(start_index: int, end_index: int):
            for item in items[start_index:end_index]:
                if cancel_event and cancel_event.is_set():
                    return
                if not item.is_valid:
                    continue
                parent = item.parent
                while parent and not parent.is_valid:
                    if cancel_event and cancel_event.is_set():
                        return
                    parent = parent.parent
                # Establish the hierarchy among surviving refresh-owned items before transferring them to the model.
                item.parent = parent
                filtered_items.append(item)

        return filtered_items if await run_chunks(collect_reparented_chunk) else None

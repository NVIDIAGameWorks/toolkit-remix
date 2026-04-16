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
import concurrent.futures
import time
from collections import Counter
from collections.abc import Callable, Iterable

import omni.usd
from omni.flux.utils.common.task_budget import AdaptiveTaskBudget

from .items import StageManagerItem
from .plugins.filter_plugin import FilterCategory as _FilterCategory
from .plugins.filter_plugin import StageManagerFilterPlugin as _StageManagerFilterPlugin


def _filter_result_closed(
    universe: set[StageManagerItem],
    predicate: Callable[[StageManagerItem], bool],
    ancestor_universe: set[StageManagerItem] | None = None,
) -> set[StageManagerItem]:
    """
    Return the set of items that would be returned by filter_items with a single predicate
    (items passing the predicate plus all their ancestors that are in ancestor_universe).
    When narrowing (e.g. sequential AND), pass the same set for universe and ancestor_universe
    so ruled-out items are not added back.
    """
    if ancestor_universe is None:
        ancestor_universe = universe
    pass_set = {item for item in universe if predicate(item)}
    result = set(pass_set)
    for item in pass_set:
        current = item.parent
        while current is not None:
            if current in ancestor_universe:
                result.add(current)
            current = current.parent
    return result


class StageManagerUtils:
    # Shared adaptive budget is intentional for the current single interaction-plugin
    # usage pattern. If multiple call sites with very different workloads emerge,
    # move to per-plugin or keyed budgets to avoid cross-workload EMA bleed.
    _task_budget = AdaptiveTaskBudget()

    @classmethod
    def _get_depth(cls, item: StageManagerItem) -> int:
        """Count how many ancestors an item has."""
        depth = 0
        current = item
        while current.parent is not None:
            depth += 1
            current = current.parent
        return depth

    @classmethod
    def get_unique_names(cls, items: Iterable[StageManagerItem]) -> dict[StageManagerItem, tuple[str, str | None]]:
        """
        Get unique names from a list of prim paths.
        If the name is not unique, the name and parent name will be returned.

        Args:
            items: List of stage manager items

        Returns:
            A dict of { path: unique_name } where unique_name is a list of prim names that should identify the path
        """
        # Prepare initial mapping from path to its base name.
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
        cls, items: Iterable[StageManagerItem], filter_plugins: Iterable[_StageManagerFilterPlugin]
    ) -> list[StageManagerItem]:
        """
        Filter items by category. Each filter's result matches what filter_items would
        return for that predicate alone (passing items plus ancestors); results are
        then combined by category: OR within PRIMS/GROUP, AND within OTHER, AND between categories.
        AND filters are applied sequentially so predicates run only on the current
        candidate set, reducing work when items have already been ruled out.
        """
        filters_by_category = {category: [] for category in _FilterCategory}
        items_set = set(items)
        for filter_obj in filter_plugins:
            filters_by_category[filter_obj.filter_category].append(filter_obj)

        candidates = items_set
        is_or_categories = (_FilterCategory.PRIMS, _FilterCategory.GROUP)

        for category in _FilterCategory:
            category_filters = filters_by_category.get(category, [])
            if not category_filters:
                continue

            is_or_filter = category in is_or_categories

            if is_or_filter:
                closed_sets = [
                    _filter_result_closed(candidates, f.filter_predicate)
                    for f in category_filters
                    if getattr(f, "filter_active", True)
                ]
                if closed_sets:
                    candidates = set().union(*closed_sets)
            else:
                for f in category_filters:
                    candidates = _filter_result_closed(candidates, f.filter_predicate)
                    if not candidates:
                        break

        return sorted(candidates, key=cls._get_depth)

    @classmethod
    @omni.usd.handle_exception
    async def filter_items(
        cls,
        items: Iterable[StageManagerItem],
        predicates: Iterable[Callable[[StageManagerItem], bool]],
        include_invalid_parents: bool = True,
    ) -> list[StageManagerItem]:
        """
        Filter items using adaptive chunked tasks on a dedicated worker thread.

        Note:
            This path intentionally uses a single-worker thread pool. Prior
            per-item fanout created substantial scheduling overhead and did not
            produce effective multi-core scaling for this Python predicate
            workload because of GIL contention.

        Args:
            items: Items to filter
            predicates: Predicates to execute on each item
            include_invalid_parents: Whether to include invalid parent items of valid items in the filtered list

        Returns:
            Filtered items list
        """
        item_list = list(items)
        predicate_list = list(predicates)

        partition = cls._task_budget.compute_partition(len(item_list), len(predicate_list))
        task_count = partition.task_count
        chunk_size = partition.chunk_size
        chunk_compute_ms = 0.0

        def _run_chunk(start_index: int, end_index: int):
            loop_start = time.perf_counter()
            for item in item_list[start_index:end_index]:
                item.reset_filter_state()
                item.is_valid = all(predicate(item) for predicate in predicate_list)
            return (time.perf_counter() - loop_start) * 1000.0

        loop = asyncio.get_event_loop()
        wait_start = loop.time()
        executed_chunks = 0
        # Intentionally single-worker: chunking improves responsiveness while
        # avoiding per-item task overhead from broad thread fanout.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="sm_filter_profile") as pool:
            for chunk_index in range(task_count):
                start_index = chunk_index * chunk_size
                if start_index >= len(item_list):
                    break
                end_index = min(start_index + chunk_size, len(item_list))
                chunk_compute_ms += await loop.run_in_executor(pool, _run_chunk, start_index, end_index)
                executed_chunks += 1
        executor_wait_ms = (loop.time() - wait_start) * 1000.0
        cls._task_budget.update_metrics(
            compute_ms=chunk_compute_ms,
            executor_wait_ms=executor_wait_ms,
            task_count=executed_chunks,
            item_count=len(item_list),
            predicate_count=len(predicate_list),
        )

        if include_invalid_parents:
            result = list(filter(lambda f: f.is_valid or f.is_child_valid, item_list))
        else:
            result = list(filter(lambda f: f.is_valid, item_list))

        return result

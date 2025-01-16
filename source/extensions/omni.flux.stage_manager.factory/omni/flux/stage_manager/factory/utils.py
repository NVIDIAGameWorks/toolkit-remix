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
import concurrent
from typing import Callable, Iterable

import omni.usd

from .items import StageManagerItem


class StageManagerUtils:
    @classmethod
    @omni.usd.handle_exception
    async def filter_items(
        cls,
        items: Iterable[StageManagerItem],
        predicates: Iterable[Callable[[StageManagerItem], bool]],
        include_invalid_parents: bool = True,
    ) -> list[StageManagerItem]:
        """
        Filter items using predicates with parallel processing.

        Args:
            items: Items to filter
            predicates: Predicates to execute on each item
            include_invalid_parents: Whether to include invalid parent items of valid items in the filtered list

        Returns:
            Filtered items list
        """
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            # Submit the jobs in an async thread to avoid locking up the UI
            tasks = await loop.run_in_executor(pool, cls._submit_jobs, items, predicates, loop, pool)
            await asyncio.gather(*tasks)

        # Filter out the invalid items
        if include_invalid_parents:
            return list(filter(lambda f: f.is_valid or f.is_child_valid, items))
        return list(filter(lambda f: f.is_valid, items))

    @classmethod
    def _submit_jobs(
        cls,
        items: Iterable[StageManagerItem],
        predicates: Iterable[Callable[[StageManagerItem], bool]],
        loop: asyncio.AbstractEventLoop,
        pool: concurrent.futures.ThreadPoolExecutor,
    ) -> list[asyncio.Future]:
        """
        Submit jobs to update the item state in parallel

        Args:
            items: The items to update
            predicates: The predicates to apply
            loop: The Asyncio event loop
            pool: The thread pool

        Returns:
            A list of futures for the submitted jobs
        """
        futures = []
        for item in items:
            # Reset the filter state
            item.reset_filter_state()
            # Start filtering
            futures.append(loop.run_in_executor(pool, cls._update_item_state, item, predicates))
        return futures

    @classmethod
    def _update_item_state(cls, item: StageManagerItem, predicates: Iterable[Callable[[StageManagerItem], bool]]):
        """
        Update the item state based on the predicates

        Args:
            item: The item to update
            predicates: The predicates to apply
        """
        item.is_valid = all(predicate(item) for predicate in predicates)

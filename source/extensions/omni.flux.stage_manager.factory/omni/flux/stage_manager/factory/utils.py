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

from typing import Callable, Iterable

from .items import StageManagerItem as _StageManagerItem


class StageManagerUtils:

    @staticmethod
    def filter_items(
        items: Iterable[_StageManagerItem], predicates: Iterable[Callable[[_StageManagerItem], bool]]
    ) -> list[_StageManagerItem]:
        """
        Filter the given items using the given filter predicates.

        Filter the items from bottom to top to make sure the children are filtered before the parent.

        Items with at least 1 valid child will be kept to ensure they appear in the UI.

        Args:
            items: A list of items to filter
            predicates: A list of predicates to execute on each item

        Returns:
            The list of filtered items
        """

        def filter_item(item):
            valid_children = []
            for child in item.children:
                if filter_item(child) is None:
                    continue
                valid_children.append(child)

            if all(predicate(item) for predicate in predicates) or valid_children:
                # Create a new item with valid children instead of modifying original
                return _StageManagerItem(item.identifier, item.data, children=valid_children)
            return None

        return [item for item in map(filter_item, items) if item is not None]

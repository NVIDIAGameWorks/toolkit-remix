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

import omni.kit.test
from omni.flux.stage_manager.factory.items import StageManagerItem
from omni.flux.stage_manager.factory.plugins.filter_plugin import FilterCategory, StageManagerFilterPlugin
from omni.flux.stage_manager.factory.utils import StageManagerUtils, _filter_result_closed

__all__ = ["TestStageManagerUtils"]


def _make_tree(spec):
    """Build items from (identifier, parent_index) spec. parent_index None = root."""
    items = []
    for identifier, parent_idx in spec:
        parent = items[parent_idx] if parent_idx is not None else None
        items.append(StageManagerItem(identifier, data=None, parent=parent))
    return items


def _single_predicate_result(items, predicate):
    """Same set as filter_items with one predicate: pass + ancestors (via is_valid propagation)."""
    for item in items:
        item.reset_filter_state()
    for item in items:
        item.is_valid = predicate(item)
    return [item for item in items if item.is_valid or item.is_child_valid]


class _TestFilterPlugin(StageManagerFilterPlugin):
    """Minimal filter plugin for tests."""

    def __init__(self, predicate, category=FilterCategory.OTHER, active=True, **kwargs):
        super().__init__(display_name="TestFilter", tooltip="For tests", **kwargs)
        self._predicate = predicate
        self.filter_category = category
        self._filter_active = active

    def filter_predicate(self, item):  # noqa F401
        return self._predicate(item)

    @property
    def filter_active(self):
        return self._filter_active

    def build_ui(self, *args, **kwargs):
        pass


class TestStageManagerUtils(omni.kit.test.AsyncTestCase):
    async def test_filter_result_closed_matches_single_predicate_filter_items(self):
        # Arrange: root -> a -> b -> c, predicate keeps only "b"
        def predicate(item):  # noqa F401
            return item.identifier == "b"

        items = _make_tree([("r", None), ("a", 0), ("b", 1), ("c", 2)])
        universe = set(items)

        # Act
        closed = _filter_result_closed(universe, predicate)
        expected = set(_single_predicate_result(items, predicate))

        # Assert
        self.assertEqual(closed, expected)
        self.assertIn(items[0], closed)  # root ancestor
        self.assertIn(items[1], closed)  # a ancestor
        self.assertIn(items[2], closed)  # b passes
        self.assertNotIn(items[3], closed)

    async def test_filter_result_closed_multiple_leaves_includes_shared_ancestors(self):
        # Arrange: root -> a, b; predicate keeps a and b
        def predicate(item):  # noqa F401
            return item.identifier in ("a", "b")

        items = _make_tree([("root", None), ("a", 0), ("b", 0)])
        universe = set(items)

        # Act
        closed = _filter_result_closed(universe, predicate)
        expected = set(_single_predicate_result(items, predicate))

        # Assert
        self.assertEqual(closed, expected)
        self.assertEqual(len(closed), 3)

    async def test_filter_result_closed_with_ancestor_universe_does_not_add_outside(self):
        # Arrange
        def predicate(item):  # noqa F401
            return item.identifier == "b"

        items = _make_tree([("r", None), ("a", 0), ("b", 1)])
        universe = set(items)

        # Act
        closed = _filter_result_closed(universe, predicate, ancestor_universe=universe)

        # Assert
        self.assertEqual(closed, {items[0], items[1], items[2]})

    async def test_filter_items_by_category_single_plugin_matches_single_predicate_set(self):
        # Arrange: root -> a -> b -> c, one plugin keeps "b"
        def predicate(item):  # noqa F401
            return item.identifier == "b"

        items = _make_tree([("r", None), ("a", 0), ("b", 1), ("c", 2)])
        plugin = _TestFilterPlugin(predicate, category=FilterCategory.OTHER)

        # Act
        result = StageManagerUtils.filter_items_by_category(items, [plugin])
        expected = set(_single_predicate_result(items, predicate))

        # Assert
        self.assertEqual(set(result), expected)

    async def test_filter_items_by_category_single_plugin_result_sorted_by_depth(self):
        # Arrange: predicate keeps "a" and "c"
        def predicate(item):  # noqa F401
            return item.identifier in ("a", "c")

        items = _make_tree([("r", None), ("a", 0), ("b", 1), ("c", 2)])
        plugin = _TestFilterPlugin(predicate, category=FilterCategory.OTHER)

        # Act
        result = StageManagerUtils.filter_items_by_category(items, [plugin])
        depths = [StageManagerUtils._get_depth(item) for item in result]

        # Assert
        self.assertEqual(depths, sorted(depths))
        self.assertEqual(set(result), set(_single_predicate_result(items, predicate)))

    async def test_filter_items_by_category_single_prim_filter_same_semantics_as_other(self):
        # Arrange
        def predicate(item):  # noqa F401
            return item.identifier == "x"

        items = _make_tree([("r", None), ("x", 0), ("y", 0)])
        plugin = _TestFilterPlugin(predicate, category=FilterCategory.PRIMS)

        # Act
        result = StageManagerUtils.filter_items_by_category(items, [plugin])
        expected = set(_single_predicate_result(items, predicate))

        # Assert
        self.assertEqual(set(result), expected)

    async def test_filter_items_by_category_result_always_sorted_by_depth(self):
        # Arrange
        def predicate(item):  # noqa F401
            return True

        items = _make_tree([("r", None), ("a", 0), ("b", 1), ("c", 1)])
        plugin = _TestFilterPlugin(predicate, category=FilterCategory.OTHER)

        # Act
        result = StageManagerUtils.filter_items_by_category(items, [plugin])
        depths = [StageManagerUtils._get_depth(item) for item in result]

        # Assert
        self.assertEqual(depths, sorted(depths))

    async def test_filter_items_by_category_same_input_yields_same_ordered_result(self):
        # Arrange
        def predicate(item):  # noqa F401
            return item.identifier != "b"

        items = _make_tree([("r", None), ("a", 0), ("b", 1)])
        plugin = _TestFilterPlugin(predicate, category=FilterCategory.OTHER)

        # Act
        result_1 = StageManagerUtils.filter_items_by_category(items, [plugin])
        result_2 = StageManagerUtils.filter_items_by_category(items, [plugin])

        # Assert
        self.assertEqual(result_1, result_2)

    async def test_filter_items_by_category_accepts_iterable_same_result_as_list(self):
        # Arrange
        def predicate(item):  # noqa F401
            return True

        items = _make_tree([("r", None), ("a", 0)])
        plugin = _TestFilterPlugin(predicate, category=FilterCategory.OTHER)

        # Act
        result_list = StageManagerUtils.filter_items_by_category(items, [plugin])
        result_iter = StageManagerUtils.filter_items_by_category(iter(items), [plugin])

        # Assert
        self.assertEqual(result_list, result_iter)

    async def test_filter_items_by_category_and_narrows_candidates_second_predicate_on_subset_only(self):
        # Arrange: root -> a -> b -> c. First filter keeps root,a. Second runs only on that subset.
        items = _make_tree([("root", None), ("a", 0), ("b", 1), ("c", 2)])
        call_counts = {id(item): 0 for item in items}

        def count_and_pass(item):
            call_counts[id(item)] += 1
            return True

        def only_a(item):
            call_counts[id(item)] += 1
            return item.identifier == "a"

        plugin_1 = _TestFilterPlugin(only_a, category=FilterCategory.OTHER)
        plugin_2 = _TestFilterPlugin(count_and_pass, category=FilterCategory.OTHER)

        # Act
        StageManagerUtils.filter_items_by_category(items, [plugin_1, plugin_2])

        # Assert: root and a seen by both; b and c only by first (then out of candidates)
        self.assertEqual(call_counts[id(items[0])], 2)
        self.assertEqual(call_counts[id(items[1])], 2)
        self.assertEqual(call_counts[id(items[2])], 1)
        self.assertEqual(call_counts[id(items[3])], 1)

    async def test_filter_items_by_category_inactive_prim_filter_skipped(self):
        # Arrange: PRIMS is OR category; filter_active=False is skipped
        def track(item):
            called.append(item)
            return True

        def predicate_none(item):  # noqa F401
            return None

        items = _make_tree([("r", None), ("a", 0)])
        called = []

        active_plugin = _TestFilterPlugin(track, category=FilterCategory.PRIMS, active=True)
        inactive_plugin = _TestFilterPlugin(predicate_none, category=FilterCategory.PRIMS, active=False)

        # Act
        StageManagerUtils.filter_items_by_category(items, [active_plugin, inactive_plugin])

        # Assert
        self.assertEqual(len(called), 2)

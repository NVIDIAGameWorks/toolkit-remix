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

from unittest.mock import Mock, patch

import carb
import omni.kit.test
from omni.flux.stage_manager.factory.plugins.filter_plugin import FilterCategory
from omni.flux.stage_manager.plugin.filter.usd.additional_filters import (
    EXCLUDE_FILTERS,
    AdditionalFilterPlugin,
    AdditionalFiltersPopupMenuDelegate,
    AdditionalFiltersPopupMenuItemDelegate,
)
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin, ToggleableUSDFilterPlugin
from pydantic import Field

__all__ = ["TestAdditionalFiltersUnit"]

_CORE_PATCH = "omni.flux.stage_manager.plugin.filter.usd.additional_filters._get_stage_manager_core_instance"


# ---------------------------------------------------------------------------
# Test filter fixtures
# ---------------------------------------------------------------------------


class _TestFilter(StageManagerUSDFilterPlugin):
    """Non-toggleable filter with a configurable field for testing _is_filter_modified."""

    display_name: str = Field(default="Test Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)
    some_value: str = Field(default="default")
    filter_category: FilterCategory = Field(default=FilterCategory.OTHER)

    def filter_predicate(self, item):
        return True

    def build_ui(self):
        pass


class _TestToggleableFilter(ToggleableUSDFilterPlugin):
    """Toggleable filter with a configurable field for testing _is_filter_modified."""

    display_name: str = Field(default="Test Toggleable Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)
    some_value: str = Field(default="default")
    filter_category: FilterCategory = Field(default=FilterCategory.PRIMS)

    def _filter_predicate(self, prim):
        return True

    def build_ui(self):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdditionalFiltersUnit(omni.kit.test.AsyncTestCase):
    # ------------------------------------------------------------------
    # Group 1 — AdditionalFilterPlugin.filter_predicate
    # ------------------------------------------------------------------

    async def test_filter_predicate_should_always_return_true(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        item = Mock()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # Group 2 — AdditionalFilterPlugin._is_filter_modified
    # ------------------------------------------------------------------

    async def test_is_filter_modified_all_defaults_should_return_false(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestFilter()

        # Act
        result = plugin._is_filter_modified(filter_obj)

        # Assert
        self.assertFalse(result)

    async def test_is_filter_modified_non_default_field_value_should_return_true(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestFilter(some_value="changed")

        # Act
        result = plugin._is_filter_modified(filter_obj)

        # Assert
        self.assertTrue(result)

    async def test_is_filter_modified_filter_active_false_should_return_false(self):
        # Arrange: filter_active=False is treated as the "inactive" state and skipped
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestToggleableFilter(filter_active=False)

        # Act
        result = plugin._is_filter_modified(filter_obj)

        # Assert
        self.assertFalse(result)

    async def test_is_filter_modified_filter_active_true_should_return_true(self):
        # Arrange: filter_active=True means the filter was explicitly enabled
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestToggleableFilter(filter_active=True)

        # Act
        result = plugin._is_filter_modified(filter_obj)

        # Assert
        self.assertTrue(result)

    async def test_is_filter_modified_excluded_fields_should_not_affect_result(self):
        # Arrange: display_name, tooltip, and enabled are in the skip set
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestToggleableFilter(filter_active=False)
        filter_obj.display_name = "Changed Name"  # excluded field — should not count

        # Act
        result = plugin._is_filter_modified(filter_obj)

        # Assert
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # Group 3 — AdditionalFilterPlugin._update_active_filters
    # ------------------------------------------------------------------

    async def test_update_active_filters_updates_value_dict_with_filter_active_state(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestToggleableFilter(filter_active=False)
        plugin._active_filters = [[filter_obj, {"filter_active": False}]]
        filter_obj.filter_active = True

        # Act
        plugin._update_active_filters()

        # Assert
        self.assertTrue(plugin._active_filters[0][1]["filter_active"])

    async def test_update_active_filters_adds_modified_filter_to_modified_filters(self):
        # Arrange: filter_active=True makes the filter "modified"
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestToggleableFilter(filter_active=True)
        plugin._active_filters = [[filter_obj, {"filter_active": True}]]

        # Act
        plugin._update_active_filters()

        # Assert
        self.assertIn(filter_obj, plugin._modified_filters)

    async def test_update_active_filters_removes_unmodified_filter_from_modified_filters(self):
        # Arrange: filter was previously modified but is now back at defaults
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestToggleableFilter(filter_active=False)
        plugin._active_filters = [[filter_obj, {"filter_active": False}]]
        plugin._modified_filters = [filter_obj]  # was previously in modified list

        # Act
        plugin._update_active_filters()

        # Assert
        self.assertNotIn(filter_obj, plugin._modified_filters)

    # ------------------------------------------------------------------
    # Group 4 — AdditionalFilterPlugin._get_available_filters
    # ------------------------------------------------------------------

    async def test_get_available_filters_no_active_interaction_returns_empty_list(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        with patch(_CORE_PATCH) as core_mock:
            core_mock.return_value.get_active_interaction.return_value = None

            # Act
            result = plugin._get_available_filters()

        # Assert
        self.assertEqual([], result)

    async def test_get_available_filters_excludes_filters_by_name(self):
        # Arrange: a filter whose name matches one of the EXCLUDE_FILTERS entries
        plugin = AdditionalFilterPlugin()
        excluded_filter = Mock(spec=StageManagerUSDFilterPlugin)
        excluded_filter.name = EXCLUDE_FILTERS[0]  # e.g. "AdditionalFilterPlugin"

        interaction_mock = Mock()
        interaction_mock.filters = [excluded_filter]
        interaction_mock.additional_filters = []

        with patch(_CORE_PATCH) as core_mock:
            core_mock.return_value.get_active_interaction.return_value = interaction_mock

            # Act
            result = plugin._get_available_filters()

        # Assert: excluded filter is not in result
        result_filters = [item[0] for item in result]
        self.assertNotIn(excluded_filter, result_filters)

    async def test_get_available_filters_excludes_non_usd_filter_plugin_and_logs_error(self):
        # Arrange: a filter that is NOT a StageManagerUSDFilterPlugin subclass
        plugin = AdditionalFilterPlugin()
        non_usd_filter = Mock()  # plain Mock — not an instance of StageManagerUSDFilterPlugin
        non_usd_filter.name = "SomeOtherFilter"

        interaction_mock = Mock()
        interaction_mock.filters = [non_usd_filter]
        interaction_mock.additional_filters = []

        with (
            patch(_CORE_PATCH) as core_mock,
            patch.object(carb, "log_error") as log_error_mock,
        ):
            core_mock.return_value.get_active_interaction.return_value = interaction_mock

            # Act
            result = plugin._get_available_filters()

        # Assert
        result_filters = [item[0] for item in result]
        self.assertNotIn(non_usd_filter, result_filters)
        self.assertEqual(1, log_error_mock.call_count)

    async def test_get_available_filters_sorts_by_category_then_display_name(self):
        # Arrange: filters in scrambled category/name order
        plugin = AdditionalFilterPlugin()

        def _make_filter(display_name, category):
            f = Mock(spec=StageManagerUSDFilterPlugin)
            f.name = display_name
            f.display_name = display_name
            f.filter_category = category
            return f

        f_prims_b = _make_filter("B Prims Filter", FilterCategory.PRIMS)
        f_group_a = _make_filter("A Group Filter", FilterCategory.GROUP)
        f_other_z = _make_filter("Z Other Filter", FilterCategory.OTHER)
        f_prims_a = _make_filter("A Prims Filter", FilterCategory.PRIMS)
        f_other_a = _make_filter("A Other Filter", FilterCategory.OTHER)

        interaction_mock = Mock()
        interaction_mock.filters = [f_prims_b, f_group_a, f_other_z, f_prims_a, f_other_a]
        interaction_mock.additional_filters = []

        with patch(_CORE_PATCH) as core_mock:
            core_mock.return_value.get_active_interaction.return_value = interaction_mock

            # Act
            result = plugin._get_available_filters()

        # Assert: sorted OTHER first, then PRIMS, then GROUP; display_name within each
        result_filters = [item[0] for item in result]
        expected_order = [f_other_a, f_other_z, f_prims_a, f_prims_b, f_group_a]
        self.assertEqual(expected_order, result_filters)

    async def test_get_available_filters_attribute_error_returns_empty_list(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        with (
            patch(_CORE_PATCH) as core_mock,
            patch.object(carb, "log_error") as log_error_mock,
        ):
            core_mock.return_value.get_active_interaction.side_effect = AttributeError("no attr")

            # Act
            result = plugin._get_available_filters()

        # Assert
        self.assertEqual([], result)
        self.assertEqual(1, log_error_mock.call_count)

    async def test_get_available_filters_includes_additional_interaction_filters(self):
        # Arrange: one filter in .filters, one in .additional_filters
        plugin = AdditionalFilterPlugin()

        filter_main = Mock(spec=StageManagerUSDFilterPlugin)
        filter_main.name = "MainFilter"
        filter_main.display_name = "Main Filter"
        filter_main.filter_category = FilterCategory.OTHER

        filter_additional = Mock(spec=StageManagerUSDFilterPlugin)
        filter_additional.name = "AdditionalFilter"
        filter_additional.display_name = "Additional Filter"
        filter_additional.filter_category = FilterCategory.OTHER

        interaction_mock = Mock()
        interaction_mock.filters = [filter_main]
        interaction_mock.additional_filters = [filter_additional]

        with patch(_CORE_PATCH) as core_mock:
            core_mock.return_value.get_active_interaction.return_value = interaction_mock

            # Act
            result = plugin._get_available_filters()

        # Assert: both filters appear in result
        result_filters = [item[0] for item in result]
        self.assertIn(filter_main, result_filters)
        self.assertIn(filter_additional, result_filters)
        self.assertEqual(2, len(result_filters))

    # ------------------------------------------------------------------
    # Group 5 — AdditionalFilterPlugin._on_filter_changed
    # ------------------------------------------------------------------

    async def test_on_filter_changed_sets_icon_name_to_filter_active_when_modified(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        plugin._icon = Mock()
        plugin._counter_circle = None  # suppress counter update
        plugin._modified_filters = [Mock()]

        with patch.object(plugin, "_update_active_filters"):
            # Act
            plugin._on_filter_changed()

        # Assert
        self.assertEqual("FilterActive", plugin._icon.name)

    async def test_on_filter_changed_sets_icon_name_to_filter_when_not_modified(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        plugin._icon = Mock()
        plugin._counter_circle = None
        plugin._modified_filters = []

        with patch.object(plugin, "_update_active_filters"):
            # Act
            plugin._on_filter_changed()

        # Assert
        self.assertEqual("Filter", plugin._icon.name)

    async def test_on_filter_changed_shows_counter_badge_when_filters_modified(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        plugin._icon = Mock()
        plugin._counter_circle = Mock()
        plugin._counter_label = Mock()
        plugin._modified_filters = [Mock(), Mock()]  # 2 modified filters

        with patch.object(plugin, "_update_active_filters"):
            # Act
            plugin._on_filter_changed()

        # Assert
        self.assertTrue(plugin._counter_circle.visible)
        self.assertTrue(plugin._counter_label.visible)
        self.assertEqual("2", plugin._counter_label.text)

    async def test_on_filter_changed_hides_counter_badge_when_not_modified(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        plugin._icon = Mock()
        plugin._counter_circle = Mock()
        plugin._counter_label = Mock()
        plugin._modified_filters = []

        with patch.object(plugin, "_update_active_filters"):
            # Act
            plugin._on_filter_changed()

        # Assert
        self.assertFalse(plugin._counter_circle.visible)
        self.assertFalse(plugin._counter_label.visible)

    # ------------------------------------------------------------------
    # Group 6 — AdditionalFiltersPopupMenuDelegate.on_reset_all
    # ------------------------------------------------------------------

    async def test_on_reset_all_resets_toggleable_filter_active_to_false(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=True)
        delegate = AdditionalFiltersPopupMenuDelegate(
            filters=[[filter_obj, {"filter_active": True}]],
        )

        with patch.object(AdditionalFiltersPopupMenuItemDelegate, "build_item"):
            # Act
            delegate.on_reset_all()

        # Assert: both the filter plugin and its item delegate entry are reset to False
        item = delegate.items[filter_obj.filter_category][0]
        self.assertFalse(filter_obj.filter_active)
        self.assertFalse(item.filter_active)

    async def test_on_reset_all_resets_non_default_field_value_to_default(self):
        # Arrange
        filter_obj = _TestToggleableFilter(some_value="changed")
        delegate = AdditionalFiltersPopupMenuDelegate(
            filters=[[filter_obj, {}]],
        )

        with patch.object(AdditionalFiltersPopupMenuItemDelegate, "build_item"):
            # Act
            delegate.on_reset_all()

        # Assert
        self.assertEqual("default", filter_obj.some_value)

    async def test_on_reset_all_calls_on_filter_changed_fn(self):
        # Arrange
        filter_obj = _TestToggleableFilter()
        on_changed_mock = Mock()
        delegate = AdditionalFiltersPopupMenuDelegate(
            filters=[[filter_obj, {}]],
            on_filter_changed_fn=on_changed_mock,
        )

        with patch.object(AdditionalFiltersPopupMenuItemDelegate, "build_item"):
            # Act
            delegate.on_reset_all()

        # Assert
        self.assertEqual(1, on_changed_mock.call_count)

    async def test_on_reset_all_with_no_callback_does_not_raise(self):
        # Arrange
        filter_obj = _TestToggleableFilter()
        delegate = AdditionalFiltersPopupMenuDelegate(
            filters=[[filter_obj, {}]],
            on_filter_changed_fn=None,
        )

        with patch.object(AdditionalFiltersPopupMenuItemDelegate, "build_item"):
            # Act / Assert: no exception raised
            delegate.on_reset_all()

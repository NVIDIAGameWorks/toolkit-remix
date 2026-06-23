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
import omni.kit.ui_test as ui_test
import omni.ui as ui
from omni.flux.stage_manager.factory.plugins.filter_plugin import FilterCategory
from omni.flux.stage_manager.plugin.filter.usd.additional_filters import (
    EXCLUDE_FILTERS,
    AdditionalFilterPlugin,
    AdditionalFiltersPopupMenu,
    AdditionalFiltersPopupMenuDelegate,
    AdditionalFiltersPopupMenuItemDelegate,
    _clamp_filter_popup_x,
    _get_filter_popup_body_height,
)
from omni.flux.stage_manager.plugin.filter.usd.base import (
    CheckboxGroupFilterPlugin,
    StageManagerUSDFilterPlugin,
    ToggleableUSDFilterPlugin,
)
from pydantic import Field

__all__ = ["TestAdditionalFiltersUnit"]

_CORE_PATCH = "omni.flux.stage_manager.plugin.filter.usd.additional_filters._get_stage_manager_core_instance"
_APP_WINDOW_WIDTH_PATCH = "omni.flux.stage_manager.plugin.filter.usd.additional_filters._get_app_window_width_points"
_APP_WINDOW_HEIGHT_PATCH = "omni.flux.stage_manager.plugin.filter.usd.additional_filters._get_app_window_height_points"


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
    refresh_count: int = Field(default=0, exclude=True)

    def _filter_predicate(self, prim):
        return True

    def build_ui(self):
        pass

    def refresh_filter_items(self):
        self.refresh_count += 1


class _TestCheckboxGroupFilter(CheckboxGroupFilterPlugin):
    """Checkbox-group filter for testing category-level bulk actions."""

    display_name: str = Field(default="Test Checkbox Group Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)
    selected: bool = Field(default=False)
    filter_category: FilterCategory = Field(default=FilterCategory.TAGS)

    def filter_predicate(self, item):
        return True

    def build_ui(self):
        pass

    def _set_all_selected(self, enabled: bool) -> None:
        self.selected = enabled

    def can_set_all_selected(self, enabled: bool) -> bool:
        return self.selected != enabled


class _TestFixedHeightFilter(StageManagerUSDFilterPlugin):
    """Filter that builds a fixed-height row for layout sizing tests."""

    display_name: str = Field(default="Fixed Height Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)
    filter_category: FilterCategory = Field(default=FilterCategory.OTHER)
    row_height: int = Field(default=24, exclude=True)

    def filter_predicate(self, item):
        return True

    def build_ui(self):
        ui.Spacer(height=ui.Pixel(self.row_height))


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

    async def test_filter_active_should_return_false(self):
        # Arrange
        plugin = AdditionalFilterPlugin()

        # Act
        filter_active = plugin.filter_active

        # Assert
        self.assertFalse(filter_active)

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

    async def test_is_filter_modified_filter_active_field_true_should_return_true(self):
        # Arrange: filter_active is runtime state, but Additional Filters still uses it as modified state
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestToggleableFilter(filter_active=True)

        # Act
        result = plugin._is_filter_modified(filter_obj)

        # Assert
        self.assertFalse(filter_obj.model_fields["filter_active"].exclude)
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

    async def test_is_filter_modified_display_false_should_return_false(self):
        # Arrange: display=False is UI placement configuration and should not count as user-edited filter state
        plugin = AdditionalFilterPlugin()
        filter_obj = _TestFilter(display=False)

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

        # Assert: sorted OTHER first, then PRIMS, then GROUP, then TAGS; display_name within each
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

    async def test_get_available_filters_deduplicates_same_name_in_filters_and_additional_filters(self):
        # Arrange: same plugin name in both .filters and .additional_filters (e.g. CustomTagsFilterPlugin
        # listed in compatible_filters and also in additional_filters)
        plugin = AdditionalFilterPlugin()

        dup_in_filters = Mock(spec=StageManagerUSDFilterPlugin)
        dup_in_filters.name = "DuplicateFilter"
        dup_in_filters.display_name = "Duplicate Filter"
        dup_in_filters.filter_category = FilterCategory.OTHER

        dup_in_additional = Mock(spec=StageManagerUSDFilterPlugin)
        dup_in_additional.name = "DuplicateFilter"
        dup_in_additional.display_name = "Duplicate Filter"
        dup_in_additional.filter_category = FilterCategory.OTHER

        interaction_mock = Mock()
        interaction_mock.filters = [dup_in_filters]
        interaction_mock.additional_filters = [dup_in_additional]

        with patch(_CORE_PATCH) as core_mock:
            core_mock.return_value.get_active_interaction.return_value = interaction_mock

            # Act
            result = plugin._get_available_filters()

        # Assert: only one entry despite the same name appearing in both lists
        self.assertEqual(1, len(result))

    async def test_has_bulk_actions_should_return_true_for_or_checkbox_category(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=False, filter_category=FilterCategory.PRIMS)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {"filter_active": False}]])

        # Act
        result = delegate.has_bulk_actions(FilterCategory.PRIMS)

        # Assert
        self.assertTrue(result)

    async def test_has_bulk_actions_should_return_true_for_checkbox_group_category(self):
        # Arrange
        filter_obj = _TestCheckboxGroupFilter(selected=False, filter_category=FilterCategory.TAGS)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {}]])

        # Act
        result = delegate.has_bulk_actions(FilterCategory.TAGS)

        # Assert
        self.assertTrue(result)

    async def test_has_bulk_actions_should_return_false_for_plain_filter_in_or_category(self):
        # Arrange
        filter_obj = _TestFilter(filter_category=FilterCategory.TAGS)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {}]])

        # Act
        result = delegate.has_bulk_actions(FilterCategory.TAGS)

        # Assert
        self.assertFalse(result)

    async def test_has_bulk_actions_should_return_false_for_and_checkbox_category(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=False, filter_category=FilterCategory.OTHER)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {"filter_active": False}]])

        # Act
        result = delegate.has_bulk_actions(FilterCategory.OTHER)

        # Assert
        self.assertFalse(result)

    async def test_has_bulk_actions_should_return_false_for_non_group_checkbox_in_and_category(self):
        # Arrange
        filter_obj = _TestCheckboxGroupFilter(selected=False, filter_category=FilterCategory.OTHER)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {}]])

        # Act
        result = delegate.has_bulk_actions(FilterCategory.OTHER)

        # Assert
        self.assertFalse(result)

    async def test_can_set_all_selected_should_return_true_when_action_would_change_or_category(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=False, filter_category=FilterCategory.GROUP)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {"filter_active": False}]])

        # Act
        result = delegate.can_set_all_selected(FilterCategory.GROUP, True)

        # Assert
        self.assertTrue(result)

    async def test_can_set_all_selected_should_return_false_when_action_would_not_change_or_category(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=True, filter_category=FilterCategory.GROUP)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {"filter_active": True}]])

        # Act
        result = delegate.can_set_all_selected(FilterCategory.GROUP, True)

        # Assert
        self.assertFalse(result)

    async def test_can_set_all_selected_should_return_false_when_checkbox_group_would_not_change(self):
        # Arrange
        filter_obj = _TestCheckboxGroupFilter(selected=True, filter_category=FilterCategory.TAGS)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {}]])

        # Act
        result = delegate.can_set_all_selected(FilterCategory.TAGS, True)

        # Assert
        self.assertFalse(result)

    async def test_can_set_all_selected_should_return_true_when_action_would_change_checkbox_group(self):
        # Arrange
        filter_obj = _TestCheckboxGroupFilter(selected=False, filter_category=FilterCategory.TAGS)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {}]])

        # Act
        result = delegate.can_set_all_selected(FilterCategory.TAGS, True)

        # Assert
        self.assertTrue(result)

    async def test_set_all_selected_should_update_or_category_filter(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=False, filter_category=FilterCategory.PRIMS)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {"filter_active": False}]])
        item = delegate.items[FilterCategory.PRIMS][0]

        with patch.object(AdditionalFiltersPopupMenuItemDelegate, "build_item") as build_item_mock:
            # Act
            result = delegate.set_all_selected(FilterCategory.PRIMS, True)

        # Assert
        self.assertTrue(result)
        self.assertTrue(filter_obj.filter_active)
        self.assertTrue(item.filter_active)
        build_item_mock.assert_called_once()
        self.assertEqual(1, filter_obj.refresh_count)

    async def test_set_all_selected_should_not_update_or_category_filter_that_already_matches(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=True, filter_category=FilterCategory.PRIMS)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {"filter_active": True}]])

        with patch.object(AdditionalFiltersPopupMenuItemDelegate, "build_item") as build_item_mock:
            # Act
            result = delegate.set_all_selected(FilterCategory.PRIMS, True)

        # Assert
        self.assertFalse(result)
        self.assertTrue(filter_obj.filter_active)
        build_item_mock.assert_not_called()
        self.assertEqual(0, filter_obj.refresh_count)

    async def test_set_all_selected_should_update_checkbox_group_filter(self):
        # Arrange
        filter_obj = _TestCheckboxGroupFilter(selected=False, filter_category=FilterCategory.TAGS)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {}]])

        # Act
        result = delegate.set_all_selected(FilterCategory.TAGS, True)

        # Assert
        self.assertTrue(result)
        self.assertTrue(filter_obj.selected)

    async def test_set_all_selected_should_not_update_and_category_filter(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=False, filter_category=FilterCategory.OTHER)
        delegate = AdditionalFiltersPopupMenuDelegate(filters=[[filter_obj, {"filter_active": False}]])

        # Act
        result = delegate.set_all_selected(FilterCategory.OTHER, True)

        # Assert
        self.assertFalse(result)
        self.assertFalse(filter_obj.filter_active)

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

    async def test_on_button_clicked_clamps_popup_inside_app_window(self):
        # Arrange
        plugin = AdditionalFilterPlugin()
        plugin._active_filters = []
        plugin._icon = Mock()
        plugin._icon.screen_position_x = 500
        plugin._icon.screen_position_y = 100
        plugin._icon.computed_height = 24

        expected_x = _clamp_filter_popup_x(plugin._icon.screen_position_x, 600)

        with (
            patch.object(plugin, "_update_active_filters"),
            patch(_APP_WINDOW_WIDTH_PATCH, return_value=600),
            patch(_APP_WINDOW_HEIGHT_PATCH, return_value=900),
            patch.object(AdditionalFiltersPopupMenu, "show_at") as show_at_mock,
        ):
            # Act
            plugin._on_button_clicked()

        # Assert
        show_at_mock.assert_called_once_with(expected_x, 124)

    async def test_get_filter_popup_body_height_clamps_to_available_app_window_height(self):
        # Arrange
        with patch(_APP_WINDOW_HEIGHT_PATCH, return_value=500):
            # Act
            result = _get_filter_popup_body_height(400)

        # Assert
        self.assertEqual(64, result)

    async def test_popup_menu_body_height_uses_computed_content_height_when_below_max(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=False, filter_category=FilterCategory.PRIMS)
        filters = [[filter_obj, {"filter_active": False}]]
        menu = AdditionalFiltersPopupMenu("Additional Filters", filters, body_height=500)
        scrolling_frame = Mock()
        scrolling_frame.computed_content_height = 120
        scrolling_frame.scroll_y_max = 0
        menu._scrolling_frame = scrolling_frame

        try:
            # Act
            menu._update_body_height()

            # Assert
            self.assertEqual(120, scrolling_frame.height.value)
        finally:
            menu.destroy()

    async def test_popup_menu_body_height_caps_to_available_height(self):
        # Arrange
        filter_obj = _TestToggleableFilter(filter_active=False, filter_category=FilterCategory.PRIMS)
        filters = [[filter_obj, {"filter_active": False}]]
        menu = AdditionalFiltersPopupMenu("Additional Filters", filters, body_height=500)
        scrolling_frame = Mock()
        scrolling_frame.computed_content_height = 600
        scrolling_frame.scroll_y_max = 0
        menu._scrolling_frame = scrolling_frame

        try:
            # Act
            menu._update_body_height()

            # Assert
            self.assertEqual(500, scrolling_frame.height.value)
        finally:
            menu.destroy()

    async def test_popup_menu_body_height_shrinks_after_real_layout(self):
        # Arrange
        filters = [
            [_TestFixedHeightFilter(filter_category=FilterCategory.OTHER), {}],
            [_TestFixedHeightFilter(filter_category=FilterCategory.PRIMS), {}],
        ]
        menu = AdditionalFiltersPopupMenu("Additional Filters", filters, body_height=500)
        window = ui.Window("TestAdditionalFiltersPopupLayout", width=400, height=600)

        try:
            # Act
            with window.frame:
                menu.build_menu_items()
            await ui_test.human_delay()
            menu._update_body_height()

            # Assert
            self.assertIsNotNone(menu._scrolling_frame)
            self.assertGreater(menu._scrolling_frame.computed_content_height, 0)
            self.assertLess(menu._scrolling_frame.height.value, 500)
        finally:
            menu.destroy()
            window.destroy()

    async def test_popup_menu_body_height_keeps_max_when_scrollable_after_real_layout(self):
        # Arrange
        filters = [
            [_TestFixedHeightFilter(filter_category=FilterCategory.PRIMS), {"filter_active": False}] for _ in range(24)
        ]
        menu = AdditionalFiltersPopupMenu("Additional Filters", filters, body_height=500)
        window = ui.Window("TestAdditionalFiltersPopupTallLayout", width=400, height=700)

        try:
            # Act
            with window.frame:
                menu.build_menu_items()
            await ui_test.human_delay()
            menu._update_body_height()

            # Assert
            self.assertIsNotNone(menu._scrolling_frame)
            self.assertGreater(menu._scrolling_frame.scroll_y_max, 0)
            self.assertEqual(500, menu._scrolling_frame.height.value)
        finally:
            menu.destroy()
            window.destroy()

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

    async def test_on_reset_all_preserves_hidden_filter_display_state(self):
        # Arrange: display controls whether the filter appears in this UI, so Reset All should not alter it
        filter_obj = _TestToggleableFilter(display=False, some_value="changed")
        delegate = AdditionalFiltersPopupMenuDelegate(
            filters=[[filter_obj, {}]],
        )

        with patch.object(AdditionalFiltersPopupMenuItemDelegate, "build_item"):
            # Act
            delegate.on_reset_all()

        # Assert
        self.assertFalse(filter_obj.display)
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
            # Act
            delegate.on_reset_all()

        # Assert
        # No exception is raised.

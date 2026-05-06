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

from omni import ui
from omni.kit import ui_test
import omni.kit.test
from omni.flux.stage_manager.factory.plugins.filter_plugin import FilterCategory
from omni.flux.stage_manager.plugin.filter.usd.additional_filters import AdditionalFiltersPopupMenuItemDelegate
from omni.flux.stage_manager.plugin.filter.usd.custom_tags import CustomTagsFilterPlugin
from omni.flux.stage_manager.plugin.filter.usd.custom_tags import _get_tag_checkbox_identifier
from pxr import Sdf

__all__ = ["TestCustomTagsFilterPluginUnit"]

_TAG_CAR = "/World/CustomTags.collection:car"
_TAG_RED = "/World/CustomTags.collection:red"
_UNTAGGED_CHECKBOX_IDENTIFIER = "filter_checkbox_custom_tags_untagged"


def _make_item(prim_path: str = "/World/Car"):
    mock_prim = Mock()
    mock_prim.GetPath.return_value = Mock()
    mock_prim.GetPath.return_value.__str__ = lambda s: prim_path
    mock_item = Mock()
    mock_item.data = mock_prim
    return mock_item


def _make_plugin_with_core(**kwargs) -> CustomTagsFilterPlugin:
    plugin = CustomTagsFilterPlugin(**kwargs)
    plugin._core = Mock()
    plugin._core.get_all_tags.return_value = []
    plugin._core.prim_has_any_tag.return_value = False
    plugin._core.get_tag_prims.return_value = []
    plugin._filter_enabled = True
    return plugin


class TestCustomTagsFilterPluginUnit(omni.kit.test.AsyncTestCase):
    # ------------------------------------------------------------------
    # Group 1 — Defaults
    # ------------------------------------------------------------------

    async def test_selected_tags_should_be_empty_by_default(self):
        # Arrange
        plugin = CustomTagsFilterPlugin()

        # Act
        result = plugin.selected_tags

        # Assert
        self.assertEqual([], result)

    async def test_include_untagged_should_be_false_by_default(self):
        # Arrange
        plugin = CustomTagsFilterPlugin()

        # Act
        result = plugin.include_untagged

        # Assert
        self.assertFalse(result)

    async def test_filter_category_should_be_tags_by_default(self):
        # Arrange
        plugin = CustomTagsFilterPlugin()

        # Act
        result = plugin.filter_category

        # Assert
        self.assertEqual(FilterCategory.TAGS, result)

    async def test_display_name_should_be_custom_tags_by_default(self):
        # Arrange
        plugin = CustomTagsFilterPlugin()

        # Act
        result = plugin.display_name

        # Assert
        self.assertEqual("Custom Tags Filter", result)

    async def test_tag_checkbox_identifier_should_be_widget_safe(self):
        # Act
        result = _get_tag_checkbox_identifier(_TAG_CAR)

        # Assert
        self.assertEqual("filter_checkbox_custom_tags_World_CustomTags_collection_car", result)

    async def test_build_ui_should_build_tag_rows_with_path_based_tags(self):
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]
        tag_checkbox_identifier = _get_tag_checkbox_identifier(_TAG_CAR)
        window = ui.Window("TestCustomTagsFilterPlugin", width=300, height=300)

        try:
            # Act
            with window.frame:
                plugin.build_ui()
            await ui_test.human_delay()

            # Assert
            tag_checkbox = ui_test.find(f"{window.title}//Frame/**/CheckBox[*].identifier=='{tag_checkbox_identifier}'")
            self.assertIsNotNone(plugin._checkboxes_frame)
            self.assertGreater(plugin._checkboxes_frame.computed_height, 0)
            self.assertGreater(plugin._checkboxes_frame.computed_width, 0)
            self.assertIsNotNone(tag_checkbox)
            self.assertGreater(tag_checkbox.widget.computed_height, 0)
            self.assertGreater(tag_checkbox.widget.computed_width, 0)
            plugin._core.refresh_stage.assert_called()
        finally:
            plugin.destroy()
            window.destroy()

    async def test_build_ui_should_align_tag_checkboxes_with_untagged_checkbox(self):
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)]
        tag_checkbox_identifier = _get_tag_checkbox_identifier(_TAG_CAR)
        red_checkbox_identifier = _get_tag_checkbox_identifier(_TAG_RED)
        window = ui.Window("TestCustomTagsFilterPluginAlignment", width=320, height=300)

        try:
            # Act
            with window.frame:
                plugin.build_ui()
            await ui_test.human_delay()

            # Assert
            untagged_checkbox = ui_test.find(
                f"{window.title}//Frame/**/CheckBox[*].identifier=='{_UNTAGGED_CHECKBOX_IDENTIFIER}'"
            )
            tag_checkbox = ui_test.find(f"{window.title}//Frame/**/CheckBox[*].identifier=='{tag_checkbox_identifier}'")
            red_checkbox = ui_test.find(f"{window.title}//Frame/**/CheckBox[*].identifier=='{red_checkbox_identifier}'")

            self.assertIsNotNone(untagged_checkbox)
            self.assertIsNotNone(tag_checkbox)
            self.assertIsNotNone(red_checkbox)
            self.assertGreater(untagged_checkbox.widget.computed_width, 0)
            self.assertAlmostEqual(
                untagged_checkbox.widget.screen_position_x, tag_checkbox.widget.screen_position_x, delta=1
            )
            self.assertAlmostEqual(
                untagged_checkbox.widget.screen_position_x, red_checkbox.widget.screen_position_x, delta=1
            )
        finally:
            plugin.destroy()
            window.destroy()

    async def test_get_checkboxes_height_should_not_include_leading_spacing(self):
        # Arrange
        plugin = _make_plugin_with_core()

        # Act
        result = plugin._get_checkboxes_height([Sdf.Path(_TAG_CAR)])

        # Assert
        self.assertEqual(40, result)

    async def test_get_checkboxes_height_should_return_full_uncapped_tag_list_height(self):
        # Arrange
        plugin = _make_plugin_with_core()
        tags = [Sdf.Path(f"/World/CustomTags.collection:tag_{i}") for i in range(10)]

        # Act
        result = plugin._get_checkboxes_height(tags)

        # Assert
        self.assertEqual(238, result)

    async def test_build_ui_should_refresh_stale_core_stage_before_querying_tags(self):
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._all_tag_paths = []
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]
        tag_checkbox_identifier = _get_tag_checkbox_identifier(_TAG_CAR)
        window = ui.Window("TestCustomTagsFilterPluginRefresh", width=300, height=300)

        try:
            # Act
            with window.frame:
                plugin.build_ui()
            await ui_test.human_delay()

            # Assert
            self.assertIsNotNone(
                ui_test.find(f"{window.title}//Frame/**/CheckBox[*].identifier=='{tag_checkbox_identifier}'")
            )
            plugin._core.refresh_stage.assert_called()
        finally:
            plugin.destroy()
            window.destroy()

    async def test_popup_item_should_render_tag_rows_with_width(self):
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]
        tag_checkbox_identifier = _get_tag_checkbox_identifier(_TAG_CAR)
        item = AdditionalFiltersPopupMenuItemDelegate(plugin, {})
        window = ui.Window("TestCustomTagsFilterPopupItem", width=320, height=300)

        try:
            # Act
            with window.frame:
                item.build_item()
            await ui_test.human_delay()

            # Assert
            tag_checkbox = ui_test.find(f"{window.title}//Frame/**/CheckBox[*].identifier=='{tag_checkbox_identifier}'")
            self.assertIsNotNone(tag_checkbox)
            self.assertGreater(item.container.computed_width, 0)
            self.assertGreater(tag_checkbox.widget.computed_width, 0)
        finally:
            item.destroy()
            plugin.destroy()
            window.destroy()

    # ------------------------------------------------------------------
    # Group 2 — filter_predicate: passthrough cases
    # ------------------------------------------------------------------

    async def test_filter_predicate_should_return_true_when_no_tags_selected(self):
        # Arrange: no selected_tags and include_untagged=False → passthrough, no filtering
        plugin = _make_plugin_with_core()
        item = _make_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_filter_predicate_should_return_true_when_core_is_none(self):
        # Arrange: _core is None (set_context_name not called); filter cannot evaluate
        plugin = CustomTagsFilterPlugin(selected_tags=[_TAG_CAR])
        plugin._filter_enabled = True
        item = _make_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert: all prims pass through when core is unavailable
        self.assertTrue(result)

    async def test_filter_predicate_should_return_true_when_filter_is_disabled(self):
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR])
        plugin._filter_enabled = False
        item = _make_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        plugin._core.prim_has_any_tag.assert_not_called()

    # ------------------------------------------------------------------
    # Group 3 — filter_predicate: OR logic (delegated to core)
    # ------------------------------------------------------------------

    async def test_filter_predicate_should_return_true_when_prim_matches_selected_tag(self):
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR])
        plugin._core.prim_has_any_tag.return_value = True
        item = _make_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        plugin._core.prim_has_any_tag.assert_called_once_with(item.data, [Sdf.Path(_TAG_CAR)])

    async def test_filter_predicate_should_return_false_when_prim_matches_no_selected_tag(self):
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR, _TAG_RED])
        plugin._core.prim_has_any_tag.return_value = False
        item = _make_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)

    async def test_filter_predicate_should_delegate_or_logic_to_core(self):
        # Arrange: multiple tags selected — core receives all paths in one call (OR semantics)
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR, _TAG_RED])
        plugin._core.prim_has_any_tag.return_value = True
        item = _make_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        plugin._core.prim_has_any_tag.assert_called_once_with(item.data, [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)])

    async def test_filter_predicate_should_pass_untagged_prim_when_include_untagged_enabled(self):
        # Arrange: include_untagged=True; prim belongs to no tag → should pass
        # No selected_tags, so the selected-tags branch is skipped; only the untagged check runs.
        plugin = _make_plugin_with_core(include_untagged=True)
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]
        plugin._core.prim_has_any_tag.return_value = False
        item = _make_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        plugin._core.prim_has_any_tag.assert_called_once_with(item.data, [Sdf.Path(_TAG_CAR)])

    async def test_filter_predicate_should_pass_untagged_prim_when_selected_tags_do_not_match(self):
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR], include_untagged=True)
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)]
        plugin._core.prim_has_any_tag.side_effect = [False, False]
        item = _make_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertEqual(2, plugin._core.prim_has_any_tag.call_count)
        plugin._core.prim_has_any_tag.assert_any_call(item.data, [Sdf.Path(_TAG_CAR)])
        plugin._core.prim_has_any_tag.assert_any_call(item.data, [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)])

    async def test_filter_predicate_should_exclude_tagged_prim_when_include_untagged_enabled(self):
        # Arrange: include_untagged=True; prim IS tagged → should be excluded
        plugin = _make_plugin_with_core(include_untagged=True)
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]
        plugin._core.prim_has_any_tag.return_value = True
        item = _make_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)
        plugin._core.prim_has_any_tag.assert_called_once_with(item.data, [Sdf.Path(_TAG_CAR)])

    # ------------------------------------------------------------------
    # Group 4 — _on_tag_toggled / _on_untagged_toggled
    # ------------------------------------------------------------------

    async def test_on_tag_toggled_should_add_tag_when_checked(self):
        # Arrange
        plugin = _make_plugin_with_core()

        # Act
        with patch.object(plugin, "_filter_items_changed"):
            plugin._on_tag_toggled(_TAG_CAR, checked=True)

        # Assert
        self.assertIn(_TAG_CAR, plugin.selected_tags)

    async def test_on_tag_toggled_should_remove_tag_when_unchecked(self):
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR])

        # Act
        with patch.object(plugin, "_filter_items_changed"):
            plugin._on_tag_toggled(_TAG_CAR, checked=False)

        # Assert
        self.assertNotIn(_TAG_CAR, plugin.selected_tags)

    async def test_on_tag_toggled_should_not_add_duplicate_when_already_selected(self):
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR])

        # Act
        with patch.object(plugin, "_filter_items_changed"):
            plugin._on_tag_toggled(_TAG_CAR, checked=True)

        # Assert
        self.assertEqual(1, plugin.selected_tags.count(_TAG_CAR))

    async def test_on_tag_toggled_should_be_noop_when_unchecking_nonexistent_tag(self):
        # Arrange
        plugin = _make_plugin_with_core()

        # Act
        with patch.object(plugin, "_filter_items_changed"):
            plugin._on_tag_toggled("/World/CustomTags.collection:missing", checked=False)

        # Assert
        self.assertEqual([], plugin.selected_tags)

    async def test_on_tag_toggled_should_notify_filter_items_changed(self):
        # Arrange
        plugin = _make_plugin_with_core()

        # Act
        with patch.object(plugin, "_filter_items_changed") as mock_changed:
            plugin._on_tag_toggled(_TAG_CAR, checked=True)

        # Assert
        mock_changed.assert_called_once()

    async def test_on_untagged_toggled_should_update_include_untagged_and_notify(self):
        # Arrange
        plugin = _make_plugin_with_core()

        # Act
        with patch.object(plugin, "_filter_items_changed") as mock_changed:
            plugin._on_untagged_toggled(checked=True)

        # Assert
        self.assertTrue(plugin.include_untagged)
        mock_changed.assert_called_once()

    # ------------------------------------------------------------------
    # Group 5 — Rebuild guard
    # ------------------------------------------------------------------

    async def test_on_tag_toggled_should_be_ignored_when_rebuilding(self):
        # Arrange: _rebuilding=True prevents UI callbacks from mutating state
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR])
        plugin._rebuilding = True

        # Act
        with patch.object(plugin, "_filter_items_changed") as mock_changed:
            plugin._on_tag_toggled(_TAG_CAR, checked=False)

        # Assert
        self.assertIn(_TAG_CAR, plugin.selected_tags)
        mock_changed.assert_not_called()

    async def test_on_untagged_toggled_should_be_ignored_when_rebuilding(self):
        # Arrange: _rebuilding=True prevents UI callbacks from mutating state
        plugin = _make_plugin_with_core(include_untagged=True)
        plugin._rebuilding = True

        # Act
        with patch.object(plugin, "_filter_items_changed") as mock_changed:
            plugin._on_untagged_toggled(checked=False)

        # Assert
        self.assertTrue(plugin.include_untagged)
        mock_changed.assert_not_called()

    # ------------------------------------------------------------------
    # Group 6 — _set_all_selected
    # ------------------------------------------------------------------

    async def test_can_set_all_selected_true_should_return_false_when_all_options_are_selected(self):
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR], include_untagged=True)
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]

        # Act
        result = plugin.can_set_all_selected(True)

        # Assert
        self.assertFalse(result)

    async def test_can_set_all_selected_false_should_return_false_when_no_options_are_selected(self):
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]

        # Act
        result = plugin.can_set_all_selected(False)

        # Assert
        self.assertFalse(result)

    async def test_set_all_selected_false_should_clear_selection(self):
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR], include_untagged=True)

        # Act
        with patch.object(plugin, "_filter_items_changed"):
            plugin._set_all_selected(False)

        # Assert
        self.assertEqual([], plugin.selected_tags)
        self.assertFalse(plugin.include_untagged)
        self.assertFalse(plugin._filter_enabled)
        self.assertFalse(plugin.enabled)

    async def test_set_all_selected_true_should_select_all(self):
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]

        # Act
        with patch.object(plugin, "_filter_items_changed"):
            plugin._set_all_selected(True)

        # Assert
        self.assertIn(_TAG_CAR, plugin.selected_tags)
        self.assertTrue(plugin.include_untagged)
        self.assertTrue(plugin._filter_enabled)
        self.assertTrue(plugin.enabled)

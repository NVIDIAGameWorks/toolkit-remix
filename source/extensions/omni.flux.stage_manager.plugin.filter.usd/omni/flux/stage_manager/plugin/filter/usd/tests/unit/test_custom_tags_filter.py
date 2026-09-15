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

import threading
from functools import partial
from unittest.mock import Mock, patch

from omni import ui
from omni.kit import ui_test
import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.factory.plugins.filter_plugin import FilterCategory
from omni.flux.stage_manager.plugin.filter.usd.additional_filters import AdditionalFiltersPopupMenuItemDelegate
from pxr import Sdf

from ... import custom_tags
from ...custom_tags import CustomTagsFilterPlugin

__all__ = ["TestCustomTagsFilterPluginUnit"]

_TAG_CAR = "/World/CustomTags.collection:car"
_TAG_RED = "/World/CustomTags.collection:red"
_CAR_PRIM_PATH = "/World/Car"
_UNTAGGED_CHECKBOX_IDENTIFIER = "filter_checkbox_custom_tags_untagged"


def _make_item(prim_path: str = _CAR_PRIM_PATH):
    """Create a mock filter item for a prim path."""
    mock_prim = Mock()
    mock_prim.GetPath.return_value = Mock()
    mock_prim.GetPath.return_value.__str__ = lambda s: prim_path
    mock_item = Mock()
    mock_item.data = mock_prim
    return mock_item


def _make_plugin_with_core(**kwargs) -> CustomTagsFilterPlugin:
    """Create an enabled Custom Tags filter with a mock query core."""
    plugin = CustomTagsFilterPlugin(**kwargs)
    plugin._core = Mock()
    plugin._core.get_all_tags.return_value = []
    plugin._core.prim_has_any_tag.return_value = False
    plugin._core.get_tag_prims.return_value = []
    plugin._filter_enabled = True
    return plugin


def _make_stage_item(prim_path: str) -> StageManagerItem:
    """Create a Stage Manager item for a prim path."""
    prim = Mock()
    prim.GetPath.return_value = Sdf.Path(prim_path)
    return StageManagerItem(prim_path, data=prim)


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

    async def test_filter_active_should_be_false_by_default(self):
        # Arrange
        plugin = CustomTagsFilterPlugin()

        # Act / Assert
        self.assertFalse(plugin.filter_active)

    async def test_filter_active_should_be_true_when_schema_has_selected_tags(self):
        # Arrange
        plugin = CustomTagsFilterPlugin(selected_tags=[_TAG_CAR])

        # Act / Assert
        self.assertTrue(plugin.filter_active)

    async def test_filter_active_should_track_non_default_tag_values(self):
        # Arrange
        plugin = CustomTagsFilterPlugin()

        # Act
        plugin.include_untagged = True

        # Assert
        self.assertTrue(plugin.filter_active)

        # Act
        plugin.include_untagged = False

        # Assert
        self.assertFalse(plugin.filter_active)

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
        """Build a stable widget-safe identifier from a tag path."""
        # Act
        result = CustomTagsFilterPlugin._get_tag_checkbox_identifier(_TAG_CAR)

        # Assert
        self.assertEqual("filter_checkbox_custom_tags_World_CustomTags_collection_car", result)

    async def test_build_ui_should_build_tag_rows_with_path_based_tags(self):
        """Build tag rows with identifiers derived from their paths."""
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]
        tag_checkbox_identifier = CustomTagsFilterPlugin._get_tag_checkbox_identifier(_TAG_CAR)
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
        """Align tag checkboxes with the untagged checkbox."""
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)]
        tag_checkbox_identifier = CustomTagsFilterPlugin._get_tag_checkbox_identifier(_TAG_CAR)
        red_checkbox_identifier = CustomTagsFilterPlugin._get_tag_checkbox_identifier(_TAG_RED)
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
        """Refresh stale tag data before rebuilding tag rows."""
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._all_tag_paths = []
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]
        tag_checkbox_identifier = CustomTagsFilterPlugin._get_tag_checkbox_identifier(_TAG_CAR)
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
        """Render popup tag rows with usable dimensions."""
        # Arrange
        plugin = _make_plugin_with_core()
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR)]
        tag_checkbox_identifier = CustomTagsFilterPlugin._get_tag_checkbox_identifier(_TAG_CAR)
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

    async def test_build_filter_predicate_with_untagged_reuses_all_tag_paths_without_mutating_plugin_caches(self):
        """Bind only reusable all-tag paths without mutating UI caches."""
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR], include_untagged=True)
        plugin._all_tag_paths = []
        plugin._prim_counts = {_TAG_CAR: 1}
        plugin._core.get_all_tags.return_value = [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)]
        plugin._core.prim_has_any_tag.side_effect = [False, False]
        item = _make_stage_item(_CAR_PRIM_PATH)
        predicate = plugin.build_filter_predicate()

        # Act
        result = predicate(item)

        # Assert
        self.assertIsInstance(predicate, partial)
        self.assertEqual(plugin.filter_predicate, predicate.func)
        self.assertEqual({"all_tag_paths"}, set(predicate.keywords))
        self.assertTrue(result)
        self.assertFalse(item.is_display_name_candidate)
        with self.assertRaises(RuntimeError):
            _ = item.prepared_group_memberships
        self.assertEqual([], plugin._all_tag_paths)
        self.assertEqual({_TAG_CAR: 1}, plugin._prim_counts)
        plugin._core.get_all_tags.assert_called_once_with()
        plugin._core.prim_has_any_tag.assert_any_call(item.data, [Sdf.Path(_TAG_CAR)])
        plugin._core.prim_has_any_tag.assert_any_call(item.data, [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)])

    async def test_plugin_teardown_keeps_replaced_cores_alive_and_obsolete_predicate_safe(self):
        """Keep in-flight cores alive without preserving obsolete predicate state."""
        # Arrange
        plugin = _make_plugin_with_core(selected_tags=[_TAG_CAR])
        original_core = plugin._core
        original_core.prim_has_any_tag.return_value = True
        replacement_core = Mock()
        item = _make_item()
        predicate = plugin.build_filter_predicate()

        with patch(
            "omni.flux.stage_manager.plugin.filter.usd.custom_tags._CustomTagsCore",
            return_value=replacement_core,
        ):
            plugin.set_context_name("replacement")
        plugin.destroy()
        state_before_evaluation = (
            plugin._all_tag_paths,
            plugin._prim_counts,
            plugin._selected_tag_paths,
            plugin._checkboxes_frame,
        )

        # Act
        result = predicate(item)

        # Assert
        self.assertEqual(plugin.filter_predicate, predicate)
        self.assertTrue(result)
        original_core.destroy.assert_not_called()
        replacement_core.destroy.assert_not_called()
        original_core.prim_has_any_tag.assert_not_called()
        replacement_core.prim_has_any_tag.assert_not_called()
        self.assertEqual(
            state_before_evaluation,
            (plugin._all_tag_paths, plugin._prim_counts, plugin._selected_tag_paths, plugin._checkboxes_frame),
        )

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

    async def test_build_filter_predicate_with_neutral_filter_prepares_targets_and_destroys_temporary_core(self):
        """Prepare ordered exact targets and release the temporary query core."""
        # Arrange
        tag_paths = [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)]
        plugin = CustomTagsFilterPlugin()
        plugin._context_name = "texturecraft"
        temporary_core = Mock()
        temporary_core.get_all_tags.return_value = tag_paths
        temporary_core.get_tag_prims.return_value = [Sdf.Path(_CAR_PRIM_PATH)]

        # Act
        with patch.object(custom_tags, "_CustomTagsCore", return_value=temporary_core) as core_class:
            plugin.build_filter_predicate(threading.Event())

        # Assert
        core_class.assert_called_once_with(context_name="texturecraft")
        temporary_core.get_all_tags.assert_called_once_with()
        self.assertEqual(tag_paths, [mock_call.args[0] for mock_call in temporary_core.get_tag_prims.call_args_list])
        temporary_core.destroy.assert_called_once_with()

    async def test_built_predicate_with_exact_targets_preserves_membership_order_and_metadata(self):
        """Retain exact tagged prims with ordered refresh-local tag metadata."""
        # Arrange
        tag_paths = [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)]
        plugin = CustomTagsFilterPlugin()
        temporary_core = Mock()
        temporary_core.get_all_tags.return_value = tag_paths
        temporary_core.get_tag_prims.side_effect = [[Sdf.Path(_CAR_PRIM_PATH)], [Sdf.Path(_CAR_PRIM_PATH)]]
        tagged_item = _make_stage_item(_CAR_PRIM_PATH)
        descendant_item = _make_stage_item(f"{_CAR_PRIM_PATH}/Wheel")
        untagged_item = _make_stage_item("/World/Truck")
        with patch.object(custom_tags, "_CustomTagsCore", return_value=temporary_core):
            predicate = plugin.build_filter_predicate(threading.Event())

        # Act
        results = [predicate(item) for item in (tagged_item, descendant_item, untagged_item)]

        # Assert
        self.assertEqual([True, False, False], results)
        self.assertEqual((_TAG_CAR, _TAG_RED), tagged_item.prepared_group_memberships)
        for item in (descendant_item, untagged_item):
            with self.assertRaises(RuntimeError):
                _ = item.prepared_group_memberships
        self.assertTrue(all(item.is_display_name_candidate for item in (tagged_item, descendant_item, untagged_item)))

    async def test_build_filter_predicate_with_pre_set_cancel_event_skips_enumeration_and_destroys_core(self):
        """Skip tag catalog and target enumeration when cancellation is already requested."""
        # Arrange
        cancel_event = threading.Event()
        cancel_event.set()
        plugin = CustomTagsFilterPlugin()
        temporary_core = Mock()

        # Act
        with patch.object(custom_tags, "_CustomTagsCore", return_value=temporary_core):
            plugin.build_filter_predicate(cancel_event)

        # Assert
        temporary_core.get_all_tags.assert_not_called()
        temporary_core.get_tag_prims.assert_not_called()
        temporary_core.destroy.assert_called_once_with()

    async def test_build_filter_predicate_with_cancelled_refresh_stops_enumerating_tags(self):
        """Stop tag enumeration after the context refresh is cancelled."""
        # Arrange
        cancel_event = threading.Event()
        tag_paths = [Sdf.Path(_TAG_CAR), Sdf.Path(_TAG_RED)]
        plugin = CustomTagsFilterPlugin()
        temporary_core = Mock()
        temporary_core.get_all_tags.return_value = tag_paths

        def cancel_after_first_target_query(_tag_path: Sdf.Path) -> list[Sdf.Path]:
            """Cancel the refresh while returning the first tag's exact targets."""
            cancel_event.set()
            return [Sdf.Path(_CAR_PRIM_PATH)]

        temporary_core.get_tag_prims.side_effect = cancel_after_first_target_query

        # Act
        with patch.object(custom_tags, "_CustomTagsCore", return_value=temporary_core):
            plugin.build_filter_predicate(cancel_event)

        # Assert
        temporary_core.get_tag_prims.assert_called_once_with(tag_paths[0])
        temporary_core.destroy.assert_called_once_with()

    async def test_prepared_predicate_with_no_tags_rejects_item(self):
        """Reject items when refresh preparation finds no tag definitions."""

        # Arrange
        plugin = CustomTagsFilterPlugin()
        temporary_core = Mock()
        temporary_core.get_all_tags.return_value = []
        with patch.object(custom_tags, "_CustomTagsCore", return_value=temporary_core):
            predicate = plugin.build_filter_predicate(threading.Event())
        item = _make_stage_item(_CAR_PRIM_PATH)

        # Act
        result = predicate(item)

        # Assert
        self.assertFalse(result)
        with self.assertRaises(RuntimeError):
            _ = item.prepared_group_memberships
        self.assertTrue(item.is_display_name_candidate)

    async def test_filter_predicate_with_neutral_configuration_returns_true(self):
        """Pass through direct evaluation while neutral preparation owns tag target resolution."""
        # Arrange
        plugin = CustomTagsFilterPlugin()
        item = _make_stage_item(_CAR_PRIM_PATH)

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

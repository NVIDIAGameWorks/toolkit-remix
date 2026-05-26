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

from types import SimpleNamespace
from unittest import mock

from omni.kit.test import AsyncTestCase
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.factory.plugins.filter_plugin import StageManagerFilterPlugin as _StageManagerFilterPlugin
from omni.flux.stage_manager.factory.plugins.interaction_plugin import (
    StageManagerInteractionPlugin as _StageManagerInteractionPlugin,
)
from omni.flux.stage_manager.plugin.interaction.usd.base.usd_base import (
    RefreshRule as _RefreshRule,
    StageManagerUSDInteractionPlugin as _StageManagerUSDInteractionPlugin,
    USDEventFilteringRules as _USDEventFilteringRules,
)
from pydantic import Field
from pxr import Sdf


class _TestInteractionPlugin(_StageManagerUSDInteractionPlugin):
    pass


class _TestFilterPlugin(_StageManagerFilterPlugin):
    display_name: str = Field(default="Test Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)

    def filter_predicate(self, item: StageManagerItem) -> bool:
        return True

    def build_ui(self, *args, **kwargs):
        pass


class TestStageManagerUSDInteractionPlugin(AsyncTestCase):
    async def test_expand_filtered_items_ignores_hidden_filter_display_state(self):
        # Arrange: display controls UI placement only and should not make the interaction expand filtered results
        child_item = mock.MagicMock()
        tree_model = mock.MagicMock()
        tree_model.get_item_children.return_value = [child_item]
        tree_widget = mock.MagicMock()
        plugin = _TestInteractionPlugin.model_construct(
            tree=SimpleNamespace(model=tree_model),
            filters=[_TestFilterPlugin(display=False, filter_active=False)],
            context_filters=[],
            internal_context_filters=[],
            columns=[],
            additional_filters=[],
            compatible_filters=[],
            compatible_widgets=[],
            compatible_trees=[],
            _tree_widget=tree_widget,
        )

        # Act
        plugin._expand_filtered_items()

        # Assert
        tree_widget.set_expanded.assert_not_called()

    def _make_plugin(self):
        return _TestInteractionPlugin.model_construct(
            tree=mock.MagicMock(),
            filters=[],
            context_filters=[],
            internal_context_filters=[],
            columns=[],
            additional_filters=[],
            compatible_filters=[],
            compatible_widgets=[],
            compatible_trees=[],
            filtering_rules=_USDEventFilteringRules(),
        )

    def _make_notice(
        self,
        changed_info_only_paths: list[Sdf.Path] | None = None,
        resynced_paths: list[Sdf.Path] | None = None,
    ):
        notice = mock.MagicMock()
        notice.GetChangedInfoOnlyPaths.return_value = changed_info_only_paths or []
        notice.GetResyncedPaths.return_value = resynced_paths or []
        notice.GetChangedFields.return_value = []
        return notice

    async def test_on_selection_changed_does_not_write_back_for_order_only_difference(self):
        # Arrange
        plugin = self._make_plugin()
        plugin._selection_update_lock = False
        plugin.synchronize_selection = True
        plugin._ignore_selection_update = False
        plugin._context_name = ""

        items = [
            SimpleNamespace(data=SimpleNamespace(GetPath=lambda: "/World/B")),
            SimpleNamespace(data=SimpleNamespace(GetPath=lambda: "/World/A")),
        ]

        with (
            mock.patch.object(_StageManagerInteractionPlugin, "_on_selection_changed", autospec=True) as super_sel,
            mock.patch.object(plugin, "_get_selection", return_value=["/World/A", "/World/B"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            plugin._on_selection_changed(items)

            # Assert
            super_sel.assert_called_once()
            selection_mock.set_selected_prim_paths.assert_not_called()

    async def test_on_selection_changed_writes_back_when_selected_set_changes(self):
        # Arrange
        plugin = self._make_plugin()
        plugin._selection_update_lock = False
        plugin.synchronize_selection = True
        plugin._ignore_selection_update = False
        plugin._context_name = ""

        items = [
            SimpleNamespace(data=SimpleNamespace(GetPath=lambda: "/World/A")),
            SimpleNamespace(data=SimpleNamespace(GetPath=lambda: "/World/C")),
        ]

        with (
            mock.patch.object(_StageManagerInteractionPlugin, "_on_selection_changed", autospec=True) as super_sel,
            mock.patch.object(plugin, "_get_selection", return_value=["/World/A", "/World/B"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            plugin._on_selection_changed(items)

            # Assert
            super_sel.assert_called_once()
            selection_mock.set_selected_prim_paths.assert_called_once_with(["/World/A", "/World/C"])

    async def test_property_resync_dirties_widgets_without_refreshing_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube.doubleSided")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=False)

    async def test_gradient_primvar_change_dirties_widgets_without_refreshing_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        notice = self._make_notice(
            changed_info_only_paths=[
                Sdf.Path("/World/Cube.primvars:color:times"),
                Sdf.Path("/World/Cube.primvars:color:values"),
            ]
        )

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=False)

    async def test_prim_resync_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_prim_named_nickname_resync_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/nickname")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_property_resync_matching_property_name_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(start="remix_category:")]
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube.remix_category:test")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_info_only_collection_property_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(start="collection:", end=":includes", use_name=True)]
        notice = self._make_notice(changed_info_only_paths=[Sdf.Path("/CustomTags.collection:RenderTag:includes")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_collection_property_resync_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(start="collection:", use_name=True)]
        notice = self._make_notice(resynced_paths=[Sdf.Path("/CustomTags.collection:RenderTag")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_visibility_property_resync_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(start="visibility", use_name=True)]
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube.visibility")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_property_resync_does_not_evaluate_prim_path_name(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(end="Cube", use_name=True)]
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube.displayColor")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=False)

    async def test_property_only_paths_do_not_force_refresh_from_prim_path_name(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(end="Special", use_name=True)]
        notice = self._make_notice(
            changed_info_only_paths=[Sdf.Path("/World/Special.displayName")],
            resynced_paths=[Sdf.Path("/World/Special.doubleSided")],
        )

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=False)

    async def test_prim_info_only_path_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        notice = self._make_notice(changed_info_only_paths=[Sdf.Path("/World/Cube")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

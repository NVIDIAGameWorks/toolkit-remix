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

from typing import ClassVar

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.factory.plugins.filter_plugin import StageManagerFilterPlugin
from omni.flux.stage_manager.plugin.filter.usd.additional_filters import AdditionalFilterPlugin
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin, ToggleableUSDFilterPlugin
from omni.flux.stage_manager.plugin.filter.usd.custom_tags import CustomTagsFilterPlugin
from omni.flux.stage_manager.plugin.filter.usd.ignore_prims import IgnorePrimsFilterPlugin
from omni.flux.stage_manager.plugin.filter.usd.search import SearchFilterPlugin
from omni.flux.stage_manager.plugin.filter.usd.visible_prims import VisiblePrimsFilterPlugin
from pydantic import Field, PrivateAttr

__all__ = ["TestStageManagerUSDFilterPluginUnit"]


class _WatchedFieldFilterPlugin(StageManagerUSDFilterPlugin):
    display_name: str = Field(default="Watched Field Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)
    watched_value: str = Field(default="All")

    _filter_active_fields: ClassVar[tuple[str, ...]] = ("watched_value",)

    def build_ui(self):
        pass

    def filter_predicate(self, _item) -> bool:
        return True

    def _refresh_filter_active(self) -> None:
        self.filter_active = self.watched_value != "All"


class _PreparedLookupFilterPlugin(StageManagerUSDFilterPlugin):
    display_name: str = Field(default="Prepared Lookup Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)

    _calls: int = PrivateAttr(default=0)

    def build_ui(self):
        pass

    def filter_predicate(self, item) -> bool:
        self._calls += 1
        return item.identifier == "keep"


class TestStageManagerUSDFilterPluginUnit(omni.kit.test.AsyncTestCase):
    async def test_filter_active_should_only_be_declared_by_stage_manager_filter_plugin(self):
        # Arrange
        filter_classes = [
            StageManagerUSDFilterPlugin,
            AdditionalFilterPlugin,
            CustomTagsFilterPlugin,
            IgnorePrimsFilterPlugin,
            SearchFilterPlugin,
            ToggleableUSDFilterPlugin,
            VisiblePrimsFilterPlugin,
            _WatchedFieldFilterPlugin,
        ]

        # Assert
        self.assertIn("filter_active", StageManagerFilterPlugin.__annotations__)
        for filter_class in filter_classes:
            with self.subTest(filter_class=filter_class.__name__):
                self.assertNotIn("filter_active", filter_class.__annotations__)

    async def test_model_post_init_should_refresh_filter_active_from_subclass_state(self):
        # Act
        plugin = _WatchedFieldFilterPlugin(watched_value="Specific")

        # Assert
        self.assertTrue(plugin.filter_active)

    async def test_watched_field_assignment_should_track_default_state(self):
        # Arrange
        plugin = _WatchedFieldFilterPlugin()

        # Act
        plugin.watched_value = "Specific"
        active_for_non_default = plugin.filter_active
        plugin.watched_value = "All"

        # Assert
        self.assertTrue(active_for_non_default)
        self.assertFalse(plugin.filter_active)

    async def test_prepare_filter_predicate_should_defer_evaluation_until_called(self):
        # Arrange
        plugin = _PreparedLookupFilterPlugin()
        kept_item = StageManagerItem("keep")
        rejected_item = StageManagerItem("reject")
        unknown_item = StageManagerItem("unknown")

        # Act
        prepared_predicate = plugin.prepare_filter_predicate()
        calls_after_preparation = plugin._calls
        prepared_results = [prepared_predicate(item) for item in (kept_item, rejected_item, unknown_item)]

        # Assert
        self.assertEqual(0, calls_after_preparation)
        self.assertEqual([True, False, False], prepared_results)
        self.assertEqual(3, plugin._calls)

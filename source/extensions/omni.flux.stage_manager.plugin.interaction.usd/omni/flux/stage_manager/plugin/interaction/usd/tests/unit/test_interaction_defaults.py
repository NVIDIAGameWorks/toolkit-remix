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

import omni.kit.test
from omni.flux.stage_manager.plugin.interaction.usd.base import StageManagerUSDInteractionPlugin
from omni.flux.stage_manager.plugin.interaction.usd.extension import StageManagerUSDInteractionPluginsExtension

from ...all_lights import AllLightsInteractionPlugin
from ...all_materials import AllMaterialsInteractionPlugin
from ...all_prims import AllPrimsInteractionPlugin
from ...all_skeletons import AllSkeletonsInteractionPlugin
from ...all_tags import AllTagsInteractionPlugin

__all__ = ["TestStageManagerUSDInteractionDefaults"]


class TestStageManagerUSDInteractionDefaults(omni.kit.test.AsyncTestCase):
    async def test_registered_interactions_should_use_shared_refresh_pipeline(self):
        # Arrange
        interaction_classes = StageManagerUSDInteractionPluginsExtension._PLUGINS

        for plugin_cls in interaction_classes:
            with self.subTest(plugin_cls=plugin_cls.__name__):
                # Act
                overrides_refresh = "_refresh_tree_model" in plugin_cls.__dict__
                overrides_context_update = "_update_context_items" in plugin_cls.__dict__
                inherits_base = issubclass(plugin_cls, StageManagerUSDInteractionPlugin)

                # Assert
                self.assertFalse(overrides_refresh)
                self.assertFalse(overrides_context_update)
                self.assertTrue(inherits_base)

    async def test_registered_interactions_should_use_expected_intrinsic_classifier_and_tree_compatibility(self):
        """Keep registered interactions compatible with their intrinsic filters and trees."""
        # Arrange
        expected_defaults = (
            (
                AllLightsInteractionPlugin,
                [{"name": "LightPrimsFilterPlugin", "filter_active": False}],
                ["LightPrimsFilterPlugin"],
                ["LightGroupsTreePlugin", "PrimGroupsTreePlugin"],
                True,
            ),
            (
                AllMaterialsInteractionPlugin,
                [{"name": "MaterialBindingsFilterPlugin"}],
                ["MaterialBindingsFilterPlugin", "MaterialPrimsFilterPlugin"],
                ["MaterialGroupsTreePlugin", "PrimGroupsTreePlugin"],
                True,
            ),
            (
                AllPrimsInteractionPlugin,
                [],
                [],
                ["PrimGroupsTreePlugin", "VirtualGroupsTreePlugin"],
                True,
            ),
            (
                AllSkeletonsInteractionPlugin,
                [{"name": "SkeletonPrimsFilterPlugin"}],
                ["SkeletonPrimsFilterPlugin"],
                ["PrimGroupsTreePlugin", "SkeletonGroupsTreePlugin"],
                True,
            ),
            (
                AllTagsInteractionPlugin,
                [{"name": "CustomTagsFilterPlugin"}],
                ["CustomTagsFilterPlugin"],
                ["CustomTagGroupsTreePlugin", "PrimGroupsTreePlugin"],
                True,
            ),
        )
        interaction_classes = StageManagerUSDInteractionPluginsExtension._PLUGINS

        for (
            interaction_class,
            expected_internal_filters,
            expected_compatible_filters,
            expected_trees,
            allow_context_ancestors,
        ) in expected_defaults:
            with self.subTest(title=interaction_class.__name__):
                # Arrange
                interaction = interaction_class()

                # Act
                internal_filters = interaction.internal_context_filters
                compatible_filters = interaction.compatible_filters
                compatible_trees = interaction.compatible_trees
                actual_allow_context_ancestors = interaction.allow_context_ancestors

                # Assert
                self.assertEqual(expected_internal_filters, internal_filters)
                self.assertEqual(expected_trees, compatible_trees)
                for filter_name in expected_compatible_filters:
                    self.assertIn(filter_name, compatible_filters)
                self.assertEqual(allow_context_ancestors, actual_allow_context_ancestors)

        self.assertEqual([interaction_class for interaction_class, *_ in expected_defaults], interaction_classes)

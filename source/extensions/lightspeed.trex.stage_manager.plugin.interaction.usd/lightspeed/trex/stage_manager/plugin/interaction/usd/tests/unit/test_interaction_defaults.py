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

from lightspeed.trex.stage_manager.plugin.interaction.usd.base import RemixStageManagerUSDInteractionPlugin
from lightspeed.trex.stage_manager.plugin.interaction.usd.extension import (
    RemixStageManagerUSDInteractionPluginsExtension,
)

from ...all_categories import RemixAllCategoriesInteractionPlugin
from ...all_lights import RemixAllLightsInteractionPlugin
from ...all_materials import RemixAllMaterialsInteractionPlugin
from ...all_meshes import RemixAllMeshesInteractionPlugin
from ...all_prims import RemixAllPrimsInteractionPlugin
from ...all_skeletons import RemixAllSkeletonsInteractionPlugin
from ...all_tags import RemixAllTagsInteractionPlugin

__all__ = ["TestRemixStageManagerUSDInteractionDefaults"]


class TestRemixStageManagerUSDInteractionDefaults(omni.kit.test.AsyncTestCase):
    """Test registered Remix Stage Manager interaction defaults."""

    async def test_registered_interactions_should_use_shared_refresh_pipeline(self):
        """Use the shared refresh pipeline for every registered interaction."""
        # Arrange
        interaction_classes = RemixStageManagerUSDInteractionPluginsExtension._PLUGINS

        for plugin_cls in interaction_classes:
            with self.subTest(title=plugin_cls.__name__):
                # Act
                overrides_refresh = "_refresh_tree_model" in plugin_cls.__dict__
                overrides_context_update = "_update_context_items" in plugin_cls.__dict__
                inherits_base = issubclass(plugin_cls, RemixStageManagerUSDInteractionPlugin)

                # Assert
                self.assertFalse(overrides_refresh)
                self.assertFalse(overrides_context_update)
                self.assertTrue(inherits_base)

    async def test_registered_interactions_should_use_expected_intrinsic_classifier_and_tree_compatibility(self):
        """Keep all seven Remix interaction defaults aligned with their grouped or hierarchical trees."""
        # Arrange
        expected_defaults = (
            (
                RemixAllCategoriesInteractionPlugin,
                ["IsCategoryFilterPlugin"],
                ["CategoryGroupsTreePlugin", "PrimGroupsTreePlugin"],
                True,
            ),
            (
                RemixAllLightsInteractionPlugin,
                ["LightPrimsFilterPlugin"],
                ["LightGroupsTreePlugin", "PrimGroupsTreePlugin"],
                True,
            ),
            (
                RemixAllMaterialsInteractionPlugin,
                ["MaterialBindingsFilterPlugin"],
                ["MaterialGroupsTreePlugin", "PrimGroupsTreePlugin"],
                True,
            ),
            (
                RemixAllMeshesInteractionPlugin,
                ["MeshPrimsFilterPlugin"],
                ["MeshGroupsTreePlugin", "PrimGroupsTreePlugin"],
                True,
            ),
            (
                RemixAllPrimsInteractionPlugin,
                [],
                ["PrimGroupsTreePlugin", "VirtualGroupsTreePlugin"],
                True,
            ),
            (
                RemixAllSkeletonsInteractionPlugin,
                ["SkeletonPrimsFilterPlugin"],
                ["PrimGroupsTreePlugin", "SkeletonGroupsTreePlugin"],
                True,
            ),
            (
                RemixAllTagsInteractionPlugin,
                ["CustomTagsFilterPlugin"],
                ["CustomTagGroupsTreePlugin", "PrimGroupsTreePlugin"],
                True,
            ),
        )
        interaction_classes = RemixStageManagerUSDInteractionPluginsExtension._PLUGINS

        for interaction_class, expected_filters, expected_trees, allow_context_ancestors in expected_defaults:
            with self.subTest(title=interaction_class.__name__):
                # Arrange
                interaction = interaction_class()

                # Act
                intrinsic_filter_names = [
                    filter_plugin["name"] for filter_plugin in interaction.internal_context_filters
                ]
                compatible_filters = interaction.compatible_filters
                compatible_trees = interaction.compatible_trees
                actual_allow_context_ancestors = interaction.allow_context_ancestors

                # Assert
                self.assertEqual(expected_filters, intrinsic_filter_names)
                self.assertEqual(expected_trees, compatible_trees)
                for filter_name in expected_filters:
                    self.assertIn(filter_name, compatible_filters)
                if interaction_class is RemixAllMaterialsInteractionPlugin:
                    self.assertIn("MaterialPrimsFilterPlugin", compatible_filters)
                self.assertEqual(allow_context_ancestors, actual_allow_context_ancestors)

        self.assertEqual([interaction_class for interaction_class, *_ in expected_defaults], interaction_classes)

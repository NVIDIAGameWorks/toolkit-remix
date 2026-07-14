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

__all__ = ["TestRemixStageManagerUSDInteractionDefaults"]


class TestRemixStageManagerUSDInteractionDefaults(omni.kit.test.AsyncTestCase):
    async def test_registered_interactions_should_use_shared_refresh_pipeline(self):
        # Arrange
        interaction_classes = RemixStageManagerUSDInteractionPluginsExtension._PLUGINS

        for plugin_cls in interaction_classes:
            with self.subTest(plugin_cls=plugin_cls.__name__):
                # Act
                overrides_refresh = "_refresh_tree_model" in plugin_cls.__dict__
                overrides_context_update = "_update_context_items" in plugin_cls.__dict__
                inherits_base = issubclass(plugin_cls, RemixStageManagerUSDInteractionPlugin)

                # Assert
                self.assertFalse(overrides_refresh)
                self.assertFalse(overrides_context_update)
                self.assertTrue(inherits_base)

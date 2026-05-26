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

import json
from pathlib import Path

import omni.kit.app
from omni.kit.test import AsyncTestCase


class TestStageManagerSchema(AsyncTestCase):
    def _load_default_schema(self):
        extension_manager = omni.kit.app.get_app().get_extension_manager()
        extension_id = extension_manager.get_enabled_extension_id("lightspeed.trex.app.resources")
        self.assertTrue(extension_id)

        schema_path = (
            Path(extension_manager.get_extension_path(extension_id))
            / "data"
            / "stage_manager_schema"
            / "default_schema.json"
        )
        self.assertTrue(schema_path.exists(), str(schema_path))
        return json.loads(schema_path.read_text(encoding="utf-8"))

    async def test_stage_manager_interactions_force_context_refresh_for_filter_property_changes(self):
        # Arrange
        schema = self._load_default_schema()
        expected_interactions = [
            "RemixAllPrimsInteractionPlugin",
            "RemixAllMeshesInteractionPlugin",
            "RemixAllMaterialsInteractionPlugin",
            "RemixAllLightsInteractionPlugin",
            "RemixAllSkeletonsInteractionPlugin",
            "RemixAllCategoriesInteractionPlugin",
            "RemixAllTagsInteractionPlugin",
        ]
        required_rule_starts = ("collection:", "visibility")

        # Act
        interaction_names = []
        missing_rules = []
        for interaction in schema["interactions"]:
            interaction_names.append(interaction["name"])
            rules = interaction["filtering_rules"]["force_refresh_rules"]
            for rule_start in required_rule_starts:
                if not any(
                    rule["use_name"] is True and rule["start"] == rule_start and "end" not in rule for rule in rules
                ):
                    missing_rules.append(f"{interaction['name']}: {rule_start}")

        # Assert
        self.assertEqual(expected_interactions, interaction_names)
        self.assertEqual([], missing_rules)

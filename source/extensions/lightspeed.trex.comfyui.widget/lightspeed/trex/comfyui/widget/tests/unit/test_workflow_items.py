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

__all__ = ["TestOutputItemGroup"]

from lightspeed.trex.comfyui.core.enums import RemixType
from lightspeed.trex.comfyui.core.models import WorkflowOutput
from omni.kit.test import AsyncTestCase

from ...workflow.items import OutputItemGroup


class TestOutputItemGroup(AsyncTestCase):
    """Test the property row that wraps one persisted workflow output."""

    async def test_output_item_group_uses_texture_label_and_persisted_output(self):
        """A texture output row without an export name keeps the persisted object and uses its semantic label."""
        # Arrange
        workflow_output = WorkflowOutput(
            node_id="20",
            remix_type=RemixType.TEXTURE_FILE_PATH,
            texture_type="albedo",
        )

        # Act
        item = OutputItemGroup(workflow_output)

        # Assert
        self.assertEqual(item.label, "Albedo")
        self.assertIs(item.workflow_output, workflow_output)
        self.assertFalse(item.can_have_children)

    async def test_output_item_group_prefers_the_export_name_and_keeps_the_kind_in_the_tooltip(self):
        """A row shows the name typed in ComfyUI, so a re-export is visible, and names the kind in its tooltip."""
        # Arrange
        workflow_output = WorkflowOutput(
            node_id="20", remix_type=RemixType.TEXTURE_FILE_PATH, texture_type="albedo", name="Passthrough Albedo"
        )

        # Act
        item = OutputItemGroup(workflow_output)

        # Assert
        self.assertEqual(item.label, "Passthrough Albedo")
        self.assertEqual(item.tooltip, "Configure the Passthrough Albedo output (Albedo)")

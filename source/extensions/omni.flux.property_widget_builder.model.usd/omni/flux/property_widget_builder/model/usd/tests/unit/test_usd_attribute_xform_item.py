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

__all__ = ("TestUSDAttributeXformItem",)

from unittest.mock import Mock

import omni.kit.test
from omni.flux.property_widget_builder.model.usd import USDAttributeXformItem


class TestUSDAttributeXformItem(omni.kit.test.AsyncTestCase):
    """Tests grouped-edit state orchestration without a USD stage."""

    async def test_toggle_group_edit_when_copy_succeeds_enables_group_edit(self):
        # Arrange
        item = Mock(spec=USDAttributeXformItem)
        item.linked_edit_enabled = False
        item.value_models = [Mock(), Mock(), Mock()]
        item.value_models[0].copy_first_channel_to_all_attributes.return_value = True

        # Act
        USDAttributeXformItem.toggle_linked_edit(item)

        # Assert
        item.set_linked_edit_enabled.assert_called_once_with(True)

    async def test_toggle_group_edit_when_copy_fails_does_not_enable_group_edit(self):
        # Arrange
        item = Mock(spec=USDAttributeXformItem)
        item.linked_edit_enabled = False
        item.value_models = [Mock(), Mock(), Mock()]
        item.value_models[0].copy_first_channel_to_all_attributes.return_value = False

        # Act
        USDAttributeXformItem.toggle_linked_edit(item)

        # Assert
        item.set_linked_edit_enabled.assert_not_called()

    async def test_toggle_group_edit_when_enabled_disables_without_copying_values(self):
        # Arrange
        item = Mock(spec=USDAttributeXformItem)
        item.linked_edit_enabled = True
        item.value_models = [Mock(), Mock(), Mock()]

        # Act
        USDAttributeXformItem.toggle_linked_edit(item)

        # Assert
        item.set_linked_edit_enabled.assert_called_once_with(False)
        item.value_models[0].copy_first_channel_to_all_attributes.assert_not_called()

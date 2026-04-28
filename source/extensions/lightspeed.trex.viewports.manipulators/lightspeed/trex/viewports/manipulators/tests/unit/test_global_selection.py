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

import omni.usd
from lightspeed.trex.viewports.manipulators.global_selection import l_apply_picking_mode
from omni.kit.test import AsyncTestCase


class TestGlobalSelection(AsyncTestCase):
    async def test_apply_picking_mode_merge_selection_preserves_existing_then_picked_order(self):
        # Arrange
        old_selection = ["/World/A"]
        picked_selection = ["/World/B"]

        # Act
        merged_selection = l_apply_picking_mode(
            old_selection,
            picked_selection,
            omni.usd.PickingMode.MERGE_SELECTION,
        )

        # Assert
        self.assertEqual(merged_selection, ["/World/A", "/World/B"])

    async def test_apply_picking_mode_merge_selection_dedupes_without_reordering_existing_paths(self):
        # Arrange
        old_selection = ["/World/A", "/World/B"]
        picked_selection = ["/World/B", "/World/C"]

        # Act
        merged_selection = l_apply_picking_mode(
            old_selection,
            picked_selection,
            omni.usd.PickingMode.MERGE_SELECTION,
        )

        # Assert
        self.assertEqual(merged_selection, ["/World/A", "/World/B", "/World/C"])

    async def test_apply_picking_mode_reset_and_select_preserves_pick_order(self):
        # Arrange
        old_selection = ["/World/A"]
        picked_selection = ["/World/C", "/World/B", "/World/C"]

        # Act
        reset_selection = l_apply_picking_mode(
            old_selection,
            picked_selection,
            omni.usd.PickingMode.RESET_AND_SELECT,
        )

        # Assert
        self.assertEqual(reset_selection, ["/World/C", "/World/B"])

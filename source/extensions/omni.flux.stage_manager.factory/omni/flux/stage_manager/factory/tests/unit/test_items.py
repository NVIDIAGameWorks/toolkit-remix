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

from ...items import StageManagerItem

__all__ = ["TestStageManagerItem"]


class TestStageManagerItem(omni.kit.test.AsyncTestCase):
    """Test data owned by individual Stage Manager items."""

    async def test_mark_display_name_candidate_marks_only_target_item(self):
        """Mark only the selected item as a display-name candidate."""
        # Arrange
        target_item = StageManagerItem("target")
        other_item = StageManagerItem("other")

        # Act
        target_item.mark_display_name_candidate()

        # Assert
        self.assertTrue(target_item.is_display_name_candidate)
        self.assertFalse(other_item.is_display_name_candidate)

    async def test_prepare_group_memberships_stores_ordered_duplicate_tuple(self):
        """Store ordered duplicate memberships as an immutable copy."""
        # Arrange
        item = StageManagerItem("item")
        memberships = ["/Looks/One", "/Looks/One", "/Looks/Two"]

        # Act
        item.prepare_group_memberships(memberships)

        # Assert
        self.assertEqual(("/Looks/One", "/Looks/One", "/Looks/Two"), item.prepared_group_memberships)

    async def test_prepared_values_without_preparation_raise_runtime_error(self):
        """Raise when either prepared value has not been prepared."""
        for preparation in ("display name", "group memberships"):
            with self.subTest(title=preparation):
                # Arrange
                item = StageManagerItem("item")

                # Act
                if preparation == "display name":
                    with self.assertRaises(RuntimeError) as error:
                        _ = item.prepared_display_name
                else:
                    with self.assertRaises(RuntimeError) as error:
                        _ = item.prepared_group_memberships

                # Assert
                expected_message = (
                    "Display name is not prepared for item 'item'."
                    if preparation == "display name"
                    else "Group memberships are not prepared for item 'item'."
                )
                self.assertEqual(expected_message, str(error.exception))

    async def test_reset_filter_state_retains_prepared_values(self):
        """Retain prepared values when resetting filter state."""
        # Arrange
        item = StageManagerItem("item")
        item.prepare_display_name(("Item", None))
        item.prepare_group_memberships(("/Item",))

        # Act
        item.reset_filter_state()

        # Assert
        self.assertEqual(("Item", None), item.prepared_display_name)
        self.assertEqual(("/Item",), item.prepared_group_memberships)

    async def test_destroy_clears_only_destroyed_item_preparation(self):
        """Clear preparation for the destroyed item while preserving another item."""
        # Arrange
        destroyed_item = StageManagerItem("destroyed")
        surviving_item = StageManagerItem("surviving")
        destroyed_item.mark_display_name_candidate()
        destroyed_item.prepare_display_name(("Destroyed", None))
        destroyed_item.prepare_group_memberships(("/Destroyed",))
        surviving_item.mark_display_name_candidate()
        surviving_item.prepare_display_name(("Surviving", None))
        surviving_item.prepare_group_memberships(("/Surviving",))

        # Act
        destroyed_item.destroy()

        # Assert
        self.assertFalse(destroyed_item.is_display_name_candidate)
        with self.assertRaises(RuntimeError):
            _ = destroyed_item.prepared_display_name
        with self.assertRaises(RuntimeError):
            _ = destroyed_item.prepared_group_memberships
        self.assertTrue(surviving_item.is_display_name_candidate)
        self.assertEqual(("Surviving", None), surviving_item.prepared_display_name)
        self.assertEqual(("/Surviving",), surviving_item.prepared_group_memberships)

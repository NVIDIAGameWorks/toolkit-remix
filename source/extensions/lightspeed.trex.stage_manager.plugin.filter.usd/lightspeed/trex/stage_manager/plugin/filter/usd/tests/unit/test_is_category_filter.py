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

from threading import Event
from unittest.mock import Mock

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem

from ...is_category import IsCategoryFilterPlugin

__all__ = ["TestIsCategoryFilterUnit"]

_SKY_ATTRIBUTE = "remix_category:sky"
_ANIMATED_WATER_ATTRIBUTE = "remix_category:animated_water"


class TestIsCategoryFilterUnit(omni.kit.test.AsyncTestCase):
    """Tests Remix Category filter predicates and context preparation."""

    async def test_filter_predicate_with_neutral_category_passes_through_without_preparation(self):
        """Pass through neutral items without reading or preparing them."""
        cases = [
            ("missing_prim", None),
            ("invalid_prim", Mock(IsValid=Mock(return_value=False))),
            ("valid_prim", Mock(IsValid=Mock(return_value=True))),
        ]
        for title, prim in cases:
            with self.subTest(title=title):
                # Arrange
                item = StageManagerItem(f"/World/{title}", data=prim)
                plugin = IsCategoryFilterPlugin()

                # Act
                result = plugin.filter_predicate(item)

                # Assert
                self.assertTrue(result)
                self.assertFalse(item.is_display_name_candidate)
                with self.assertRaises(RuntimeError):
                    _ = item.prepared_group_memberships
                if prim is not None:
                    prim.IsValid.assert_not_called()
                    prim.GetAttributes.assert_not_called()

    async def test_build_filter_predicate_with_truthy_categories_prepares_recognized_names_in_source_order(
        self,
    ):
        """Prepare only recognized truthy category names in source attribute order."""
        # Arrange
        attributes = []
        for name, value in (
            (_ANIMATED_WATER_ATTRIBUTE, True),
            ("remix_category:unknown", True),
            (_SKY_ATTRIBUTE, True),
        ):
            attribute = Mock()
            attribute.GetName.return_value = name
            attribute.IsValid.return_value = True
            attribute.Get.return_value = value
            attributes.append(attribute)
        prim = Mock()
        prim.IsValid.return_value = True
        prim.GetAttributes.return_value = attributes
        item = StageManagerItem("/World/Prim", data=prim)
        plugin = IsCategoryFilterPlugin()

        # Act
        result = plugin.build_filter_predicate(Event())(item)

        # Assert
        self.assertTrue(result)
        self.assertEqual((_ANIMATED_WATER_ATTRIBUTE, _SKY_ATTRIBUTE), item.prepared_group_memberships)
        self.assertTrue(item.is_display_name_candidate)
        prim.GetAttributes.assert_called_once_with()
        attributes[1].Get.assert_not_called()

    async def test_build_filter_predicate_with_missing_or_invalid_prim_rejects_without_metadata(self):
        """Reject missing and invalid prims without marking display-name candidates."""
        cases = [("missing_prim", None), ("invalid_prim", Mock(IsValid=Mock(return_value=False)))]
        for title, prim in cases:
            with self.subTest(title=title):
                # Arrange
                item = StageManagerItem(f"/World/{title}", data=prim)
                plugin = IsCategoryFilterPlugin()

                # Act
                result = plugin.build_filter_predicate(Event())(item)

                # Assert
                self.assertFalse(result)
                self.assertFalse(item.is_display_name_candidate)
                if prim is not None:
                    prim.GetAttributes.assert_not_called()

    async def test_build_filter_predicate_with_no_truthy_recognized_category_rejects_after_marking(self):
        """Reject false, unknown, absent, and invalid category candidates after marking them."""
        cases = [
            ("false", [(_SKY_ATTRIBUTE, True, False)]),
            ("unknown", [("remix_category:unknown", True, True)]),
            ("absent", []),
            ("invalid", [(_SKY_ATTRIBUTE, False, True)]),
        ]
        for title, attribute_values in cases:
            with self.subTest(title=title):
                # Arrange
                attributes = []
                for name, valid, value in attribute_values:
                    attribute = Mock()
                    attribute.GetName.return_value = name
                    attribute.IsValid.return_value = valid
                    attribute.Get.return_value = value
                    attributes.append(attribute)
                prim = Mock()
                prim.IsValid.return_value = True
                prim.GetAttributes.return_value = attributes
                item = StageManagerItem(f"/World/{title}", data=prim)
                plugin = IsCategoryFilterPlugin()

                # Act
                result = plugin.build_filter_predicate(Event())(item)

                # Assert
                self.assertFalse(result)
                with self.assertRaises(RuntimeError):
                    _ = item.prepared_group_memberships
                self.assertTrue(item.is_display_name_candidate)

    async def test_filter_predicate_with_category_states_matches_all_or_enabled_attribute(self):
        """Match only enabled attributes for selected categories."""
        cases = [
            ("unknown_category", "Unknown Category", True, True, False, False, False),
            ("sky_enabled", "Sky", True, True, True, True, True),
            ("sky_disabled", "Sky", True, False, False, True, True),
            ("sky_missing", "Sky", False, False, False, True, False),
        ]
        for title, category_type, attribute_valid, attribute_value, expected, reads_attribute, reads_value in cases:
            with self.subTest(title=title):
                # Arrange
                attribute = Mock()
                attribute.IsValid.return_value = attribute_valid
                attribute.Get.return_value = attribute_value
                prim = Mock()
                prim.GetAttribute.return_value = attribute
                item = StageManagerItem(f"/World/{title}", data=prim)
                plugin = IsCategoryFilterPlugin(category_type=category_type)

                # Act
                result = plugin.build_filter_predicate(Event())(item)

                # Assert
                self.assertEqual(expected, result)
                self.assertFalse(item.is_display_name_candidate)
                with self.assertRaises(RuntimeError):
                    _ = item.prepared_group_memberships
                if reads_attribute:
                    prim.GetAttribute.assert_called_once_with(_SKY_ATTRIBUTE)
                else:
                    prim.GetAttribute.assert_not_called()
                if reads_value:
                    attribute.Get.assert_called_once_with()
                else:
                    attribute.Get.assert_not_called()

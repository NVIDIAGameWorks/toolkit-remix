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

from unittest.mock import Mock

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem
from pxr import Sdf, Usd, UsdGeom

from ...is_category import IsCategoryFilterPlugin

__all__ = ["TestIsCategoryFilterUnit"]

_SKY_ATTRIBUTE = "remix_category:sky"


class TestIsCategoryFilterUnit(omni.kit.test.AsyncTestCase):
    """Tests Remix Category predicates."""

    async def test_filter_predicate_with_category_states_matches_all_or_enabled_attribute(self):
        """Match all categories or an enabled selected attribute."""
        cases = [
            ("all_categories", "All Categories", True, False),
            ("unknown_category", "Unknown Category", False, False),
            ("sky_enabled", "Sky", True, True),
        ]

        for title, category_type, expected, reads_attribute in cases:
            with self.subTest(title=title):
                # Arrange
                attribute = Mock()
                attribute.IsValid.return_value = True
                attribute.Get.return_value = True
                prim = Mock()
                prim.GetAttribute.return_value = attribute
                item = Mock()
                item.data = prim
                plugin = IsCategoryFilterPlugin(category_type=category_type)

                # Act
                result = plugin.filter_predicate(item)

                # Assert
                self.assertEqual(expected, result)
                if reads_attribute:
                    prim.GetAttribute.assert_called_once_with(_SKY_ATTRIBUTE)
                else:
                    prim.GetAttribute.assert_not_called()

    async def test_filter_predicate_with_real_usd_category_states_returns_expected_match(self):
        """Return the expected category result for representative USD attribute states."""
        cases = [
            ("all_categories", "All Categories", None, True),
            ("unknown_category", "Unknown Category", None, False),
            ("sky_true", "Sky", True, True),
            ("sky_false", "Sky", False, False),
            ("sky_missing", "Sky", None, False),
        ]

        for title, category_type, sky_value, expected in cases:
            with self.subTest(title=title):
                # Arrange
                stage = Usd.Stage.CreateInMemory()
                prim = UsdGeom.Xform.Define(stage, "/World/Prim").GetPrim()
                if sky_value is not None:
                    prim.CreateAttribute(_SKY_ATTRIBUTE, Sdf.ValueTypeNames.Bool).Set(sky_value)
                item = StageManagerItem(prim.GetPath(), data=prim)
                plugin = IsCategoryFilterPlugin(category_type=category_type)

                # Act
                result = plugin.filter_predicate(item)

                # Assert
                self.assertEqual(expected, result)

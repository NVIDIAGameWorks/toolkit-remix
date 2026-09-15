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

from unittest import mock

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem
from pxr import UsdSkel

from ...skeleton_prims import SkeletonPrimsFilterPlugin

__all__ = ["TestSkeletonPrimsFilterPluginUnit"]


class TestSkeletonPrimsFilterPluginUnit(omni.kit.test.AsyncTestCase):
    """Test skeleton prim filtering."""

    async def test_filter_predicate_with_skeleton_related_prim_returns_expected_result(self):
        """Retain binding and skeleton container prims while rejecting unrelated prims."""
        cases = (
            ("binding", True, None, True),
            ("skeleton", False, "Skeleton", True),
            ("skel_root", False, "SkelRoot", True),
            ("unrelated", False, "Xform", False),
        )

        for title, has_binding_api, type_name, expected_result in cases:
            with self.subTest(title=title):
                # Arrange
                prim = mock.Mock()
                prim.HasAPI.return_value = has_binding_api
                prim.GetTypeName.return_value = type_name
                item = StageManagerItem(title, data=prim)
                plugin = SkeletonPrimsFilterPlugin()

                # Act
                result = plugin.filter_predicate(item)

                # Assert
                self.assertEqual(expected_result, result)
                prim.HasAPI.assert_called_once_with(UsdSkel.BindingAPI)
                if has_binding_api:
                    prim.GetTypeName.assert_not_called()
                else:
                    prim.GetTypeName.assert_called_once_with()

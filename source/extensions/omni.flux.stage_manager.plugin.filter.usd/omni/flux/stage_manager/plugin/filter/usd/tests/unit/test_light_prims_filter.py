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

from ... import light_prims
from ...light_prims import LightPrimsFilterPlugin

__all__ = ["TestLightPrimsFilterPlugin"]


class TestLightPrimsFilterPlugin(omni.kit.test.AsyncTestCase):
    """Tests user-facing light filtering."""

    async def test_filter_predicate_with_light_states_returns_supported_lights_without_preparation(self):
        """Return supported lights without mutating preparation state."""
        cases = (
            ("supported_light", True, mock.sentinel.supported_light_type, True),
            ("unsupported_light", True, None, False),
            ("non_light", False, None, False),
        )

        for title, has_light_api, light_type, expected_result in cases:
            with self.subTest(title=title):
                # Arrange
                plugin = LightPrimsFilterPlugin()
                prim = mock.Mock()
                prim.HasAPI.return_value = has_light_api
                item = StageManagerItem(f"/World/{title}", data=prim)

                with mock.patch.object(light_prims, "get_light_type", return_value=light_type) as get_light_type:
                    predicate = plugin.build_filter_predicate()

                    # Act
                    result = predicate(item)

                # Assert
                self.assertEqual(expected_result, result)
                self.assertFalse(item.is_display_name_candidate)
                prim.HasAPI.assert_called_once()
                if has_light_api:
                    get_light_type.assert_called_once_with(prim)
                else:
                    get_light_type.assert_not_called()

    async def test_build_filter_predicate_with_inactive_filter_marks_only_supported_lights(self):
        """Prepare only supported lights for an inactive intrinsic configuration."""
        cases = (
            ("supported_light", True, mock.sentinel.supported_light_type, True, True),
            ("unsupported_light", True, None, False, False),
            ("non_light", False, None, False, False),
        )

        for title, has_light_api, light_type, expected_result, expected_candidate in cases:
            with self.subTest(title=title):
                # Arrange
                plugin = LightPrimsFilterPlugin(filter_active=False)
                prim = mock.Mock()
                prim.HasAPI.return_value = has_light_api
                item = StageManagerItem(f"/World/{title}", data=prim)

                with mock.patch.object(light_prims, "get_light_type", return_value=light_type) as get_light_type:
                    predicate = plugin.build_filter_predicate(mock.Mock())

                    # Act
                    result = predicate(item)

                # Assert
                self.assertEqual(expected_result, result)
                self.assertEqual(expected_candidate, item.is_display_name_candidate)
                prim.HasAPI.assert_called_once()
                if has_light_api:
                    get_light_type.assert_called_once_with(prim)
                else:
                    get_light_type.assert_not_called()

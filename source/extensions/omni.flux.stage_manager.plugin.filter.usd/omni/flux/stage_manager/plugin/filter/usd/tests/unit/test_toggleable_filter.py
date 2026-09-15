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
from omni.flux.stage_manager.factory import StageManagerItem
from pydantic import Field

from ...base import ToggleableUSDFilterPlugin

__all__ = ["TestToggleableUSDFilterPluginUnit"]


class _TestToggleableFilterPlugin(ToggleableUSDFilterPlugin):
    """Record item evaluations for the toggleable-filter contract test."""

    display_name: str = Field(default="Test Toggleable Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)

    evaluated_items: list[StageManagerItem] = Field(default_factory=list, exclude=True)

    def _evaluate_item(self, item: StageManagerItem) -> bool:
        """Record the evaluated item and return its data truthiness."""
        self.evaluated_items.append(item)
        return bool(item.data)


class TestToggleableUSDFilterPluginUnit(omni.kit.test.AsyncTestCase):
    """Test the shared toggleable-filter predicate contract."""

    async def test_filter_predicate_with_toggle_states_returns_match_inversion_or_pass_through(self):
        """Apply the shared activity and inclusion policy around one item evaluation."""
        cases = (
            ("active_include_match", True, True, object(), True, 1),
            ("active_include_no_match", True, True, None, False, 1),
            ("active_exclude_match", True, False, object(), False, 1),
            ("active_exclude_no_match", True, False, None, True, 1),
            ("inactive", False, True, None, True, 0),
        )

        for title, filter_active, include_results, item_data, expected_result, expected_evaluations in cases:
            with self.subTest(title=title):
                # Arrange
                filter_plugin = _TestToggleableFilterPlugin(
                    filter_active=filter_active, include_results=include_results
                )
                item = StageManagerItem("item", data=item_data)

                # Act
                result = filter_plugin.filter_predicate(item)

                # Assert
                self.assertEqual(expected_result, result)
                self.assertEqual(expected_evaluations, len(filter_plugin.evaluated_items))
                if expected_evaluations:
                    self.assertIs(item, filter_plugin.evaluated_items[0])

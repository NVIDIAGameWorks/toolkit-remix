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

import threading

import omni.kit.test

from ...items import StageManagerItem
from ...plugins.filter_plugin import StageManagerFilterPlugin

__all__ = ["TestStageManagerFilterPlugin"]

_KEPT_IDENTIFIER = "kept"


class _FilterPlugin(StageManagerFilterPlugin):
    """Provide a concrete filter plugin for the base-contract test."""

    def filter_predicate(self, item: StageManagerItem) -> bool:
        """Keep items with the configured identifier."""
        return item.identifier == _KEPT_IDENTIFIER

    def build_ui(self, *args, **kwargs):
        """Satisfy the UI plugin contract without building test UI."""


class TestStageManagerFilterPlugin(omni.kit.test.AsyncTestCase):
    """Test Stage Manager filter-plugin base contracts."""

    async def test_build_filter_predicate_with_optional_cancel_event_returns_item_results(self):
        """Return the item predicate with or without refresh cancellation state."""
        for predicate_arguments in ((), (threading.Event(),)):
            with self.subTest(title=f"cancel_event={bool(predicate_arguments)}"):
                # Arrange
                plugin = _FilterPlugin(display_name="Test", tooltip="Test filter")

                # Act
                predicate = plugin.build_filter_predicate(*predicate_arguments)

                # Assert
                self.assertTrue(predicate(StageManagerItem(_KEPT_IDENTIFIER)))
                self.assertFalse(predicate(StageManagerItem("discarded")))

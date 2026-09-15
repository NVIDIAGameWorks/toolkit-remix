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

from unittest.mock import MagicMock, patch

from lightspeed.trex.capture_tree.model import CaptureTreeDelegate, CaptureTreeItem
from omni.kit.test import AsyncTestCase


class TestCaptureTreeDelegate(AsyncTestCase):
    """Tests CaptureTreeDelegate item double-click dispatch."""

    async def test_on_item_double_clicked_with_left_button_dispatches_item(self):
        """Dispatch the capture item when the left button double-clicks it."""
        # Arrange
        callback = MagicMock()
        item = CaptureTreeItem("C:/captures/capture.usda", None)
        with patch.object(CaptureTreeDelegate, "_CaptureTreeDelegate__create_bigger_image_ui"):
            delegate = CaptureTreeDelegate(item_double_clicked_fn=callback)
        self.addCleanup(delegate.destroy)

        # Act
        delegate._on_item_double_clicked(item, 0, 0, 0, 0)

        # Assert
        callback.assert_called_once_with(item)

    async def test_on_item_double_clicked_with_non_left_button_does_not_dispatch(self):
        """Ignore a double-click from a button other than the left button."""
        # Arrange
        callback = MagicMock()
        item = CaptureTreeItem("C:/captures/capture.usda", None)
        with patch.object(CaptureTreeDelegate, "_CaptureTreeDelegate__create_bigger_image_ui"):
            delegate = CaptureTreeDelegate(item_double_clicked_fn=callback)
        self.addCleanup(delegate.destroy)

        # Act
        delegate._on_item_double_clicked(item, 0, 0, 1, 0)

        # Assert
        callback.assert_not_called()

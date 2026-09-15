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

from unittest.mock import AsyncMock, patch

from lightspeed.trex.capture_tree.model import CaptureTreeModel
from omni.kit.test import AsyncTestCase


class TestCaptureTreeModel(AsyncTestCase):
    """Tests CaptureTreeModel progress refresh behavior."""

    async def test_refresh_when_progress_is_hidden_does_not_fetch_progress(self):
        """Skip progress fetching when progress display is disabled."""
        # Arrange
        model = CaptureTreeModel("", show_progress=False)
        self.addCleanup(model.destroy)

        with patch.object(model, "fetch_progress") as mock_fetch_progress:
            # Act
            model.refresh([])

        # Assert
        mock_fetch_progress.assert_not_called()

    async def test_refresh_when_progress_is_visible_fetches_progress(self):
        """Fetch progress when progress display is enabled."""
        # Arrange
        model = CaptureTreeModel("", show_progress=True)
        self.addCleanup(model.destroy)

        with patch.object(model, "fetch_progress") as mock_fetch_progress:
            # Act
            model.refresh([])

        # Assert
        mock_fetch_progress.assert_called_once()

    async def test_fetch_progress_with_no_children_completes_cleanly(self):
        """Notify progress completion without scheduling item work for no children."""
        # Arrange
        model = CaptureTreeModel("")
        self.addCleanup(model.destroy)

        with (
            patch.object(model, "_CaptureTreeModel__task_completed") as mock_task_completed,
            patch.object(model, "_CaptureTreeModel__on_progress_updated") as mock_on_progress_updated,
            patch.object(model, "async_get_captured_hashes", AsyncMock()) as mock_async_get_captured_hashes,
        ):
            # Act
            await model._CaptureTreeModel__fetch_progress([])

        # Assert
        mock_async_get_captured_hashes.assert_not_awaited()
        mock_on_progress_updated.assert_called_once()
        mock_task_completed.assert_called_once()

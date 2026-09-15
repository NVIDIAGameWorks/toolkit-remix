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

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from lightspeed.common.constants import REMIX_CAPTURE_FOLDER
from lightspeed.trex.capture_tree.model import CaptureTreeItem
from lightspeed.trex.project_wizard.core import ProjectWizardKeys
from omni.kit.test import AsyncTestCase

from ... import setup_ui
from ...setup_ui import SetupPage


class TestSetupPage(AsyncTestCase):
    """Tests SetupPage capture-picker state changes."""

    async def setUp(self):
        """Create an isolated setup page."""
        self._temporary_directory = TemporaryDirectory()
        with (
            patch.object(setup_ui, "_CaptureCoreSetup", return_value=MagicMock()),
            patch.object(setup_ui, "_CaptureTreeModel", return_value=MagicMock()),
            patch.object(setup_ui, "_CaptureTreeDelegate", return_value=MagicMock()),
        ):
            self._page = SetupPage()

    async def tearDown(self):
        """Destroy the setup page and its temporary directory."""
        self._page.destroy()
        self._temporary_directory.cleanup()

    async def test_fetch_capture_files_wrapped_current_directory_publishes_results(self):
        """Publish captures fetched for the current Remix directory."""
        # Arrange
        remix_directory = Path(self._temporary_directory.name)
        captures_directory = remix_directory / REMIX_CAPTURE_FOLDER
        captures = [(str(captures_directory / "capture.usda"), None)]
        self._page.payload = {ProjectWizardKeys.REMIX_DIRECTORY.value: remix_directory}
        published = MagicMock()

        async def fetch(_directory):
            return captures

        with patch.object(setup_ui, "_async_wrap", return_value=fetch):
            # Act
            await self._page._SetupPage__fetch_capture_files_wrapped(captures_directory, published)

        # Assert
        published.assert_called_once_with(captures)

    async def test_fetch_capture_files_wrapped_stale_directory_does_not_publish(self):
        """Avoid publishing captures fetched for a previous Remix directory."""
        # Arrange
        stale_directory = Path(self._temporary_directory.name) / "old" / REMIX_CAPTURE_FOLDER
        self._page.payload = {ProjectWizardKeys.REMIX_DIRECTORY.value: Path(self._temporary_directory.name) / "current"}
        published = MagicMock()

        async def fetch(_directory):
            return [("stale.usda", None)]

        with patch.object(setup_ui, "_async_wrap", return_value=fetch):
            # Act
            await self._page._SetupPage__fetch_capture_files_wrapped(stale_directory, published)

        # Assert
        published.assert_not_called()

    async def test_fetch_capture_files_wrapped_destroyed_page_does_not_publish(self):
        """Avoid publishing captures after the setup page is destroyed."""
        # Arrange
        captures_directory = Path(self._temporary_directory.name) / REMIX_CAPTURE_FOLDER
        published = MagicMock()

        async def fetch(_directory):
            self._page.destroy()
            return [("capture.usda", None)]

        with patch.object(setup_ui, "_async_wrap", return_value=fetch):
            # Act
            await self._page._SetupPage__fetch_capture_files_wrapped.__wrapped__(
                self._page, captures_directory, published
            )

        # Assert
        published.assert_not_called()

    async def test_update_payload_remix_new_directory_clears_capture_file(self):
        """Clear the selected capture when the Remix directory changes."""
        # Arrange
        old_directory = Path(self._temporary_directory.name) / "old"
        new_directory = Path(self._temporary_directory.name) / "new"
        self._page.payload = {
            ProjectWizardKeys.REMIX_DIRECTORY.value: old_directory,
            ProjectWizardKeys.CAPTURE_FILE.value: old_directory / "captures" / "capture.usda",
        }
        self._page._capture_selected = True
        self._page._project_path_picker = MagicMock()

        with (
            patch.object(self._page, "_SetupPage__validate_project_path", return_value=None),
            patch.object(self._page, "_SetupPage__enable_capture_picker"),
        ):
            # Act
            self._page._SetupPage__update_payload_remix(str(new_directory))

        # Assert
        self.assertEqual(new_directory, self._page.payload[ProjectWizardKeys.REMIX_DIRECTORY.value])
        self.assertNotIn(ProjectWizardKeys.CAPTURE_FILE.value, self._page.payload)
        self.assertFalse(self._page._capture_selected)

    async def test_capture_item_double_clicked_when_unblocked_selects_capture_and_requests_next(self):
        """Select the activated capture and advance when all requirements are valid."""
        # Arrange
        item = CaptureTreeItem("C:/captures/capture.usda", None)
        request_next = MagicMock()
        self._page._capture_tree = SimpleNamespace(selection=[])
        self._page._open_or_create = False
        self._page._show_capture_picker = False
        self._page._project_path_valid = True
        self._page._remix_path_valid = True
        self._page._capture_selected = False
        self._page.request_next = request_next

        # Act
        self._page._SetupPage__on_capture_item_double_clicked(item)

        # Assert
        self.assertIs(item, self._page._capture_tree.selection[0])
        self.assertEqual(Path(item.path), self._page.payload[ProjectWizardKeys.CAPTURE_FILE.value])
        self.assertTrue(self._page._capture_selected)
        self.assertFalse(self._page.blocked)
        request_next.assert_called_once_with()

    async def test_capture_item_double_clicked_when_other_input_invalid_selects_without_requesting_next(self):
        """Select the activated capture without advancing when the page remains blocked."""
        # Arrange
        item = CaptureTreeItem("C:/captures/capture.usda", None)
        request_next = MagicMock()
        self._page._capture_tree = SimpleNamespace(selection=[])
        self._page._open_or_create = False
        self._page._show_capture_picker = False
        self._page._project_path_valid = False
        self._page._remix_path_valid = True
        self._page._capture_selected = False
        self._page.request_next = request_next

        # Act
        self._page._SetupPage__on_capture_item_double_clicked(item)

        # Assert
        self.assertIs(item, self._page._capture_tree.selection[0])
        self.assertEqual(Path(item.path), self._page.payload[ProjectWizardKeys.CAPTURE_FILE.value])
        self.assertTrue(self._page._capture_selected)
        self.assertTrue(self._page.blocked)
        request_next.assert_not_called()

    async def test_open_or_create_changed_to_create_without_capture_blocks_page(self):
        """Block project creation when no capture is selected."""
        # Arrange
        self._page._open_or_create = True
        self._page._show_capture_picker = False
        self._page._project_path_valid = True
        self._page._remix_path_valid = True
        self._page._capture_selected = False
        self._page.blocked = False

        # Act
        self._page.open_or_create = False

        # Assert
        self.assertTrue(self._page.blocked)

    async def test_show_capture_picker_enabled_without_capture_blocks_existing_project(self):
        """Block existing-project setup when the enabled picker has no selection."""
        # Arrange
        self._page._open_or_create = True
        self._page._show_capture_picker = False
        self._page._project_path_valid = True
        self._page._remix_path_valid = True
        self._page._capture_selected = False
        self._page.blocked = False

        # Act
        self._page.show_capture_picker = True

        # Assert
        self.assertTrue(self._page.blocked)

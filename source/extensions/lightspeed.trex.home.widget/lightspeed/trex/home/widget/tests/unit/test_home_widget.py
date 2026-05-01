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

from unittest.mock import AsyncMock, MagicMock, patch

from omni.kit.test import AsyncTestCase

from lightspeed.trex.home.widget.home_widget import HomePageWidget


def _make_widget() -> HomePageWidget:
    widget = HomePageWidget.__new__(HomePageWidget)
    widget._recent_saved_file = MagicMock()
    widget._recent_saved_file.find_thumbnail_async = AsyncMock(return_value=None)
    widget._set_recent_items = MagicMock()
    return widget


class TestRefreshRecentItemsDeferred(AsyncTestCase):
    async def test_successful_project_is_included_with_correct_details(self):
        # Arrange
        widget = _make_widget()
        widget._recent_saved_file.get_recent_file_data.return_value = {
            "/project/good.usda": {"game": "GameA", "capture": "/cap.usda"},
        }
        widget._recent_saved_file.get_path_detail.return_value = {
            "Game": "GameA",
            "Capture": "/cap.usda",
            "Invalid": [],
        }
        widget._recent_saved_file.find_thumbnail_async = AsyncMock(
            return_value=("/project/good.usda", "/project/.thumbs/256x256/good.usda.png")
        )

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        items = widget._set_recent_items.call_args[0][0]
        self.assertEqual(len(items), 1)
        title, thumbnail, details = items[0]
        self.assertEqual(title, "good.usda")
        self.assertIn(".thumbs", thumbnail)
        self.assertEqual(details.get("Game"), "GameA")
        self.assertEqual(details.get("Capture"), "/cap.usda")

    async def test_oserror_from_get_path_detail_marks_item_invalid(self):
        # Arrange
        widget = _make_widget()
        widget._recent_saved_file.get_recent_file_data.return_value = {
            "/project/broken.usda": {"game": "G", "capture": "C"},
        }
        widget._recent_saved_file.get_path_detail.side_effect = OSError("disk error")

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        items = widget._set_recent_items.call_args[0][0]
        self.assertEqual(len(items), 1)
        _, _, details = items[0]
        self.assertIn("Invalid", details)

    async def test_attributeerror_from_get_path_detail_marks_item_invalid(self):
        # Arrange
        widget = _make_widget()
        widget._recent_saved_file.get_recent_file_data.return_value = {
            "/project/bad.usda": {"game": "G", "capture": "C"},
        }
        widget._recent_saved_file.get_path_detail.side_effect = AttributeError("missing attr")

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        items = widget._set_recent_items.call_args[0][0]
        self.assertEqual(len(items), 1)
        _, _, details = items[0]
        self.assertIn("Invalid", details)

    async def test_get_path_detail_returning_invalid_entry_is_preserved_in_details(self):
        # Arrange
        widget = _make_widget()
        widget._recent_saved_file.get_recent_file_data.return_value = {
            "/project/corrupt.usda": {"game": "G", "capture": "C"},
        }
        widget._recent_saved_file.get_path_detail.return_value = {
            "Invalid": [("/project/corrupt.usda", "unrecognised header")],
        }

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        items = widget._set_recent_items.call_args[0][0]
        _, _, details = items[0]
        self.assertIn("Invalid", details)
        self.assertGreater(len(details["Invalid"]), 0)

    async def test_oserror_from_find_thumbnail_marks_item_invalid(self):
        # Arrange
        widget = _make_widget()
        widget._recent_saved_file.get_recent_file_data.return_value = {
            "/project/no_thumb.usda": {"game": "G", "capture": "C"},
        }
        widget._recent_saved_file.get_path_detail.return_value = {
            "Game": "G",
            "Capture": "C",
            "Invalid": [],
        }
        widget._recent_saved_file.find_thumbnail_async = AsyncMock(side_effect=OSError("thumbnail read failed"))

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        items = widget._set_recent_items.call_args[0][0]
        _, _, details = items[0]
        self.assertIn("Invalid", details)

    async def test_mix_of_failing_and_succeeding_projects_all_appear_in_items(self):
        # Arrange
        widget = _make_widget()
        widget._recent_saved_file.get_recent_file_data.return_value = {
            "/project/good.usda": {"game": "GameA", "capture": "/cap.usda"},
            "/project/oserror.usda": {"game": "G", "capture": "C"},
            "/project/attributeerror.usda": {"game": "G", "capture": "C"},
            "/project/bad_magic.usda": {"game": "G", "capture": "C"},
            "/project/unsupported.abc": {"game": "G", "capture": "C"},
        }

        def _path_detail(path, _recent_file_data=None):
            if path == "/project/good.usda":
                return {"Game": "GameA", "Capture": "/cap.usda", "Invalid": []}
            if path == "/project/oserror.usda":
                raise OSError("permission denied")
            if path == "/project/attributeerror.usda":
                raise AttributeError("NoneType has no attribute 'realPath'")
            if path == "/project/bad_magic.usda":
                return {"Invalid": [("/project/bad_magic.usda", "unrecognised header")]}
            if path == "/project/unsupported.abc":
                return {"Invalid": [("/project/unsupported.abc", "unsupported extension '.abc'")]}
            return {}

        widget._recent_saved_file.get_path_detail.side_effect = _path_detail

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        items = widget._set_recent_items.call_args[0][0]
        self.assertEqual(len(items), 5)

        by_title = {title: details for title, _, details in items}
        self.assertEqual(by_title["good.usda"].get("Game"), "GameA")
        self.assertIn("Invalid", by_title["oserror.usda"])
        self.assertIn("Invalid", by_title["attributeerror.usda"])
        self.assertIn("Invalid", by_title["bad_magic.usda"])
        self.assertIn("Invalid", by_title["unsupported.abc"])


class TestLoadWorkFile(AsyncTestCase):
    async def test_invalid_item_shows_dialog_and_does_not_fire_load_event(self):
        # Arrange
        widget = HomePageWidget.__new__(HomePageWidget)
        widget._window_visible = True
        mock_item = MagicMock()
        mock_item.invalid = [("/project/invalid.usda", "unrecognised header")]
        widget._recent_model = MagicMock()
        widget._recent_model.get_item_by_path.return_value = mock_item

        with (
            patch("lightspeed.trex.home.widget.home_widget._TrexMessageDialog") as mock_dialog,
            patch("lightspeed.trex.home.widget.home_widget._get_event_manager_instance") as mock_event_manager,
        ):
            # Act
            widget._load_work_file("/project/invalid.usda")

        # Assert
        mock_dialog.assert_called_once()
        mock_event_manager.assert_not_called()

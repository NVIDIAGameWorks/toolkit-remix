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

import asyncio

from unittest.mock import AsyncMock, MagicMock, patch

from lightspeed.common.constants import GlobalEventNames
from omni.flux.utils.common import Event, EventSubscription
from omni.kit.test import AsyncTestCase

from lightspeed.trex.home.widget.home_widget import HomePageWidget


def _make_widget() -> HomePageWidget:
    widget = HomePageWidget.__new__(HomePageWidget)
    widget._window_visible = True
    widget._refresh_recent_items_generation = 0
    widget._refresh_recent_items_task = None
    widget._recent_saved_file = MagicMock()
    widget._recent_saved_file.find_thumbnail_async = AsyncMock(return_value=None)
    widget._set_recent_items = MagicMock()
    return widget


class TestRefreshRecentItemsDeferred(AsyncTestCase):
    """Test deferred recent-project refresh behavior."""

    async def test_stale_refresh_does_not_update_or_save(self):
        """Discard stale recent-project refresh results without saving or updating Home."""
        # Arrange
        widget = _make_widget()
        widget._refresh_recent_items_generation = 2
        recent_file_data = {"/project/stale.usda": {"game": "Game", "capture": "Capture"}}
        widget._recent_saved_file.get_recent_file_data.return_value = recent_file_data

        def _path_detail(path, shared_recent_file_data):
            shared_recent_file_data[path]["validation"] = {"schema": 1}
            return {"Game": "Game", "Invalid": []}

        widget._recent_saved_file.get_path_detail.side_effect = _path_detail

        # Act
        await widget._refresh_recent_items_deferred(1)

        # Assert
        widget._recent_saved_file.save_recent_file.assert_not_called()
        widget._recent_saved_file.find_thumbnail_async.assert_not_called()
        widget._set_recent_items.assert_not_called()

    async def test_validation_updates_are_saved_before_thumbnail_lookup(self):
        """Persist changed validation data before thumbnail discovery begins."""
        # Arrange
        widget = _make_widget()
        recent_file_data = {
            "/project/first.usda": {"game": "First", "capture": "/first_capture.usda"},
            "/project/second.usda": {"game": "Second", "capture": "/second_capture.usda"},
        }
        widget._recent_saved_file.get_recent_file_data.return_value = recent_file_data
        events = []

        def _path_detail(path, shared_recent_file_data):
            events.append(f"validate:{path}")
            shared_recent_file_data[path]["validation"] = {"schema": 1}
            return {"Game": shared_recent_file_data[path]["game"], "Invalid": []}

        def _save_recent_file(_data):
            events.append("save")

        async def _find_thumbnail(path):
            events.append(f"thumbnail:{path}")

        widget._recent_saved_file.get_path_detail.side_effect = _path_detail
        widget._recent_saved_file.save_recent_file.side_effect = _save_recent_file
        widget._recent_saved_file.find_thumbnail_async.side_effect = _find_thumbnail

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        self.assertEqual(["validate:/project/first.usda", "validate:/project/second.usda", "save"], events[:3])
        widget._recent_saved_file.save_recent_file.assert_called_once_with(recent_file_data)

    async def test_thumbnail_lookups_run_with_bounded_concurrency(self):
        """Limit concurrent thumbnail lookups to the configured batch size."""
        # Arrange
        widget = _make_widget()
        widget._recent_saved_file.get_recent_file_data.return_value = {
            f"/project/{index}.usda": {"game": f"Game {index}", "capture": f"/capture/{index}.usda"}
            for index in range(9)
        }
        widget._recent_saved_file.get_path_detail.return_value = {"Invalid": []}
        release = asyncio.Event()
        active = 0
        maximum_active = 0
        release_scheduled = False

        async def _find_thumbnail(_path):
            nonlocal active, maximum_active, release_scheduled
            active += 1
            maximum_active = max(maximum_active, active)
            if not release_scheduled:
                asyncio.get_running_loop().call_soon(release.set)
                release_scheduled = True
            await release.wait()
            active -= 1

        widget._recent_saved_file.find_thumbnail_async.side_effect = _find_thumbnail

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        self.assertEqual(8, maximum_active)
        self.assertEqual(9, widget._recent_saved_file.find_thumbnail_async.await_count)

    async def test_cold_validation_yields_between_batches(self):
        """Yield one application update between cold-validation batches."""
        # Arrange
        widget = _make_widget()
        recent_file_data = {
            f"/project/{index}.usda": {"game": f"Game {index}", "capture": f"/capture/{index}.usda"}
            for index in range(9)
        }
        widget._recent_saved_file.get_recent_file_data.return_value = recent_file_data

        def _path_detail(path, shared_recent_file_data):
            shared_recent_file_data[path]["validation"] = {"schema": 1}
            return {"Invalid": []}

        widget._recent_saved_file.get_path_detail.side_effect = _path_detail
        app = MagicMock()
        app.next_update_async = AsyncMock()

        with patch("lightspeed.trex.home.widget.home_widget.omni.kit.app.get_app", return_value=app):
            # Act
            await widget._refresh_recent_items_deferred()

        # Assert
        app.next_update_async.assert_awaited_once_with()

    async def test_current_refresh_logs_ready_only_after_all_items_reach_model(self):
        """Report recents ready only after the complete model update."""
        # Arrange
        widget = _make_widget()
        widget._refresh_recent_items_generation = 1
        widget._recent_saved_file.get_recent_file_data.return_value = {
            "/project/first.usda": {"game": "First", "capture": "FirstCapture"},
            "/project/second.usda": {"game": "Second", "capture": "SecondCapture"},
        }
        widget._recent_saved_file.get_path_detail.side_effect = [
            {"Game": "First", "Invalid": []},
            {"Game": "Second", "Invalid": []},
        ]
        later_thumbnail_started = asyncio.Event()
        release_later_thumbnail = asyncio.Event()

        async def _find_thumbnail(path):
            if path.endswith("second.usda"):
                later_thumbnail_started.set()
                await release_later_thumbnail.wait()

        widget._recent_saved_file.find_thumbnail_async.side_effect = _find_thumbnail

        # Act
        with patch("lightspeed.trex.home.widget.home_widget.carb.log_info") as log_info_mock:
            refresh_task = asyncio.create_task(widget._refresh_recent_items_deferred(1))
            try:
                await later_thumbnail_started.wait()
                model_called_while_pending = widget._set_recent_items.called
                ready_logged_while_pending = log_info_mock.called
            finally:
                release_later_thumbnail.set()
                await refresh_task

        # Assert
        self.assertFalse(model_called_while_pending)
        self.assertFalse(ready_logged_while_pending)
        widget._set_recent_items.assert_called_once()
        log_info_mock.assert_called_once_with("RECENTS_READY")

    async def test_cache_hits_do_not_save_recent_data(self):
        """Avoid writing recent-project data when every cache entry is unchanged."""
        # Arrange
        widget = _make_widget()
        recent_file_data = {
            "/project/first.usda": {"game": "First", "capture": "/first_capture.usda"},
            "/project/second.usda": {"game": "Second", "capture": "/second_capture.usda"},
        }
        widget._recent_saved_file.get_recent_file_data.return_value = recent_file_data
        widget._recent_saved_file.get_path_detail.side_effect = [
            {"Game": "First", "Invalid": []},
            {"Game": "Second", "Invalid": []},
        ]

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        widget._recent_saved_file.save_recent_file.assert_not_called()

    async def test_cache_miss_does_not_restore_project_removed_during_refresh(self):
        """Do not save validation for a project removed while thumbnail lookup yields."""
        # Arrange
        widget = _make_widget()
        recent_file_data = {
            "/project/removed.usda": {"game": "Removed", "capture": "/removed_capture.usda"},
        }
        widget._recent_saved_file.get_recent_file_data.side_effect = [recent_file_data, {}]

        def _path_detail(path, shared_recent_file_data):
            shared_recent_file_data[path]["validation"] = {"schema": 1}
            return {"Game": "Removed", "Invalid": []}

        widget._recent_saved_file.get_path_detail.side_effect = _path_detail

        # Act
        await widget._refresh_recent_items_deferred()

        # Assert
        self.assertEqual(2, widget._recent_saved_file.get_recent_file_data.call_count)
        widget._recent_saved_file.save_recent_file.assert_not_called()

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


class TestVisibilityRefresh(AsyncTestCase):
    """Test Home refresh scheduling across visibility changes."""

    async def test_show_refreshes_when_becoming_visible(self):
        """Refresh Home when it becomes visible."""
        # Arrange
        widget = HomePageWidget.__new__(HomePageWidget)
        widget._window_visible = False
        widget.refresh = MagicMock()
        widget._HomePageWidget__settings = MagicMock()
        widget._HomePageWidget__settings.get.return_value = False
        main_window = MagicMock()

        with patch("lightspeed.trex.home.widget.home_widget.get_main_window", return_value=main_window):
            # Act
            widget.show(True)

        # Assert
        widget.refresh.assert_called_once_with()

    async def test_hide_cancels_pending_refresh(self):
        """Cancel pending recent-project work when Home hides."""
        # Arrange
        widget = HomePageWidget.__new__(HomePageWidget)
        widget._window_visible = True
        widget._refresh_recent_items_generation = 0
        pending_task = MagicMock()
        widget._refresh_recent_items_task = pending_task
        widget._HomePageWidget__settings = MagicMock()
        widget._HomePageWidget__settings.get.return_value = False
        main_window = MagicMock()

        with patch("lightspeed.trex.home.widget.home_widget.get_main_window", return_value=main_window):
            # Act
            widget.show(False)

        # Assert
        pending_task.cancel.assert_called_once_with()
        self.assertIsNone(widget._refresh_recent_items_task)

    async def test_destroy_releases_wizard_completion_subscription(self):
        """Release the owned wizard-completion subscription during teardown."""
        # Arrange
        wizard_completed = Event()
        callback = MagicMock()
        widget = HomePageWidget.__new__(HomePageWidget)
        widget._refresh_recent_items_generation = 0
        widget._refresh_recent_items_task = None
        widget._sub_wizard_completed = EventSubscription(wizard_completed, callback)

        with patch("lightspeed.trex.home.widget.home_widget.reset_default_attrs"):
            # Act
            widget.destroy()

        # Assert
        self.assertNotIn(callback, wizard_completed)
        self.assertIsNone(widget._sub_wizard_completed)


class TestLoadWorkFile(AsyncTestCase):
    """Test Home workfile dispatch behavior."""

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

    async def test_existing_project_delegates_validation_and_workspace_transition_to_stagecraft(self):
        """Delegate existing-project validation and workspace loading to StageCraft."""
        # Arrange
        widget = HomePageWidget.__new__(HomePageWidget)
        widget._window_visible = True
        widget._recent_model = MagicMock()
        widget._recent_model.get_item_by_path.return_value = None
        event_manager = MagicMock()

        with (
            patch("lightspeed.trex.home.widget.home_widget.Path.exists", return_value=True),
            patch("lightspeed.trex.home.widget.home_widget._get_event_manager_instance", return_value=event_manager),
            patch("lightspeed.trex.home.widget.home_widget.load_layout") as mock_load_layout,
        ):
            # Act
            widget._load_work_file("/project/legacy.usda")

        # Assert
        event_manager.call_global_custom_event.assert_called_once_with(
            GlobalEventNames.LOAD_PROJECT_PATH.value, "/project/legacy.usda"
        )
        mock_load_layout.assert_not_called()

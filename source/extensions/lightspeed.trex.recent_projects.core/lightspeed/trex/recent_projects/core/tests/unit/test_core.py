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

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from omni.kit.test import AsyncTestCase

from lightspeed.trex.recent_projects.core import RecentProjectsCore

_RECENT_FILE_ATTR = "_RecentProjectsCore__get_recent_file"


class TestRecentProjectsCorePersistence(AsyncTestCase):
    async def test_save_and_reload_round_trip(self):
        # Arrange
        data = {"/some/project.usda": {"game": "GameA", "capture": "/cap.usda"}}
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                core = RecentProjectsCore()
                core.save_recent_file(data)

                # Act
                loaded = core.get_recent_file_data()

        # Assert
        self.assertEqual(loaded, data)

    async def test_missing_file_returns_empty_dict(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                # Act
                result = RecentProjectsCore().get_recent_file_data()

        # Assert
        self.assertEqual(result, {})

    async def test_corrupt_json_returns_empty_dict(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            Path(recent_file).write_text("NOT JSON {{", encoding="utf8")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                # Act
                result = RecentProjectsCore().get_recent_file_data()

        # Assert
        self.assertEqual(result, {})

    async def test_corrupt_json_creates_backup_file(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            Path(recent_file).write_text("NOT JSON {{", encoding="utf8")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                # Act
                RecentProjectsCore().get_recent_file_data()

            # Assert
            self.assertTrue(Path(f"{recent_file}.bak").exists())

    async def test_malformed_entry_non_dict_is_skipped(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            raw = {
                "/good/project.usda": {"game": "G", "capture": "C"},
                "/bad/project.usda": "not a dict",
            }
            Path(recent_file).write_text(json.dumps(raw), encoding="utf8")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                # Act
                result = RecentProjectsCore().get_recent_file_data()

        # Assert
        self.assertIn("/good/project.usda", result)
        self.assertNotIn("/bad/project.usda", result)

    async def test_malformed_entry_missing_required_key_is_skipped(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            raw = {
                "/good/project.usda": {"game": "G", "capture": "C"},
                "/no_capture.usda": {"game": "G"},
            }
            Path(recent_file).write_text(json.dumps(raw), encoding="utf8")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                # Act
                result = RecentProjectsCore().get_recent_file_data()

        # Assert
        self.assertIn("/good/project.usda", result)
        self.assertNotIn("/no_capture.usda", result)

    async def test_save_creates_missing_parent_directories(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "a", "b", "c")
            nested_file = os.path.join(nested, "recent_saved_file.json")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=nested_file):
                # Act
                RecentProjectsCore().save_recent_file({"/p.usda": {"game": "G", "capture": "C"}})

            # Assert
            self.assertTrue(Path(nested_file).exists())


class TestRecentProjectsCoreOperations(AsyncTestCase):
    async def test_append_adds_new_path_with_correct_metadata(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                # Act
                result = RecentProjectsCore().append_path_to_recent_file("/proj.usda", "GameA", "/cap.usda")

        # Assert
        self.assertIn("/proj.usda", result)
        self.assertEqual(result["/proj.usda"]["game"], "GameA")
        self.assertEqual(result["/proj.usda"]["capture"], "/cap.usda")

    async def test_append_moves_duplicate_to_end_and_updates_metadata(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                core = RecentProjectsCore()
                core.append_path_to_recent_file("/first.usda", "Original", "C")
                core.append_path_to_recent_file("/second.usda", "G", "C")

                # Act
                result = core.append_path_to_recent_file("/first.usda", "Updated", "C")

        # Assert
        self.assertEqual(list(result.keys())[-1], "/first.usda")
        self.assertEqual(result["/first.usda"]["game"], "Updated")

    async def test_append_truncates_list_to_41_items(self):
        # Arrange
        existing = {f"/proj_{i}.usda": {"game": "G", "capture": "C"} for i in range(45)}
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                core = RecentProjectsCore()
                with patch.object(core, "get_recent_file_data", return_value=existing):
                    # Act
                    result = core.append_path_to_recent_file("/new.usda", "G", "C", save=False)

        # Assert
        self.assertLessEqual(len(result), 41)

    async def test_remove_existing_path_removes_it(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                core = RecentProjectsCore()
                core.append_path_to_recent_file("/proj.usda", "G", "C")

                # Act
                result = core.remove_path_from_recent_file("/proj.usda")

        # Assert
        self.assertNotIn("/proj.usda", result)

    async def test_remove_preserves_other_entries(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                core = RecentProjectsCore()
                core.append_path_to_recent_file("/keep.usda", "G", "C")
                core.append_path_to_recent_file("/remove.usda", "G", "C")

                # Act
                result = core.remove_path_from_recent_file("/remove.usda")

        # Assert
        self.assertIn("/keep.usda", result)
        self.assertNotIn("/remove.usda", result)

    async def test_remove_nonexistent_path_is_noop(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                core = RecentProjectsCore()
                core.append_path_to_recent_file("/proj.usda", "G", "C")

                # Act
                result = core.remove_path_from_recent_file("/other.usda")

        # Assert
        self.assertIn("/proj.usda", result)


class TestRecentProjectsCoreGetPathDetail(AsyncTestCase):
    async def test_get_path_detail_passes_usd_validation_but_find_or_open_raises(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.usda")
            Path(path).write_bytes(b"#usda 1.0\n")
            recent_file_data = {path: {"game": "TestGame", "capture": "/capture/cap.usda"}}
            core = RecentProjectsCore()

            def _find_or_open_raises(_layer_path: str):
                raise RuntimeError("simulated Sdf.Layer.FindOrOpen failure")

            # Act
            with patch(
                "lightspeed.trex.recent_projects.core.core.Sdf.Layer.FindOrOpen",
                side_effect=_find_or_open_raises,
            ) as find_or_open_mock:
                result = core.get_path_detail(path, recent_file_data=recent_file_data)

        # Assert
        find_or_open_mock.assert_called_once_with(path)
        self.assertEqual(result.get("Game"), "TestGame")
        self.assertEqual(result.get("Capture"), "/capture/cap.usda")
        self.assertEqual(len(result.get("Invalid", [])), 1)


class TestConvertSize(AsyncTestCase):
    async def test_zero_returns_zero_bytes_string(self):
        # Act
        result = RecentProjectsCore.convert_size(0)

        # Assert
        self.assertEqual(result, "0B")

    async def test_negative_returns_zero_bytes_string(self):
        # Act
        result = RecentProjectsCore.convert_size(-1)

        # Assert
        self.assertEqual(result, "0B")

    async def test_small_value_reports_bytes(self):
        # Act
        result = RecentProjectsCore.convert_size(512)

        # Assert
        self.assertIn("B", result)

    async def test_kilobyte_range_reports_kb(self):
        # Act
        result = RecentProjectsCore.convert_size(2 * 1024)

        # Assert
        self.assertIn("KB", result)

    async def test_megabyte_range_reports_mb(self):
        # Act
        result = RecentProjectsCore.convert_size(2 * 1024 * 1024)

        # Assert
        self.assertIn("MB", result)

    async def test_gigabyte_range_reports_gb(self):
        # Act
        result = RecentProjectsCore.convert_size(2 * 1024 * 1024 * 1024)

        # Assert
        self.assertIn("GB", result)

    async def test_astronomically_large_value_does_not_raise(self):
        # Act
        result = RecentProjectsCore.convert_size(10**30)

        # Assert
        self.assertIsInstance(result, str)

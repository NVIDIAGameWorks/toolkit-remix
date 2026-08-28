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
from unittest.mock import MagicMock, patch

from omni.kit.test import AsyncTestCase

import lightspeed.trex.recent_projects.core.core as core_module
from lightspeed.trex.recent_projects.core import RecentProjectsCore

_RECENT_FILE_ATTR = "_RecentProjectsCore__get_recent_file"


def _fingerprint_for(path: str) -> dict[str, int | bool]:
    """Return the expected fingerprint for a test file."""
    path_stat = Path(path).stat()
    return {
        "exists": True,
        "is_file": True,
        "size": path_stat.st_size,
        "mtime_ns": path_stat.st_mtime_ns,
    }


def _cached_entry(path: str) -> dict:
    return {
        "game": "CachedGame",
        "capture": "/capture/cap.usda",
        "validation": {
            "schema": 2,
            "inputs": {"game": "CachedGame", "capture": "/capture/cap.usda"},
            "fingerprints": {path: _fingerprint_for(path)},
            "details": {"Game": "CachedGame", "Capture": "/capture/cap.usda", "Invalid": []},
        },
    }


class TestRecentProjectsCorePersistence(AsyncTestCase):
    """Test recent-project persistence and atomic replacement."""

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

    async def test_save_recent_file_replaces_target_atomically(self):
        """Replace the recent-project file atomically after writing its temporary file."""
        # Arrange
        data = {"/project.usda": {"game": "Game", "capture": "/capture.usda"}}
        real_replace = os.replace
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            Path(recent_file).write_text("{}", encoding="utf8")
            with (
                patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file),
                patch.object(core_module.os, "replace", wraps=real_replace) as replace_mock,
                patch.object(core_module.Path, "unlink") as unlink_mock,
            ):
                # Act
                RecentProjectsCore().save_recent_file(data)

            # Assert
            temporary_path, target_path = replace_mock.call_args.args
            self.assertEqual(recent_file, target_path)
            self.assertFalse(Path(temporary_path).exists())
            self.assertEqual(data, json.loads(Path(recent_file).read_text(encoding="utf8")))
            unlink_mock.assert_not_called()

    async def test_save_recent_file_replace_failure_preserves_existing_file(self):
        """Preserve the existing recent-project file when atomic replacement fails."""
        # Arrange
        original_data = {"/original.usda": {"game": "Original", "capture": "/original_capture.usda"}}
        replacement_data = {"/replacement.usda": {"game": "Replacement", "capture": "/replacement_capture.usda"}}
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            Path(recent_file).write_text(json.dumps(original_data), encoding="utf8")
            with (
                patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file),
                patch.object(core_module.os, "replace", side_effect=OSError("replace failed")),
            ):
                # Act
                RecentProjectsCore().save_recent_file(replacement_data)

            # Assert
            self.assertEqual(original_data, json.loads(Path(recent_file).read_text(encoding="utf8")))
            self.assertEqual([Path(recent_file)], list(Path(tmp).iterdir()))


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
    async def test_get_path_fingerprint_stats_existing_path_once(self):
        """Reuse one stat result to classify an existing path."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.usda")
            Path(path).write_bytes(b"#usda 1.0\n")
            original_stat = Path.stat

            with patch.object(Path, "stat", autospec=True, side_effect=original_stat) as stat_mock:
                # Act
                result = RecentProjectsCore._get_path_fingerprint(path)

        # Assert
        self.assertTrue(result["is_file"])
        stat_mock.assert_called_once_with(Path(path))

    async def test_get_path_detail_reuses_cached_validation_when_fingerprint_matches(self):
        """Reuse cached validation when all recorded fingerprints match."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.usda")
            Path(path).write_bytes(b"#usda 1.0\n")
            entry = _cached_entry(path)

            # Act
            with patch("lightspeed.trex.recent_projects.core.core.Sdf.Layer.FindOrOpen") as find_or_open_mock:
                result = RecentProjectsCore().get_path_detail(path, recent_file_data={path: entry})

        # Assert
        find_or_open_mock.assert_not_called()
        self.assertEqual(result, entry["validation"]["details"])

    async def test_cached_validation_rejects_stale_entries(self):
        """Reject incomplete, mismatched, and legacy cache entries."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.usda")
            Path(path).write_bytes(b"#usda 1.0\n")
            entries = []
            missing_success = _cached_entry(path)
            missing_success["validation"]["details"] = {}
            entries.append(("missing success", missing_success))
            changed_input = _cached_entry(path)
            changed_input["game"] = "CurrentGame"
            entries.append(("changed input", changed_input))
            legacy_schema = _cached_entry(path)
            legacy_schema["validation"]["schema"] = 1
            entries.append(("legacy schema", legacy_schema))

            # Act / Assert
            for reason, entry in entries:
                with self.subTest(reason=reason):
                    self.assertIsNone(RecentProjectsCore._get_cached_validation_details(entry, path))

    async def test_get_path_detail_successful_cache_miss_mutates_supplied_data_without_saving(self):
        """Cache successful validation in caller-owned data without persisting it."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.usda")
            Path(path).write_bytes(b"#usda 1.0\n")
            expected_fingerprint = _fingerprint_for(path)
            recent_file_data = {path: {"game": "TestGame", "capture": "/capture/cap.usda"}}
            core = RecentProjectsCore()

            project_layer = MagicMock()
            project_layer.subLayerPaths = []

            with (
                patch.object(core, "save_recent_file") as save_recent_file_mock,
                patch(
                    "lightspeed.trex.recent_projects.core.core.Sdf.Layer.FindOrOpen",
                    return_value=project_layer,
                ),
            ):
                # Act
                result = core.get_path_detail(path, recent_file_data=recent_file_data)

        # Assert
        validation = recent_file_data[path]["validation"]
        self.assertEqual(set(validation), {"schema", "inputs", "fingerprints", "details"})
        self.assertEqual(validation["inputs"], {"game": "TestGame", "capture": "/capture/cap.usda"})
        self.assertEqual(validation["fingerprints"], {path: expected_fingerprint})
        self.assertEqual(validation["details"]["Game"], "TestGame")
        self.assertEqual(validation["details"]["Capture"], "/capture/cap.usda")
        self.assertEqual(validation["details"]["Invalid"], [])
        self.assertEqual(result["Invalid"], [])
        save_recent_file_mock.assert_not_called()

    async def test_get_path_detail_successful_cache_miss_saves_data_loaded_by_core(self):
        """Persist successful validation when the core owns the recent-project data."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.usda")
            Path(path).write_bytes(b"#usda 1.0\n")
            recent_file_data = {path: {"game": "TestGame", "capture": "/capture/cap.usda"}}
            core = RecentProjectsCore()
            project_layer = MagicMock()
            project_layer.subLayerPaths = []

            with (
                patch.object(core, "get_recent_file_data", return_value=recent_file_data),
                patch.object(core, "save_recent_file") as save_recent_file_mock,
                patch(
                    "lightspeed.trex.recent_projects.core.core.Sdf.Layer.FindOrOpen",
                    return_value=project_layer,
                ),
            ):
                # Act
                core.get_path_detail(path)

        # Assert
        save_recent_file_mock.assert_called_once_with(recent_file_data)

    async def test_get_path_detail_retries_transient_read_failure_without_fingerprint_change(self):
        """Revalidate after a transient read failure clears without changing the file."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.usda")
            Path(path).write_bytes(b"#usda 1.0\n")
            recent_file_data = {path: {"game": "TestGame", "capture": "/capture/cap.usda"}}
            fingerprint = _fingerprint_for(path)
            core = RecentProjectsCore()

            with patch("builtins.open", side_effect=PermissionError(32, "file is in use")):
                first_result = core.get_path_detail(path, recent_file_data=recent_file_data)
            validation_after_failure = recent_file_data[path].get("validation")

            project_layer = MagicMock()
            project_layer.subLayerPaths = []
            with patch(
                "lightspeed.trex.recent_projects.core.core.Sdf.Layer.FindOrOpen",
                return_value=project_layer,
            ) as find_or_open_mock:
                # Act
                second_result = core.get_path_detail(path, recent_file_data=recent_file_data)
            fingerprint_after = _fingerprint_for(path)

        # Assert
        self.assertEqual(fingerprint, fingerprint_after)
        self.assertIn("could not be read", first_result["Invalid"][0][1])
        self.assertIsNone(validation_after_failure)
        self.assertEqual([], second_result["Invalid"])
        find_or_open_mock.assert_called_once_with(path)

    async def test_get_path_detail_stores_root_and_non_capture_sublayer_fingerprints(self):
        """Store fingerprints for the root and validated non-capture sublayers."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.usda")
            replacement_path = os.path.join(tmp, "replacement.usda")
            capture_path = os.path.join(tmp, "capture.usda")
            for layer_path in (path, replacement_path, capture_path):
                Path(layer_path).write_bytes(b"#usda 1.0\n")
            expected_fingerprints = {
                path: _fingerprint_for(path),
                replacement_path: _fingerprint_for(replacement_path),
            }

            recent_file_data = {path: {"game": "TestGame", "capture": capture_path}}
            project_layer = MagicMock()
            project_layer.subLayerPaths = ["replacement.usda", "capture.usda"]
            replacement_layer = MagicMock()
            replacement_layer.customLayerData = {}
            core = RecentProjectsCore()

            with (
                patch.object(core, "save_recent_file") as save_recent_file_mock,
                patch("lightspeed.trex.recent_projects.core.core.Sdf.Layer.FindOrOpen", return_value=project_layer),
                patch(
                    "lightspeed.trex.recent_projects.core.core.Sdf.ComputeAssetPathRelativeToLayer",
                    side_effect=[replacement_path, capture_path],
                ),
                patch(
                    "lightspeed.trex.recent_projects.core.core.Sdf.Layer.FindOrOpenRelativeToLayer",
                    return_value=replacement_layer,
                ),
                patch(
                    "lightspeed.trex.recent_projects.core.core.is_layer_from_capture",
                    side_effect=lambda layer_path: layer_path == capture_path,
                ),
            ):
                # Act
                core.get_path_detail(path, recent_file_data=recent_file_data)

        # Assert
        fingerprints = recent_file_data[path]["validation"]["fingerprints"]
        self.assertEqual(fingerprints, expected_fingerprints)
        self.assertNotIn(capture_path, fingerprints)
        save_recent_file_mock.assert_not_called()

    async def test_cached_validation_invalidates_changed_root_or_dependency(self):
        """Reject cached validation when a recorded file changes."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.usda")
            replacement_path = os.path.join(tmp, "replacement.usda")
            Path(path).write_bytes(b"#usda 1.0\n")
            Path(replacement_path).write_bytes(b"#usda 1.0\n")
            for changed_path in (path, replacement_path):
                with self.subTest(changed_path=changed_path):
                    entry = _cached_entry(path)
                    entry["validation"]["fingerprints"][replacement_path] = _fingerprint_for(replacement_path)
                    Path(changed_path).write_bytes(b"#usda 1.0\n# changed\n")

                    # Act / Assert
                    self.assertIsNone(RecentProjectsCore._get_cached_validation_details(entry, path))

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

    async def test_get_path_detail_invalid_file_preserves_recent_entry_metadata(self):
        """Preserve recent-project metadata when validation fails."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            recent_file = os.path.join(tmp, "recent_saved_file.json")
            path = os.path.join(tmp, "corrupt.usda")
            Path(path).write_bytes(b"NOTVALID")
            recent_file_data = {path: {"game": "RecentGame", "capture": "/capture/recent.usda"}}

            with patch.object(RecentProjectsCore, _RECENT_FILE_ATTR, return_value=recent_file):
                # Act
                result = RecentProjectsCore().get_path_detail(path, recent_file_data=recent_file_data)

        # Assert
        self.assertIn("Invalid", result)
        self.assertEqual(result["Game"], "RecentGame")
        self.assertEqual(result["Capture"], "/capture/recent.usda")


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

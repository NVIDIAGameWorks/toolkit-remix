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

import os
import tempfile
from pathlib import Path

from omni.kit.test import AsyncTestCase

from lightspeed.trex.recent_projects.core import RecentProjectsCore
from lightspeed.trex.recent_projects.core.core import UsdFileSignature


class TestRecentProjectsCoreValidators(AsyncTestCase):
    async def test_for_extension_returns_correct_member(self):
        # Arrange
        test_cases = [
            (".usda", UsdFileSignature.USDA),
            (".usdc", UsdFileSignature.USDC),
            (".usdz", UsdFileSignature.USDZ),
            (".usd", UsdFileSignature.USD),
        ]

        for ext, expected in test_cases:
            with self.subTest(ext=ext):
                # Act
                result = UsdFileSignature.for_extension(ext)

                # Assert
                self.assertIs(result, expected)

    async def test_for_extension_returns_none_for_unknown_extensions(self):
        # Arrange
        unknown_extensions = (".txt", ".usd2", "", ".obj", ".abc")

        for ext in unknown_extensions:
            with self.subTest(ext=ext):
                # Act
                result = UsdFileSignature.for_extension(ext)

                # Assert
                self.assertIsNone(result)

    async def test_usd_extension_accepts_both_usda_and_usdc_signatures(self):
        # Act
        signatures = UsdFileSignature.USD.signatures

        # Assert
        self.assertIn(b"#usda 1.", signatures)
        self.assertIn(b"PXR-USDC", signatures)

    async def test_single_format_members_have_exactly_one_signature(self):
        # Assert
        self.assertEqual(len(UsdFileSignature.USDA.signatures), 1)
        self.assertEqual(len(UsdFileSignature.USDC.signatures), 1)
        self.assertEqual(len(UsdFileSignature.USDZ.signatures), 1)

    async def test_extension_property_matches_member_name(self):
        # Assert
        self.assertEqual(UsdFileSignature.USDA.extension, ".usda")
        self.assertEqual(UsdFileSignature.USDC.extension, ".usdc")
        self.assertEqual(UsdFileSignature.USDZ.extension, ".usdz")
        self.assertEqual(UsdFileSignature.USD.extension, ".usd")

    async def test_validate_path_empty_string_fails(self):
        # Act
        ok, reason = RecentProjectsCore._validate_path("")

        # Assert
        self.assertFalse(ok)
        self.assertIn("empty", reason)

    async def test_validate_path_whitespace_only_fails(self):
        # Act
        ok, reason = RecentProjectsCore._validate_path("   ")

        # Assert
        self.assertFalse(ok)
        self.assertIn("empty", reason)

    async def test_validate_path_nonexistent_file_fails(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "does_not_exist.usda")

            # Act
            ok, reason = RecentProjectsCore._validate_path(missing)

        # Assert
        self.assertFalse(ok)
        self.assertIn("does not exist", reason)

    async def test_validate_path_directory_fails(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            # Act
            ok, reason = RecentProjectsCore._validate_path(tmp)

        # Assert
        self.assertFalse(ok)
        self.assertIn("not a file", reason)

    async def test_validate_path_existing_file_passes(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.usda")
            Path(path).touch()

            # Act
            ok, reason = RecentProjectsCore._validate_path(path)

        # Assert
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    async def test_validate_json_entry_string_value_fails(self):
        # Act
        ok, reason = RecentProjectsCore._validate_json_entry("/path.usda", "string")

        # Assert
        self.assertFalse(ok)
        self.assertIn("not a dict", reason)

    async def test_validate_json_entry_list_value_fails(self):
        # Act
        ok, reason = RecentProjectsCore._validate_json_entry("/path.usda", ["game", "capture"])

        # Assert
        self.assertFalse(ok)
        self.assertIn("not a dict", reason)

    async def test_validate_json_entry_none_value_fails(self):
        # Act
        ok, reason = RecentProjectsCore._validate_json_entry("/path.usda", None)

        # Assert
        self.assertFalse(ok)
        self.assertIn("not a dict", reason)

    async def test_validate_json_entry_missing_game_key_fails(self):
        # Act
        ok, reason = RecentProjectsCore._validate_json_entry("/path.usda", {"capture": "/cap.usda"})

        # Assert
        self.assertFalse(ok)
        self.assertIn("game", reason)

    async def test_validate_json_entry_missing_capture_key_fails(self):
        # Act
        ok, reason = RecentProjectsCore._validate_json_entry("/path.usda", {"game": "MyGame"})

        # Assert
        self.assertFalse(ok)
        self.assertIn("capture", reason)

    async def test_validate_json_entry_valid_entry_passes(self):
        # Act
        ok, reason = RecentProjectsCore._validate_json_entry("/path.usda", {"game": "MyGame", "capture": "/cap.usda"})

        # Assert
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    async def test_validate_json_entry_extra_keys_are_allowed(self):
        # Act
        ok, _ = RecentProjectsCore._validate_json_entry("/path.usda", {"game": "G", "capture": "C", "extra": "ignored"})

        # Assert
        self.assertTrue(ok)

    async def test_validate_usd_file_unsupported_extension_fails(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "file.txt")
            Path(path).write_bytes(b"#usda 1.0\n")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertFalse(ok)
        self.assertIn("unsupported extension", reason)

    async def test_validate_usd_file_empty_file_fails(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.usda")
            Path(path).touch()

            # Act
            ok, reason = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertFalse(ok)
        self.assertIn("empty", reason)

    async def test_validate_usd_file_wrong_magic_bytes_fails(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.usda")
            Path(path).write_bytes(b"NOTVALID")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertFalse(ok)
        self.assertIn("unrecognised header", reason)

    async def test_validate_usd_file_valid_usda_magic_passes(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "valid.usda")
            Path(path).write_bytes(b"#usda 1.0\n# rest of file")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    async def test_validate_usd_file_valid_usdc_magic_passes(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "valid.usdc")
            Path(path).write_bytes(b"PXR-USDCpadding")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    async def test_validate_usd_file_valid_usdz_magic_passes(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "valid.usdz")
            Path(path).write_bytes(b"PK\x03\x04extradata")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    async def test_validate_usd_file_usd_extension_accepts_usda_magic(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "file.usd")
            Path(path).write_bytes(b"#usda 1.0\n")

            # Act
            ok, _ = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertTrue(ok)

    async def test_validate_usd_file_usd_extension_accepts_usdc_magic(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "file.usd")
            Path(path).write_bytes(b"PXR-USDCpadding")

            # Act
            ok, _ = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertTrue(ok)

    async def test_validate_usd_file_usda_extension_rejects_usdc_magic(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mismatch.usda")
            Path(path).write_bytes(b"PXR-USDCpadding")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertFalse(ok)
        self.assertIn("unrecognised header", reason)

    async def test_validate_usd_file_usdc_extension_rejects_usda_magic(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mismatch.usdc")
            Path(path).write_bytes(b"#usda 1.0\n")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_file(path)

        # Assert
        self.assertFalse(ok)
        self.assertIn("unrecognised header", reason)

    async def test_validate_usd_layer_nonexistent_fails_at_path_stage(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "missing.usda")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_layer(missing)

        # Assert
        self.assertFalse(ok)
        self.assertIn("does not exist", reason)

    async def test_validate_usd_layer_bad_magic_fails_at_file_stage(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.usda")
            Path(path).write_bytes(b"NOTVALID")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_layer(path)

        # Assert
        self.assertFalse(ok)
        self.assertIn("unrecognised header", reason)

    async def test_validate_usd_layer_valid_file_passes(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "good.usda")
            Path(path).write_bytes(b"#usda 1.0\n")

            # Act
            ok, reason = RecentProjectsCore._validate_usd_layer(path)

        # Assert
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    async def test_get_path_detail_nonexistent_path_returns_invalid(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "missing.usda")

            # Act
            result = RecentProjectsCore().get_path_detail(missing)

        # Assert
        self.assertIn("Invalid", result)
        self.assertGreater(len(result["Invalid"]), 0)

    async def test_get_path_detail_corrupt_magic_returns_invalid(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "corrupt.usda")
            Path(path).write_bytes(b"NOTVALID")

            # Act
            result = RecentProjectsCore().get_path_detail(path)

        # Assert
        self.assertIn("Invalid", result)
        self.assertGreater(len(result["Invalid"]), 0)
        self.assertIsNone(result.get("Game"))
        self.assertIsNone(result.get("Capture"))

    async def test_get_path_detail_unsupported_extension_returns_invalid(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "file.abc")
            Path(path).write_bytes(b"#usda 1.0\n")

            # Act
            result = RecentProjectsCore().get_path_detail(path)

        # Assert
        self.assertIn("Invalid", result)
        self.assertGreater(len(result["Invalid"]), 0)

    async def test_get_path_detail_empty_file_returns_invalid(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.usda")
            Path(path).touch()

            # Act
            result = RecentProjectsCore().get_path_detail(path)

        # Assert
        self.assertIn("Invalid", result)
        self.assertGreater(len(result["Invalid"]), 0)

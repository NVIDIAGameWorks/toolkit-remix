import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import omni.client
import omni.kit.test
from lightspeed.trex.replacement.core.shared import Setup as ReplacementCore


class MockListEntry:
    def __init__(self, path: str, size: int = 0, access: int = 0, flags=omni.client.ItemFlags.READABLE_FILE):
        self.relative_path = path
        self.size = size
        self.access = access
        self.flags = flags
        self.modified_time = datetime.now()


class TestSetup(omni.kit.test.AsyncTestCase):

    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()

    async def test_is_path_valid_existing_file_valid_usd(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usd")), True, True)

    async def test_is_path_valid_existing_file_valid_usda(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usda")), True, True)

    async def test_is_path_valid_existing_file_valid_usdc(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usdc")), True, True)

    async def test_is_path_valid_new_file_valid_usd(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usd")), False, True)

    async def test_is_path_valid_new_file_valid_usda(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usda")), False, True)

    async def test_is_path_valid_new_file_valid_usdc(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usdc")), False, True)

    async def test_is_path_valid_invalid_path_empty(self):
        await self.__run_test_is_path_valid("", False, False)

    async def test_is_path_valid_invalid_not_usd(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.abc")), False, False)

    async def test_is_path_valid_invalid_is_in_capture_dir(self):
        await self.__run_test_is_path_valid(
            str(Path(f"{self.temp_dir.name}/capture/subdir/replacements.usd")), False, False
        )

    async def test_is_path_valid_invalid_is_in_gamereadyassets_dir(self):
        await self.__run_test_is_path_valid(
            str(Path(f"{self.temp_dir.name}/gameReadyAssets/subdir/replacements.usd")), False, False
        )

    async def test_is_path_valid_invalid_not_writable(self):
        # Arrange
        path = Path(f"{self.temp_dir.name}/replacements.usd")

        with patch.object(omni.client, "stat") as mocked:
            read_only_entry = MockListEntry(str(path), flags=omni.client.ItemFlags.READABLE_FILE)
            mocked.return_value = (omni.client.Result.OK, read_only_entry)

            # Act
            is_valid = ReplacementCore.is_path_valid(str(path), True)

            # Assert
            self.assertEqual(False, is_valid)

    async def test_is_path_valid_invalid_cannot_have_children(self):
        # Arrange
        path = Path(f"{self.temp_dir.name}/replacements.usd")

        with patch.object(omni.client, "stat") as mocked:
            read_only_entry = MockListEntry(str(path), flags=omni.client.ItemFlags.READABLE_FILE)
            mocked.return_value = (omni.client.Result.OK, read_only_entry)

            # Act
            is_valid = ReplacementCore.is_path_valid(str(path), False)

            # Assert
            self.assertEqual(False, is_valid)

    async def __run_test_is_path_valid(self, path: str, existing: bool, expected_result: bool):
        # Arrange
        if path and existing:
            os.makedirs(Path(path).parent, exist_ok=True)
            with open(path, "xb"):
                pass

        # Act
        is_valid = ReplacementCore.is_path_valid(path, existing)

        # Assert
        self.assertEqual(expected_result, is_valid)

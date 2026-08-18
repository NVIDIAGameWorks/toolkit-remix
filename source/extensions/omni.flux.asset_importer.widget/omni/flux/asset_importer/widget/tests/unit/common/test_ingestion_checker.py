"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.kit
import omni.kit.test
from omni.flux.asset_importer.core.data_models import SUPPORTED_ASSET_EXTENSIONS, SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.widget.common.ingestion_checker import validate_file_selection, validate_texture_selection


class TestIngestionCheckerUnit(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()

    async def test_validate_file_selection_pass(self):
        # Arrange
        base_path = Path(self.temp_dir.name)
        ext = sorted(SUPPORTED_ASSET_EXTENSIONS)[0]
        items = [base_path / f"0.{ext}", base_path / f"1.{ext}", base_path / f"2.{ext}"]
        for item in items:
            item.touch()

        # Act
        is_valid = validate_file_selection(items)

        # Assert
        self.assertTrue(is_valid)

    async def test_validate_file_selection_uppercase_usd_pass(self):
        """Accept supported uppercase USD file extensions."""
        # Arrange
        base_path = Path(self.temp_dir.name)
        items = [base_path / "0.USD", base_path / "1.USDA", base_path / "2.USDC"]
        for item in items:
            item.touch()

        # Act
        is_valid = validate_file_selection(items)

        # Assert
        self.assertTrue(is_valid)

    async def test_validate_texture_selection_pass(self):
        # Arrange
        base_path = Path(self.temp_dir.name)
        ext = sorted(SUPPORTED_TEXTURE_EXTENSIONS)[0]
        items = [base_path / f"0.{ext}", base_path / f"1.{ext}", base_path / f"2.{ext}"]
        for item in items:
            item.touch()

        # Act
        is_valid = validate_texture_selection(items)

        # Assert
        self.assertTrue(is_valid)

    async def test_validate_file_selection_fail_bad_ext(self):
        # Arrange
        base_path = Path(self.temp_dir.name)
        ext = sorted(SUPPORTED_ASSET_EXTENSIONS)[0]
        items = [
            base_path / f"0.{ext}",
            base_path / f"1.{ext}",
            base_path / "2.INVALID",
        ]
        for item in items:
            item.touch()

        # Act
        is_valid = validate_file_selection(items)

        # Assert
        self.assertFalse(is_valid)

    async def test_validate_texture_selection_fail_bad_ext(self):
        # Arrange
        base_path = Path(self.temp_dir.name)
        ext = sorted(SUPPORTED_TEXTURE_EXTENSIONS)[0]
        items = [
            base_path / "0.INVALID",
            base_path / f"1.{ext}",
            base_path / f"2.{ext}",
        ]
        for item in items:
            item.touch()

        # Act
        is_valid = validate_texture_selection(items)

        # Assert
        self.assertFalse(is_valid)

    async def test_validate_file_selection_with_extensionless_file_returns_false(self):
        # Arrange
        item = Path(self.temp_dir.name) / "extensionless"
        item.touch()

        # Act
        is_valid = validate_file_selection([item])

        # Assert
        self.assertFalse(is_valid)

    async def test_validate_texture_selection_with_extensionless_file_returns_false(self):
        # Arrange
        item = Path(self.temp_dir.name) / "extensionless"
        item.touch()

        # Act
        is_valid = validate_texture_selection([item])

        # Assert
        self.assertFalse(is_valid)

    async def test_validate_file_selection_fail_bad_dir(self):
        # Arrange
        base_path = Path(self.temp_dir.name)
        sub1 = base_path / "first"
        sub2 = base_path / "second"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)
        items = [sub1, sub2]

        # Act
        is_valid = validate_file_selection(items)

        # Assert
        self.assertFalse(is_valid)

    async def test_validate_texture_selection_fail_bad_dir(self):
        # Arrange
        base_path = Path(self.temp_dir.name)
        sub1 = base_path / "first"
        sub2 = base_path / "second"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)
        items = [sub1, sub2]

        # Act
        is_valid = validate_texture_selection(items)

        # Assert
        self.assertFalse(is_valid)

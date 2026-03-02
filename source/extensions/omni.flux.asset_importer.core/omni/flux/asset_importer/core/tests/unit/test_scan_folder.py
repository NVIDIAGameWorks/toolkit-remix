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
from unittest.mock import MagicMock

import omni.kit.test

from omni.flux.asset_importer.core.scan_folder.dialog import ScannerCore


class TestScannerCore(omni.kit.test.AsyncTestCase):
    def test_get_valid_files_excludes_invalid_extensions(self):
        """REMIX-4347: get_valid_files must only return files with valid ingest extensions."""
        core = ScannerCore(callbacks={})

        # (filename, suffix, should_be_included)
        cases = [
            ("texture.png", ".png", True),
            ("mesh.fbx", ".fbx", True),
            ("material.mdl", ".mdl", False),
            ("readme.txt", ".txt", False),
            ("metadata.meta", ".meta", False),
        ]

        for name, suffix, should_include in cases:
            with self.subTest(file=name):
                # Arrange
                mock_file = MagicMock()
                mock_file.is_file.return_value = True
                mock_file.suffix = suffix
                mock_file.name = name
                mock_folder = MagicMock(spec=Path)
                mock_folder.iterdir.return_value = iter([mock_file])

                # Act
                result = core.get_valid_files(mock_folder, "")

                # Assert
                if should_include:
                    self.assertEqual(len(result), 1)
                else:
                    self.assertEqual(len(result), 0)

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
from unittest.mock import patch

import omni.kit
import omni.kit.test
import omni.usd
from omni.flux.asset_importer.widget.file_import_list import FileImportItem
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.kit.test_suite.helpers import wait_stage_loading


class TestFileImportListItems(omni.kit.test.AsyncTestCase):

    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.stage = None

    async def test_path_returns_path(self):
        # Arrange
        path_0 = Path("Test")
        item_0 = FileImportItem(path_0)

        # Act
        val = item_0.path

        # Assert
        self.assertEqual(path_0, val)

    async def test_path_is_valid(self):
        # Arrange
        path_0 = Path("Test")
        item_0 = FileImportItem(path_0)

        # Act
        with patch.object(_OmniUrl, "exists") as mock_exist:
            mock_exist.return_value = True
            val, _message = item_0.is_valid(item_0.path)

        # Assert
        self.assertTrue(val)

    async def test_path_is_not_valid(self):
        # Arrange
        path_0 = Path("Test")
        item_0 = FileImportItem(path_0)

        # Act
        val, _message = item_0.is_valid(item_0.path)

        # Assert
        self.assertFalse(val)

    async def test_value_model_returns_value_model(self):
        # Arrange
        path_0 = Path("Test")
        item_0 = FileImportItem(path_0)

        # Act
        val = item_0.value_model

        # Assert
        self.assertEqual(str(path_0), val.get_value_as_string())

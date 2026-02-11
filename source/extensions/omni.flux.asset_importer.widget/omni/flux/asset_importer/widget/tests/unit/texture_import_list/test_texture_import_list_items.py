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
from unittest.mock import Mock

import omni.usd
from omni.flux.asset_importer.widget.texture_import_list import TextureImportItem, TextureTypes


class TestTextureImportListItems(omni.kit.test.AsyncTestCase):
    async def test_path_returns_path(self):
        # Arrange
        path_0 = Path("Test")
        item_0 = TextureImportItem(path_0)

        # Act
        val = item_0.path

        # Assert
        self.assertEqual(path_0, val)

    async def test_texture_type_returns_texture_type(self):
        # Arrange
        item_0 = TextureImportItem(Mock())
        item_1 = TextureImportItem(Mock(), texture_type=TextureTypes.EMISSIVE)

        # Act
        val_0 = item_0.texture_type
        val_1 = item_1.texture_type

        # Assert
        self.assertEqual(TextureTypes.OTHER, val_0)
        self.assertEqual(TextureTypes.EMISSIVE, val_1)

    async def test_texture_type_setter_sets_value_and_triggers_event(self):
        # Arrange
        item_0 = TextureImportItem(Mock())

        callback_mock = Mock()
        _ = item_0.subscribe_item_texture_type_changed(callback_mock)

        # Act
        item_0.texture_type = TextureTypes.NORMAL_DX

        # Assert
        self.assertEqual(TextureTypes.NORMAL_DX, item_0._texture_type)
        self.assertEqual(1, callback_mock.call_count)

    async def test_value_model_returns_value_model(self):
        # Arrange
        path_0 = Path("Test")
        item_0 = TextureImportItem(path_0)

        # Act
        val = item_0.value_model

        # Assert
        self.assertEqual(str(path_0), val.get_value_as_string())

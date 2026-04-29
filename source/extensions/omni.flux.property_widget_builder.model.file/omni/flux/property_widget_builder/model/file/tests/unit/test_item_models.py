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

from types import SimpleNamespace
from unittest.mock import patch

import omni.client
import omni.kit.test
from omni.flux.property_widget_builder.model.file.item_model.name import CustomFileAttributeNameModel
from omni.flux.property_widget_builder.model.file.item_model.name import FileAttributeNameModel
from omni.flux.property_widget_builder.model.file.item_model.value import CustomFileAttributeValueModel
from omni.flux.property_widget_builder.model.file.item_model.value import FileAttributeValueModel


class TestFileItemModels(omni.kit.test.AsyncTestCase):
    async def test_file_attribute_name_model_uses_attribute_when_display_name_is_missing(self):
        # Arrange
        model = FileAttributeNameModel("omniverse://server/file.usda", "42")

        # Act
        value = model.get_value()

        # Assert
        self.assertEqual("42", value)
        self.assertEqual("42", model.get_value_as_string())
        self.assertEqual(42.0, model.get_value_as_float())
        self.assertTrue(model.get_value_as_bool())
        self.assertEqual(42, model.get_value_as_int())

    async def test_file_attribute_name_model_uses_display_name_when_provided(self):
        # Arrange
        model = FileAttributeNameModel("omniverse://server/file.usda", "size", display_attr_name="File Size")

        # Act
        value = model.get_value_as_string()

        # Assert
        self.assertEqual("File Size", value)

    async def test_file_attribute_name_model_with_empty_path_keeps_empty_default_values(self):
        # Arrange
        model = FileAttributeNameModel("", "size")

        # Act
        value = model.get_value()

        # Assert
        self.assertIsNone(value)
        self.assertEqual("", model.get_value_as_string())
        self.assertEqual(0.0, model.get_value_as_float())
        self.assertFalse(model.get_value_as_bool())
        self.assertEqual(0, model.get_value_as_int())

    async def test_custom_file_attribute_name_model_uses_custom_attribute_name(self):
        # Arrange
        model = CustomFileAttributeNameModel("Resolution")

        # Act
        value = model.get_value_as_string()

        # Assert
        self.assertEqual("Resolution", value)

    async def test_file_attribute_value_model_reads_requested_list_entry_attribute(self):
        # Arrange
        entry = SimpleNamespace(flags=omni.client.ItemFlags.READABLE_FILE, size=128)

        with patch.object(omni.client, "stat", return_value=(omni.client.Result.OK, entry)):
            # Act
            model = FileAttributeValueModel("omniverse://server/file.usda", "size")

        # Assert
        self.assertEqual(128, model.get_value())
        self.assertEqual("128", model.get_value_as_string())
        self.assertEqual(128.0, model.get_value_as_float())
        self.assertTrue(model.get_value_as_bool())
        self.assertEqual(128, model.get_value_as_int())

    async def test_file_attribute_value_model_refresh_notifies_when_stat_value_changes(self):
        # Arrange
        first_entry = SimpleNamespace(flags=omni.client.ItemFlags.READABLE_FILE, size=128)
        second_entry = SimpleNamespace(flags=omni.client.ItemFlags.READABLE_FILE, size=256)

        with patch.object(
            omni.client,
            "stat",
            side_effect=[(omni.client.Result.OK, first_entry), (omni.client.Result.OK, second_entry)],
        ):
            model = FileAttributeValueModel("omniverse://server/file.usda", "size")

            with patch.object(model, "_value_changed") as value_changed_mock:
                # Act
                model.refresh()

        # Assert
        self.assertEqual(256, model.get_value())
        value_changed_mock.assert_called_once_with()

    async def test_file_attribute_value_model_ignores_unreadable_files(self):
        # Arrange
        entry = SimpleNamespace(flags=0, size=128)

        with patch.object(omni.client, "stat", return_value=(omni.client.Result.OK, entry)):
            # Act
            model = FileAttributeValueModel("omniverse://server/file.usda", "size")

        # Assert
        self.assertIsNone(model.get_value())
        self.assertEqual("", model.get_value_as_string())
        self.assertEqual(0.0, model.get_value_as_float())
        self.assertFalse(model.get_value_as_bool())
        self.assertEqual(0, model.get_value_as_int())

    async def test_custom_file_attribute_value_model_uses_custom_value_and_multiline_metadata(self):
        # Arrange
        model = CustomFileAttributeValueModel("1024 px", (True, 2))

        # Act
        value = model.get_value_as_string()

        # Assert
        self.assertEqual("1024 px", value)
        self.assertEqual((True, 2), model.multiline)

    async def test_custom_file_attribute_value_model_set_value_updates_cached_value(self):
        # Arrange
        model = CustomFileAttributeValueModel("before", (False, 0))

        # Act
        model.set_value("after")

        # Assert
        self.assertEqual("after", model.get_value())

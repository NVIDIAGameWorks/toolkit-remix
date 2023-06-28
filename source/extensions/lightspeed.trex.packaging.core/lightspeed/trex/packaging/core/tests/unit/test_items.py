"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from unittest.mock import Mock, PropertyMock, call, patch

import omni.kit.test
from lightspeed.trex.packaging.core import ModPackagingSchema
from lightspeed.trex.replacement.core.shared import Setup as ReplacementCore
from omni.flux.utils.common.omni_url import OmniUrl


class TestModPackagingSchema(omni.kit.test.AsyncTestCase):
    async def test_at_least_one_none_should_raise_value_error(self):
        # Arrange
        with self.assertRaises(ValueError) as cm:
            # Act
            ModPackagingSchema.at_least_one([])

        # Assert
        self.assertEqual("At least 1 mod file should exist in the stage", str(cm.exception))

    async def test_at_least_one_valid_should_return_value(self):
        # Arrange
        expected = [Mock()]

        # Act
        val = ModPackagingSchema.at_least_one(expected)

        # Assert
        self.assertEqual(expected, val)

    async def test_is_mod_file_valid_invalid_should_raise_value_error(self):
        # Arrange
        mod_file = Mock()

        with patch.object(ReplacementCore, "is_mod_file") as mod_file_mock:
            mod_file_mock.return_value = False

            with self.assertRaises(ValueError) as cm:
                # Act
                ModPackagingSchema.is_mod_file_valid(mod_file)

        # Assert
        self.assertEqual(f"The path is not a valid mod file: {mod_file}", str(cm.exception))

        self.assertEqual(1, mod_file_mock.call_count)
        self.assertEqual(call(str(mod_file)), mod_file_mock.call_args)

    async def test_is_mod_file_valid_valid_should_return_value(self):
        # Arrange
        mod_file = Mock()

        with patch.object(ReplacementCore, "is_mod_file") as mod_file_mock:
            mod_file_mock.return_value = True

            # Act
            val = ModPackagingSchema.is_mod_file_valid(mod_file)

        # Assert
        self.assertEqual(mod_file, val)

        self.assertEqual(1, mod_file_mock.call_count)
        self.assertEqual(call(str(mod_file)), mod_file_mock.call_args)

    async def test_layer_exists_does_not_exist_should_raise_value_error(self):
        # Arrange
        mod_file = Mock()

        with patch.object(OmniUrl, "exists", new_callable=PropertyMock) as exists_mock:
            exists_mock.return_value = False

            with self.assertRaises(ValueError) as cm:
                # Act
                ModPackagingSchema.layer_exists(mod_file)

        # Assert
        self.assertEqual(f"The selected layer does not exist: {mod_file}", str(cm.exception))
        self.assertEqual(1, exists_mock.call_count)

    async def test_layer_exists_exists_should_return_value(self):
        # Arrange
        mod_file = Mock()

        with patch.object(OmniUrl, "exists", new_callable=PropertyMock) as exists_mock:
            exists_mock.return_value = True

            # Act
            val = ModPackagingSchema.layer_exists(mod_file)

        # Assert
        self.assertEqual(mod_file, val)
        self.assertEqual(1, exists_mock.call_count)

    async def test_is_not_empty_empty_should_raise_value_error(self):
        # Arrange
        with self.assertRaises(ValueError) as cm:
            # Act
            ModPackagingSchema.is_not_empty("    ")

        # Assert
        self.assertEqual("The value cannot be empty", str(cm.exception))

    async def test_is_not_empty_not_empty_should_return_value(self):
        # Arrange
        expected = "TestString"

        # Act
        val = ModPackagingSchema.is_not_empty(expected)

        # Assert
        self.assertEqual(expected, val)

    async def test_is_valid_version_invalid_should_raise_value_error(self):
        # Arrange
        with self.assertRaises(ValueError) as cm:
            # Act
            ModPackagingSchema.is_valid_version("1a.123.abc")

        # Assert
        self.assertEqual(
            'The version must use the following format: "{MAJOR}.{MINOR}.{PATCH}". Example: 1.0.1', str(cm.exception)
        )

    async def test_is_valid_version_valid_should_return_value(self):
        # Arrange
        expected_1 = "123.987.123456789"
        expected_2 = "123.987"

        # Act
        val_1 = ModPackagingSchema.is_valid_version(expected_1)
        val_2 = ModPackagingSchema.is_valid_version(expected_2)

        # Assert
        self.assertEqual(expected_1, val_1)
        self.assertEqual(expected_2, val_2)

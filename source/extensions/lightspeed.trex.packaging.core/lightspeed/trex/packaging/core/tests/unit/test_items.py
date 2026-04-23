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

from unittest.mock import Mock, PropertyMock, call, patch

import omni.kit.test
from lightspeed.trex.packaging.core.enum import ModPackagingMode
from lightspeed.trex.packaging.core.items import ModPackagingSchema
from lightspeed.trex.replacement.core.shared import Setup as ReplacementCore
from omni.flux.asset_importer.core.data_models import UsdExtensions as _UsdExtensions
from omni.flux.utils.common.omni_url import OmniUrl
from pydantic import ValidationError


class TestModPackagingSchema(omni.kit.test.AsyncTestCase):
    @staticmethod
    def _valid_schema_kwargs(**overrides):
        schema_kwargs = {
            "context_name": "Packaging",
            "mod_layer_paths": ["C:/mods/mod.usda"],
            "selected_layer_paths": ["C:/mods/mod.usda"],
            "output_directory": "C:/output",
            "mod_name": "Test Mod",
            "mod_version": "1.0.0",
        }
        schema_kwargs.update(overrides)
        return schema_kwargs

    def _create_schema(self, **overrides):
        with (
            patch.object(ReplacementCore, "is_mod_file", return_value=True),
            patch.object(OmniUrl, "exists", new_callable=PropertyMock, return_value=True),
        ):
            return ModPackagingSchema(**self._valid_schema_kwargs(**overrides))

    def _get_schema_validation_error(self, **overrides):
        with (
            patch.object(ReplacementCore, "is_mod_file", return_value=True),
            patch.object(OmniUrl, "exists", new_callable=PropertyMock, return_value=True),
        ):
            with self.assertRaises(ValidationError) as cm:
                ModPackagingSchema(**self._valid_schema_kwargs(**overrides))

        return cm.exception

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
        mod_file = [Mock()]

        with patch.object(ReplacementCore, "is_mod_file") as mod_file_mock:
            mod_file_mock.return_value = False

            with self.assertRaises(ValueError) as cm:
                # Act
                ModPackagingSchema.is_mod_file_valid(mod_file)

        # Assert
        self.assertEqual(f"The path is not a valid mod file: {mod_file[0]}", str(cm.exception))
        self.assertEqual(1, mod_file_mock.call_count)
        self.assertEqual(call(str(mod_file[0])), mod_file_mock.call_args)

    async def test_is_mod_file_valid_valid_should_return_value(self):
        # Arrange
        mod_file = [Mock()]

        with patch.object(ReplacementCore, "is_mod_file") as mod_file_mock:
            mod_file_mock.return_value = True

            # Act
            val = ModPackagingSchema.is_mod_file_valid(mod_file)

        # Assert
        self.assertEqual(mod_file, val)
        self.assertEqual(1, mod_file_mock.call_count)
        self.assertEqual(call(str(mod_file[0])), mod_file_mock.call_args)

    async def test_layer_exists_does_not_exist_should_raise_value_error(self):
        # Arrange
        mod_file = [Mock()]

        with patch.object(OmniUrl, "exists", new_callable=PropertyMock) as exists_mock:
            exists_mock.return_value = False

            with self.assertRaises(ValueError) as cm:
                # Act
                ModPackagingSchema.layer_exists(mod_file)

        # Assert
        self.assertEqual(f"The selected layer does not exist: {mod_file[0]}", str(cm.exception))
        self.assertEqual(1, exists_mock.call_count)

    async def test_layer_exists_exists_should_return_value(self):
        # Arrange
        mod_file = [Mock()]

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

    async def test_is_valid_version_patch_should_return_value(self):
        # Arrange
        expected = "123.987.123456789"

        # Act
        val = ModPackagingSchema.is_valid_version(expected)

        # Assert
        self.assertEqual(expected, val)

    async def test_is_valid_version_major_minor_should_return_value(self):
        # Arrange
        expected = "123.987"

        # Act
        val = ModPackagingSchema.is_valid_version(expected)

        # Assert
        self.assertEqual(expected, val)

    async def test_schema_defaults_to_flatten_mode_and_usd_output_format(self):
        # Arrange

        # Act
        model = self._create_schema()

        # Assert
        self.assertEqual(ModPackagingMode.FLATTEN, model.packaging_mode)
        self.assertEqual(_UsdExtensions.USD, model.output_format)

    async def test_schema_accepts_packaging_modes(self):
        for packaging_mode, expected_mode in (
            ("redirect", ModPackagingMode.REDIRECT),
            ("import", ModPackagingMode.IMPORT),
            ("flatten", ModPackagingMode.FLATTEN),
        ):
            with self.subTest(packaging_mode=packaging_mode):
                # Arrange

                # Act
                model = self._create_schema(packaging_mode=packaging_mode)

                # Assert
                self.assertEqual(expected_mode, model.packaging_mode)

    async def test_schema_rejects_invalid_packaging_mode(self):
        # Arrange

        # Act
        error = self._get_schema_validation_error(packaging_mode="unsupported")

        # Assert
        self.assertIn("packaging_mode", str(error))

    async def test_schema_accepts_output_formats(self):
        for output_format, expected_output_format in (
            (None, None),
            ("usd", _UsdExtensions.USD),
            ("usda", _UsdExtensions.USDA),
            ("usdc", _UsdExtensions.USDC),
        ):
            with self.subTest(output_format=output_format):
                # Arrange

                # Act
                model = self._create_schema(output_format=output_format)

                # Assert
                self.assertEqual(expected_output_format, model.output_format)

    async def test_schema_rejects_invalid_output_format(self):
        # Arrange

        # Act
        error = self._get_schema_validation_error(output_format="unsupported")

        # Assert
        self.assertIn("output_format", str(error))

    async def test_schema_rejects_legacy_redirect_external_dependencies_field(self):
        # Arrange

        # Act
        error = self._get_schema_validation_error(redirect_external_dependencies=True)

        # Assert
        self.assertIn("redirect_external_dependencies", str(error))

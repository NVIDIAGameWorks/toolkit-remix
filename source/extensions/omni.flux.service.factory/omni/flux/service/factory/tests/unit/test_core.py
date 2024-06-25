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

from unittest.mock import Mock

from omni.flux.service.factory import get_instance
from omni.kit.test.async_unittest import AsyncTestCase


class TestServiceFactoryCore(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.factory = get_instance()

    # After running each test
    async def tearDown(self):
        self.factory.destroy()
        self.factory = None

    async def test_is_service_registered_should_return_expected_value(self):
        # Arrange
        valid_name = "ValidService"
        test_cases = {
            valid_name: True,
            "InvalidService": False,
        }

        for service_name, expected_value in test_cases.items():
            with self.subTest(title=f"service_name_{service_name}"):
                self.factory._services = {valid_name: Mock()}  # noqa PLW0212

                # Act
                value = self.factory.is_service_registered(service_name)

                # Assert
                self.assertEqual(value, expected_value)

    async def test_get_service_from_name_should_return_expected_value_or_none(self):
        # Arrange
        valid_name = "ValidService"
        valid_service = Mock()

        test_cases = {
            valid_name: valid_service,
            "InvalidService": None,
        }

        for service_name, expected_value in test_cases.items():
            with self.subTest(title=f"service_name_{service_name}"):
                self.factory._services = {valid_name: valid_service}  # noqa PLW0212

                # Act
                value = self.factory.get_service_from_name(service_name)

                # Assert
                self.assertEqual(value, expected_value)

    async def test_get_all_services_should_return_all_services(self):
        # Arrange
        expected_value = {
            "Test_01": Mock(),
            "Test_02": Mock(),
            "Test_03": Mock(),
            "Test_04": Mock(),
        }

        self.factory._services = expected_value  # noqa PLW0212

        # Act
        value = self.factory.get_all_services()

        # Assert
        self.assertEqual(value, expected_value)

    async def test_register_services_should_add_service(self):
        # Arrange
        valid_name_01 = "ValidService_01"
        valid_service_01 = Mock()
        valid_service_01.name = valid_name_01

        valid_name_02 = "ValidService_02"
        valid_service_02 = Mock()
        valid_service_02.name = valid_name_02

        # Act
        self.factory.register_services([valid_service_01, valid_service_02])

        # Assert
        self.assertDictEqual(
            self.factory._services, {valid_name_01: valid_service_01, valid_name_02: valid_service_02}  # noqa PLW0212
        )

    async def test_unregister_services_should_remove_service(self):
        # Arrange
        valid_name_01 = "ValidService_01"
        valid_service_01 = Mock()
        valid_service_01.name = valid_name_01

        valid_name_02 = "ValidService_02"
        valid_service_02 = Mock()
        valid_service_02.name = valid_name_02

        valid_name_03 = "ValidService_03"
        valid_service_03 = Mock()
        valid_service_03.name = valid_name_03

        self.factory._services = {  # noqa PLW0212
            valid_name_01: valid_service_01,
            valid_name_02: valid_service_02,
            valid_name_03: valid_service_03,
        }

        # Act
        self.factory.unregister_services([valid_service_01, valid_service_03])

        # Assert
        self.assertDictEqual(self.factory._services, {valid_name_02: valid_service_02})  # noqa PLW0212

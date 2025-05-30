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

from unittest.mock import call, patch

from fastapi import Depends, Query
from omni.flux.service.factory import ServiceBase
from omni.flux.service.shared import BaseServiceModel
from omni.kit.test import AsyncTestCase
from omni.services.core import exceptions, routers


class TestService(ServiceBase):
    @classmethod
    @property
    def prefix(cls) -> str:
        return "/test"

    def register_endpoints(self):
        pass


class TestModel(BaseServiceModel):
    value: bool = True


class TestServiceBase(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    async def test_properties_return_expected_values(self):
        # Arrange
        service = TestService()

        # Act
        name = service.name
        prefix = service.prefix
        router = service.router

        # Assert
        self.assertEqual(name, "TestService")
        self.assertEqual(prefix, "/test")
        self.assertIsInstance(router, routers.ServiceAPIRouter)

    async def test_inject_hidden_fields_adds_field_to_base_model(self):
        # Arrange
        context_name = "TestContextName"

        # Act
        value = TestService.inject_hidden_fields(TestModel, context_name=context_name)
        model_instance = value(value=True)

        # Assert
        # Verify the field exists in the model
        self.assertIsNotNone(value.model_fields.get("context_name", None))
        # Check that the field has the correct value and is accessible
        self.assertEqual(model_instance.context_name, context_name)
        # Verify the field is not included in the JSON schema
        self.assertNotIn("context_name", value.model_json_schema().get("properties", {}))

    async def test_validate_param_returns_dependency(self):
        # Arrange
        pass

        # Act
        param = TestService.validate_path_param(TestModel)

        # Assert
        self.assertIsInstance(param, type(Depends()))

    async def test_validate_param_converts_param_to_model(self):
        # Arrange
        param = TestService.validate_path_param(TestModel)
        expected_value = True

        # Act
        val = await param.dependency(expected_value)

        # Assert
        self.assertEqual(val, TestModel(value=expected_value))

    async def test_validate_param_validates_param(self):
        # Arrange
        expected_value = False
        expected_context = "TestContextName"
        expected_exception = "Test Exception"
        param = TestService.validate_path_param(TestModel, context_name=expected_context)

        with patch.object(BaseServiceModel, "model_validate") as parse_obj_mock:
            parse_obj_mock.side_effect = ValueError(expected_exception)

            # Act
            with self.assertRaises(exceptions.KitServicesBaseException) as cm:
                await param.dependency(expected_value)

        # Assert
        self.assertEqual(1, parse_obj_mock.call_count)
        self.assertEqual(
            call({"value": expected_value}, context={"context_name": expected_context}), parse_obj_mock.call_args
        )

        self.assertEqual(cm.exception.status_code, 422)
        self.assertEqual(cm.exception.detail, expected_exception)

    async def test_describe_query_param_returns_query(self):
        # Arrange
        expected_value = True
        expected_description = "Test Description"

        # Act
        query = TestService.describe_query_param(expected_value, expected_description)

        # Assert
        self.assertIsInstance(query, type(Query()))
        self.assertEqual(query.default, expected_value)
        self.assertEqual(query.description, expected_description)

    async def test_raise_error_raises_kit_service_base_exception(self):
        # Arrange
        error_code = 404
        error_message = "Test Not Found"

        # Act
        with self.assertRaises(exceptions.KitServicesBaseException) as cm:
            TestService.raise_error(error_code, error_message)

        # Assert
        self.assertEqual(cm.exception.status_code, error_code)
        self.assertEqual(cm.exception.detail, error_message)

    async def test_raise_error_from_existing_error_raises_kit_service_base_exception_from(self):
        # Arrange
        error_code = 400
        error_message = ValueError("Test Value Error")

        # Act
        with self.assertRaises(exceptions.KitServicesBaseException) as cm:
            TestService.raise_error(error_code, error_message)

        # Assert
        self.assertEqual(cm.exception.status_code, error_code)
        self.assertEqual(cm.exception.detail, str(error_message))

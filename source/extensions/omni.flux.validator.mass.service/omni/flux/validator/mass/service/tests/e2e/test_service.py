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

import unittest

import omni.usd
from omni.flux.service.factory import get_instance as get_service_factory_instance
from omni.flux.utils.common.api import send_request
from omni.kit.test import AsyncTestCase
from omni.services.core import main


class TestMassValidatorService(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context()

        factory = get_service_factory_instance()

        # Register the service in the app
        self.service = factory.get_plugin_from_name("MassValidatorService")()
        main.register_router(router=self.service.router, prefix=self.service.prefix)

    # After running each test
    async def tearDown(self):
        main.deregister_router(router=self.service.router, prefix=self.service.prefix)

        self.service = None

        if self.context.can_close_stage():
            await self.context.close_stage_async()

        self.context = None
        self.project_path = None

    @unittest.skip("Not implemented yet")
    async def test_add_item_to_model_queue_works_as_expected(self):
        # Arrange
        pass

        # Act
        response = await send_request("POST", f"{self.service.prefix}/queue/model")

        # Assert
        self.assertEqual(response, {})

    @unittest.skip("Not implemented yet")
    async def test_add_item_to_material_queue_works_as_expected(self):
        # Arrange
        pass

        # Act
        response = await send_request("POST", f"{self.service.prefix}/queue/material")

        # Assert
        self.assertEqual(response, {})

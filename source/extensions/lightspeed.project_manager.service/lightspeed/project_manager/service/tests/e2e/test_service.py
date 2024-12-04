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

import carb
import omni.usd
from fastapi.testclient import TestClient
from omni.flux.service.factory import get_instance as get_service_factory_instance
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path
from omni.services.core import main


class TestProjectManagerService(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        factory = get_service_factory_instance()

        # Register the service in the app
        self.project_manager = factory.get_plugin_from_name("ProjectManagerService")()
        main.register_router(router=self.project_manager.router, prefix=self.project_manager.prefix)

        # Setup a test client to send requests
        host = carb.settings.get_settings().get("/exts/omni.services.transport.server.http/host")
        port = carb.settings.get_settings().get("/exts/omni.services.transport.server.http/port")
        self.client = TestClient(main.get_app(), base_url=f"http://{host}:{port}")

    # After running each test
    async def tearDown(self):
        main.deregister_router(router=self.project_manager.router)

        self.client = None
        self.project_manager = None

    async def test_get_loaded_project_valid_should_return_opened_project(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            # Act
            response = self.client.get(self.project_manager.prefix)

            # Assert
            self.assertTrue(response.is_success)
            self.assertEqual(response.json(), {"layer_id": project_url.path.replace("/", "\\")})

    async def test_get_loaded_project_no_project_should_return_not_found(self):
        # Arrange
        pass

        # Act
        response = self.client.get(self.project_manager.prefix)

        # Assert
        self.assertTrue(response.is_error)
        self.assertEqual(response.status_code, 404)

    async def test_open_project_valid_should_open_project(self):
        # Arrange
        project_path = get_test_data_path(__name__, "usd/full_project/full_project.usda")

        # Act
        response = self.client.put(f"{self.project_manager.prefix}/{project_path}")

        # Assert
        self.assertTrue(response.is_success)

        stage = omni.usd.get_context("").get_stage()
        root_layer = stage.GetRootLayer().identifier
        self.assertEqual(OmniUrl(root_layer).path.lower(), OmniUrl(project_path).path.lower())

    async def test_open_project_invalid_should_return_unprocessable_entity(self):
        # Arrange
        project_path = "Z:/Invalid/Project/Path.usd"

        # Act
        response = self.client.put(f"{self.project_manager.prefix}/{project_path}")

        # Assert
        self.assertTrue(response.is_error)
        self.assertEqual(response.status_code, 422)

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

import omni.usd
from omni.flux.utils.common.api import send_request
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit.test import AsyncTestCase
from omni.services.core import main

from lightspeed.trex.service.core.routes.stagecraft.project import ProjectManagerService

_TEST_PROJECT = "usd/project_example/combined.usda"


class TestProjectManagerService(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        # Register the service in the app
        self.project_manager = ProjectManagerService()
        main.register_router(router=self.project_manager.router, prefix=self.project_manager.prefix)

    # After running each test
    async def tearDown(self):
        main.deregister_router(router=self.project_manager.router)

        self.project_manager = None

    async def test_get_loaded_project_valid_should_return_opened_project(self):
        # Arrange
        async with open_test_project(_TEST_PROJECT) as project_url:
            # Act
            response = await send_request("GET", self.project_manager.prefix, raw_response=True)

            # Assert
            self.assertEqual(response.status_code, 200, msg=response.json())
            self.assertEqual(response.json(), {"layer_id": project_url.path.replace("/", "\\")})

    async def test_get_loaded_project_no_project_should_return_not_found(self):
        # Arrange
        pass

        # Act
        response = await send_request("GET", self.project_manager.prefix, raw_response=True)

        # Assert
        self.assertEqual(response.status_code, 404)

    async def test_open_project_valid_should_open_project(self):
        # Arrange
        async with open_test_project(_TEST_PROJECT) as project_url:
            # The helper opens the copy; start from an empty stage so the route is what opens it.
            await omni.usd.get_context().new_stage_async()

            # Act
            response = await send_request("PUT", f"{self.project_manager.prefix}/{project_url.path}", raw_response=True)

            # Assert
            self.assertEqual(response.status_code, 200, msg=response.json())

            stage = omni.usd.get_context("").get_stage()
            root_layer = stage.GetRootLayer().identifier
            self.assertEqual(OmniUrl(root_layer).path.lower(), project_url.path.lower())

    async def test_open_project_invalid_should_return_unprocessable_entity(self):
        # Arrange
        project_path = "Z:/Invalid/Project/Path.usd"

        # Act
        response = await send_request("PUT", f"{self.project_manager.prefix}/{project_path}", raw_response=True)

        # Assert
        self.assertEqual(response.status_code, 422)

    async def test_close_project_without_pending_changes_should_succeed(self):
        # Arrange
        async with open_test_project(_TEST_PROJECT):
            # Act - Close project without pending changes (should succeed)
            response = await send_request("DELETE", self.project_manager.prefix, raw_response=True)

            # Assert - Should return 200 OK (no pending changes, closes successfully)
            self.assertEqual(response.status_code, 200, msg=response.json())
            self.assertEqual(response.json(), "OK")

            # Verify no project is loaded after closing
            get_response = await send_request("GET", self.project_manager.prefix, raw_response=True)
            self.assertEqual(get_response.status_code, 404)

    async def test_close_project_with_force_flag_should_succeed(self):
        # Arrange
        async with open_test_project(_TEST_PROJECT):
            # Act - Close project with force flag (should always succeed)
            response = await send_request("DELETE", f"{self.project_manager.prefix}?force=true", raw_response=True)

            # Assert - Should return 200 OK (force flag bypasses pending changes check)
            self.assertEqual(response.status_code, 200, msg=response.json())
            self.assertEqual(response.json(), "OK")

            # Verify no project is loaded after closing
            get_response = await send_request("GET", self.project_manager.prefix, raw_response=True)
            self.assertEqual(get_response.status_code, 404)

    async def test_close_project_without_project_loaded_should_handle_gracefully(self):
        # Arrange - No project loaded

        # Act - Try to close project when none is loaded
        close_response = await send_request("DELETE", self.project_manager.prefix, raw_response=True)

        # Assert - Should still return success (graceful handling for no project)
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(close_response.json(), "OK")

        # Verify no project is loaded (should still be 404)
        get_response = await send_request("GET", self.project_manager.prefix, raw_response=True)
        self.assertEqual(get_response.status_code, 404)

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

import httpx
import omni.usd
from omni.flux.service.factory import get_instance as get_service_factory_instance
from omni.flux.utils.common.api import send_request
from omni.flux.validator.manager.core import ValidationSchema
from omni.flux.validator.mass.queue.core import get_mass_validation_queue_instance
from omni.kit.test import AsyncTestCase
from omni.services.core import main


class TestMassValidatorService(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context()

        factory = get_service_factory_instance()

        # Register the service in the app
        self.service = factory.get_plugin_from_name("MassValidatorService")(schema_models=[])
        main.register_router(router=self.service.router, prefix=self.service.prefix)

    # After running each test
    async def tearDown(self):
        main.deregister_router(router=self.service.router, prefix=self.service.prefix)

        self.service = None

        if self.context.can_close_stage():
            await self.context.close_stage_async()

        self.context = None
        self.project_path = None

    async def test_update_schema_with_body_notifies_queue(self):
        """Forward the JSON body and queue ID through REST to the validation queue."""
        # Arrange
        context = {"name": "CurrentStage", "data": {"context_name": ""}}
        body = {
            "name": "Schema update regression",
            "context_plugin": context,
            "check_plugins": [
                {
                    "name": "PrintPrims",
                    "context_plugin": context,
                    "selector_plugins": [{"name": "AllPrims", "data": {}}],
                    "data": {},
                }
            ],
            "data": {"nested": {"items": ["mesh", "material"]}},
            "progress": 0.75,
        }
        updates = []
        self.update_subscription = get_mass_validation_queue_instance().subscribe_on_update_item(
            lambda schema, queue_id: updates.append((schema, queue_id))
        )
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.get_app()), base_url="http://test"
            ) as client:
                # Act
                response = await client.put(
                    f"{self.service.prefix}/schema", params={"queue_id": "rest-body-regression"}, json=body
                )

            # Assert
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), "OK")
            self.assertEqual(len(updates), 1)
            updated_schema, queue_id = updates[0]
            self.assertEqual(queue_id, "rest-body-regression")
            self.assertEqual(updated_schema.progress, 0.75)
            self.assertEqual(updated_schema.name, body["name"])
            self.assertEqual(updated_schema.data, body["data"])
            self.assertEqual(len(updated_schema.check_plugins), 1)
            self.assertEqual(updated_schema.context_plugin.name, "CurrentStage")
        finally:
            self.update_subscription = None

    async def test_update_schema_openapi_exposes_serializable_validation_fields(self):
        """Keep the REST request contract aligned with the serializable validation model."""
        # Arrange
        expected = {name for name, field in ValidationSchema.model_fields.items() if not field.exclude}

        # Act
        spec = main.get_app().openapi()

        # Assert
        request = spec["paths"][f"{self.service.prefix}/schema"]["put"]["requestBody"]
        self.assertTrue(request["required"])
        schema_name = request["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]
        schema = spec["components"]["schemas"][schema_name]
        self.assertEqual(set(schema["properties"]), expected)
        self.assertEqual(set(schema["required"]), {"name", "context_plugin", "check_plugins"})

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

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

import shutil
import sys
import tempfile
from pathlib import Path
from typing import cast

import carb.settings
from lightspeed.trex.service.core.routes.ingestcraft import IngestCraftService
from omni.flux.utils.common.api import send_request
from omni.flux.utils.common.path_utils import read_metadata
from omni.flux.utils.widget.resources import get_test_data
from omni.flux.validator.factory import VALIDATION_PASSED
from omni.flux.validator.manager.core import EXTS_MASS_VALIDATOR_SERVICE_PREFIX
from omni.flux.validator.mass.core.executors.external_process_executor import OVERRIDE_EXPERIENCE
from omni.kit.test import AsyncTestCase
from omni.services.core import main
from requests import Response


class TestIngestionService(AsyncTestCase):
    """Ingestion tests that go through the REST API."""

    async def test_ingest_model_with_default_executor_creates_validated_usd(self):
        """Queue a model through REST and make sure that the CLI process writes a validated USD file.

        The default external process executor runs the ingestion CLI, which sends schema updates back to this
        process. The test checks the response, the output USD file, and its validation metadata.
        """
        # Arrange
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "cube.usda"
            shutil.copyfile(cast(str, get_test_data("usd/project_example/sources/cube.usda")), input_path)
            output_path = Path(temporary_directory) / "output" / "cube.usd"
            settings = carb.settings.get_settings()
            original_settings = {
                key: settings.get(key) for key in (OVERRIDE_EXPERIENCE, EXTS_MASS_VALIDATOR_SERVICE_PREFIX)
            }
            original_arguments = sys.argv[:]
            service = IngestCraftService()
            prefix = f"/test{service.prefix}"
            main.register_router(router=service.router, prefix=prefix)
            try:
                settings.set(EXTS_MASS_VALIDATOR_SERVICE_PREFIX, prefix)
                settings.set(OVERRIDE_EXPERIENCE, "${kit}/../apps/lightspeed.app.trex.validation_cli.kit")
                # The child must run the CLI, not the test runner or another HTTP server.
                sys.argv[2:] = []

                # Act
                response = cast(
                    Response,
                    await send_request(
                        "POST",
                        f"{prefix}/mass-validator/queue/model",
                        raw_response=True,
                        json={
                            "context_plugin": {
                                "data": {"input_files": [str(input_path)], "output_directory": str(output_path.parent)}
                            }
                        },
                        timeout=120,
                    ),
                )

                # Assert
                self.assertEqual(response.status_code, 200, response.text)
                [schema] = response.json()["completed_schemas"]
                self.assertIs(schema["validation_passed"], True)
                self.assertTrue(output_path.is_file())
                self.assertIs(read_metadata(str(output_path), VALIDATION_PASSED), True)
            finally:
                sys.argv[:] = original_arguments
                main.deregister_router(router=service.router, prefix=prefix)
                for key, value in original_settings.items():
                    if value is None:
                        settings.destroy_item(key)
                    else:
                        settings.set(key, value)

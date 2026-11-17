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

import json
import pathlib
import tempfile

from lightspeed.trex.comfyui.core.job import ComfyUIAssetJob, ComfyUIJob
from lightspeed.trex.comfyui.core.models import ComfyUIWorkflowRequest, Workflow
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import JobGraph
from omni.flux.job_queue.core.serializer import serialize
from omni.kit.test import AsyncTestCase


class TestComfyUIPersistenceE2E(AsyncTestCase):
    """Restore saved ComfyUI jobs through the public SQLite queue API."""

    async def test_get_job_with_ten_field_generation_records_preserves_fields_and_defaults_output_url(self) -> None:
        """Both generation job types retain all old fields without an output URL."""
        request = ComfyUIWorkflowRequest({}, (), "saved-client", 90.0, None, Workflow())
        for job_type in (ComfyUIJob, ComfyUIAssetJob):
            with self.subTest(title=job_type.__name__), tempfile.TemporaryDirectory() as directory:
                # Save a real graph with non-default legacy fields.
                database_path = str(pathlib.Path(directory) / "queue.sqlite")
                queue = QueueInterface(database_path)
                job = job_type(
                    name=f"Saved {job_type.__name__}",
                    skip_reason="A required source texture is missing.",
                    context_name="texturecraft",
                    prim_paths=["/Asset/First", "/Asset/Second"],
                    material_path="/Asset/Looks/Material",
                    scheme="https",
                    host="saved-comfyui.example",
                    port=9443,
                )
                graph = JobGraph(name="Saved generation", jobs=[job])
                graph.bind(job, job.WORKFLOW_REQUEST, request)
                queue.submit(graph)

                # Remove the output URL to reproduce the released ten-field record.
                record = json.loads(serialize(job))
                record["value"]["value"] = record["value"]["value"][:10]
                with queue.connection() as connection:
                    connection.execute(
                        "UPDATE jobs SET job_data = ? WHERE job_id = ?", (json.dumps(record), str(job.job_id))
                    )
                    connection.commit()

                # Reopen the queue. Dataclass equality includes the default output URL and exact job type.
                self.assertEqual(QueueInterface(database_path).get_job(job.job_id), job)

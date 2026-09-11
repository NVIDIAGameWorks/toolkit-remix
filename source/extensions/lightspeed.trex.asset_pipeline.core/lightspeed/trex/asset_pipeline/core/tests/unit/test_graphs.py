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

import pathlib
from dataclasses import dataclass
from typing import Any, ClassVar

import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.job import (
    Job,
    JobGraph,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgressCallback,
)

from lightspeed.trex.asset_pipeline.core.jobs import (
    MeshOptimizationJob,
    PrepareOptimizationJob,
    TextureProcessingJob,
    add_asset_optimization_jobs,
    build_asset_optimization_graph,
    build_texture_optimization_graph,
)
from lightspeed.trex.asset_pipeline.core.jobs.apply_handler import SaveMeshMetadataHandler, SaveTextureMetadataHandler
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    MeshOptimizationRequest,
    MeshOptimizationResult,
    TextureProcessingItem,
    TextureProcessingRequest,
    TextureProcessingResult,
)


class _CustomAssetHandler(ApplyHandler[MeshOptimizationResult, None, None]):
    """Minimal custom handler for asset graph injection tests."""

    name = "CustomAssetHandler"
    input_type = MeshOptimizationResult
    target_type = type(None)
    receipt_type = type(None)
    apply_policy = "always_automatic"

    async def capture_receipt(self, value, target):
        return None

    async def apply(self, value, target, receipt):
        pass

    async def revert(self, value, target, receipt):
        pass


class _CustomTextureHandler(ApplyHandler[TextureProcessingResult, None, None]):
    """Minimal custom handler for texture graph injection tests."""

    name = "CustomTextureHandler"
    input_type = TextureProcessingResult
    target_type = type(None)
    receipt_type = type(None)
    apply_policy = "always_automatic"

    async def capture_receipt(self, value, target):
        return None

    async def apply(self, value, target, receipt):
        pass

    async def revert(self, value, target, receipt):
        pass


@dataclass
class _MeshRequestJob(Job):
    """Provide a mesh request through one typed output endpoint."""

    REQUEST: ClassVar[JobOutputPort[MeshOptimizationRequest]] = JobOutputPort("request", MeshOptimizationRequest)
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = (REQUEST,)

    async def execute(
        self,
        _job_directory: pathlib.Path,
        _inputs: JobInputs,
        _progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return one mesh request."""
        return JobOutputs(
            {
                self.REQUEST: MeshOptimizationRequest(
                    source_path=pathlib.Path("/models/mesh.fbx"),
                    source_root=pathlib.Path("/models"),
                )
            }
        )


class TestGraphFactories(omni.kit.test.AsyncTestCase):
    """Verify the public graph factories build the approved job shapes."""

    async def test_asset_graph_joins_prepare_and_texture_into_the_mesh_job(self):
        """A model graph runs prepare, texture, and mesh, and the mesh job consumes both inputs."""
        # Arrange
        request = MeshOptimizationRequest(
            source_path=pathlib.Path("/models/mesh.fbx"),
            source_root=pathlib.Path("/models"),
        )

        # Act
        graph, mesh_job = build_asset_optimization_graph(request)

        # Assert
        self.assertIsInstance(mesh_job, MeshOptimizationJob)
        job_types = {type(job) for job in graph.jobs}
        self.assertEqual(job_types, {PrepareOptimizationJob, TextureProcessingJob, MeshOptimizationJob})

    async def test_asset_graph_binds_metadata_only_on_the_terminal_job(self):
        """Only the terminal mesh job writes metadata, so sidecars are written once."""
        # Arrange
        request = MeshOptimizationRequest(
            source_path=pathlib.Path("/models/mesh.fbx"),
            source_root=pathlib.Path("/models"),
        )

        # Act
        graph, mesh_job = build_asset_optimization_graph(request)

        # Assert
        self.assertIs(mesh_job.apply_binding.handler_type, SaveMeshMetadataHandler)
        bound = [job for job in graph.jobs if job.apply_binding is not None]
        self.assertEqual(bound, [mesh_job])

    async def test_asset_graph_caller_supplied_handler_and_target_are_honoured(self):
        """A caller-supplied handler_type and target propagate to the terminal job."""
        # Arrange
        request = MeshOptimizationRequest(
            source_path=pathlib.Path("/models/mesh.fbx"),
            source_root=pathlib.Path("/models"),
        )
        custom_target = None

        # Act
        graph, mesh_job = build_asset_optimization_graph(
            request, handler_type=_CustomAssetHandler, target=custom_target
        )

        # Assert
        self.assertIs(mesh_job.apply_binding.handler_type, _CustomAssetHandler)
        self.assertEqual(mesh_job.apply_binding.target, custom_target)

    async def test_texture_graph_has_one_job_that_writes_metadata(self):
        """A standalone texture graph holds only the texture job, and it writes metadata."""
        # Arrange
        request = TextureProcessingRequest(
            items=(
                TextureProcessingItem(
                    key="texture_0",
                    path=pathlib.Path("/textures/albedo.png"),
                    texture_type=TextureTypes.DIFFUSE,
                ),
            ),
            source_root=pathlib.Path("/textures"),
            output_url=None,
        )

        # Act
        graph, texture_job = build_texture_optimization_graph(request)

        # Assert
        self.assertIsInstance(texture_job, TextureProcessingJob)
        self.assertEqual(len(graph.jobs), 1)
        self.assertIsNotNone(texture_job.apply_binding)
        self.assertIs(texture_job.apply_binding.handler_type, SaveTextureMetadataHandler)

    async def test_texture_graph_binds_source_textures_to_request(self):
        """The texture graph binds the SOURCE_TEXTURES port to the passed request."""
        # Arrange
        request = TextureProcessingRequest(
            items=(
                TextureProcessingItem(
                    key="texture_0",
                    path=pathlib.Path("/textures/albedo.png"),
                    texture_type=TextureTypes.DIFFUSE,
                ),
            ),
            source_root=pathlib.Path("/textures"),
            output_url=None,
        )

        # Act
        graph, texture_job = build_texture_optimization_graph(request)

        # Assert
        bound_inputs = {(inp.job_id, inp.port) for inp in graph.literal_inputs}
        self.assertIn((texture_job.job_id, TextureProcessingJob.SOURCE_TEXTURES), bound_inputs)
        literal_input = next(
            inp
            for inp in graph.literal_inputs
            if inp.job_id == texture_job.job_id and inp.port == TextureProcessingJob.SOURCE_TEXTURES
        )
        self.assertEqual(literal_input.value, request)

    async def test_texture_graph_returned_job_is_the_terminal_job(self):
        """The returned job is the texture job itself."""
        # Arrange
        request = TextureProcessingRequest(
            items=(
                TextureProcessingItem(
                    key="texture_0",
                    path=pathlib.Path("/textures/albedo.png"),
                    texture_type=TextureTypes.DIFFUSE,
                ),
            ),
            source_root=pathlib.Path("/textures"),
            output_url=None,
        )

        # Act
        _graph, texture_job = build_texture_optimization_graph(request)

        # Assert
        self.assertIs(texture_job, next(iter(_graph.jobs)))

    async def test_texture_graph_caller_supplied_handler_and_target_are_honoured(self):
        """A caller-supplied handler_type and target propagate to the terminal texture job."""
        # Arrange
        request = TextureProcessingRequest(
            items=(
                TextureProcessingItem(
                    key="texture_0",
                    path=pathlib.Path("/textures/albedo.png"),
                    texture_type=TextureTypes.DIFFUSE,
                ),
            ),
            source_root=pathlib.Path("/textures"),
            output_url=None,
        )
        custom_target = None

        # Act
        graph, texture_job = build_texture_optimization_graph(
            request, handler_type=_CustomTextureHandler, target=custom_target
        )

        # Assert
        self.assertIs(texture_job.apply_binding.handler_type, _CustomTextureHandler)
        self.assertEqual(texture_job.apply_binding.target, custom_target)

    async def test_asset_compositor_connects_endpoint_and_omits_apply_when_requested(self):
        """The compositor accepts a producer endpoint and can omit the terminal Apply binding."""
        # Arrange
        graph = JobGraph(name="Asset optimization")
        source_job = _MeshRequestJob(name="Source model")
        graph.add_job(source_job)

        # Act
        mesh_job = add_asset_optimization_jobs(
            graph,
            source_job.output(_MeshRequestJob.REQUEST),
            handler_type=None,
        )

        # Assert
        self.assertEqual(len(graph.jobs), 4)
        self.assertIsNone(mesh_job.apply_binding)
        self.assertTrue(
            any(
                connection.source_job_id == source_job.job_id
                and connection.source_port is _MeshRequestJob.REQUEST
                and connection.target_port is PrepareOptimizationJob.SOURCE_MODEL
                for connection in graph.connections
            )
        )

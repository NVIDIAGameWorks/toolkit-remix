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

from __future__ import annotations

__all__ = [
    "add_asset_optimization_jobs",
    "build_asset_optimization_graph",
    "build_texture_optimization_graph",
]

from typing import Any

from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.job import ApplyBinding, JobGraph, JobOutputEndpoint

from .apply_handler import SaveMeshMetadataHandler, SaveTextureMetadataHandler
from .mesh_optimization import MeshOptimizationJob
from .models import MeshOptimizationRequest, TextureProcessingRequest
from .prepare_optimization import PrepareOptimizationJob
from .texture_processing import TextureProcessingJob


def build_texture_optimization_graph(
    request: TextureProcessingRequest,
    *,
    name: str = "Texture optimization",
    handler_type: type[ApplyHandler] = SaveTextureMetadataHandler,
    target: Any = None,
) -> tuple[JobGraph, TextureProcessingJob]:
    """Build a standalone graph that optimizes one texture batch.

    A caller submits the returned graph and reads the terminal job's outputs.

    A product that must do more on success, such as registration in a library, supplies its own
    handler. That handler extends this default, so metadata still reaches every published file.
    The parameter keeps the dependency one way: this extension never imports its products.

    A caller that already owns an upstream job, such as one that generates the source textures,
    adds its own ``TextureProcessingJob`` to its own graph instead of calling this function: build
    the job, add it, and connect the upstream job's output to ``SOURCE_TEXTURES`` directly.

    Args:
        request: Source textures to optimize.
        name: Display name for the graph and its job.
        handler_type: Apply handler bound to the terminal job.
        target: Typed product target persisted with the job for that handler.

    Returns:
        The graph and its terminal texture job.
    """
    graph = JobGraph(name=name)
    texture_job = TextureProcessingJob(
        name=name,
        apply_binding=ApplyBinding(
            output_port=TextureProcessingJob.PROCESSED_TEXTURES,
            handler_type=handler_type,
            target=target,
        ),
    )
    graph.add_job(texture_job)
    graph.bind(texture_job, TextureProcessingJob.SOURCE_TEXTURES, request)
    return graph, texture_job


def add_asset_optimization_jobs(
    graph: JobGraph,
    source: JobOutputEndpoint[MeshOptimizationRequest] | MeshOptimizationRequest,
    *,
    handler_type: type[ApplyHandler] | None = SaveMeshMetadataHandler,
    target: Any = None,
) -> MeshOptimizationJob:
    """Add the canonical asset-optimization jobs to a graph.

    Args:
        graph: Graph that owns the added jobs.
        source: Literal model request or producer endpoint.
        handler_type: Apply handler bound to the terminal mesh job, or None.
        target: Typed product target persisted for the handler.

    Returns:
        The terminal mesh job.
    """
    prepare_job = PrepareOptimizationJob(name="Prepare optimization")
    graph.add_job(prepare_job)
    if isinstance(source, MeshOptimizationRequest):
        graph.bind(prepare_job, PrepareOptimizationJob.SOURCE_MODEL, source)
    else:
        graph.connect(source, prepare_job.input(PrepareOptimizationJob.SOURCE_MODEL))

    texture_job = TextureProcessingJob(name="Optimize textures")
    graph.add_job(texture_job)
    graph.connect(
        prepare_job.output(PrepareOptimizationJob.TEXTURE_REQUEST),
        texture_job.input(TextureProcessingJob.SOURCE_TEXTURES),
    )

    apply_binding = None
    if handler_type is not None:
        apply_binding = ApplyBinding(
            output_port=MeshOptimizationJob.OPTIMIZED_MESH,
            handler_type=handler_type,
            target=target,
        )
    mesh_job = MeshOptimizationJob(name="Optimize mesh", apply_binding=apply_binding)
    graph.add_job(mesh_job)
    graph.connect(
        prepare_job.output(PrepareOptimizationJob.PREPARED_MESH),
        mesh_job.input(MeshOptimizationJob.SOURCE_MODEL),
    )
    graph.connect(
        texture_job.output(TextureProcessingJob.PROCESSED_TEXTURES),
        mesh_job.input(MeshOptimizationJob.TEXTURE_INPUT),
    )
    return mesh_job


def build_asset_optimization_graph(
    request: MeshOptimizationRequest,
    *,
    name: str = "Asset optimization",
    handler_type: type[ApplyHandler] = SaveMeshMetadataHandler,
    target: Any = None,
) -> tuple[JobGraph, MeshOptimizationJob]:
    """Build the graph that optimizes one model.

    Args:
        request: Source model to optimize.
        name: Display name for the graph.
        handler_type: Apply handler bound to the terminal mesh job.
        target: Typed product target persisted with the job for that handler.

    Returns:
        The graph and its terminal mesh job.
    """
    graph = JobGraph(name=name)
    mesh_job = add_asset_optimization_jobs(
        graph,
        request,
        handler_type=handler_type,
        target=target,
    )
    return graph, mesh_job

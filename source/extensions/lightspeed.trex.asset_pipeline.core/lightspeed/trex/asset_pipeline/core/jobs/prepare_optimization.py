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

__all__ = ["PrepareOptimizationJob"]

import pathlib
from dataclasses import dataclass
from typing import Any, ClassVar

from omni.flux.job_queue.core.job import (
    Job,
    JobInputPort,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgress,
    JobProgressCallback,
)

from .models import (
    MeshOptimizationRequest,
    PrepareOptimizationResult,
    TextureProcessingItem,
    TextureProcessingRequest,
)
from ..constants import PROCESSED_OUTPUT_DIR_NAME
from ..pipeline import (
    RemixAssetItem,
    RemixAssetPipelineConfig,
    RemixAssetPipelineContext,
    run_remix_asset_pipeline,
)
from ..pipeline.builder import build_prepare_optimization_steps


@dataclass
class PrepareOptimizationJob(Job):
    """Run the mesh-preparation phase as one typed queue job.

    The job imports the source model, then discovers its texture bindings and composed layers without editing
    or saving the stage. Material conversion belongs to the mesh phase; the ledger is keyed by
    ``(material_path, texture_type)`` so bindings survive that later rewrite. Its outputs feed a
    ``TextureProcessingJob`` (the discovered texture batch) and a ``MeshOptimizationJob`` (the prepared model
    state).

    Attributes:
        SOURCE_MODEL: Required mesh-optimization request input port.
        TEXTURE_REQUEST: Ready-made texture-processing request output port carrying the collected texture batch.
        PREPARED_MESH: Immutable prepared-model state output port.
    """

    SOURCE_MODEL: ClassVar[JobInputPort[MeshOptimizationRequest]] = JobInputPort(
        "source_model", MeshOptimizationRequest
    )
    TEXTURE_REQUEST: ClassVar[JobOutputPort[TextureProcessingRequest]] = JobOutputPort(
        "texture_request", TextureProcessingRequest
    )
    PREPARED_MESH: ClassVar[JobOutputPort[PrepareOptimizationResult]] = JobOutputPort(
        "prepared_mesh", PrepareOptimizationResult
    )
    input_ports: ClassVar[tuple[JobInputPort[Any], ...]] = (SOURCE_MODEL,)
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = (TEXTURE_REQUEST, PREPARED_MESH)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Run the preparation steps and publish the prepared model state.

        Args:
            job_directory: Queue-owned directory holding the durable prepared model.
            inputs: Exact typed inputs resolved from graph connections or literal bindings.
            progress_callback: Async callback receiving structured pipeline progress.

        Returns:
            Immutable prepared model state and the collected texture batch request.

        Raises:
            KeyError: If the required source-model input is absent.
            OSError: If local processing fails.
        """
        request = inputs[self.SOURCE_MODEL]
        processed_count = 0

        async def on_step_started(step, _index: int, _total: int) -> None:
            """Bridge pipeline phase updates to structured job progress.

            Args:
                step: Pipeline step carrying the user-facing phase description.
                _index: Unused one-based pipeline phase index.
                _total: Unused pipeline phase count.
            """
            await progress_callback(JobProgress(completed=processed_count, total=1, detail=step.description))

        async def on_item_completed(_item: RemixAssetItem, completed: int, total: int) -> None:
            """Report one genuinely completed source item.

            Args:
                _item: Processed pipeline item; identity is already retained by request order.
                completed: Number of source items that finished processing.
                total: Total source-item count for the batch.
            """
            nonlocal processed_count
            processed_count = completed
            await progress_callback(JobProgress(completed=completed, total=total, detail="Prepare model"))

        remix_item = RemixAssetItem.from_model(request.source_path)
        local_output_dir = job_directory / PROCESSED_OUTPUT_DIR_NAME
        config = RemixAssetPipelineConfig(output_dir=local_output_dir, texture_type=None)
        context = RemixAssetPipelineContext(items=[remix_item], source_root=request.source_root)
        # DiscoverTexturesStep records the composed layer identifiers on the context; read them
        # after the pipeline completes.
        steps = build_prepare_optimization_steps(config)
        await run_remix_asset_pipeline(
            config,
            context,
            steps=steps,
            on_step_started=on_step_started,
            on_item_completed=on_item_completed,
        )

        # Discovery already assigned each texture its deterministic identity key, so the request
        # items and the ledger agree without any positional counter.
        texture_items = tuple(
            TextureProcessingItem(
                key=texture.key,
                path=texture.path,
                texture_type=texture.texture_type,
            )
            for texture in remix_item.textures
        )
        texture_ledger = tuple(context.texture_ledger)
        result = PrepareOptimizationResult(
            model_work_path=remix_item.value,
            texture_items=texture_items,
            referenced_layers=context.referenced_layers,
            texture_ledger=texture_ledger,
            replace_udim_textures_by_empty=request.replace_udim_textures_by_empty,
            source_path=remix_item.source_path,
            source_root=request.source_root,
            output_url=request.output_url,
        )
        # Keep intermediate textures local. The mesh job publishes the complete asset.
        texture_request = TextureProcessingRequest(
            items=texture_items,
            source_root=request.source_root,
            output_url=None,
        )
        await progress_callback(JobProgress(completed=1, total=1, detail="Model preparation complete"))
        return JobOutputs({self.TEXTURE_REQUEST: texture_request, self.PREPARED_MESH: result})

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

__all__ = ["TextureProcessingJob"]

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

from . import publication
from .models import ProcessedTexture, TextureProcessingItem, TextureProcessingRequest, TextureProcessingResult
from .pipeline_config import RemixAssetPipelineConfig
from .pipeline_context import RemixAssetPipelineContext
from .pipeline_item import RemixAssetItem
from .pipeline_runner import run_remix_asset_pipeline


@dataclass
class TextureProcessingJob(Job):
    """Run the canonical Remix texture pipeline as one reusable typed queue job.

    Attributes:
        SOURCE_TEXTURES: Required texture-processing request input port.
        PROCESSED_TEXTURES: Immutable processed-textures output port.
    """

    SOURCE_TEXTURES: ClassVar[JobInputPort[TextureProcessingRequest]] = JobInputPort(
        "source_textures", TextureProcessingRequest
    )
    PROCESSED_TEXTURES: ClassVar[JobOutputPort[TextureProcessingResult]] = JobOutputPort(
        "processed_textures", TextureProcessingResult
    )
    input_ports: ClassVar[tuple[JobInputPort[Any], ...]] = (SOURCE_TEXTURES,)
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = (PROCESSED_TEXTURES,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Process and publish one typed texture batch.

        Args:
            job_directory: Queue-owned directory available for remote-publication staging.
            inputs: Exact typed inputs resolved from graph connections or literal bindings.
            progress_callback: Async callback receiving structured pipeline progress.

        Returns:
            Immutable processed-textures output after the entire batch is published.

        Raises:
            KeyError: If the required source-textures input is absent.
            OSError: If local processing or publication fails.
            RuntimeError: If remote publication or pipeline output validation fails.
        """
        request = inputs[self.SOURCE_TEXTURES]
        texture_count = len(request.items)
        processed_count = 0

        async def on_step_started(step, _index: int, _total: int) -> None:
            """Bridge pipeline phase updates to structured job progress.

            Args:
                step: Pipeline step carrying the user-facing phase description.
                _index: Unused one-based pipeline phase index.
                _total: Unused pipeline phase count.
            """
            await progress_callback(
                JobProgress(completed=processed_count, total=texture_count, detail=step.description)
            )

        async def on_item_completed(_item: RemixAssetItem, completed: int, total: int) -> None:
            """Report one genuinely completed source item.

            Args:
                _item: Processed pipeline item; identity is already retained by request order.
                completed: Number of source items that finished processing.
                total: Total source-item count for the batch.
            """
            nonlocal processed_count
            processed_count = completed
            await progress_callback(JobProgress(completed=completed, total=total, detail="Optimize textures"))

        remix_items = [self._to_remix_item(item) for item in request.items]
        if request.output_url is None:
            local_output_dir = job_directory / "processed"
            is_remote_output = False
        else:
            local_output_dir = publication.get_local_output_path(request.output_url)
            is_remote_output = local_output_dir is None
            if is_remote_output:
                local_output_dir = job_directory / "processed"

        context = RemixAssetPipelineContext(items=remix_items, source_root=request.source_root)
        await run_remix_asset_pipeline(
            RemixAssetPipelineConfig(output_dir=local_output_dir, texture_type=None),
            context,
            on_step_started=on_step_started,
            on_item_completed=on_item_completed,
        )

        local_outputs = [self._get_primary_output(item) for item in remix_items]
        if is_remote_output and request.output_url is not None:
            output_urls = await publication.publish_remote_outputs(
                local_output_dir,
                local_outputs,
                request.output_url,
                texture_count,
                progress_callback,
            )
        else:
            output_urls = [str(path) for path in local_outputs]

        result = TextureProcessingResult(
            items=tuple(
                self._to_processed_texture(request_item, remix_item, output_url)
                for request_item, remix_item, output_url in zip(
                    request.items,
                    remix_items,
                    output_urls,
                    strict=True,
                )
            )
        )
        await progress_callback(
            JobProgress(completed=texture_count, total=texture_count, detail="Texture optimization complete")
        )
        return JobOutputs({self.PROCESSED_TEXTURES: result})

    @staticmethod
    def _to_remix_item(item: TextureProcessingItem) -> RemixAssetItem:
        """Convert one immutable request item to the existing mutable pipeline type.

        Args:
            item: Persisted source item.

        Returns:
            Existing Remix pipeline item carrying the same semantics.
        """
        return RemixAssetItem.from_texture(item.path, item.texture_type)

    @staticmethod
    def _get_primary_output(item: RemixAssetItem) -> pathlib.Path:
        """Return the final primary output from a completed pipeline item.

        Args:
            item: Completed mutable pipeline item.

        Returns:
            Final published texture path.

        Raises:
            RuntimeError: If a texture item does not have exactly one processed texture.
        """
        if len(item.textures) != 1:
            raise RuntimeError("Processed texture item must contain exactly one texture output")
        return item.textures[0].path

    @staticmethod
    def _to_processed_texture(
        request_item: TextureProcessingItem,
        remix_item: RemixAssetItem,
        output_url: str,
    ) -> ProcessedTexture:
        """Build one immutable published record from a completed pipeline item.

        Args:
            request_item: Original source record.
            remix_item: Completed pipeline item carrying final semantics.
            output_url: Final local path or remote publication URL.

        Returns:
            Immutable result record safe for persistence and Apply.
        """
        return ProcessedTexture(
            key=request_item.key,
            source_path=request_item.path,
            asset_url=output_url,
            texture_type=remix_item.textures[0].texture_type,
        )

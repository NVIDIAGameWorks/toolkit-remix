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

__all__ = ["MeshOptimizationJob"]

import pathlib
from dataclasses import dataclass, replace
from typing import Any, ClassVar

from omni.client import combine_urls
from omni.flux.job_queue.core.job import (
    Job,
    JobInputPort,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgress,
    JobProgressCallback,
)
from omni.flux.utils.common.path_utils import hash_file
from pxr import UsdUtils

from .models import (
    MeshOptimizationResult,
    PrepareOptimizationResult,
    TextureProcessingResult,
    resolve_processed_textures,
)
from ..pipeline import (
    AssetKind,
    RemixAssetItem,
    RemixAssetPipelineConfig,
    RemixAssetPipelineContext,
    run_remix_asset_pipeline,
)
from ..pipeline.builder import build_remix_mesh_pipeline
from ..utils import publish_remote_outputs, resolve_local_output_dir
from ..worker import run_in_worker_thread


@dataclass
class MeshOptimizationJob(Job):
    """Run the mesh-optimization phase as one typed queue job.

    The job restores the prepared model state published by a ``PrepareOptimizationJob``, copies the textures
    published by a ``TextureProcessingJob`` into its own output at their source-relative layout (``textures/<name>``
    for an imported FBX, as legacy wrote it), and rewrites the model's texture references to those copies.
    Metadata is not written here; a caller binds ``apply_binding`` to a metadata-writing Apply handler on this job.

    Attributes:
        SOURCE_MODEL: Required prepared-model input port.
        TEXTURE_INPUT: Required processed-textures input port.
        OPTIMIZED_MESH: Immutable optimized-mesh output port.
    """

    SOURCE_MODEL: ClassVar[JobInputPort[PrepareOptimizationResult]] = JobInputPort(
        "source_model", PrepareOptimizationResult
    )
    TEXTURE_INPUT: ClassVar[JobInputPort[TextureProcessingResult]] = JobInputPort(
        "processed_textures", TextureProcessingResult
    )
    OPTIMIZED_MESH: ClassVar[JobOutputPort[MeshOptimizationResult]] = JobOutputPort(
        "optimized_mesh", MeshOptimizationResult
    )
    input_ports: ClassVar[tuple[JobInputPort[Any], ...]] = (SOURCE_MODEL, TEXTURE_INPUT)
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = (OPTIMIZED_MESH,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Restore the prepared model state, inject processed textures, and publish the final model.

        Args:
            job_directory: Queue-owned directory available for local publication.
            inputs: Exact typed inputs resolved from graph connections.
            progress_callback: Async callback receiving structured pipeline progress.

        Returns:
            Immutable optimized-mesh output after the model is published.

        Raises:
            KeyError: If a required input is absent.
            ValueError: If the processed textures do not cover the collected texture records.
            OSError: If local processing or publication fails.
            RuntimeError: If remote publication or source hashing fails.
        """
        prepared = inputs[self.SOURCE_MODEL]
        texture_result = inputs[self.TEXTURE_INPUT]

        async def on_step_started(step, _index: int, _total: int) -> None:
            """Bridge pipeline phase updates to structured job progress.

            Args:
                step: Pipeline step carrying the user-facing phase description.
                _index: Unused one-based pipeline phase index.
                _total: Unused pipeline phase count.
            """
            await progress_callback(JobProgress(completed=0, total=1, detail=step.description))

        async def on_item_completed(_item: RemixAssetItem, completed: int, total: int) -> None:
            """Report one genuinely completed source item.

            Args:
                _item: Processed pipeline item; identity is already retained by request order.
                completed: Number of source items that finished processing.
                total: Total source-item count for the batch.
            """
            await progress_callback(JobProgress(completed=completed, total=total, detail="Optimize mesh"))

        remix_item = RemixAssetItem(
            value=prepared.model_work_path,
            kind=AssetKind.MODEL,
            source_path=prepared.source_path,
        )
        local_output_dir, is_remote_output = resolve_local_output_dir(job_directory, prepared.output_url)
        config = RemixAssetPipelineConfig(output_dir=local_output_dir, texture_type=None)
        context = RemixAssetPipelineContext(items=[remix_item], source_root=prepared.source_root)
        context.replace_udim_textures_by_empty = prepared.replace_udim_textures_by_empty
        # Validate every ledger entry against the texture result and build the lookup map.
        processed_textures = resolve_processed_textures(prepared.texture_ledger, texture_result)
        steps = build_remix_mesh_pipeline(config, processed_textures)
        await run_remix_asset_pipeline(
            config,
            context,
            steps=steps,
            on_step_started=on_step_started,
            on_item_completed=on_item_completed,
        )

        validation_passed = not any(state.error for state in context.execution_state.values())

        # Build the complete lineage from model, sub-USD layers, and textures.
        model_output_path = remix_item.value
        local_outputs = [model_output_path, *(published_path for _, published_path in context.sub_usd_lineage)]
        if is_remote_output and prepared.output_url is not None:
            output_urls = await publish_remote_outputs(
                local_output_dir,
                local_outputs,
                prepared.output_url,
                1,
                progress_callback,
            )
        else:
            output_urls = [str(path) for path in local_outputs]

        model_source_path = prepared.source_path
        if await run_in_worker_thread(model_source_path.is_file):
            model_hash = await run_in_worker_thread(hash_file, str(model_source_path))
        else:
            # Source identity does not exist on disk; hash the published output.
            model_hash = await run_in_worker_thread(hash_file, str(model_output_path))
        if model_hash is None:
            raise RuntimeError(f"Cannot hash model lineage entry: {model_source_path}")
        model_entry = (
            str(model_source_path),
            output_urls[0],
            model_hash,
        )

        # The runner mutates and moves each sub-USD dependency in this job's own workspace before
        # publication, so its recorded identity is already relocated by the time lineage is assembled.
        # Match each published dependency back to the durable, unmutated copy this job received from
        # PrepareOptimizationJob, by the stable relative structure both the prepared model and the
        # published model preserve, and hash that prepared original instead of the moved path.
        prepared_root = prepared.model_work_path.resolve().parent
        prepared_layers, _prepared_assets, _prepared_unresolved = await run_in_worker_thread(
            UsdUtils.ComputeAllDependencies, str(prepared.model_work_path)
        )
        prepared_layer_paths: dict[str, pathlib.Path] = {}
        for layer in prepared_layers:
            if not layer.realPath:
                continue
            real_path = pathlib.Path(layer.realPath).resolve()
            if real_path == prepared.model_work_path.resolve() or not real_path.is_relative_to(prepared_root):
                continue
            prepared_layer_paths[str(real_path.relative_to(prepared_root))] = real_path

        sub_usd_entries: list[tuple[str, str, str]] = []
        for index, (_runner_source_path, published_path) in enumerate(context.sub_usd_lineage):
            relative = published_path.relative_to(model_output_path.parent)
            prepared_path = prepared_layer_paths.get(str(relative))
            if prepared_path is not None and await run_in_worker_thread(prepared_path.is_file):
                source_path = prepared_path
            else:
                # Prepared original is not accessible; hash the published output.
                source_path = published_path
            layer_hash = await run_in_worker_thread(hash_file, str(source_path))
            if layer_hash is None:
                raise RuntimeError(f"Cannot hash sub-USD lineage entry: {source_path}")
            sub_usd_entries.append(
                (
                    str(source_path),
                    output_urls[index + 1],
                    layer_hash,
                )
            )

        published_textures = texture_result.rebased_onto(remix_item.textures)
        if is_remote_output and prepared.output_url is not None:
            output_directory_url = f"{prepared.output_url.rstrip('/')}/"
            texture_urls = {
                str(path): combine_urls(output_directory_url, path.relative_to(local_output_dir).as_posix())
                for texture in remix_item.textures
                for path in (texture.path, *texture.udim_tiles)
            }
            published_textures = TextureProcessingResult(
                items=tuple(
                    replace(
                        item,
                        asset_url=texture_urls.get(item.asset_url, item.asset_url),
                        udim_tiles=tuple(texture_urls.get(tile, tile) for tile in item.udim_tiles),
                    )
                    for item in published_textures.items
                ),
                lineage=tuple(
                    (source_path, texture_urls.get(output_url, output_url), source_hash)
                    for source_path, output_url, source_hash in published_textures.lineage
                ),
                validation_passed=published_textures.validation_passed,
            )
        complete_lineage = (model_entry,) + tuple(sub_usd_entries) + published_textures.lineage

        await progress_callback(JobProgress(completed=1, total=1, detail="Mesh optimization complete"))
        return JobOutputs(
            {
                self.OPTIMIZED_MESH: MeshOptimizationResult(
                    asset_url=output_urls[0],
                    texture_result=published_textures,
                    lineage=complete_lineage,
                    source_path=prepared.source_path,
                    validation_passed=validation_passed,
                )
            }
        )

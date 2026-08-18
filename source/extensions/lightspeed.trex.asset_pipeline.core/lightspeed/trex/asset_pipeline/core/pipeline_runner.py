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

__all__ = ["run_remix_asset_pipeline"]

import pathlib
import shutil
import uuid
from collections.abc import Awaitable, Callable, Iterable

import carb
from omni.flux.asset_pipeline.core import PipelineStep, run_pipeline, validate_pipeline
from omni.flux.asset_pipeline.core.pipeline import PipelineProgressCallback

from .pipeline_builder import build_remix_asset_pipeline
from .pipeline_config import RemixAssetPipelineConfig
from .pipeline_context import RemixAssetPipelineContext
from .pipeline_item import AssetKind, RemixAssetItem, TextureAsset, get_texture_source_path
from .worker import run_in_worker_thread


async def run_remix_asset_pipeline(
    config: RemixAssetPipelineConfig,
    context: RemixAssetPipelineContext,
    steps: Iterable[PipelineStep] | None = None,
    *,
    on_step_started: PipelineProgressCallback | None = None,
    on_item_completed: Callable[[RemixAssetItem, int, int], Awaitable[None]] | None = None,
) -> None:
    """Run the Remix asset pipeline and publish its outputs as the final reported phase.

    Args:
        config: Canonical pipeline configuration.
        context: Remix items and runner-owned paths for this run.
        steps: Configured processing steps, or None to build them from ``config``.
        on_step_started: Async callback awaited before each runnable phase.
        on_item_completed: Async callback awaited after each source item finishes processing.

    Raises:
        PipelineValidationError: If the configured steps cannot run against ``context``.
        OSError: If the output directory or temporary workspace cannot be created or removed.
    """
    temp_dir = config.output_dir.parent / f"remix_asset_pipeline_{uuid.uuid4().hex}"
    items = list(context.items)
    try:
        await run_in_worker_thread(config.output_dir.mkdir, parents=True, exist_ok=True)
        await run_in_worker_thread(temp_dir.mkdir)
        context.work_dir = temp_dir
        context.output_dir = config.output_dir
        context.clear_output_paths()
        configured_steps = list(steps) if steps is not None else build_remix_asset_pipeline(config)
        validate_pipeline(configured_steps, context)

        async def on_processing_step_started(step: PipelineStep, index: int, _total: int) -> None:
            """Report a processing phase within the complete pipeline phase count.

            Args:
                step: Processing step that started.
                index: One-based position of the processing step.
                _total: Processing-only phase count supplied by the generic runner.
            """
            if on_step_started is not None:
                await on_step_started(step, index, len(configured_steps) + 1)

        for item_index, item in enumerate(items, start=1):
            context.execution_state.clear()
            context.items = [item]
            await run_pipeline(configured_steps, context, on_step_started=on_processing_step_started)
            if on_item_completed is not None:
                await on_item_completed(item, item_index, len(items))

        context.items = items

        async def on_publish_started(step: PipelineStep, _index: int, _total: int) -> None:
            """Report publication as the final configured phase.

            Args:
                step: Publication step.
                _index: Single-step pipeline index, replaced with the configured phase position.
                _total: Single-step pipeline total, replaced with the complete phase count.
            """
            if on_step_started is not None:
                await on_step_started(step, len(configured_steps) + 1, len(configured_steps) + 1)

        await run_pipeline(
            [_PublishOutputsStep()],
            context,
            on_step_started=on_publish_started,
        )
    finally:
        context.items = items
        try:
            context.close_stage_cache()
        finally:
            context.clear_output_paths()
            context.work_dir = None
            context.output_dir = None
            await run_in_worker_thread(_remove_workspace, temp_dir)


def _remove_workspace(path: pathlib.Path) -> None:
    """Remove a pipeline workspace when creation reached the filesystem.

    Args:
        path: Workspace path to remove from a worker thread.

    Raises:
        OSError: If an existing workspace cannot be removed.
    """
    if path.exists():
        shutil.rmtree(path)


class _PublishOutputsStep(PipelineStep):
    """Publish processed Remix assets to their final destinations."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the stable publication phase name.

        Returns:
            The pipeline phase identifier.
        """
        return "publish_outputs"

    @property
    def description(self) -> str:
        """Return the user-facing publication phase description.

        Returns:
            The publication phase label shown to users.
        """
        return "Save processed assets"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Publish all final item files outside the event-loop thread.

        Args:
            context: Pipeline state containing the final asset paths and temporary work directory.

        Raises:
            FileNotFoundError: If a reported pipeline output is missing.
            RuntimeError: If the work directory is unset or two outputs resolve to the same destination.
            OSError: If an output cannot be published.
        """
        if context.work_dir is None:
            raise RuntimeError("publish_outputs: context.work_dir must be set by the pipeline runner")
        await run_in_worker_thread(_publish_outputs, context, context.work_dir)


def _publish_outputs(
    context: RemixAssetPipelineContext,
    work_dir: pathlib.Path,
) -> None:
    """Publish final files with rollback for replaced destinations.

    Item and texture paths are updated only after every file is published successfully.

    Args:
        context: Pipeline state containing the assets and reserved output destinations.
        work_dir: Temporary workspace whose files can be moved instead of copied.

    Raises:
        FileNotFoundError: If a reported pipeline output is missing.
        RuntimeError: If two outputs resolve to the same destination.
        OSError: If an output cannot be published.
    """
    published: dict[pathlib.Path, pathlib.Path] = {}
    published_destinations: dict[pathlib.Path, pathlib.Path] = {}
    rollback_entries: list[tuple[pathlib.Path, pathlib.Path | None]] = []
    item_updates: list[tuple[RemixAssetItem, pathlib.Path]] = []
    texture_updates: list[tuple[TextureAsset, pathlib.Path]] = []

    def publish(path: pathlib.Path, source_key: pathlib.Path) -> pathlib.Path:
        """Publish one output path and its metadata sidecar at most once.

        Args:
            path: Processed file to publish.
            source_key: Original asset path used to reserve the destination.

        Returns:
            Final destination of the published file.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            RuntimeError: If another output already owns the destination.
            OSError: If the output or metadata sidecar cannot be published.
        """
        if path in published:
            return published[path]
        if not path.exists():
            raise FileNotFoundError(f"Pipeline output missing before publish: {path}")

        destination = context.get_output_path(path, source_path=source_key)
        if destination in published_destinations:
            raise RuntimeError(
                f"Pipeline output destination is already published: {destination} "
                f"from {published_destinations[destination]}"
            )
        if path != destination:
            move_to_destination(path, destination)

        meta_path = path.with_suffix(path.suffix + ".meta")
        if meta_path.exists():
            destination_meta = destination.with_suffix(destination.suffix + ".meta")
            if meta_path != destination_meta:
                move_to_destination(meta_path, destination_meta)

        published[path] = destination
        published_destinations[destination] = path
        return destination

    def move_to_destination(path: pathlib.Path, destination: pathlib.Path) -> None:
        """Move or copy a file while retaining any replaced destination for rollback.

        Args:
            path: File to publish.
            destination: Final output path.

        Raises:
            OSError: If the source cannot be published or the destination cannot be backed up.
        """
        backup_path = None
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            # Keep the replaced file in the output directory so a killed process still leaves a recoverable original.
            backup_path = destination.with_name(f".{destination.name}.asset_pipeline_backup_{uuid.uuid4().hex}")
            destination.replace(backup_path)

        rollback_entries.append((destination, backup_path))
        if path.is_relative_to(work_dir):
            shutil.move(str(path), str(destination))
        else:
            shutil.copy2(path, destination)

    try:
        for item in context.items:
            if item.kind is AssetKind.MODEL:
                item_updates.append((item, publish(item.value, item.source_path)))
            for texture in item.textures:
                texture_updates.append((texture, publish(texture.path, get_texture_source_path(texture))))
    except Exception:
        for destination, backup_path in reversed(rollback_entries):
            if destination.exists():
                try:
                    destination.unlink()
                except OSError as cleanup_error:
                    carb.log_warn(f"Unable to remove incomplete asset pipeline output {destination}: {cleanup_error}")
            if backup_path is not None and backup_path.exists():
                try:
                    backup_path.replace(destination)
                except OSError as cleanup_error:
                    carb.log_warn(f"Unable to restore asset pipeline backup {backup_path}: {cleanup_error}")
        raise
    else:
        for _destination, backup_path in rollback_entries:
            if backup_path is not None:
                try:
                    backup_path.unlink()
                except OSError as cleanup_error:
                    carb.log_warn(f"Unable to remove asset pipeline backup {backup_path}: {cleanup_error}")
        for item, path in item_updates:
            item.value = path
        for texture, path in texture_updates:
            texture.path = path

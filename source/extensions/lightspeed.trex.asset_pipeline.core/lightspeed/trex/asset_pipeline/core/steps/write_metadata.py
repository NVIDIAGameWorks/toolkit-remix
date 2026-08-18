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

__all__ = ["WriteMetadataStep"]

import carb
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.common.path_utils import hash_file, write_metadata

from ..pipeline_context import RemixAssetPipelineContext
from ..pipeline_item import RemixAssetItem, iter_pipeline_output_paths
from ..worker import run_in_worker_thread


def _write_output_metadata(file_path: str) -> str:
    """Hash one output and write its metadata in one blocking operation.

    Args:
        file_path: Processed output whose metadata sidecar should be written.

    Returns:
        The output hash stored in the metadata sidecar.

    Raises:
        FileNotFoundError: If the output cannot be hashed before the metadata write.
    """
    file_hash = hash_file(file_path)
    if file_hash is None:
        raise FileNotFoundError(f"Pipeline output cannot be hashed before metadata write: {file_path}")
    write_metadata(file_path, "base_hash", file_hash)
    write_metadata(file_path, "validation_passed", True)
    return file_hash


class WriteMetadataStep(PipelineStep):
    """Write deterministic .meta sidecars for final processed assets."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier.

        Returns:
            Stable pipeline step name.
        """
        return "write_metadata"

    @property
    def description(self) -> str:
        """Return a human-readable description.

        Returns:
            User-facing phase description.
        """
        return "Save asset information"

    def should_run(self, context: PipelineContext) -> bool:
        """Return true when the context contains at least one output path.

        Args:
            context: Pipeline state to inspect.

        Returns:
            Whether any final output requires metadata.
        """
        return any(iter_pipeline_output_paths(context))

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no work for the already-compatible context.

        Args:
            context: Pipeline state without output paths.

        Returns:
            User-readable skip reason.
        """
        return "no processed asset outputs"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Hash each output path and write its .meta sidecar file.

        Args:
            context: Pipeline state containing the processed output paths.

        Raises:
            FileNotFoundError: If an output cannot be hashed before writing metadata.
        """
        for path in iter_pipeline_output_paths(context):
            file_path = str(path)
            file_hash = await run_in_worker_thread(_write_output_metadata, file_path)

            carb.log_info(f"[WriteMetadata] Wrote metadata for {file_path} (hash={file_hash[:8]}...)")

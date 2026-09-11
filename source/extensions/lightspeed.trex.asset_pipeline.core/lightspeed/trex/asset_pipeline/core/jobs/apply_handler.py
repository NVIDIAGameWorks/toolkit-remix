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
    "SaveMeshMetadataHandler",
    "SaveTextureMetadataHandler",
]

import abc
import pathlib
from typing import Generic, TypeVar

from omni.client import is_local_url
from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.enums import ApplyPolicy

from ..metadata import (
    MetadataApplyReceipt,
    capture_metadata_receipt,
    get_current_validation_extensions,
    revert_metadata,
    write_input_sidecars,
    write_metadata_for_paths,
)
from ..worker import run_in_worker_thread
from .models import MeshOptimizationResult, TextureProcessingResult

_ResultT = TypeVar("_ResultT", TextureProcessingResult, MeshOptimizationResult)


class _SaveMetadataHandler(ApplyHandler[_ResultT, None, MetadataApplyReceipt], Generic[_ResultT]):
    """Write metadata sidecars for one completed pipeline result."""

    target_type = type(None)
    receipt_type = MetadataApplyReceipt
    apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC

    @staticmethod
    @abc.abstractmethod
    def _local_output_paths(value: _ResultT) -> list[pathlib.Path | str]:
        """Return the published output paths."""
        raise NotImplementedError

    @staticmethod
    @abc.abstractmethod
    def _input_paths(value: _ResultT) -> list[pathlib.Path]:
        """Return the local consumed input paths."""
        raise NotImplementedError

    async def capture_receipt(self, value: _ResultT, target: None) -> MetadataApplyReceipt:
        """Read the prior sidecar content of every path before Apply overwrites it.

        Inputs are captured with the outputs. Apply writes an input sidecar, so revert must restore it.
        Otherwise a reverted run leaves metadata behind on a file it did not produce.

        Args:
            value: Completed result whose paths receive metadata.
            target: Unused; metadata writing has no live project target.

        Returns:
            The prior sidecar content of every output and local input.
        """
        del target
        return await run_in_worker_thread(
            capture_metadata_receipt, self._local_output_paths(value) + self._input_paths(value)
        )

    async def apply(self, value: _ResultT, target: None, receipt: MetadataApplyReceipt) -> None:
        """Write all sidecars as one reversible Apply attempt.

        Args:
            value: Completed result whose outputs and local inputs receive metadata.
            target: Unused; metadata writing has no live project target.
            receipt: Durable pre-Apply state used by Revert.
        """
        del target, receipt
        # Read the extension manager here, on the Kit thread, not inside the worker.
        validation_extensions = get_current_validation_extensions()
        output_paths = self._local_output_paths(value)
        input_paths = self._input_paths(value)
        rollback_receipt = await run_in_worker_thread(
            capture_metadata_receipt,
            output_paths + input_paths,
        )
        try:
            await run_in_worker_thread(write_input_sidecars, input_paths)
            await run_in_worker_thread(
                write_metadata_for_paths,
                output_paths,
                validation_extensions,
                value.validation_passed,
            )
        except BaseException as apply_error:
            try:
                await run_in_worker_thread(revert_metadata, rollback_receipt)
            except BaseException as rollback_error:  # noqa: BLE001 - Rollback must report every failure.
                raise RuntimeError(
                    f"Metadata Apply failed and rollback could not restore prior sidecars: {rollback_error}"
                ) from apply_error
            raise

    async def revert(self, value: _ResultT, target: None, receipt: MetadataApplyReceipt) -> None:
        """Restore every written sidecar to its pre-Apply state.

        Args:
            value: Unused; the receipt carries every sidecar path.
            target: Unused; metadata writing has no live project target.
            receipt: Prior sidecar content captured before Apply.
        """
        del value, target
        await run_in_worker_thread(revert_metadata, receipt)


class SaveTextureMetadataHandler(_SaveMetadataHandler[TextureProcessingResult]):
    """Write deterministic metadata sidecars for a completed texture batch's outputs.

    Bind this handler only on the terminal job of a graph (a standalone ``TextureProcessingJob``), never on a
    ``TextureProcessingJob`` feeding a downstream ``MeshOptimizationJob``: applying textures before the mesh
    completes would write metadata for outputs the mesh job's own Apply has not yet finished consuming.
    """

    name = "SaveTextureMetadataHandler"
    input_type = TextureProcessingResult

    @staticmethod
    def _local_output_paths(value: TextureProcessingResult) -> list[pathlib.Path | str]:
        """Return all processed texture output URLs."""
        return [item.asset_url for item in value.items]

    @staticmethod
    def _input_paths(value: TextureProcessingResult) -> list[pathlib.Path]:
        """Return the local source texture inputs."""
        return [item.source_path for item in value.items if is_local_url(str(item.source_path))]


class SaveMeshMetadataHandler(_SaveMetadataHandler[MeshOptimizationResult]):
    """Write deterministic metadata sidecars for a completed mesh's output and its processed textures.

    Bind this handler only on the terminal ``MeshOptimizationJob`` of a graph, not on the model graph's inner
    ``TextureProcessingJob``: this handler is the single place metadata is written for a whole model graph, so
    the mesh result carries the consumed ``TextureProcessingResult`` for exactly this purpose.
    """

    name = "SaveMeshMetadataHandler"
    input_type = MeshOptimizationResult

    @staticmethod
    def _local_output_paths(value: MeshOptimizationResult) -> list[pathlib.Path | str]:
        """Return the mesh and processed texture output URLs."""
        return [
            value.asset_url,
            *(item.asset_url for item in value.texture_result.items),
        ]

    @staticmethod
    def _input_paths(value: MeshOptimizationResult) -> list[pathlib.Path]:
        """Return the local model and source texture inputs."""
        paths: list[pathlib.Path] = []
        if value.source_path is not None and is_local_url(str(value.source_path)):
            paths.append(value.source_path)
        paths.extend(item.source_path for item in value.texture_result.items if is_local_url(str(item.source_path)))
        return paths

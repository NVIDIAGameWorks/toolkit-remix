"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

__all__ = ["TextureProcessingDisplayAdapter"]

import pathlib
from urllib.request import url2pathname

import carb
from lightspeed.trex.asset_pipeline.core.job import TextureProcessingJob
from lightspeed.trex.asset_pipeline.core.models import TextureProcessingRequest, TextureProcessingResult
from omni.client import break_url, is_local_url
from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.core.models import QueueJobDetailsSnapshot
from omni.flux.job_queue.core.job import JobProgress
from omni.flux.job_queue.widget.display_adapter_base import (
    JobAction,
    JobDetailDirectories,
    JobDetailField,
    JobDetailSection,
    JobDisplayAdapter,
)
from omni.flux.job_queue.widget.constants import ADAPTER_ERRORS
from omni.flux.job_queue.widget.enums import DisplayState, JobDetailSectionPlacement
from omni.flux.utils.common.path_utils import open_file_using_os_default


class TextureProcessingDisplayAdapter(JobDisplayAdapter):
    """Present the shared texture-processing job without product-specific assumptions."""

    name = "texture_processing"
    job_type = TextureProcessingJob
    source_name = "Texture Processing"
    display_name = "Texture optimization"
    active_status_label = "Optimizing textures"
    _OPEN_TEXTURE_DIRECTORY_ACTION_ID = "open_processed_texture_directory"

    def get_name_tooltip(self, job: TextureProcessingJob) -> str:
        """Describe the reusable processing and publication step.

        Args:
            job: Texture-processing job being displayed.

        Returns:
            Generic processing description.
        """
        return "Prepare, optimize, and publish textures for efficient use in RTX Remix."

    def get_active_status_label(self, job: TextureProcessingJob, progress: JobProgress | None) -> str | None:
        """Show the exact active pipeline phase when one is available.

        Args:
            job: Active texture-processing job.
            progress: Latest structured pipeline progress.

        Returns:
            Current pipeline phase, or the generic preparation fallback.
        """
        if progress is not None and progress.detail:
            return progress.detail
        return self.active_status_label

    def get_active_progress_label(self, job: TextureProcessingJob, progress: JobProgress | None) -> str | None:
        """Format structured texture-count progress.

        Args:
            job: Active texture-processing job.
            progress: Latest structured processing progress.

        Returns:
            Completed texture count, or None before progress begins.
        """
        if progress is None or progress.completed is None or progress.total is None:
            return None
        return f"{progress.completed} of {progress.total} textures"

    def _get_output_action_state(self, job: TextureProcessingJob) -> tuple[pathlib.Path | None, str]:
        """Return the processed-output directory action's current state.

        Args:
            job: Texture-processing job whose persisted outputs should be inspected.

        Returns:
            Shared local output directory and exact user-facing tooltip.
        """
        try:
            details = get_job_queue().get_job_details(job.job_id, include_values=True)
        except ADAPTER_ERRORS as error:
            carb.log_warn(f"Could not resolve processed textures for queue job {job.job_id}: {error}")
            return None, "Processed texture information is unavailable."

        result = details.outputs.get(job.PROCESSED_TEXTURES) if details.outputs is not None else None
        if type(result) is not TextureProcessingResult or not result.items:
            return None, "Processed textures are not available yet."

        local_paths = tuple(
            path for item in result.items if (path := self._local_asset_path(item.asset_url)) is not None
        )
        if not local_paths:
            return None, "Processed textures are stored remotely and cannot be opened in File Explorer."
        if len(local_paths) != len(result.items):
            return None, "Processed textures are split between local and remote locations."
        output_directory = self._shared_parent(local_paths)
        if output_directory is None:
            return None, "Processed textures are stored in multiple local directories."
        return output_directory, "Open the processed texture directory in File Explorer."

    def _get_result_output_directory(
        self,
        job: TextureProcessingJob,
        details: QueueJobDetailsSnapshot,
    ) -> pathlib.Path | None:
        """Resolve the exact shared local parent represented by processed textures.

        Args:
            job: Texture-processing job whose declared output port is inspected.
            details: Public details containing optional persisted output values.

        Returns:
            Shared local processed-texture directory, or None when unavailable or remote-only.
        """
        result = details.outputs.get(job.PROCESSED_TEXTURES) if details.outputs is not None else None
        if type(result) is not TextureProcessingResult:
            return None
        output_paths = tuple(
            path for item in result.items if (path := self._local_asset_path(item.asset_url)) is not None
        )
        return self._shared_parent(output_paths)

    @staticmethod
    def _shared_parent(paths: tuple[pathlib.Path, ...]) -> pathlib.Path | None:
        """Return one exact shared parent without guessing a broader directory.

        Args:
            paths: Local texture paths represented by one typed port value.

        Returns:
            The exact common parent, or None when the textures span directories.
        """
        parents = {path.parent for path in paths}
        return next(iter(parents)) if len(parents) == 1 else None

    @staticmethod
    def _local_asset_path(asset_url: str) -> pathlib.Path | None:
        """Convert one local asset URL or path to a native path.

        Args:
            asset_url: Published texture URL from a typed processing result.

        Returns:
            Native local path, or None for a remote URL.
        """
        if not is_local_url(asset_url):
            return None
        url = break_url(asset_url)
        return pathlib.Path(url2pathname(url.path) if url.scheme == "file" else asset_url)

    def get_detail_directories(
        self,
        job: TextureProcessingJob,
        details: QueueJobDetailsSnapshot,
        context_name: str,
    ) -> JobDetailDirectories:
        """Resolve the exact local directory represented by typed inputs.

        Args:
            job: Texture-processing job whose typed values are inspected.
            details: Public details containing resolved input and output values.
            context_name: USD context retained for the adapter contract.

        Returns:
            Shared input directory when it has one exact local parent.
        """
        request = details.inputs.get(job.SOURCE_TEXTURES) if details.inputs is not None else None
        input_paths = tuple(item.path for item in request.items) if type(request) is TextureProcessingRequest else ()
        return JobDetailDirectories(self._shared_parent(input_paths))

    def get_job_actions(self, job: TextureProcessingJob, context_name: str) -> tuple[JobAction, ...]:
        """Expose one stable child-owned directory action.

        Args:
            job: Texture-processing job whose published files may be revealed.
            context_name: USD context retained for the adapter contract.

        Returns:
            Directory action enabled only when one local directory represents every processed texture.
        """
        output_directory, tooltip = self._get_output_action_state(job)
        return (
            JobAction(
                self._OPEN_TEXTURE_DIRECTORY_ACTION_ID,
                "Reveal in File Explorer",
                "OpenFolder",
                tooltip,
                output_directory is not None,
            ),
        )

    def execute_action(self, action_id: str, job: TextureProcessingJob, context_name: str) -> None:
        """Open the directory containing this job's local processed textures.

        Args:
            action_id: Stable action identifier selected by the queue row.
            job: Texture-processing job whose output should be revealed.
            context_name: USD context retained for the adapter contract.
        """
        if action_id != self._OPEN_TEXTURE_DIRECTORY_ACTION_ID:
            raise KeyError(action_id)
        output_directory, _ = self._get_output_action_state(job)
        if output_directory is None:
            return
        open_file_using_os_default(str(output_directory), highlight=False)

    def get_detail_sections(
        self,
        job: TextureProcessingJob,
        details: QueueJobDetailsSnapshot,
        context_name: str,
    ) -> tuple[JobDetailSection, ...]:
        """Expose every published texture through one ordered section after Outputs.

        Args:
            job: Texture-processing job whose exact output port is inspected.
            details: Public typed queue details with optional persisted output values.
            context_name: USD context retained for the adapter contract.

        Returns:
            One processed-texture section, including remote outputs that cannot be revealed locally.
        """
        result = details.outputs.get(job.PROCESSED_TEXTURES) if details.outputs is not None else None
        if type(result) is not TextureProcessingResult:
            return ()
        fields = tuple(
            JobDetailField(
                f"texture_processing.output.{index}",
                item.key.replace("_", " ").title(),
                item.asset_url,
                "Processed texture published by the reusable asset pipeline.",
            )
            for index, item in enumerate(result.items)
        )
        if not fields:
            return ()
        return (
            JobDetailSection(
                "processed_textures",
                "Processed textures",
                fields,
                JobDetailSectionPlacement.AFTER_OUTPUTS,
                self._get_result_output_directory(job, details),
            ),
        )

    def get_state_tooltip(
        self,
        job: TextureProcessingJob,
        state: DisplayState,
        state_reason: str | None,
    ) -> str | None:
        """Return generic processing, publication, and Apply guidance.

        Args:
            job: Texture-processing job whose state is displayed.
            state: Current queue display state.
            state_reason: Persisted technical detail for the current state.

        Returns:
            Friendly state guidance, or None for the queue default.
        """
        if state is DisplayState.WAITING_FOR_DEPENDENCIES:
            return "Waiting for generated textures."
        if state is DisplayState.SKIPPED:
            return state_reason or "Texture optimization was skipped because its source job could not finish."
        if state is DisplayState.IN_PROGRESS:
            return state_reason or "Optimizing and publishing textures for RTX Remix."
        if state is DisplayState.READY_TO_APPLY:
            return "The optimized textures are ready to add to the project."
        if state in (DisplayState.APPLYING, DisplayState.REAPPLYING):
            return "Adding the optimized textures to the project."
        if state is DisplayState.REVERTING:
            return "Restoring the project values used before the first Apply."
        if state is DisplayState.APPLIED:
            return "The optimized textures were added to the project."
        if state in (DisplayState.APPLY_FAILED, DisplayState.REAPPLY_FAILED):
            return state_reason or "The optimized textures could not be added. Check the open project, then try again."
        if state is DisplayState.REVERT_FAILED:
            return state_reason or (
                "The previous project values could not be restored. Resolve external edits, then try Revert again."
            )
        if state is DisplayState.FAILED:
            return state_reason or "The generated textures could not be optimized or published."
        return None

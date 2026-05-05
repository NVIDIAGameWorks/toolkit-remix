"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import dataclasses
import pathlib
import time
from typing import TYPE_CHECKING, Any

import carb
import omni.flux.job_queue.core.execute
import omni.flux.job_queue.core.interface
import omni.flux.job_queue.core.job

if TYPE_CHECKING:
    from lightspeed.trex.ai_tools.widget import comfy


def _get_default_comfy_url() -> str:
    from lightspeed.trex.ai_tools.widget import settings  # noqa: PLC0415

    return settings.get_comfy_url()


def _get_default_workflow() -> comfy.Workflow:
    from lightspeed.trex.ai_tools.widget import comfy  # noqa: PLC0415

    return comfy.Workflow()


@dataclasses.dataclass
class OutputArtifact:
    """
    Represents an output artifact from a ComfyUI workflow.

    Contains the downloaded file path along with any metadata from the workflow
    that can be used by handlers to determine how to process the artifact.
    """

    path: pathlib.Path
    node_id: str = ""
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a metadata value by key."""
        return self.metadata.get(key, default)


@dataclasses.dataclass
class ComfyJob(omni.flux.job_queue.core.job.Job):
    """
    A job that executes a ComfyUI workflow and produces output artifacts.

    The prim_paths field stores the USD prim paths that this job's results
    should be applied to. This allows the same job results to be applied
    to multiple prims that share the same input data.

    Attributes:
        comfy_url: URL of the ComfyUI server.
        workflow: The workflow to execute.
        timeout: Maximum execution time in seconds (default 5 minutes).
        output_filename_prefix: Optional prefix for output filenames.
        prim_paths: USD prim paths that results should be applied to.
        job_dir: Directory for job outputs. Auto-set in pre_execute if None.

    Apply Flow:
        1. Job completes and stores OutputArtifacts in Result event
        2. ApplyHandlerRegistry routes to ComfyJobApplyHandler (based on job type)
        3. ComfyJobApplyHandler delegates to artifact handlers (TextureArtifactHandler, etc.)
        4. Artifact handlers ingest and apply results to USD stage
    """

    comfy_url: str = dataclasses.field(default_factory=_get_default_comfy_url)
    workflow: comfy.Workflow = dataclasses.field(default_factory=_get_default_workflow)
    timeout: float = 60.0 * 5.0  # 5 minutes
    output_filename_prefix: str | None = None
    prim_paths: list[str] = dataclasses.field(default_factory=list)
    job_dir: pathlib.Path | None = None

    def __post_init__(self):
        from lightspeed.trex.ai_tools.widget import comfy  # noqa: PLC0415

        # Normalize the ComfyUI URL
        if not self.comfy_url:
            raise ValueError("comfy_url must not be empty")
        self.comfy_url = comfy.normalize_url(self.comfy_url)
        if not self.workflow:
            raise ValueError("workflow must not be empty")
        super().__post_init__()

    def pre_execute(self, interface: omni.flux.job_queue.core.interface.QueueInterface) -> None:
        if self.job_dir is None:
            self.job_dir = omni.flux.job_queue.core.execute.get_default_job_directory(interface, self.job_id)

    def execute(self) -> list[OutputArtifact]:
        """
        Execute the ComfyUI workflow and return a list of output artifacts.

        Each artifact includes the downloaded file path and metadata from the
        workflow that describes what kind of output it is.
        """
        from lightspeed.trex.ai_tools.widget import comfy  # noqa: PLC0415

        carb.log_info(f"[ComfyJob][{self.job_id}] Starting...")

        if not self.job_dir:
            raise ValueError("No job_dir set in ComfyJob. Call pre_execute first.")

        comfy_interface = comfy.ComfyInterface(
            url=self.comfy_url,
            client_id=str(self.job_id),
        )

        comfy_job_subfolder = f"rtx-remix/{self.job_id}"

        self.workflow.upload_and_replace_filepaths(comfy_job_subfolder, comfy_interface)

        prompt = self.workflow.get_prompt(context={"job_id": str(self.job_id)})

        # This extra data can be used by the RTX Remix Save Texture node to inform how to name the files.
        extra_data = {
            "extra_pnginfo": {
                "rtx-remix": {
                    "subfolder": comfy_job_subfolder,
                },
                # The ComfyUI nodepack comfyui-impact-pack also uses the extra_pnginfo to send along extra
                # information, but they aren't careful about how they extract the data so it causes KeyError if the
                # user has this nodepack installed and does not include these keys...
                "workflow": {
                    "nodes": [],
                },
            },
        }

        carb.log_info(f"[ComfyJob][{self.job_id}] Submitting workflow to ComfyUI...")
        start = time.time()
        prompt_id, comfy_outputs_by_node = comfy_interface.execute(prompt, extra_data=extra_data, timeout=self.timeout)
        tag = f"[ComfyJob][{self.job_id}][{prompt_id}]"
        carb.log_info(f"{tag} Workflow completed in {time.time() - start:.2f}s")

        output_dir = self.job_dir / "outputs" / prompt_id

        carb.log_info(f"{tag} Downloading outputs to {output_dir}...")

        if self.output_filename_prefix is None:
            filename_prefix = f"{self.job_id}_{prompt_id}"
        else:
            filename_prefix = self.output_filename_prefix

        artifacts: list[OutputArtifact] = []

        for node_id, comfy_outputs in comfy_outputs_by_node.items():
            # Get the output metadata from the workflow
            output_meta = self.workflow.get_output_metadata(node_id)
            if output_meta is None:
                carb.log_warn(f"Skipping output from node ID: {node_id} (not in workflow outputs)")
                continue

            for comfy_output in comfy_outputs:
                carb.log_info(f"{tag} Downloading output: {comfy_output.subfolder}/{comfy_output.filename}...")
                downloaded_path = comfy_interface.download(output_dir, comfy_output)

                unique_filename = f"{filename_prefix}_{downloaded_path.name}"
                unique_path = downloaded_path.parent / unique_filename

                downloaded_path.rename(unique_path)

                # Create artifact with the metadata from workflow
                artifact = OutputArtifact(
                    path=unique_path,
                    node_id=node_id,
                    metadata=output_meta.copy(),
                )
                artifacts.append(artifact)

                name = output_meta.get("name", node_id)
                carb.log_info(f"{tag} Downloaded artifact: {name} -> {unique_path}")

        # Sort by the order specified in metadata
        artifacts.sort(key=lambda a: a.get("order", 0))

        return artifacts

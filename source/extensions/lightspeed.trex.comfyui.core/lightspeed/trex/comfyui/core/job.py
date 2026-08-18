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

__all__ = ["ComfyUIJob"]

import dataclasses
import hashlib
import pathlib
from copy import deepcopy
from typing import Any, ClassVar

from lightspeed.trex.asset_pipeline.core.models import TextureProcessingItem, TextureProcessingRequest
from omni.flux.job_queue.core.errors import JobExecutionError
from omni.flux.job_queue.core.job import (
    Job,
    JobInputPort,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgress,
    JobProgressCallback,
)

from .api import ComfyUIAPI, ComfyUIImageResult
from .connection import get_connected_endpoint
from .maps import OUTPUT_TEXTURE_TYPE_MAP
from .models import ComfyUIWorkflowRequest, Workflow
from .prompt import set_prompt_value
from .url import build_url, canonical_endpoint, is_valid_local_leaf


@dataclasses.dataclass
class ComfyUIJob(Job):
    """Submit one material workflow to an exact ComfyUI server.

    Attributes:
        WORKFLOW_REQUEST: Required resolved-workflow input port.
        GENERATED_TEXTURES: Generated texture-processing request output port.
        context_name: USD context captured for queue display and server matching.
        prim_paths: Selected prims sharing the target material.
        material_path: Material represented by this graph.
        scheme: Saved ComfyUI server URL scheme.
        host: Saved ComfyUI server hostname or address.
        port: Saved ComfyUI server port.
    """

    WORKFLOW_REQUEST: ClassVar[JobInputPort[ComfyUIWorkflowRequest]] = JobInputPort(
        "workflow_request", ComfyUIWorkflowRequest
    )
    GENERATED_TEXTURES: ClassVar[JobOutputPort[TextureProcessingRequest]] = JobOutputPort(
        "generated_textures", TextureProcessingRequest
    )
    input_ports: ClassVar[tuple[JobInputPort[Any], ...]] = (WORKFLOW_REQUEST,)
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = (GENERATED_TEXTURES,)

    context_name: str = ""
    prim_paths: list[str] = dataclasses.field(default_factory=list)
    material_path: str = ""
    scheme: str = "http"
    host: str = "127.0.0.1"
    port: int = 8188

    def get_schedule_block_reason(self) -> str | None:
        """Return why this job must wait for its saved ComfyUI server.

        Returns:
            User-facing block reason, or ``None`` when the saved server is connected.
        """
        try:
            target = canonical_endpoint(self.scheme, self.host, self.port)
        except ValueError:
            return (
                "This job has an invalid ComfyUI server address. "
                "Connect to a server, then change the server for this job."
            )
        connected = get_connected_endpoint(self.context_name)
        target_url = build_url(*target)
        if connected is None:
            return f"Connect to the ComfyUI server at {target_url} to run this job."
        if connected != target:
            connected_url = build_url(*connected)
            return (
                f"This job is waiting for {target_url}. The current connection is {connected_url}. "
                "Connect to the original server or use Change Server for this job."
            )
        return None

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Execute the ComfyUI workflow and download its declared outputs.

        Args:
            job_directory: Queue-managed directory where downloaded artifacts are stored.
            inputs: Typed graph inputs containing the exact workflow request.
            progress_callback: Async structured progress reporter.

        Returns:
            One texture-processing request containing the downloaded textures.

        Raises:
            JobExecutionError: If a workflow phase fails, carrying safe user guidance and its diagnostic cause.
        """
        request = inputs[self.WORKFLOW_REQUEST]
        api = ComfyUIAPI(self.scheme, self.host, self.port)
        await progress_callback(JobProgress(completed=0, total=4, detail="Uploading inputs to ComfyUI."))
        try:
            uploaded_refs = await self._upload_images(api, request)
        except Exception as error:
            raise JobExecutionError(
                "ComfyUI could not upload this workflow's input textures. Check the input files and server, then try again.",
                error,
            ) from error
        try:
            prompt = self._build_prompt(request, uploaded_refs)
        except Exception as error:
            raise JobExecutionError(
                "The saved ComfyUI workflow inputs are no longer valid. Edit and submit the workflow again.",
                error,
            ) from error
        await progress_callback(JobProgress(completed=1, total=4, detail="Submitting workflow to ComfyUI."))
        server_subfolder = f"rtx-remix/{self.job_id}"
        try:
            prompt_id = await api.submit_prompt(
                prompt,
                request.client_id,
                extra_data={
                    "extra_pnginfo": {
                        "rtx-remix": {"subfolder": server_subfolder},
                        "workflow": {"nodes": []},
                    }
                },
            )
        except Exception as error:
            raise JobExecutionError(
                "ComfyUI could not start this workflow. Check the server connection and workflow, then try again.",
                error,
            ) from error
        await progress_callback(JobProgress(completed=2, total=4, detail="ComfyUI is generating textures."))
        try:
            history = await api.wait_for_prompt_completion(prompt_id, request.timeout)
        except TimeoutError as error:
            raise JobExecutionError(
                "ComfyUI did not finish before this job timed out. Check the server and try again.",
                error,
            ) from error
        except Exception as error:
            raise JobExecutionError(
                "The ComfyUI connection stopped before generation finished. Check the server and try again.",
                error,
            ) from error
        try:
            images = self._parse_results(history, prompt_id, request.workflow)
        except Exception as error:
            raise JobExecutionError(
                "ComfyUI finished without the exact declared texture outputs. Check the workflow outputs and try again.",
                error,
            ) from error
        await progress_callback(JobProgress(completed=3, total=4, detail="Downloading generated textures."))
        try:
            await self._download_images(api, images, prompt_id, job_directory)
        except Exception as error:
            raise JobExecutionError(
                "RTX Remix could not download every generated texture from ComfyUI. Check the server and try again.",
                error,
            ) from error
        await progress_callback(
            JobProgress(
                completed=4,
                total=4,
                detail=f"Downloaded {len(images)} generated {'texture' if len(images) == 1 else 'textures'}.",
            )
        )
        items = []
        for image in images:
            if image.path is None:
                error = RuntimeError("ComfyUI did not download every generated texture")
                raise JobExecutionError(
                    "RTX Remix could not download every generated texture from ComfyUI. Check the server and try again.",
                    error,
                ) from error
            texture_type = OUTPUT_TEXTURE_TYPE_MAP.get(image.texture_type)
            if texture_type is None:
                error = ValueError(f"Unsupported generated texture type: {image.texture_type}")
                raise JobExecutionError(
                    "ComfyUI returned a texture type this version of RTX Remix does not support. "
                    "Update the workflow or RTX Remix, then try again.",
                    error,
                ) from error
            items.append(
                TextureProcessingItem(
                    key=image.texture_type,
                    path=image.path,
                    texture_type=texture_type,
                )
            )
        return JobOutputs(
            {
                self.GENERATED_TEXTURES: TextureProcessingRequest(
                    items=tuple(items),
                    source_root=job_directory / "outputs" / prompt_id,
                    output_url=request.output_url,
                )
            }
        )

    async def _upload_images(
        self,
        api: ComfyUIAPI,
        request: ComfyUIWorkflowRequest,
    ) -> dict[str, dict[str, Any]]:
        """Upload input images to the server's job-specific namespace.

        Args:
            api: Connected ComfyUI client used for uploads.
            request: Workflow request containing the source texture bindings.

        Returns:
            Upload response for each unique source texture path.
        """
        uploaded: dict[str, dict[str, Any]] = {}
        for texture_path in dict.fromkeys(source_path for _, source_path in request.input_bindings):
            source_key = hashlib.sha256(texture_path.encode("utf-8")).hexdigest()[:12]
            subfolder = f"rtx-remix/{self.job_id}/inputs/{source_key}"
            uploaded[texture_path] = await api.upload_image(texture_path, subfolder=subfolder)
        return uploaded

    def _build_prompt(
        self,
        request: ComfyUIWorkflowRequest,
        uploaded_refs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the prompt and replace every mapped source with its server path.

        Args:
            request: Workflow request containing the prompt and input bindings.
            uploaded_refs: Upload responses keyed by source texture path.

        Returns:
            Independent prompt populated with server-side input image paths.

        Raises:
            ValueError: If a mapped workflow input no longer exists in the prompt.
            RuntimeError: If a mapped upload is missing or malformed.
        """
        prompt = deepcopy(request.prompt)
        for port_id, source_path in request.input_bindings:
            upload_result = uploaded_refs.get(source_path)
            if upload_result is None:
                raise RuntimeError(f"Workflow input '{port_id}' was not uploaded: {source_path}")

            server_filename = upload_result.get("name", "")
            if not server_filename:
                raise RuntimeError(f"Upload response for workflow input '{port_id}' has no filename")
            server_subfolder = upload_result.get("subfolder", "")
            if not isinstance(server_subfolder, str):
                raise RuntimeError(f"Upload response for workflow input '{port_id}' has an invalid subfolder")
            server_path = (
                str(pathlib.PurePosixPath(server_subfolder) / server_filename) if server_subfolder else server_filename
            )
            set_prompt_value(prompt, port_id, server_path)
        return prompt

    async def _download_images(
        self,
        api: ComfyUIAPI,
        images: list[ComfyUIImageResult],
        prompt_id: str,
        job_directory: pathlib.Path,
    ) -> None:
        """Download parsed server outputs into this queue job's artifact directory.

        Args:
            api: Connected ComfyUI client used for downloads.
            images: Validated server image descriptors to download.
            prompt_id: Completed prompt identifier used to namespace the output directory.
            job_directory: Queue-managed root directory for this job's artifacts.

        Raises:
            RuntimeError: If an output filename is unsafe or resolves to a duplicate path.
        """
        output_directory = job_directory / "outputs" / prompt_id
        downloads: list[tuple[ComfyUIImageResult, pathlib.Path]] = []
        destinations: set[pathlib.Path] = set()
        for image in images:
            if not is_valid_local_leaf(image.filename):
                raise RuntimeError("ComfyUI output does not produce a portable local filename")
            destination = output_directory / image.subfolder / image.filename
            if destination in destinations:
                raise RuntimeError("ComfyUI outputs resolve to the same local artifact path")
            destinations.add(destination)
            downloads.append((image, destination))

        for image, destination in downloads:
            image.path = await api.download_image(image, destination)

    def _parse_results(
        self,
        history: dict[str, Any],
        prompt_id: str,
        workflow: Workflow,
    ) -> list[ComfyUIImageResult]:
        """Extract declared final output images from execution history.

        Args:
            history: ComfyUI execution history keyed by prompt identifier.
            prompt_id: Completed prompt whose declared outputs should be parsed.
            workflow: Workflow declaring the exact final output nodes.

        Returns:
            Valid output images ordered by their workflow output specifications.

        Raises:
            RuntimeError: If the history or any declared output is missing, malformed, or unsafe.
        """
        if not isinstance(history, dict) or not isinstance(history.get(prompt_id), dict):
            raise RuntimeError("Invalid ComfyUI history response")
        outputs = history[prompt_id].get("outputs")
        if not isinstance(outputs, dict):
            raise RuntimeError("Invalid ComfyUI history response")
        if not workflow.output_specs:
            raise RuntimeError("ComfyUI workflow does not declare output nodes")

        results: list[ComfyUIImageResult] = []
        for output_spec in sorted(workflow.output_specs, key=lambda spec: spec.order):
            node_output = outputs.get(output_spec.node_id)
            if node_output is None:
                raise RuntimeError(
                    f"ComfyUI did not produce a final image for declared output '{output_spec.texture_type}'"
                )
            if not isinstance(node_output, dict) or not isinstance(node_output.get("images", []), list):
                raise RuntimeError("Invalid ComfyUI history response")
            final_images = []
            for image_info in node_output.get("images", []):
                if not isinstance(image_info, dict):
                    raise RuntimeError("Invalid ComfyUI history response")
                if image_info.get("type") == "output":
                    final_images.append(image_info)
            if not final_images:
                raise RuntimeError(
                    f"ComfyUI did not produce a final image for declared output '{output_spec.texture_type}'"
                )
            if len(final_images) != 1:
                raise RuntimeError(
                    f"ComfyUI produced multiple final images for declared output '{output_spec.texture_type}'; "
                    "exactly one is required"
                )
            filename = final_images[0].get("filename")
            subfolder = final_images[0].get("subfolder", "")
            if not self._is_safe_server_path(filename, subfolder):
                raise RuntimeError("Invalid ComfyUI history response")
            results.append(
                ComfyUIImageResult(
                    filename=filename,
                    texture_type=output_spec.texture_type,
                    order=output_spec.order,
                    subfolder=subfolder,
                )
            )
        return results

    @staticmethod
    def _is_safe_server_path(filename: Any, subfolder: Any) -> bool:
        """Return whether server-controlled output fields are safe relative paths.

        Args:
            filename: Server-provided output filename to validate.
            subfolder: Server-provided relative output directory to validate.

        Returns:
            Whether both values form a portable relative artifact path.
        """
        if not is_valid_local_leaf(filename):
            return False
        if not isinstance(subfolder, str):
            return False
        subfolder_path = pathlib.PurePosixPath(subfolder)
        return (
            not subfolder_path.is_absolute()
            and ".." not in subfolder_path.parts
            and all(is_valid_local_leaf(part) for part in subfolder_path.parts)
        )

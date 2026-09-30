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

__all__ = [
    "ComfyUIAssetJob",
    "ComfyUIJob",
    "ViewerRenderedInputError",
]

import dataclasses
import hashlib
import pathlib
import posixpath
import re
import tempfile
from copy import deepcopy
from functools import partial
from typing import Any, ClassVar

from lightspeed.common.constants import REMIX_FOLDER, TEXTURES_FOLDER
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    MeshOptimizationRequest,
    TextureOptimizationItem,
    TextureOptimizationRequest,
)
from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
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

from pxr import Ar, Sdf, UsdUtils

from .api import ComfyUIAPI, ComfyUIExecutionError
from .connection import get_connected_endpoint
from .constants import COMFYUI_ASSET_OUTPUT_FOLDER, COMFYUI_INPUTS_FOLDER, COMFYUI_OUTPUTS_FOLDER
from .enums import RemixType
from .maps import OUTPUT_TEXTURE_TYPE_MAP
from .models import (
    ComfyUIFileResult,
    ComfyUIWorkflowRequest,
    Workflow,
)
from .prompt import set_prompt_value
from .url import build_url, canonical_endpoint, is_valid_local_leaf


def _child_url(output_url: str | None, folder: str) -> str | None:
    """Return the publication URL for one child folder, or ``None`` for queue-owned output."""
    return f"{output_url.rstrip('/')}/{folder}" if output_url is not None else None


def _prepare_mesh_upload(layers: list[Sdf.Layer], directory: str, assets: dict[str, str]) -> list[tuple[str, str]]:
    """Copy USD layers and map their dependencies to server-relative paths."""
    destinations = {
        layer.identifier: ("" if index == 0 else f"layers/{index}/") + pathlib.PurePosixPath(layer.identifier).name
        for index, layer in enumerate(layers)
    }

    def remap(layer, path):
        if not path or pathlib.PurePosixPath(path).suffix.lower() == ".mdl":
            return path
        resolved = Sdf.ComputeAssetPathRelativeToLayer(layer, path).replace("\\", "/")
        destination = destinations.get(resolved) or assets[resolved]
        return posixpath.relpath(destination, posixpath.dirname(destinations[layer.identifier]) or ".")

    files = []
    for layer in layers:
        copied = Sdf.Layer.CreateAnonymous()
        copied.TransferContent(layer)
        UsdUtils.ModifyAssetPaths(copied, partial(remap, layer))
        name = destinations[layer.identifier]
        path = pathlib.Path(directory) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not copied.Export(str(path)):
            raise RuntimeError(f"Cannot copy ComfyUI mesh layer: {layer.identifier}")
        files.append((str(path), name))
    return files


class ViewerRenderedInputError(ValueError):
    """A prompt input depends on files that only the ComfyUI browser viewer renders."""


# Known ComfyUI file loaders require server files, not browser viewer renders.
_VIEWER_FILE_LOADERS = frozenset({"LoadImage", "LoadImageMask", "Load3D", "Load3DAnimation", "LoadAudio", "LoadVideo"})
# ComfyUI viewer files use a relative path followed by one space and ``[temp]``.
_VIEWER_TEMP_FILE = re.compile(r"^[^\s\[\]]+\.\w+ \[temp\]$")


def _reject_viewer_rendered_inputs(prompt: dict[str, Any]) -> None:
    """Fail before submission when a node input points at browser-rendered temp files.

    Nodes such as ``Load3D`` store the viewer's scene renders as ``<name> [temp]`` references. Those files
    exist only in the browser session that saved the workflow, so an API submission cannot load them.

    Args:
        prompt: Prompt about to be submitted.

    Raises:
        ViewerRenderedInputError: If any node input references a ``[temp]`` file.
    """

    def has_temp_reference(value: Any) -> bool:
        if isinstance(value, str):
            return _VIEWER_TEMP_FILE.match(value) is not None
        if isinstance(value, dict):
            return any(has_temp_reference(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(has_temp_reference(item) for item in value)
        return False

    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        node_type = node.get("class_type", "node")
        metadata = node.get("_meta")
        remix_metadata = metadata.get("rtx-remix") if isinstance(metadata, dict) else None
        input_tags = remix_metadata.get("inputs") if isinstance(remix_metadata, dict) else None
        if not isinstance(input_tags, dict):
            input_tags = {}
        for input_name, value in inputs.items():
            input_tag = input_tags.get(input_name)
            consumes_file = (
                isinstance(input_tag, dict)
                and input_tag.get("remix_type") in (RemixType.TEXTURE_FILE_PATH, RemixType.MESH_FILE_PATH)
                or node_type in _VIEWER_FILE_LOADERS
                or (node_type.startswith("RTXRemix") and (input_name.endswith("_path") or input_name == "image"))
            )
            if consumes_file and has_temp_reference(value):
                raise ViewerRenderedInputError(
                    f"Workflow node {node_type} (node {node_id}) input '{input_name}' uses files rendered by the "
                    "ComfyUI browser viewer. RTX Remix cannot provide them. Use a node that reads the file path "
                    "directly, then export the workflow again."
                )


@dataclasses.dataclass
class ComfyUIJob(Job):
    """Submit one workflow to an exact ComfyUI server and download its declared files.

    ``GENERATED_TEXTURES`` carries one texture pipeline request, published under ``textures/``.
    """

    WORKFLOW_REQUEST: ClassVar[JobInputPort[ComfyUIWorkflowRequest]] = JobInputPort(
        "workflow_request", ComfyUIWorkflowRequest
    )
    GENERATED_TEXTURES: ClassVar[JobOutputPort[TextureOptimizationRequest]] = JobOutputPort(
        "generated_textures", TextureOptimizationRequest
    )
    input_ports: ClassVar[tuple[JobInputPort[Any], ...]] = (WORKFLOW_REQUEST,)
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = (GENERATED_TEXTURES,)

    context_name: str = ""
    prim_paths: list[str] = dataclasses.field(default_factory=list)
    material_path: str = ""
    scheme: str = "http"
    host: str = "127.0.0.1"
    port: int = 8188

    @property
    def _server_root(self) -> pathlib.PurePosixPath:
        """Return this job's subfolder on the ComfyUI server."""
        return pathlib.PurePosixPath(REMIX_FOLDER, str(self.job_id))

    def get_schedule_block_reason(self) -> str | None:
        """Return why this job must wait for its saved ComfyUI server."""
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
        """Run the workflow and return its texture processing request."""
        request = inputs[self.WORKFLOW_REQUEST]
        files, source_root = await self._generate_files(job_directory, request, progress_callback)
        return JobOutputs(
            {
                self.GENERATED_TEXTURES: TextureOptimizationRequest(
                    items=self._make_texture_items(files),
                    source_root=source_root,
                    output_url=_child_url(request.output_url, TEXTURES_FOLDER),
                ),
            }
        )

    async def _generate_files(
        self,
        job_directory: pathlib.Path,
        request: ComfyUIWorkflowRequest,
        progress_callback: JobProgressCallback,
    ) -> tuple[list[ComfyUIFileResult], pathlib.Path]:
        """Run one workflow and download its declared files."""
        api = ComfyUIAPI(self.scheme, self.host, self.port)
        await progress_callback(JobProgress(completed=0, total=4, detail="Uploading inputs to ComfyUI."))
        try:
            uploaded_refs = await self._upload_inputs(api, request)
        except Exception as error:
            message = "ComfyUI could not upload this workflow's input files. Check the input files and server, then try again."
            if "413" in str(error):
                message = (
                    "ComfyUI refused an input file because it is larger than the server upload limit (100 MB by "
                    "default). Start ComfyUI with --max-upload-size <MB> set above the file size, then try again."
                )
            raise JobExecutionError(message, error) from error
        try:
            prompt = self._build_prompt(request, uploaded_refs)
        except ViewerRenderedInputError as error:
            raise JobExecutionError(str(error), error) from error
        except Exception as error:
            raise JobExecutionError(
                "The saved ComfyUI workflow inputs are no longer valid. Edit and submit the workflow again.",
                error,
            ) from error
        await progress_callback(JobProgress(completed=1, total=4, detail="Submitting workflow to ComfyUI."))
        server_subfolder = str(self._server_root)
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
        await progress_callback(JobProgress(completed=2, total=4, detail="ComfyUI is generating files."))
        try:
            history = await api.wait_for_prompt_completion(prompt_id, request.timeout)
        except TimeoutError as error:
            raise JobExecutionError(
                "ComfyUI did not finish before this job timed out. Check the server and try again.",
                error,
            ) from error
        except ComfyUIExecutionError as error:
            raise JobExecutionError(error.user_message, error) from error
        except Exception as error:
            raise JobExecutionError(
                "The ComfyUI connection stopped before generation finished. Check the server and try again.",
                error,
            ) from error
        try:
            files = self._parse_results(history, prompt_id, request.workflow)
        except Exception as error:
            raise JobExecutionError(
                "ComfyUI finished without the exact declared file outputs. Check the workflow outputs and try again.",
                error,
            ) from error
        await progress_callback(JobProgress(completed=3, total=4, detail="Downloading generated files."))
        try:
            output_directory = await self._download_files(api, files, prompt_id, job_directory)
        except Exception as error:
            raise JobExecutionError(
                "RTX Remix could not download every generated file from ComfyUI. Check the server and try again.",
                error,
            ) from error
        await progress_callback(
            JobProgress(
                completed=4,
                total=4,
                detail=f"Downloaded {len(files)} generated {'file' if len(files) == 1 else 'files'}.",
            )
        )
        return files, output_directory

    @staticmethod
    def _make_texture_items(files: list[ComfyUIFileResult]) -> tuple[TextureOptimizationItem, ...]:
        """Map downloaded textures to supported pipeline texture types."""
        items = []
        for file_result in files:
            if file_result.remix_type is not RemixType.TEXTURE_FILE_PATH:
                continue
            texture_type = OUTPUT_TEXTURE_TYPE_MAP.get(file_result.texture_type or "")
            if texture_type is None:
                error = ValueError(f"Unsupported generated texture type: {file_result.texture_type}")
                raise JobExecutionError(
                    "ComfyUI returned a texture type this version of RTX Remix does not support.", error
                ) from error
            items.append(TextureOptimizationItem(key=file_result.key, path=file_result.path, texture_type=texture_type))
        return tuple(items)

    async def _upload_inputs(
        self,
        api: ComfyUIAPI,
        request: ComfyUIWorkflowRequest,
    ) -> dict[tuple[RemixType, str], dict[str, Any]]:
        """Upload each unique semantic input to an isolated server subfolder.

        Args:
            api: Connected ComfyUI client used for uploads.
            request: Workflow request containing semantic source bindings.

        Returns:
            Upload responses keyed by semantic and source URL.
        """
        uploaded: dict[tuple[RemixType, str], dict[str, Any]] = {}
        uploaded_sources: dict[str, dict[str, Any]] = {}

        def resolved_source(path):
            return (str(Ar.GetResolver().Resolve(path)) or path).replace("\\", "/")

        def native_mesh(binding):
            return binding.remix_type is RemixType.MESH_FILE_PATH and pathlib.PurePosixPath(
                binding.source
            ).suffix.lower() in (".usd", ".usda", ".usdc")

        async def upload_source(path, convert_dds):
            resolved = resolved_source(path)
            if resolved not in uploaded_sources:
                source_key = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]
                uploaded_sources[resolved] = await api.upload_file(
                    path,
                    subfolder=str(self._server_root / COMFYUI_INPUTS_FOLDER / source_key),
                    convert_dds=convert_dds,
                )
            return uploaded_sources[resolved]

        # Direct textures determine conversion and the shared server path before mesh copies are authored.
        for binding in sorted(request.input_bindings, key=native_mesh):
            key = (binding.remix_type, binding.source)
            if key in uploaded:
                continue
            if binding.remix_type not in (RemixType.TEXTURE_FILE_PATH, RemixType.MESH_FILE_PATH):
                raise ValueError(f"Unsupported ComfyUI file input semantic: {binding.remix_type}")
            resolved = resolved_source(binding.source)
            if native_mesh(binding) and resolved not in uploaded_sources:
                layers, assets, unresolved = await run_in_worker_thread(UsdUtils.ComputeAllDependencies, binding.source)
                unresolved = [path for path in unresolved if pathlib.PurePosixPath(path).suffix.lower() != ".mdl"]
                if not layers or unresolved:
                    raise RuntimeError(f"Cannot resolve ComfyUI mesh dependencies: {binding.source}: {unresolved}")
                root = Sdf.Layer.Find(binding.source)
                layers = [root, *(layer for layer in layers if layer != root)]
                source_key = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]
                subfolder = str(self._server_root / COMFYUI_INPUTS_FOLDER / source_key)
                asset_paths = {}
                for asset in assets:
                    if pathlib.PurePosixPath(asset).suffix.lower() == ".mdl":
                        continue
                    result = await upload_source(asset, False)
                    server_path = str(pathlib.PurePosixPath(result.get("subfolder", "")) / result["name"])
                    asset_paths[asset.replace("\\", "/")] = posixpath.relpath(server_path, subfolder)
                for layer in layers:
                    previous = uploaded_sources.get(resolved_source(layer.identifier))
                    if previous is not None:
                        server_path = str(pathlib.PurePosixPath(previous.get("subfolder", "")) / previous["name"])
                        asset_paths[layer.identifier] = posixpath.relpath(server_path, subfolder)
                layers = [layer for layer in layers if resolved_source(layer.identifier) not in uploaded_sources]
                with tempfile.TemporaryDirectory() as directory:
                    files = await run_in_worker_thread(_prepare_mesh_upload, layers, directory, asset_paths)
                    for layer, (path, name) in zip(layers, files):
                        result = await api.upload_file(
                            path,
                            subfolder=str(pathlib.PurePosixPath(subfolder) / pathlib.PurePosixPath(name).parent),
                            convert_dds=False,
                        )
                        uploaded_sources[resolved_source(layer.identifier)] = result
                uploaded[key] = uploaded_sources[resolved]
            else:
                uploaded[key] = await upload_source(binding.source, binding.remix_type is RemixType.TEXTURE_FILE_PATH)
        return uploaded

    def _build_prompt(
        self,
        request: ComfyUIWorkflowRequest,
        uploaded_refs: dict[tuple[RemixType, str], dict[str, Any]],
    ) -> dict[str, Any]:
        """Replace semantic source values with their uploaded server paths.

        Args:
            request: Workflow request containing the prompt and input bindings.
            uploaded_refs: Upload responses keyed by semantic and source URL.

        Returns:
            Independent prompt populated with server-side file paths.

        Raises:
            RuntimeError: If an upload response is missing or malformed.
            ValueError: If a mapped workflow input no longer exists in the prompt.
        """
        prompt = deepcopy(request.prompt)
        for binding in request.input_bindings:
            upload_result = uploaded_refs.get((binding.remix_type, binding.source))
            if upload_result is None:
                raise RuntimeError(f"Workflow input '{binding.port_id}' was not uploaded: {binding.source}")
            server_filename = upload_result.get("name", "")
            if not server_filename:
                raise RuntimeError(f"Upload response for workflow input '{binding.port_id}' has no filename")
            server_subfolder = upload_result.get("subfolder", "")
            if not isinstance(server_subfolder, str):
                raise RuntimeError(f"Upload response for workflow input '{binding.port_id}' has an invalid subfolder")
            server_path = (
                str(pathlib.PurePosixPath(server_subfolder) / server_filename) if server_subfolder else server_filename
            )
            set_prompt_value(prompt, binding.port_id, server_path)
        _reject_viewer_rendered_inputs(prompt)
        return prompt

    async def _download_files(
        self,
        api: ComfyUIAPI,
        files: list[ComfyUIFileResult],
        prompt_id: str,
        job_directory: pathlib.Path,
    ) -> pathlib.Path:
        """Download parsed outputs into this queue job's artifact directory.

        Args:
            api: Connected ComfyUI client used for downloads.
            files: Validated server file descriptors to download.
            prompt_id: Completed prompt identifier used to namespace outputs.
            job_directory: Queue-managed root directory for this job's artifacts.

        Returns:
            Directory that holds every downloaded file for this prompt.

        Raises:
            RuntimeError: If an output filename is unsafe or resolves to a duplicate path.
        """
        output_directory = job_directory / COMFYUI_OUTPUTS_FOLDER / prompt_id
        downloads: list[tuple[ComfyUIFileResult, pathlib.Path]] = []
        destinations: set[pathlib.Path] = set()
        for file_result in files:
            if not is_valid_local_leaf(file_result.filename):
                raise RuntimeError("ComfyUI output does not produce a portable local filename")
            destination = output_directory / file_result.subfolder / file_result.filename
            if destination in destinations:
                raise RuntimeError("ComfyUI outputs resolve to the same local artifact path")
            destinations.add(destination)
            downloads.append((file_result, destination))

        for file_result, destination in downloads:
            file_result.path = await api.download_file(file_result, destination)
        return output_directory

    def _parse_results(
        self,
        history: dict[str, Any],
        prompt_id: str,
        workflow: Workflow,
    ) -> list[ComfyUIFileResult]:
        """Extract exactly one final file for every processable tagged output.

        Args:
            history: ComfyUI execution history keyed by prompt identifier.
            prompt_id: Completed prompt whose declared outputs are parsed.
            workflow: Workflow declaring the exact final output nodes.

        Returns:
            Valid output files in workflow order.

        Raises:
            RuntimeError: If history or a declared output is missing, malformed, unsafe, or duplicated.
        """
        if not isinstance(history, dict) or not isinstance(history.get(prompt_id), dict):
            raise RuntimeError("Invalid ComfyUI history response")
        outputs = history[prompt_id].get("outputs")
        if not isinstance(outputs, dict):
            raise RuntimeError("Invalid ComfyUI history response")
        output_specs = [
            spec
            for spec in sorted(workflow.output_specs, key=lambda value: value.order)
            if spec.remix_type in {RemixType.TEXTURE_FILE_PATH, RemixType.MESH_FILE_PATH}
        ]
        if not output_specs:
            raise RuntimeError("ComfyUI workflow does not declare processable output nodes")

        results: list[ComfyUIFileResult] = []
        for output_spec in output_specs:
            node_output = outputs.get(output_spec.node_id)
            output_label = output_spec.texture_type or "mesh"
            if not isinstance(node_output, dict):
                raise RuntimeError(f"ComfyUI did not produce a final file for declared output '{output_label}'")
            channel = "images" if output_spec.remix_type is RemixType.TEXTURE_FILE_PATH else "3d"
            channel_values = node_output.get(channel, [])
            if not isinstance(channel_values, list):
                raise RuntimeError("Invalid ComfyUI history response")
            final_files = []
            for file_info in channel_values:
                if not isinstance(file_info, dict):
                    raise RuntimeError("Invalid ComfyUI history response")
                if file_info.get("type") == "output":
                    final_files.append(file_info)
            if not final_files:
                raise RuntimeError(f"ComfyUI did not produce a final file for declared output '{output_label}'")
            if len(final_files) != 1:
                raise RuntimeError(
                    f"ComfyUI produced multiple final files for declared output '{output_label}'; "
                    "exactly one is required"
                )
            filename = final_files[0].get("filename")
            subfolder = final_files[0].get("subfolder", "")
            if not self._is_safe_server_path(filename, subfolder):
                raise RuntimeError("Invalid ComfyUI history response")
            results.append(
                ComfyUIFileResult(
                    filename=filename,
                    key=output_spec.node_id,
                    remix_type=output_spec.remix_type,
                    order=output_spec.order,
                    subfolder=subfolder,
                    texture_type=output_spec.texture_type,
                )
            )
        return results

    @staticmethod
    def _is_safe_server_path(filename: Any, subfolder: Any) -> bool:
        """Return whether server-controlled output fields form a safe relative path.

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


@dataclasses.dataclass
class ComfyUIAssetJob(ComfyUIJob):
    """Generate one mesh and its optional textures for the asset pipeline."""

    MESH_REQUEST: ClassVar[JobOutputPort[MeshOptimizationRequest]] = JobOutputPort(
        "mesh_request", MeshOptimizationRequest
    )
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = (MESH_REQUEST,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Download one asset and return its mesh optimization request."""
        request = inputs[self.WORKFLOW_REQUEST]
        files, _ = await self._generate_files(job_directory, request, progress_callback)
        mesh_files = [item for item in files if item.remix_type is RemixType.MESH_FILE_PATH]
        if len(mesh_files) != 1 or mesh_files[0].path is None:
            error = RuntimeError("ComfyUI asset workflows require one downloaded mesh output")
            raise JobExecutionError("RTX Remix could not prepare the generated mesh.", error) from error
        mesh_path = mesh_files[0].path
        return JobOutputs(
            {
                self.MESH_REQUEST: MeshOptimizationRequest(
                    source_path=mesh_path,
                    source_root=mesh_path.parent,
                    output_url=_child_url(request.output_url, COMFYUI_ASSET_OUTPUT_FOLDER),
                    extra_textures=self._make_texture_items(files),
                ),
            }
        )

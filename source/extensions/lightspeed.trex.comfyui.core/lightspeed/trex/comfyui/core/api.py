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

__all__ = ["ComfyUIAPI", "ComfyUIImageResult"]

import asyncio
import dataclasses
import mimetypes
import pathlib
import tempfile
from time import monotonic
from typing import Any
from urllib.parse import quote

from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
from omni import client
from omni.flux.utils.common.omni_url import OmniUrl
from PIL import Image
from requests import RequestException, Response, request

from .enums import WorkflowCategory, WorkflowSourceType
from .url import build_url, is_valid_local_leaf


def _is_valid_workflow_name(name: object) -> bool:
    """Check whether a workflow name is safe as one encoded URL path segment.

    Args:
        name: Candidate workflow name.

    Returns:
        True if the name is a portable local path segment.
    """
    return isinstance(name, str) and is_valid_local_leaf(name)


def _convert_dds_to_png(source_path: str, destination_path: str) -> None:
    """Convert one DDS input to a temporary PNG outside the owner event loop.

    Args:
        source_path: Local path to the source DDS image.
        destination_path: Local path where the PNG is written.
    """
    with Image.open(source_path) as image:
        image.save(destination_path, "PNG")


def _write_download(destination: pathlib.Path, response: Response) -> None:
    """Stream one downloaded response outside the owner event loop.

    Args:
        destination: Local path where the response body is written.
        response: Streaming HTTP response to consume and close.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as output:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    output.write(chunk)
    finally:
        response.close()


@dataclasses.dataclass
class ComfyUIImageResult:
    """Describe one declared texture output from a ComfyUI execution."""

    filename: str
    texture_type: str
    order: int = 0
    subfolder: str = ""
    path: pathlib.Path | None = None


class ComfyUIAPI:
    """Access workflow, prompt, and image endpoints on a ComfyUI server."""

    def __init__(self, scheme: str, host: str, port: int):
        """Initialize a client for one ComfyUI endpoint.

        Args:
            scheme: HTTP URL scheme for the server.
            host: Server hostname or IP address.
            port: Server TCP port.

        Raises:
            ValueError: If any endpoint component is invalid.
        """
        self._base_url = build_url(scheme, host, port)

    @property
    def base_url(self) -> str:
        """Return the normalized base URL for the ComfyUI server.

        Returns:
            Server URL without an API endpoint path.
        """
        return self._base_url

    async def _request(self, method: str, endpoint: str, **kwargs) -> Response:
        """Send one bounded HTTP request and normalize transport failures.

        Args:
            method: HTTP method for the request.
            endpoint: API endpoint path relative to the server base URL.
            **kwargs: Additional arguments forwarded to ``requests.request``.

        Returns:
            Successful HTTP response.

        Raises:
            RuntimeError: If the request fails or returns an HTTP error status.
        """
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        kwargs.setdefault("timeout", 30.0)

        try:
            response = await run_in_worker_thread(request, method, f"{self._base_url}{endpoint}", **kwargs)
            response.raise_for_status()
            return response
        except RequestException as exc:
            raise RuntimeError(f"ComfyUI request failed: {exc}") from exc

    async def _send_request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any] | list[Any]:
        """Send one JSON request and validate the top-level response type.

        Args:
            method: HTTP method for the request.
            endpoint: API endpoint path relative to the server base URL.
            **kwargs: Additional arguments forwarded to the HTTP request.

        Returns:
            Decoded JSON object or array.

        Raises:
            RuntimeError: If the request fails or the response is not a JSON object or array.
        """
        response = await self._request(method, endpoint, **kwargs)
        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError("Invalid ComfyUI JSON response") from exc
        if not isinstance(result, (dict, list)):
            raise RuntimeError("Invalid ComfyUI JSON response")
        return result

    async def ping(self) -> dict[str, Any]:
        """Check server health through the system statistics endpoint.

        Returns:
            Server system statistics.

        Raises:
            RuntimeError: If the request fails or the response is not an object.
        """
        result = await self._send_request("GET", "/system_stats")
        if not isinstance(result, dict):
            raise RuntimeError("Invalid ComfyUI system_stats response")
        return result

    async def get_workflow_list(self) -> list[tuple[WorkflowCategory, WorkflowSourceType, str]]:
        """Fetch available workflows from the rtx-remix endpoint.

        Returns:
            List of ``(category, source_type, name)`` tuples.

        Raises:
            RuntimeError: If the request fails or the workflow catalog is malformed.
        """
        result = await self._send_request("GET", "/rtx-remix/v1/workflows")
        if not isinstance(result, dict):
            raise RuntimeError("Invalid ComfyUI workflows response")
        results: list[tuple[WorkflowCategory, WorkflowSourceType, str]] = []
        all_workflows = result.get("workflows", {})
        if not isinstance(all_workflows, dict):
            raise RuntimeError("Invalid ComfyUI workflows response")
        for cat_str, sources in all_workflows.items():
            if not isinstance(sources, dict):
                continue
            try:
                category = WorkflowCategory(cat_str)
            except ValueError:
                continue
            for src_str, workflow_infos in sources.items():
                if not isinstance(workflow_infos, list):
                    continue
                try:
                    source_type = WorkflowSourceType(src_str)
                except ValueError:
                    continue
                for info in workflow_infos:
                    if isinstance(info, dict) and _is_valid_workflow_name(info.get("name")):
                        results.append((category, source_type, info["name"]))
        return results

    async def get_workflow_data(
        self,
        source_type: WorkflowSourceType,
        name: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch the API prompt and full graph for a workflow.

        Args:
            source_type: Where the workflow originates.
            name: Workflow name.

        Returns:
            API prompt data and the corresponding full graph data.

        Raises:
            RuntimeError: If either request fails or returns malformed workflow data.
            ValueError: If the workflow name is not a safe path segment.
        """
        api_workflow = await self._fetch_workflow(WorkflowCategory.API, source_type, name)
        full_workflow = await self._fetch_workflow(WorkflowCategory.FULL, source_type, name)
        return api_workflow, full_workflow

    async def _fetch_workflow(
        self,
        category: WorkflowCategory,
        source_type: WorkflowSourceType,
        name: str,
    ) -> dict[str, Any]:
        """Fetch one workflow category and validate its object payload.

        Args:
            category: Workflow representation to fetch.
            source_type: Where the workflow originates.
            name: Workflow name.

        Returns:
            Workflow data from the response payload.

        Raises:
            RuntimeError: If the request fails or returns malformed workflow data.
            ValueError: If the workflow name is not a safe path segment.
        """
        if not _is_valid_workflow_name(name):
            raise ValueError(f"Invalid ComfyUI workflow name: {name!r}")
        result = await self._send_request(
            "GET",
            f"/rtx-remix/v1/workflows/{category.value}/{source_type.value}/{quote(name, safe='')}",
        )
        if not isinstance(result, dict):
            raise RuntimeError("Invalid ComfyUI workflow data response")
        data = result.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("Invalid ComfyUI workflow data response")
        return data

    async def upload_image(self, file_path: str, *, subfolder: str = "") -> dict[str, Any]:
        """Upload an image file to the ComfyUI server.

        Args:
            file_path: Local or Omniverse path to the image to upload.
            subfolder: Server input subfolder used to isolate this job's files.

        Returns:
            Validated server metadata for the uploaded input image.

        Raises:
            OSError: If the input cannot be localized, read, converted, or cleaned up.
            RuntimeError: If the request fails or returns malformed upload metadata.
        """
        source_url = OmniUrl(file_path)
        upload_filename = source_url.name
        with tempfile.TemporaryDirectory() as temporary_directory:
            upload_path = file_path
            if client.break_url(file_path).scheme:
                upload_path = str(pathlib.Path(temporary_directory) / f"input{source_url.suffix}")
                copy_result = await client.copy_async(file_path, upload_path, client.CopyBehavior.OVERWRITE)
                if copy_result != client.Result.OK:
                    raise OSError(f"Cannot localize ComfyUI input {file_path}: {copy_result}")

            if source_url.suffix.lower() == ".dds":
                converted_path = str(pathlib.Path(temporary_directory) / "converted.png")
                await run_in_worker_thread(_convert_dds_to_png, upload_path, converted_path)
                upload_path = converted_path
                upload_filename = f"{source_url.stem}.png"

            mime_type = mimetypes.guess_type(upload_filename)[0] or "application/octet-stream"
            with open(upload_path, "rb") as file_handle:
                result = await self._send_request(
                    "POST",
                    "/upload/image",
                    data={"overwrite": "true", "subfolder": subfolder, "type": "input"},
                    files={"image": (upload_filename, file_handle, mime_type)},
                )

        if (
            not isinstance(result, dict)
            or not isinstance(result.get("name"), str)
            or not result["name"]
            or not isinstance(result.get("subfolder", ""), str)
            or result.get("type") != "input"
        ):
            raise RuntimeError("Invalid ComfyUI upload response")
        return result

    async def download_image(
        self,
        image: ComfyUIImageResult,
        destination: pathlib.Path,
    ) -> pathlib.Path:
        """Download one typed output image to an explicit local artifact path.

        Args:
            image: Server image metadata returned in prompt history.
            destination: Exact local output path.

        Returns:
            The written destination path.

        Raises:
            OSError: If the destination cannot be written.
            RuntimeError: If the download request fails.
        """
        response = await self._request(
            "GET",
            "/view",
            params={"filename": image.filename, "subfolder": image.subfolder, "type": "output"},
            stream=True,
        )
        await run_in_worker_thread(_write_download, destination, response)
        return destination

    async def submit_prompt(
        self,
        prompt: dict[str, Any],
        client_id: str,
        *,
        extra_data: dict[str, Any] | None = None,
    ) -> str:
        """Submit a prompt and return its server-assigned identifier.

        Args:
            prompt: Workflow prompt payload to execute.
            client_id: Unique identifier for the client session.
            extra_data: Optional metadata to include with the prompt.

        Returns:
            Server-assigned prompt identifier.

        Raises:
            RuntimeError: If the request fails or returns an invalid prompt identifier.
        """
        request_data = {"prompt": prompt, "client_id": client_id}
        if extra_data is not None:
            request_data["extra_data"] = extra_data
        response = await self._send_request("POST", "/prompt", json=request_data)
        if not isinstance(response, dict) or not is_valid_local_leaf(response.get("prompt_id")):
            raise RuntimeError("Invalid ComfyUI prompt response")
        return response["prompt_id"]

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        """Fetch execution history for a prompt.

        Args:
            prompt_id: Server-assigned identifier returned by submit_prompt.

        Returns:
            History response keyed by prompt identifier.

        Raises:
            RuntimeError: If the identifier is invalid or the request returns malformed history.
        """
        if not is_valid_local_leaf(prompt_id):
            raise RuntimeError("Invalid ComfyUI prompt identifier")
        result = await self._send_request("GET", f"/history/{quote(prompt_id, safe='')}")
        if not isinstance(result, dict):
            raise RuntimeError("Invalid ComfyUI history response")
        return result

    async def wait_for_prompt_completion(
        self,
        prompt_id: str,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        """Poll history until a prompt completes and return its history response.

        Args:
            prompt_id: Server-assigned identifier returned by ``submit_prompt``.
            timeout: Maximum seconds to wait for completion.
            poll_interval: Maximum seconds between history requests.

        Returns:
            Completed history response keyed by prompt identifier.

        Raises:
            RuntimeError: If history reports execution failure or contains invalid data.
            TimeoutError: If the prompt does not complete within the timeout.
        """
        deadline = monotonic() + timeout

        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}")
            try:
                history = await asyncio.wait_for(self.get_history(prompt_id), timeout=remaining)
            except TimeoutError as exc:
                raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}") from exc
            entry = history.get(prompt_id)
            if isinstance(entry, dict):
                self._raise_for_failed_history(prompt_id, entry)
                status = entry.get("status", {})
                if isinstance(status, dict) and status.get("completed") is True:
                    return history

            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}")
            sleep_for = min(poll_interval, remaining)
            await asyncio.sleep(sleep_for)

    @staticmethod
    def _raise_for_failed_history(prompt_id: str, entry: dict[str, Any]) -> None:
        """Raise when a prompt history entry reports execution failure.

        Args:
            prompt_id: Server-assigned prompt identifier.
            entry: History entry for the prompt.

        Raises:
            RuntimeError: If the history entry reports an execution failure.
        """
        status = entry.get("status", {})
        if not isinstance(status, dict):
            return

        messages = status.get("messages", [])
        if not isinstance(messages, (list, tuple)):
            messages = []
        for message in messages:
            if not isinstance(message, (list, tuple)) or len(message) < 2:
                continue
            message_type = message[0]
            if message_type in ("execution_error", "execution_interrupted"):
                raise RuntimeError(f"ComfyUI execution failed for prompt {prompt_id}: {message[1]}")

        status_str = status.get("status_str")
        if status_str == "error":
            raise RuntimeError(f"ComfyUI execution failed for prompt {prompt_id}: {status}")

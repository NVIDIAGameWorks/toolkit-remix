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

import base64
import copy
import dataclasses
import enum
import json
import mimetypes
import os
import pathlib
import socket
import struct
import tempfile
import threading
import urllib.parse
import uuid
from collections.abc import Callable, Iterator
from typing import Any, Generic, Literal, TypeVar

import carb
import requests
from omni.flux.utils.common import Event, EventSubscription
from PIL import Image
from pxr import Usd

from .settings import get_comfy_url, set_comfy_url

T = TypeVar("T")


_comfy_interface: ComfyInterface | None = None


TYPE_MAP = {
    "str": str,
    "pathlib.Path": pathlib.Path,
    "bool": bool,
    "int": int,
    "float": float,
}


class ConnectionState(enum.Enum):
    """Connection state for the ComfyUI server."""

    CONNECTED = ("Disconnect", "Connected")  # (button_text, status_text)
    DISCONNECTED = ("Connect", "Disconnected")

    @property
    def button_text(self) -> str:
        """Text for the connect/disconnect button."""
        return self.value[0]

    @property
    def status_text(self) -> str:
        """Text describing the current connection status."""
        return self.value[1]


@dataclasses.dataclass
class Field(Generic[T]):
    name: str
    native_type: type
    default_value: T
    value: T | Callable[[Usd.Prim], T]
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Workflow:
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    name: str = dataclasses.field(default="Workflow")
    inputs: list[Field] = dataclasses.field(default_factory=list)
    # Output metadata keyed by node_id - just raw dicts from the workflow JSON
    output_metadata: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)

    @property
    def outputs(self) -> list[str]:
        """List of output node IDs (for backwards compatibility)."""
        return list(self.output_metadata.keys())

    def get_output_metadata(self, node_id: str) -> dict[str, Any] | None:
        """Get output metadata for a specific node ID."""
        return self.output_metadata.get(node_id)

    @classmethod
    def from_dict(cls, data: dict[str, Any], name: str = "Workflow") -> Workflow:
        """
        Return an instance of Workflow with inputs and outputs generated from metadata within `data`.

        Example JSON structure for a node with remix metadata:

          "143": {
            "inputs": {
              "image": "metalwall065f.png"
            },
            "class_type": "LoadImage",
            "_meta": {
              "title": "Load Your Image",
              "rtx-remix": {
                "inputs": {
                  "image": {
                    "name": "Texture",
                    "type": "str",
                    "remix_type": "texture_file_path",
                    "order": 0,
                    "additional_data": {
                      "tooltip": "Input texture file to be processed by the workflow",
                      "group": ""
                    }
                  }
                }
              }
            }
          }

        Example output node:

          "1332": {
            "inputs": { ... },
            "class_type": "RTXRemixSaveTexture",
            "_meta": {
              "title": "RTX Remix Save Texture",
              "rtx-remix": {
                "output": {
                  "name": "albedo",
                  "type": "str",
                  "remix_type": "texture_file_path",
                  "order": 2,
                  "additional_data": {
                    "texture_type": "albedo",
                    "tooltip": "...",
                    "group": ""
                  }
                }
              }
            }
          }
        """

        fields = []
        output_metadata: dict[str, dict[str, Any]] = {}

        for node_id, node in data.items():
            meta = node.get("_meta")
            if not meta:
                continue
            remix = meta.get("rtx-remix")
            if not remix:
                continue

            # Process output metadata
            output = remix.get("output")
            if output:
                # Flatten all output metadata into one dict
                node_output_meta = dict(output)  # Copy top-level keys
                # Merge additional_data if present
                if "additional_data" in node_output_meta:
                    additional = node_output_meta.pop("additional_data")
                    node_output_meta.update(additional)
                # Store keyed by node_id
                output_metadata[node_id] = node_output_meta

            # Process input metadata
            inputs = remix.get("inputs")
            if not inputs:
                continue

            for port_name, node_data in inputs.items():
                metadata = {
                    "port_id": f"{node_id}.inputs.{port_name}",
                    "label": node_data.get("name", port_name),
                    "order": node_data.get("order", 0),
                }
                if "additional_data" in node_data:
                    metadata.update(node_data["additional_data"])
                type_name = node_data.get("type", "str")
                native_type = TYPE_MAP.get(type_name)
                if native_type is None:
                    carb.log_warn(f"Unsupported workflow input type '{type_name}' for {node_id}.{port_name}; using str")
                    native_type = str
                # TODO: The node-pack has this additional remix_type data which we're using to inform us that this
                #  port is actually for a texture filepath. At the moment, we are only registering LazyValue by
                #  native type and not taking this extra metadata into consideration. When we go to implement other
                #  LazyValue types, we will want to revisit this.
                if native_type is str and node_data.get("remix_type") == "texture_file_path":
                    native_type = pathlib.Path
                value = node["inputs"][port_name]
                field = Field(
                    name=port_name,
                    native_type=native_type,
                    default_value=value,
                    value=value,
                    metadata=metadata,
                )
                fields.append(field)

        return cls(
            data=data,
            name=name,
            inputs=fields,
            output_metadata=output_metadata,
        )

    def upload_and_replace_filepaths(self, subfolder: str, comfy_interface: ComfyInterface):
        """
        Upload any pathlib.Path fields to ComfyUI and update the field value to the uploaded server path.
        """
        for field in self.inputs:
            if isinstance(field.value, pathlib.Path):
                comfy_output = ComfyOutput(
                    filename=field.value.name,
                    subfolder=subfolder,
                    output_type="input",
                )
                carb.log_info(f"Uploading file to ComfyUI: {field.value}")
                new_path = comfy_interface.upload(str(field.value), comfy_output)
                carb.log_info(f"Upload complete. ComfyUI file: {new_path}")
                field.value = new_path

    def get_prompt(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        workflow = copy.deepcopy(self.data)

        for field in self.inputs:
            port_id = field.metadata.get("port_id")
            if port_id is None:
                continue

            parts = port_id.split(".")

            # Navigate to the nested location
            current = workflow
            for part in parts[:-1]:
                if part not in current:
                    raise KeyError(f"Path '{'.'.join(parts[:-1])}' not found in workflow")
                current = current[part]

            # Set the final value
            final_key = parts[-1]
            if not isinstance(current, dict):
                raise TypeError(f"Cannot set '{final_key}' on non-dict type at path '{'.'.join(parts[:-1])}'")

            value = field.value
            if context and isinstance(value, str):
                value = value.format(**context)
            if isinstance(value, pathlib.Path):
                value = value.as_posix()

            current[final_key] = value

        return workflow


class SimpleWebSocket:
    """
    A simple implementation of a WebSocket client using standard libraries.
    """

    HANDSHAKE_TIMEOUT = 10.0
    MAX_HANDSHAKE_RESPONSE_BYTES = 16 * 1024
    HANDSHAKE_READ_SIZE = 4096

    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self._recv_buffer = b""
        self.lock = threading.Lock()

    @classmethod
    def _create_websocket_connection(cls, host: str, port: int, path: str) -> tuple[socket.socket, bytes]:
        sock = socket.create_connection((host, port), timeout=cls.HANDSHAKE_TIMEOUT)

        try:
            # Generate WebSocket key
            key = base64.b64encode(os.urandom(16)).decode("utf-8")

            # Send WebSocket handshake
            handshake = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"\r\n"
            )
            sock.sendall(handshake.encode("utf-8"))

            # Read handshake response
            response = b""
            while b"\r\n\r\n" not in response:
                if len(response) >= cls.MAX_HANDSHAKE_RESPONSE_BYTES:
                    raise ConnectionError("WebSocket handshake response exceeded maximum size")
                remaining = cls.MAX_HANDSHAKE_RESPONSE_BYTES - len(response)
                chunk = sock.recv(min(cls.HANDSHAKE_READ_SIZE, remaining))
                if not chunk:
                    raise ConnectionError("WebSocket connection closed during handshake")
                response += chunk

            header_end = response.index(b"\r\n\r\n") + 4
            recv_buffer = response[header_end:]
        except Exception:
            sock.close()
            raise

        return sock, recv_buffer

    def _recv(self, count: int) -> bytes:
        if not self.sock:
            raise ConnectionError("WebSocket is not connected")
        if self._recv_buffer:
            chunk = self._recv_buffer[:count]
            self._recv_buffer = self._recv_buffer[count:]
            if len(chunk) == count:
                return chunk
            return chunk + self.sock.recv(count - len(chunk))
        return self.sock.recv(count)

    def _recv_exact(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            chunk = self._recv(count - len(data))
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk
        return data

    def _recv_websocket_message(self) -> str:
        fragmented_opcode = None
        fragments: list[bytes] = []

        while True:
            header = self._recv_exact(2)

            fin = bool(header[0] & 0x80)
            opcode = header[0] & 0x0F
            masked = header[1] & 0x80
            payload_len = header[1] & 0x7F

            if payload_len == 126:
                ext_len = self._recv_exact(2)
                payload_len = struct.unpack(">H", ext_len)[0]
            elif payload_len == 127:
                ext_len = self._recv_exact(8)
                payload_len = struct.unpack(">Q", ext_len)[0]

            mask = b""
            if masked:
                mask = self._recv_exact(4)

            # Receive the full payload
            payload = b""
            while len(payload) < payload_len:
                chunk = self._recv(payload_len - len(payload))
                if not chunk:
                    raise ConnectionError("Connection closed while reading payload")
                payload += chunk

            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

            if opcode == 0x1:
                if fin:
                    return payload.decode("utf-8")
                fragmented_opcode = opcode
                fragments = [payload]
                continue
            if opcode == 0x0:
                if fragmented_opcode is None:
                    raise ConnectionError("Unexpected WebSocket continuation frame")
                fragments.append(payload)
                if fin:
                    message = b"".join(fragments)
                    opcode = fragmented_opcode
                    fragmented_opcode = None
                    fragments = []
                    if opcode == 0x1:
                        return message.decode("utf-8")
                continue
            if opcode == 0x8:
                raise ConnectionError("WebSocket closed by server")

    def __iter__(self) -> Iterator[str]:
        while True:
            yield self.recv()

    def __next__(self) -> str:
        return self.recv()

    def __enter__(self) -> SimpleWebSocket:
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def connect(self, url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        if not parsed.netloc:
            parsed = urllib.parse.urlparse(f"http://{url}")

        if parsed.scheme not in ("http", "ws"):
            raise ValueError(f"url is invalid: {url}")

        host = parsed.hostname
        if host is None:
            raise ValueError(f"url is invalid: {url}")
        port = parsed.port or 80

        if parsed.path:
            path = parsed.path
        else:
            path = "/"
        if parsed.query:
            path += f"?{parsed.query}"

        self.sock, self._recv_buffer = self._create_websocket_connection(host, port, path)

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None
        self._recv_buffer = b""

    def settimeout(self, timeout: float) -> None:
        if not self.sock:
            raise ConnectionError("WebSocket is not connected")
        self.sock.settimeout(timeout)

    def recv(self) -> str:
        if not self.sock:
            raise ConnectionError("WebSocket is not connected")
        with self.lock:
            return self._recv_websocket_message()


def get_comfy_interface() -> ComfyInterface:
    """Get the singleton ComfyInterface instance."""
    global _comfy_interface
    if _comfy_interface is None:
        _comfy_interface = ComfyInterface()
    return _comfy_interface


def normalize_url(url: str) -> str:
    if not url.startswith("http"):
        url = "http://" + url
    return url.removesuffix("/")


@dataclasses.dataclass(frozen=True)
class ComfyOutput:
    """
    Represents a file within ComfyUI.
    """

    filename: str
    subfolder: str = ""
    output_type: Literal["output", "temp", "input"] = "output"


class ComfyInterface:
    """
    Client interface for communicating with a ComfyUI server.

    Provides methods for:
    - Submitting workflow prompts
    - Waiting for completion via WebSocket
    - Uploading input files
    - Downloading output files
    - Listing available workflows

    Properties:
        url: The normalized ComfyUI server URL.
        client_id: Unique client identifier for WebSocket subscriptions.
    """

    def __init__(
        self,
        url: str | None = None,
        client_id: str | None = None,
    ) -> None:
        self._url = ""
        if url is None:
            url = get_comfy_url()
        self.set_url(url)

        if client_id is None:
            client_id = uuid.uuid4().hex
        self._client_id = client_id

        self._workflow: Workflow | None = None
        self._connection_state = ConnectionState.DISCONNECTED
        self._on_connected_changed = Event()
        self._on_workflow_changed = Event()

    @property
    def url(self) -> str:
        """Get the ComfyUI server URL."""
        return self._url

    @property
    def client_id(self) -> str:
        """Get the client ID."""
        return self._client_id

    @property
    def workflow(self) -> Workflow | None:
        """Get the currently selected workflow."""
        return self._workflow

    @property
    def connection_state(self) -> ConnectionState:
        """Get the connection state."""
        return self._connection_state

    @property
    def connected(self) -> bool:
        """Get whether the interface is connected (convenience property)."""
        return self._connection_state == ConnectionState.CONNECTED

    def set_url(self, url: str) -> None:
        """Set a normalized ComfyUI server URL and save it to settings."""
        self._url = normalize_url(url)
        set_comfy_url(self._url)

    def set_workflow(self, workflow: Workflow | None) -> None:
        """Set the currently selected workflow and fire event if changed."""
        if self._workflow != workflow:
            self._workflow = workflow
            self._on_workflow_changed(workflow)

    def set_connected(self, state: ConnectionState) -> None:
        """
        Set the connection state and fire event if changed.

        When disconnecting, automatically clears the workflow to ensure consistent state.

        Args:
            state: The new connection state
        """
        if self._connection_state != state:
            self._connection_state = state
            # Clear workflow when disconnecting to ensure consistent state
            if state == ConnectionState.DISCONNECTED:
                self.set_workflow(None)
            self._on_connected_changed(state)

    def submit(self, prompt: dict[str, Any], extra_data: dict[str, Any] | None = None) -> str:
        """
        Submit a workflow to the ComfyUI server and return the prompt_id.
        """
        data = {
            "client_id": self.client_id,
            "prompt": prompt,
        }
        if extra_data:
            data["extra_data"] = extra_data

        res = requests.post(f"{self.url}/prompt", json=data)
        res.raise_for_status()
        result = res.json()
        return result["prompt_id"]

    def wait_for_complete(self, ws: SimpleWebSocket, prompt_id: str) -> None:
        """
        Wait for a prompt workflow to complete. The provided SimpleWebSocket should be connected *before* the prompt
        is submitted.
        """
        try:
            while True:
                raw = ws.recv()
                if isinstance(raw, str):
                    try:
                        message = json.loads(raw)
                    except json.decoder.JSONDecodeError:
                        carb.log_warn(f"Received non-JSON ComfyUI WebSocket message: {raw[:200]}")
                        continue

                    if not isinstance(message, dict):
                        carb.log_warn(f"Received unexpected ComfyUI WebSocket message: {message!r}")
                        continue

                    msg_type = message.get("type")
                    data = message.get("data", {})

                    # Check for completion via executing message
                    if msg_type == "executing" and data.get("node") is None and data.get("prompt_id") == prompt_id:
                        return

                    if msg_type == "execution_success" and data.get("prompt_id") == prompt_id:
                        return
                    if msg_type == "execution_error" and data.get("prompt_id") == prompt_id:
                        raise RuntimeError(f"ComfyUI execution error for prompt {prompt_id}: {data}")
                    if msg_type == "execution_interrupted" and data.get("prompt_id") == prompt_id:
                        raise RuntimeError(f"ComfyUI execution interrupted for prompt {prompt_id}: {data}")
        finally:
            ws.close()

    def iter_outputs(self, prompt_id) -> Iterator[tuple[str, ComfyOutput]]:
        """
        Using the ComfyUI server history API, iterate over all output images for the given prompt_id.
        """
        res = requests.get(f"{self.url}/history/{prompt_id}")
        res.raise_for_status()
        all_history = res.json()
        prompt_history = all_history.get(prompt_id)

        if prompt_history is None:
            raise ValueError(f"No history found for prompt_id {prompt_id}")

        for node_id, node_output in prompt_history["outputs"].items():
            if "images" in node_output:
                for image in node_output["images"]:
                    if image["type"] == "output":
                        yield (
                            node_id,
                            ComfyOutput(
                                filename=image["filename"],
                                subfolder=image["subfolder"],
                                output_type=image["type"],
                            ),
                        )

    def execute(
        self,
        prompt: dict[str, Any],
        extra_data: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> tuple[str, dict[str, list[ComfyOutput]]]:
        """
        Execute a prompt workflow, wait for completion, and return the prompt ID plus output images by node ID.
        """
        with SimpleWebSocket() as ws:
            ws.connect(f"{self.url}/ws?clientId={self.client_id}")
            ws.settimeout(timeout)

            prompt_id = self.submit(prompt, extra_data=extra_data)
            self.wait_for_complete(ws, prompt_id)
            outputs: dict[str, list[ComfyOutput]] = {}
            for node_id, output in self.iter_outputs(prompt_id):
                outputs.setdefault(node_id, []).append(output)
            return prompt_id, outputs

    def download(self, directory: pathlib.Path, output: ComfyOutput) -> pathlib.Path:
        """
        Download output data using the ComfyUI server API.
        """
        params = {
            "filename": output.filename,
            "subfolder": output.subfolder,
            "type": output.output_type,
        }
        res = requests.get(f"{self.url}/view", params=params)
        res.raise_for_status()

        output_path = directory / output.subfolder / output.filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as f:
            f.write(res.content)
        return output_path

    def upload(self, filepath: str, output: ComfyOutput) -> str:
        """
        Upload a file using the ComfyUI server API.

        Args:
            filepath (str): Path to the file to be uploaded.
            output (ComfyOutput): Specifies where the file should be uploaded to.
        """
        if output.output_type != "input":
            raise ValueError("Can only upload to input")

        # Track if we created a temp file
        temp_filepath = None
        filename = output.filename

        # Convert DDS to PNG due to an issue where ComfyUI will use a ton of VRAM
        if filepath.lower().endswith(".dds"):
            # Create a temporary PNG file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")  # noqa PLR1732
            temp_filepath = temp_file.name
            temp_file.close()

            # Save as PNG
            with Image.open(filepath) as img:
                img.save(temp_filepath, "PNG")
            filepath = temp_filepath

            # Update filename to PNG
            filename = pathlib.Path(output.filename).stem + ".png"

        try:
            # Determine mimetype based on file extension
            mimetype, _ = mimetypes.guess_type(filename)
            if not mimetype:
                mimetype = "application/octet-stream"

            with open(filepath, "rb") as f:
                res = requests.post(
                    f"{self.url}/upload/image",
                    data={
                        "overwrite": "true",
                        "subfolder": output.subfolder,
                        "type": output.output_type,
                    },
                    files={"image": (filename, f, mimetype)},
                )
            res.raise_for_status()

            if output.subfolder:
                return f"{output.subfolder}/{filename}"
            return filename
        finally:
            # Clean up temp file if we created one
            if temp_filepath and os.path.exists(temp_filepath):
                os.unlink(temp_filepath)

    def stats(self) -> dict[str, Any]:
        """
        Get stats about the comfy server.
        """
        res = requests.get(f"{self.url}/system_stats")
        res.raise_for_status()
        return res.json()

    def is_alive(self) -> bool:
        try:
            self.stats()
        except requests.RequestException:
            return False
        return True

    def get_workflows(self) -> dict[str, Any]:
        """
        Get workflows exported from the comfyui-rtx_remix node pack. This also includes workflows that are shipped
        with the nodepack.

        See: https://github.com/NVIDIAGameWorks/ComfyUI-RTX-Remix
        """
        res = requests.get(f"{self.url}/rtx-remix/v1/workflows")
        res.raise_for_status()
        return res.json()

    def get_api_workflows(self) -> list[tuple[str, str]]:
        results = []
        response = self.get_workflows()
        api_workflows = response["workflows"]["api"]
        for source_type, workflow_infos in api_workflows.items():
            for workflow_info in workflow_infos:
                results.append((source_type, workflow_info["name"]))
        return results

    def get_workflow_data(self, source_type: str, workflow_name: str) -> dict[str, Any]:
        res = requests.get(f"{self.url}/rtx-remix/v1/workflows/api/{source_type}/{workflow_name}")
        res.raise_for_status()
        response_data = res.json()
        return response_data["data"]

    def subscribe_connected_changed(self, callback: Callable[[ConnectionState], None]) -> EventSubscription:
        """
        Subscribe to connection state changes.

        Args:
            callback: Function to call when connection state changes

        Returns:
            Subscription object that will automatically unsubscribe when destroyed
        """
        return EventSubscription(self._on_connected_changed, callback)

    def subscribe_workflow_changed(self, callback: Callable[[Workflow | None], None]) -> EventSubscription:
        """
        Subscribe to workflow changes.

        Args:
            callback: Function to call when workflow changes

        Returns:
            Subscription object that will automatically unsubscribe when destroyed
        """
        return EventSubscription(self._on_workflow_changed, callback)

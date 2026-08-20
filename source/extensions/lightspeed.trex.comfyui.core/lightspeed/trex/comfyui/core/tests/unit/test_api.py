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

import asyncio
import pathlib
import threading
from unittest.mock import AsyncMock, MagicMock, call, mock_open, patch

from lightspeed.trex.comfyui.core.api import ComfyUIAPI, ComfyUIImageResult, _convert_dds_to_png
from lightspeed.trex.comfyui.core.enums import WorkflowCategory, WorkflowSourceType, WorkflowType
from lightspeed.trex.comfyui.core.models import Workflow, WorkflowTypeCategory, WorkflowTypeOption
from omni import client
from omni.kit.test import AsyncTestCase


class TestComfyUIAPI(AsyncTestCase):
    """Test ComfyUI HTTP request, response, and polling behavior."""

    async def test_send_request_sets_socket_timeout(self):
        """Every HTTP request has a finite connect/read timeout."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        response = MagicMock()
        response.json.return_value = {}

        # Act
        with patch("lightspeed.trex.comfyui.core.api.request", return_value=response) as request:
            await api._send_request("GET", "/system_stats")

        # Assert
        self.assertGreater(request.call_args.kwargs["timeout"], 0)

    async def test_send_request_runs_blocking_http_off_the_event_loop(self):
        """HTTP transport runs in a worker thread before response validation."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        response = MagicMock()

        async def run_in_thread(function, *args, **kwargs):
            """Run a blocking callable inline for deterministic async testing.

            Args:
                function: Callable to execute.
                *args: Positional arguments forwarded to the callable.
                **kwargs: Keyword arguments forwarded to the callable.

            Returns:
                The callable's result.
            """
            return function(*args, **kwargs)

        with (
            patch("lightspeed.trex.comfyui.core.api.request", return_value=response) as request,
            patch(
                "lightspeed.trex.comfyui.core.api.run_in_worker_thread", AsyncMock(side_effect=run_in_thread)
            ) as run_in_worker_thread,
        ):
            # Act
            result = await api._request("GET", "/system_stats")

        # Assert
        self.assertIs(result, response)
        run_in_worker_thread.assert_awaited_once()
        self.assertIs(run_in_worker_thread.await_args.args[0], request)
        response.raise_for_status.assert_called_once_with()

    async def test_request_waits_for_blocking_transport_before_propagating_cancellation(self):
        """Cancellation cannot close request-owned resources while the worker still uses them."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        started = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        def blocking_request(*_args, **_kwargs):
            """Block the mock HTTP request until the test releases it.

            Args:
                *_args: Ignored positional request arguments.
                **_kwargs: Ignored keyword request arguments.

            Returns:
                A mock HTTP response.
            """
            loop.call_soon_threadsafe(started.set)
            release.wait()
            return MagicMock()

        with patch("lightspeed.trex.comfyui.core.api.request", side_effect=blocking_request):
            task = asyncio.create_task(api._request("GET", "/system_stats"))
            await started.wait()

            # Act
            task.cancel()
            await asyncio.sleep(0)

            # Assert
            try:
                self.assertFalse(task.done())
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_upload_dds_converts_and_preserves_server_location(self):
        """DDS uploads use PNG data and explicit ComfyUI input location fields."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(
            return_value={"name": "source.png", "subfolder": "rtx-remix/job-1", "type": "input"}
        )

        temporary_directory = MagicMock()
        temporary_directory.__enter__.return_value = "C:/temp"
        converted_path = str(pathlib.Path("C:/temp") / "converted.png")
        converted_image = MagicMock()
        with (
            patch("lightspeed.trex.comfyui.core.api.tempfile.TemporaryDirectory", return_value=temporary_directory),
            patch("lightspeed.trex.comfyui.core.api.Image.open") as image_open,
            patch("builtins.open", mock_open()),
            patch(
                "lightspeed.trex.comfyui.core.api.run_in_worker_thread",
                AsyncMock(side_effect=lambda function, *args: function(*args)),
            ) as run_in_worker_thread,
        ):
            image_open.return_value.__enter__.return_value = converted_image
            # Act
            result = await api.upload_image("C:/textures/source.dds", subfolder="rtx-remix/job-1")

        # Assert
        request_call = api._send_request.await_args
        self.assertEqual(
            request_call.kwargs["data"],
            {"overwrite": "true", "subfolder": "rtx-remix/job-1", "type": "input"},
        )
        self.assertEqual(request_call.kwargs["files"]["image"][0], "source.png")
        self.assertEqual(result, {"name": "source.png", "subfolder": "rtx-remix/job-1", "type": "input"})
        converted_image.save.assert_called_once_with(converted_path, "PNG")
        run_in_worker_thread.assert_any_await(_convert_dds_to_png, "C:/textures/source.dds", converted_path)
        temporary_directory.__exit__.assert_called_once()

    async def test_upload_localizes_omniverse_input(self):
        """Nucleus-hosted workflow inputs are copied locally before HTTP upload."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(
            return_value={"name": "albedo.png", "subfolder": "rtx-remix/job-1", "type": "input"}
        )
        temporary_directory = MagicMock()
        temporary_directory.__enter__.return_value = "C:/temp"
        localized_path = str(pathlib.Path("C:/temp") / "input.png")
        file_handle = mock_open()

        # Act
        with (
            patch("lightspeed.trex.comfyui.core.api.tempfile.TemporaryDirectory", return_value=temporary_directory),
            patch(
                "lightspeed.trex.comfyui.core.api.client.copy_async", AsyncMock(return_value=client.Result.OK)
            ) as copy,
            patch("builtins.open", file_handle),
        ):
            result = await api.upload_image(
                "omniverse://server/Projects/Scene/albedo.png",
                subfolder="rtx-remix/job-1",
            )

        # Assert
        copy.assert_awaited_once_with(
            "omniverse://server/Projects/Scene/albedo.png",
            localized_path,
            client.CopyBehavior.OVERWRITE,
        )
        self.assertEqual(api._send_request.await_args.kwargs["files"]["image"][0], "albedo.png")
        self.assertEqual(result["name"], "albedo.png")
        temporary_directory.__exit__.assert_called_once()

    async def test_upload_dds_cleans_temporary_directory_when_conversion_fails(self):
        """A failed DDS conversion cleans its temporary directory."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        temporary_directory = MagicMock()
        temporary_directory.__enter__.return_value = "C:/temp"
        with (
            patch("lightspeed.trex.comfyui.core.api.tempfile.TemporaryDirectory", return_value=temporary_directory),
            patch("lightspeed.trex.comfyui.core.api.Image.open", side_effect=OSError("conversion failed")),
            self.assertRaises(OSError) as error,
        ):
            # Act
            await api.upload_image("C:/textures/invalid.dds")

        # Assert
        self.assertIn("conversion failed", str(error.exception))
        temporary_directory.__exit__.assert_called_once()

    async def test_workflow_list_rejects_malformed_nested_payload(self):
        """Malformed workflow containers fail with a normalized response error."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(return_value={"workflows": []})

        # Act
        with self.assertRaises(RuntimeError) as error:
            await api.get_workflow_list()

        # Assert
        self.assertIn("Invalid ComfyUI workflows response", str(error.exception))

    async def test_workflow_names_reject_dot_path_segments(self):
        """Dot-segment workflow names cannot escape their category route."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock()

        for name in (".", ".."):
            with self.subTest(name=name):
                # Act
                with self.assertRaises(ValueError) as error:
                    await api._fetch_workflow(WorkflowCategory.API, WorkflowSourceType.USER, name)

                # Assert
                self.assertIn("Invalid ComfyUI workflow name", str(error.exception))
        api._send_request.assert_not_awaited()

    async def test_submit_prompt_preserves_output_namespace_metadata(self):
        """Prompt requests retain the RTX Remix output namespace."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(return_value={"prompt_id": "prompt-123"})
        extra_data = {"extra_pnginfo": {"rtx-remix": {"subfolder": "rtx-remix/job-1"}}}

        # Act
        result = await api.submit_prompt({"1": {}}, "client-1", extra_data=extra_data)

        # Assert
        self.assertEqual(result, "prompt-123")
        api._send_request.assert_awaited_once_with(
            "POST",
            "/prompt",
            json={"prompt": {"1": {}}, "client_id": "client-1", "extra_data": extra_data},
        )

    async def test_submit_prompt_rejects_unsafe_identifier(self):
        """A server prompt identifier cannot escape the local artifact directory."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(return_value={"prompt_id": "../outside"})

        # Act
        with self.assertRaises(RuntimeError) as error:
            await api.submit_prompt({}, "client-1")

        # Assert
        self.assertIn("Invalid ComfyUI prompt response", str(error.exception))

    async def test_prompt_id_rejects_nonportable_local_leaf(self):
        """Prompt identifiers must be portable local directory names."""
        # Arrange
        unsafe_prompt_ids = ("prompt?#", 'prompt"', "CON", "name.", "name ", "x" * 256)

        for prompt_id in unsafe_prompt_ids:
            with self.subTest(prompt_id=prompt_id):
                api = ComfyUIAPI("http", "127.0.0.1", 8188)
                api._send_request = AsyncMock(return_value={"prompt_id": prompt_id})

                # Act
                with self.assertRaises(RuntimeError) as error:
                    await api.submit_prompt({}, "client-1")

                # Assert
                self.assertIn("Invalid ComfyUI prompt response", str(error.exception))

    async def test_prompt_id_is_encoded_as_one_url_segment(self):
        """A valid prompt identifier cannot alter its history URL segment."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(return_value={})

        # Act
        await api.get_history("prompt +@")

        # Assert
        api._send_request.assert_awaited_once_with("GET", "/history/prompt%20%2B%40")

    async def test_download_image_writes_typed_output(self):
        """A typed image result downloads to the requested local artifact path."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        response = MagicMock()
        response.iter_content.return_value = (b"image-", b"bytes")
        api._request = AsyncMock(return_value=response)
        image = ComfyUIImageResult(filename="result.png", texture_type="albedo", subfolder="nested")
        destination = pathlib.Path("C:/jobs/result.png")

        with (
            patch.object(pathlib.Path, "mkdir") as mkdir,
            patch.object(pathlib.Path, "open", mock_open()) as open_file,
            patch(
                "lightspeed.trex.comfyui.core.api.run_in_worker_thread",
                AsyncMock(side_effect=lambda function, *args: function(*args)),
            ) as run_in_worker_thread,
        ):
            # Act
            result = await api.download_image(image, destination)

        # Assert
        self.assertEqual(result, destination)
        mkdir.assert_called_once_with(parents=True, exist_ok=True)
        open_file.assert_called_once_with("wb")
        self.assertEqual(
            open_file().write.call_args_list,
            [call(b"image-"), call(b"bytes")],
        )
        response.close.assert_called_once_with()
        run_in_worker_thread.assert_awaited_once()
        api._request.assert_awaited_once_with(
            "GET",
            "/view",
            params={"filename": "result.png", "subfolder": "nested", "type": "output"},
            stream=True,
        )

    async def test_ping_returns_system_stats(self):
        """System stats accepts dictionary responses from ComfyUI."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(return_value={"system": {"os": "test"}})

        # Act
        result = await api.ping()

        # Assert
        self.assertEqual(result, {"system": {"os": "test"}})

    async def test_get_workflow_list_filters_invalid_entries(self):
        """Workflow listing ignores malformed and unknown category/source entries."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(
            return_value={
                "workflows": {
                    "api": {
                        "rtx-remix": [
                            {"name": "material"},
                            {"name": "folder/workflow"},
                            {"name": "."},
                            {"missing": "name"},
                        ],
                        "invalid-source": [{"name": "ignored"}],
                    },
                    "full": {
                        "user": [{"name": "custom"}],
                        "rtx-remix": "not-a-list",
                    },
                    "invalid-category": {
                        "rtx-remix": [{"name": "ignored"}],
                    },
                    "api-but-not-dict": "ignored",
                }
            }
        )

        # Act
        result = await api.get_workflow_list()

        # Assert
        self.assertEqual(
            result,
            [
                Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.RTX_REMIX, name="material"),
                Workflow(category=WorkflowCategory.FULL, source_type=WorkflowSourceType.USER, name="custom"),
            ],
        )

    async def test_get_workflow_list_parses_entry_metadata(self):
        """Workflow listing resolves display metadata from complete catalog entries."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(
            return_value={
                "workflows": {
                    "api": {
                        "rtx-remix": [
                            {
                                "name": "material",
                                "path": "material.json",
                                "size": 1024,
                                "modified": 123.4,
                                "displayName": "Material Generation",
                                "description": "Generates a PBR material.",
                                "workflowType": "Material Generation",
                            }
                        ]
                    }
                }
            }
        )

        # Act
        result = await api.get_workflow_list()

        # Assert
        self.assertEqual(len(result), 1)
        workflow = result[0]
        self.assertEqual(workflow.name, "material")
        self.assertIs(workflow.category, WorkflowCategory.API)
        self.assertIs(workflow.source_type, WorkflowSourceType.RTX_REMIX)
        self.assertEqual(workflow.display_name, "Material Generation")
        self.assertEqual(workflow.description, "Generates a PBR material.")
        self.assertIs(workflow.workflow_type, WorkflowType.MATERIAL_GENERATION)
        self.assertEqual(workflow.api, {})

    async def test_get_workflow_types_parses_categories_with_descriptions(self):
        """Type listing parses the documented categories payload into ordered options."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(
            return_value={
                "success": True,
                "categories": [
                    {
                        "name": "Generation",
                        "types": [
                            {"value": "Asset Generation", "description": "Server description of the asset type."},
                            {"value": "Material Generation", "description": "Server description of the material type."},
                        ],
                    },
                    {"name": "Other", "types": [{"value": "Other", "description": "Anything else."}]},
                ],
            }
        )

        # Act
        result = await api.get_workflow_types()

        # Assert
        self.assertEqual(
            result,
            [
                WorkflowTypeCategory(
                    name="Generation",
                    types=(
                        WorkflowTypeOption(WorkflowType.ASSET_GENERATION, "Server description of the asset type."),
                        WorkflowTypeOption(
                            WorkflowType.MATERIAL_GENERATION, "Server description of the material type."
                        ),
                    ),
                ),
                WorkflowTypeCategory(name="Other", types=(WorkflowTypeOption(WorkflowType.OTHER, "Anything else."),)),
            ],
        )
        api._send_request.assert_awaited_once_with("GET", "/rtx-remix/v1/workflows/types")

    async def test_get_workflow_types_returns_empty_list_for_non_dict_response(self):
        """A non-object response yields no category instead of raising."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(return_value=["not", "a", "dict"])

        # Act
        result = await api.get_workflow_types()

        # Assert
        self.assertEqual(result, [])

    async def test_get_workflow_data_fetches_api_and_full_snapshot(self):
        """Default workflow fetch returns API prompt and full graph from one snapshot request path."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(
            side_effect=[
                {"data": {"api": "prompt"}},
                {"data": {"full": "graph"}},
            ]
        )

        # Act
        result = await api.get_workflow_data(WorkflowSourceType.RTX_REMIX, "workflow")

        # Assert
        self.assertEqual(result, ({"api": "prompt"}, {"full": "graph"}))

    async def test_workflow_name_is_encoded_as_one_url_segment(self):
        """Portable workflow names retain spaces and Unicode through URL encoding."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(return_value={"data": {}})

        # Act
        await api.get_workflow_data(
            WorkflowSourceType.USER,
            "My α Workflow",
        )

        # Assert
        self.assertEqual(
            api._send_request.await_args_list,
            [
                call("GET", "/rtx-remix/v1/workflows/api/user/My%20%CE%B1%20Workflow"),
                call("GET", "/rtx-remix/v1/workflows/full/user/My%20%CE%B1%20Workflow"),
            ],
        )

    async def test_get_workflow_data_raises_on_missing_data(self):
        """Malformed workflow responses should keep normalized RuntimeError handling."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api._send_request = AsyncMock(return_value={"unexpected": {}})

        # Act
        with self.assertRaises(RuntimeError) as exception:
            await api.get_workflow_data(
                WorkflowSourceType.RTX_REMIX,
                "workflow",
            )

        # Assert
        self.assertIsInstance(exception.exception, RuntimeError)

    async def test_wait_for_prompt_completion_polls_until_history_is_ready(self):
        """Prompt completion returns history once the prompt appears with outputs."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        responses = [
            {},
            {
                "prompt-123": {
                    "outputs": {
                        "99": {"images": [{"filename": "output.png"}]},
                    },
                    "status": {"completed": True, "status_str": "success"},
                },
            },
        ]

        async def mock_history(_prompt_id):
            """Return the next staged history response.

            Args:
                _prompt_id: Prompt identifier ignored by the staged response.

            Returns:
                The next staged history response.
            """
            return responses.pop(0)

        api.get_history = mock_history

        # Act
        history = await api.wait_for_prompt_completion("prompt-123", timeout=1, poll_interval=0)

        # Assert
        self.assertIn("prompt-123", history)

    async def test_wait_for_prompt_completion_ignores_partial_outputs_until_completed(self):
        """Partial output history should not complete until ComfyUI reports completion."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        responses = [
            {
                "prompt-123": {
                    "outputs": {
                        "99": {"images": [{"filename": "partial.png"}]},
                    },
                    "status": {"completed": False, "status_str": "running"},
                },
            },
            {
                "prompt-123": {
                    "outputs": {
                        "99": {"images": [{"filename": "output.png"}]},
                    },
                    "status": {"completed": True, "status_str": "success"},
                },
            },
        ]

        async def mock_history(_prompt_id):
            """Return the next staged history response.

            Args:
                _prompt_id: Prompt identifier ignored by the staged response.

            Returns:
                The next staged history response.
            """
            return responses.pop(0)

        api.get_history = mock_history

        # Act
        history = await api.wait_for_prompt_completion("prompt-123", timeout=1, poll_interval=0)

        # Assert
        self.assertIn("prompt-123", history)
        self.assertFalse(responses)

    async def test_wait_for_prompt_completion_raises_on_execution_error(self):
        """History status errors should fail the job instead of looking successful."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)

        async def mock_history(_prompt_id):
            """Return a failed execution history response.

            Args:
                _prompt_id: Prompt identifier ignored by the fixed response.

            Returns:
                History containing a completed execution error.
            """
            return {
                "prompt-123": {
                    "outputs": {},
                    "status": {
                        "completed": True,
                        "status_str": "error",
                        "messages": [
                            [
                                "execution_error",
                                {
                                    "prompt_id": "prompt-123",
                                    "exception_message": "node failed",
                                },
                            ],
                        ],
                    },
                },
            }

        api.get_history = mock_history

        # Act
        with self.assertRaises(RuntimeError) as exception:
            await api.wait_for_prompt_completion("prompt-123", timeout=1, poll_interval=0)

        # Assert
        self.assertIn("node failed", str(exception.exception))

    async def test_wait_for_prompt_completion_raises_on_execution_interrupted(self):
        """Interrupted history messages should fail the job instead of looking successful."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)

        async def mock_history(_prompt_id):
            """Return an interrupted execution history response.

            Args:
                _prompt_id: Prompt identifier ignored by the fixed response.

            Returns:
                History containing an interrupted execution error.
            """
            return {
                "prompt-123": {
                    "outputs": {},
                    "status": {
                        "completed": True,
                        "status_str": "error",
                        "messages": [
                            [
                                "execution_interrupted",
                                {
                                    "prompt_id": "prompt-123",
                                    "exception_message": "user interrupted",
                                },
                            ],
                        ],
                    },
                },
            }

        api.get_history = mock_history

        # Act
        with self.assertRaises(RuntimeError) as exception:
            await api.wait_for_prompt_completion("prompt-123", timeout=1, poll_interval=0)

        # Assert
        self.assertIn("user interrupted", str(exception.exception))

    async def test_wait_for_prompt_completion_handles_malformed_messages(self):
        """Malformed optional messages do not hide an explicit error status."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)
        api.get_history = AsyncMock(
            return_value={
                "prompt-123": {
                    "outputs": {},
                    "status": {"completed": True, "status_str": "error", "messages": None},
                }
            }
        )

        # Act
        with self.assertRaises(RuntimeError) as exception:
            await api.wait_for_prompt_completion("prompt-123", timeout=1, poll_interval=0)

        # Assert
        self.assertIn("prompt-123", str(exception.exception))

    async def test_wait_for_prompt_completion_times_out(self):
        """Missing history eventually times out."""
        # Arrange
        api = ComfyUIAPI("http", "127.0.0.1", 8188)

        api.get_history = AsyncMock(return_value={})

        # Act
        with (
            patch("lightspeed.trex.comfyui.core.api.monotonic", side_effect=(0.0, 0.0, 2.0)),
            self.assertRaises(TimeoutError) as exception,
        ):
            await api.wait_for_prompt_completion("prompt-123", timeout=1, poll_interval=0)

        # Assert
        self.assertIsInstance(exception.exception, TimeoutError)
        api.get_history.assert_awaited_once_with("prompt-123")

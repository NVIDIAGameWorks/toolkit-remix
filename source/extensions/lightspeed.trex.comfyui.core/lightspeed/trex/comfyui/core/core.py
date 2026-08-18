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

__all__ = [
    "ComfyUICore",
    "ComfyUIRetargetState",
    "ComfyUISubmission",
    "ComfyUISubmissionResult",
]

import asyncio
import dataclasses
import math
import pathlib
import uuid
from collections.abc import Callable, Iterable, Iterator
from copy import deepcopy
from typing import Any

import carb
from lightspeed.common.constants import REMIX_INGESTED_ASSETS_FOLDER
from lightspeed.trex.asset_pipeline.core.job import TextureProcessingJob
from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.core.enums import JobState
from omni.flux.job_queue.core.errors import QueueSubmissionError
from omni.flux.job_queue.core.job import ApplyBinding, JobGraph
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.common.materials import get_materials_from_prim_paths
from omni.flux.utils.common.progress import INDETERMINATE_PROGRESS_TOTAL, run_worker_with_latest_progress
from omni.usd import get_context
from pxr import Sdf, Tf, Usd, UsdGeom, UsdShade

from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore

from .api import ComfyUIAPI
from .connection import get_connected_endpoint, set_connected_endpoint
from .enums import (
    ComfyUIEventType,
    ComfyUIOperation,
    ComfyUIRetargetResult,
    ComfyUIState,
    RemixType,
    WorkflowCategory,
    WorkflowSourceType,
)
from .events import publish_comfyui_event
from .apply_handler import ComfyUIJobApplyHandler
from .job import ComfyUIJob
from .maps import OUTPUT_TEXTURE_TYPE_MAP
from .models import ComfyUIApplyTarget, ComfyUIWorkflowRequest, Workflow
from .prompt import set_prompt_value
from .resolvers import ResolverConfigurationError, ResolverValueError, StageExpandingResolver
from .settings import ComfyUISettings
from .url import Endpoint, build_url, canonical_endpoint


@dataclasses.dataclass(frozen=True, slots=True)
class ComfyUISubmission:
    """Carry the exact graphs prepared for one user submission.

    Attributes:
        graphs: Independently submitted material graphs in deterministic order.
        skipped_count: Graphs whose generation job was prepared as skipped.
    """

    graphs: tuple[JobGraph, ...]
    skipped_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class ComfyUISubmissionResult:
    """Report the exact outcome of one prepared submission.

    Attributes:
        submitted_count: Graphs durably accepted by the queue.
        failed_count: Graphs that were rejected or not attempted after cancellation or shutdown.
    """

    submitted_count: int
    failed_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class ComfyUIRetargetState:
    """Describe the state needed to render Retarget.

    Attributes:
        is_queued: Whether the generation job can still be edited.
        saved_endpoint: Endpoint persisted with the generation job, if valid.
        connected_endpoint: Endpoint currently connected for this USD context, if any.
    """

    is_queued: bool
    saved_endpoint: Endpoint | None
    connected_endpoint: Endpoint | None

    @property
    def can_retarget(self) -> bool:
        """Return whether the job can move to the current connection."""
        return self.is_queued and self.connected_endpoint is not None and self.saved_endpoint != self.connected_endpoint


def _normalize_json_value(value: Any) -> Any:
    """Return a JSON-compatible copy of a resolved workflow value.

    Args:
        value: Resolved workflow value to normalize.

    Returns:
        Equivalent value composed only of JSON-compatible types.

    Raises:
        TypeError: If a dictionary key is not a string or a value type is unsupported.
        ValueError: If a floating-point value is not finite.
    """
    if isinstance(value, pathlib.Path):
        return value.as_posix()
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Workflow input dictionaries must use string keys")
        return {key: _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Workflow input numbers must be finite")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"Workflow input value is not JSON serializable: {type(value).__name__}")


def _get_processed_texture_output_url(stage: Usd.Stage, job_id: uuid.UUID) -> str | None:
    """Build the durable destination for one material's processed textures.

    Args:
        stage: Live stage whose root determines project-owned versus queue-owned publication.
        job_id: Stable generation job identifier.

    Returns:
        URI-safe project destination, or ``None`` when the anonymous stage requires queue-owned output.
    """
    root_layer = stage.GetRootLayer()
    if root_layer.anonymous:
        return None
    project_path = str(root_layer.identifier)
    project_directory = OmniUrl(OmniUrl(project_path).parent_url)
    return str(project_directory / REMIX_INGESTED_ASSETS_FOLDER / "comfyui" / str(job_id))


def _get_workflow_status_message(error: BaseException) -> str:
    """Return user-facing guidance for a failed workflow load.

    Args:
        error: Workflow failure retained in the log for technical diagnosis.

    Returns:
        Plain-language recovery guidance that does not expose exception details.
    """
    if isinstance(error, asyncio.CancelledError):
        return "Workflow loading was canceled. Select the workflow to try again."
    if isinstance(error, (TypeError, ValueError, KeyError)):
        return (
            "ComfyUI returned workflow information that RTX Remix could not read. "
            "Update the RTX Remix ComfyUI nodes and try again."
        )
    return "The workflow could not be loaded. Select it again or reconnect to ComfyUI."


def _get_texture_label(texture_type: str) -> str:
    """Return a plain-language texture type label.

    Args:
        texture_type: Workflow texture type identifier.

    Returns:
        Lowercase label without identifier separators or a redundant texture suffix.
    """
    return texture_type.removesuffix("_texture").replace("_", " ").strip().lower() or "texture"


class ComfyUICore:
    """Control ComfyUI workflow discovery and job preparation for one USD context.

    Connects to a running external ComfyUI server.
    """

    def __init__(
        self,
        context_name: str,
        *,
        settings_changed_callback: Callable[[str, object], None] | None = None,
    ):
        """Initialize the ComfyUI runtime for one USD context.

        Args:
            context_name: USD context this runtime operates on.
            settings_changed_callback: Optional process-wide settings change observer.

        Raises:
            ValueError: If ``context_name`` is None.
        """
        if context_name is None:
            raise ValueError("context_name must be provided explicitly")
        self._context_name = context_name
        self._settings = ComfyUISettings(
            settings_changed_callback=settings_changed_callback or self.handle_settings_changed,
        )

        self._workflow: Workflow | None = None
        self._available_workflows: list[tuple[WorkflowCategory, WorkflowSourceType, str]] = []
        self._status_message = ""
        self._last_connection_error = ""
        self._client_id = str(uuid.uuid4())
        self._connect_generation = 0
        self._workflow_discovery_generation = 0
        self._workflow_load_generation = 0
        self._workflow_base_url: str | None = None
        self._connected_base_url: str | None = None
        self._active_operation: ComfyUIOperation | None = None
        self._destroyed = False

        self._state = ComfyUIState.READY
        self._objects_changed_subscription = Tf.Notice.Register(
            Usd.Notice.ObjectsChanged,
            self._on_objects_changed,
            None,
        )

    @property
    def context_name(self) -> str:
        """Return the USD context name this instance operates on.

        Returns:
            USD context name supplied during initialization.
        """
        return self._context_name

    def _on_objects_changed(self, notice, stage) -> None:
        """Publish this core's context when authored visibility changes.

        Args:
            notice: USD ObjectsChanged-compatible notice.
            stage: Stage that emitted the notice.
        """
        if stage != get_context(self._context_name).get_stage():
            return
        paths = (*notice.GetChangedInfoOnlyPaths(), *notice.GetResyncedPaths())
        if any(path.IsPropertyPath() and path.name == UsdGeom.Tokens.visibility for path in paths):
            publish_comfyui_event(self._context_name, ComfyUIEventType.STAGE_VISIBILITY_CHANGED)

    @property
    def state(self) -> ComfyUIState:
        """Return the current lifecycle state of the ComfyUI connection.

        Returns:
            Current connection lifecycle state.
        """
        return self._state

    @property
    def workflow(self) -> Workflow | None:
        """Return the currently selected workflow.

        Returns:
            Selected workflow, or None when no workflow is active.
        """
        return self._workflow

    @property
    def status_message(self) -> str:
        """Return the human-readable message describing the current state.

        Returns:
            Status detail associated with the latest state transition.
        """
        return self._status_message

    @property
    def last_connection_error(self) -> str:
        """Return technical details from the current failed connection attempt.

        Returns:
            Exact connection exception, or an empty string outside the current error state.
        """
        return self._last_connection_error

    @property
    def settings(self) -> ComfyUISettings:
        """Return the connection and server settings facade.

        Returns:
            Settings facade owned by this runtime.
        """
        return self._settings

    @property
    def is_ready(self) -> bool:
        """Check whether the current endpoint is connected with a workflow selected.

        Returns:
            True if jobs can be prepared against the current endpoint.
        """
        return self._workflow is not None and self._is_current_runtime_endpoint()

    @property
    def is_connected(self) -> bool:
        """Check whether RUNNING state belongs to the configured endpoint.

        Returns:
            True if the active connection matches current settings.
        """
        return self._state == ComfyUIState.RUNNING and self._connected_base_url == self.base_url

    @property
    def available_workflows(self) -> list[tuple[WorkflowCategory, WorkflowSourceType, str]]:
        """Return a snapshot of the last successfully fetched workflow catalog.

        Returns:
            ``(category, source_type, name)`` tuples safe for caller mutation.
        """
        return list(self._available_workflows)

    @property
    def base_url(self) -> str:
        """Return the server URL derived from current connection settings.

        Returns:
            Normalized ComfyUI server base URL.
        """
        return build_url(self._settings.protocol.scheme, self._settings.host, self._settings.port)

    @property
    def api(self) -> ComfyUIAPI:
        """Create an API client for current connection settings.

        Returns:
            New client bound to the configured endpoint.
        """
        return ComfyUIAPI(self._settings.protocol.scheme, self._settings.host, self._settings.port)

    def set_workflow(self, value: Workflow | None) -> None:
        """Commit a workflow, invalidating any older in-flight load.

        Args:
            value: Workflow to select, or None to clear the selection.

        Raises:
            RuntimeError: If extension shutdown invalidated this runtime.
        """
        self._ensure_active()
        self._workflow_load_generation += 1
        self._publish_workflow(value)

    def _publish_workflow(self, value: Workflow | None) -> None:
        """Commit a workflow without invalidating the load that owns it.

        Args:
            value: Workflow to publish, or None to clear the selection.

        Raises:
            RuntimeError: If a subscriber invalidates this runtime during publication.
        """
        self._workflow = value
        self._workflow_base_url = None
        publish_comfyui_event(self._context_name, ComfyUIEventType.WORKFLOW_CHANGED, {"workflow": value})
        self._ensure_active()

    async def fetch_available_workflows(self) -> list[tuple[WorkflowCategory, WorkflowSourceType, str]]:
        """Fetch available workflows from the ComfyUI server.

        Calls the /rtx-remix/v1/workflows endpoint via api.get_workflow_list().
        Returns API and full workflow categories from RTX Remix and user sources.
        Current results update the internal cache and emit WORKFLOWS_LOADED.
        Results made stale by newer discovery, shutdown, or endpoint changes are
        rejected. A callback that changes the endpoint after publication causes
        the previous cache to be restored.

        Returns:
            Current workflow catalog after stale-result handling.

        Raises:
            RuntimeError: If the runtime is destroyed or the server response is invalid.
        """
        self._ensure_active()
        self._workflow_discovery_generation += 1
        generation = self._workflow_discovery_generation
        api = self.api
        previous_workflows = self.available_workflows
        try:
            workflows = await self._request_available_workflows(api)
        except RuntimeError:
            if (
                not self._destroyed
                and generation == self._workflow_discovery_generation
                and api.base_url != self.base_url
            ):
                self._set_state(ComfyUIState.READY)
            raise
        self._ensure_active()
        if self._stop_stale_discovery(generation, api, previous_workflows):
            self._ensure_active()
            return self.available_workflows
        self._restore_available_workflows(workflows, notify=True)
        published = self.available_workflows
        self._ensure_active()
        if self._stop_stale_discovery(generation, api, previous_workflows, published=True):
            self._ensure_active()
            return self.available_workflows
        return published

    async def _request_available_workflows(
        self, api: ComfyUIAPI
    ) -> list[tuple[WorkflowCategory, WorkflowSourceType, str]]:
        """Request workflows through a client captured by the caller.

        Args:
            api: Client bound to the endpoint that owns the discovery request.

        Returns:
            Workflow tuples returned by the server.

        Raises:
            RuntimeError: If the request or response is invalid.
        """
        try:
            return await api.get_workflow_list()
        except RuntimeError as error:
            carb.log_warn(f"Failed to fetch workflows: {error}")
            raise

    def _restore_available_workflows(
        self,
        workflows: list[tuple[WorkflowCategory, WorkflowSourceType, str]],
        *,
        notify: bool,
    ) -> None:
        """Restore a workflow-list snapshot and optionally notify subscribers.

        Args:
            workflows: Workflow catalog snapshot to restore.
            notify: Whether to emit a workflows-loaded event.
        """
        self._available_workflows = list(workflows)
        if notify:
            publish_comfyui_event(
                self._context_name,
                ComfyUIEventType.WORKFLOWS_LOADED,
                {
                    "workflows": self.available_workflows,
                },
            )

    async def load_workflow(self, source_type: WorkflowSourceType, name: str) -> None:
        """Fetch a workflow's data from the server and set it as the active workflow.

        A load only commits while it remains the newest request for the captured
        endpoint. Endpoint changes restore READY without committing stale data;
        current request and parse failures are rolled back and propagated.

        Args:
            source_type: Where the workflow originates.
            name: The workflow name.

        Raises:
            asyncio.CancelledError: If the workflow-loading task is cancelled.
            RuntimeError: The core is destroyed or workflow loading fails.
            TypeError: Returned workflow or preset values have invalid types.
            ValueError: Returned workflow data is invalid.
            KeyError: Required workflow data is missing.
        """
        self._ensure_active()
        self._workflow_load_generation += 1
        generation = self._workflow_load_generation
        self._publish_workflow(None)
        self._ensure_active()
        if generation != self._workflow_load_generation:
            return
        api = self.api
        try:
            api_workflow, full_workflow = await api.get_workflow_data(source_type, name)
            workflow = Workflow.from_litegraph_dict(
                api_workflow,
                full_workflow=full_workflow,
                name=name,
                context_name=self._context_name,
            )
            workflow.source_type = source_type
            workflow.category = WorkflowCategory.API
        except asyncio.CancelledError as error:
            self._handle_workflow_load_failure(error, generation, api, workflow_published=False)
            raise
        except (RuntimeError, TypeError, ValueError, KeyError) as error:
            self._handle_workflow_load_failure(error, generation, api, workflow_published=False)
            raise

        self._ensure_active()
        if generation != self._workflow_load_generation:
            return
        if api.base_url != self.base_url:
            self._set_state(ComfyUIState.READY)
            self._ensure_active()
            return
        self._status_message = ""
        try:
            self._publish_workflow(workflow)
            self._ensure_active()
            if generation != self._workflow_load_generation:
                return
            if self._workflow is not workflow:
                return
            if api.base_url != self.base_url:
                self._publish_workflow(None)
                self._ensure_active()
                self._set_state(ComfyUIState.READY)
                self._ensure_active()
                return
            self._workflow_base_url = api.base_url
        except (RuntimeError, asyncio.CancelledError) as error:
            self._handle_workflow_load_failure(error, generation, api, workflow_published=True)
            raise

    def _handle_workflow_load_failure(
        self,
        failure: BaseException,
        generation: int,
        api: ComfyUIAPI,
        *,
        workflow_published: bool,
    ) -> None:
        """Roll back a failed current workflow load.

        Args:
            failure: Exception that interrupted workflow loading.
            generation: Generation owned by the failed load.
            api: Client bound to the endpoint used by the failed load.
            workflow_published: Whether the failed load published its workflow.
        """
        if self._destroyed or generation != self._workflow_load_generation:
            return
        endpoint_changed = api.base_url != self.base_url
        if workflow_published or not endpoint_changed:
            self._publish_workflow(None)
        if self._destroyed or generation != self._workflow_load_generation:
            return
        endpoint_changed = api.base_url != self.base_url
        if endpoint_changed:
            self._set_state(ComfyUIState.READY)
        else:
            self._set_state(self._state, _get_workflow_status_message(failure))

    async def shutdown(self) -> None:
        """Disconnect from the external ComfyUI server."""
        if self._destroyed:
            return
        self._connect_generation += 1
        self._workflow_discovery_generation += 1
        self._workflow_load_generation += 1
        self.set_workflow(None)
        if self._destroyed:
            return
        self._set_state(ComfyUIState.READY)

    async def prepare_jobs(
        self,
        prim_paths: list[str] | None = None,
        progress: Callable[[int, int, Any], Any] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[JobGraph]:
        """Build one material graph for review against the current ComfyUI endpoint.

        Listing and graph preparation run on a worker thread so the UI stays responsive; ``progress``
        reports listing progress on the main thread and ``is_cancelled`` lets the caller abort it.

        Args:
            prim_paths: Explicit selection snapshot, or the current USD selection when omitted.
            progress: Optional callback receiving current count, total count, and a status message.
            is_cancelled: Optional callback returning whether the caller requested cancellation.

        Returns:
            One two-stage graph per unique selected material, or an empty list when cancelled.

        Raises:
            RuntimeError: Preparation overlaps another operation or the current endpoint is unavailable.
        """
        self._ensure_active()
        self._begin_operation(ComfyUIOperation.JOB_PREPARATION)
        try:
            needs_connect = not self._is_current_runtime_endpoint()
            if needs_connect:
                await self.connect()
                if self._state != ComfyUIState.RUNNING or self._connected_base_url != self.base_url:
                    raise RuntimeError("Could not connect to the current ComfyUI endpoint")

            graphs = await self._create_job_graphs(prim_paths=prim_paths, progress=progress, is_cancelled=is_cancelled)
            self._ensure_active()
            if not self._is_current_runtime_endpoint():
                raise RuntimeError("Cannot prepare jobs without a current ComfyUI endpoint")
            return graphs
        finally:
            self._finish_operation()

    async def prepare_submission(
        self,
        prim_paths: list[str] | None = None,
        progress: Callable[[int, int, Any], Any] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> ComfyUISubmission:
        """Prepare exact material graphs and the state needed for UI confirmation.

        Args:
            prim_paths: Explicit selection snapshot, or the current USD selection when omitted.
            progress: Optional callback receiving current count, total count, and a status message.
            is_cancelled: Optional callback returning whether the caller requested cancellation.

        Returns:
            Prepared submission returned to the requesting UI for confirmation. Empty when cancelled.
        """
        graphs = tuple(await self.prepare_jobs(prim_paths=prim_paths, progress=progress, is_cancelled=is_cancelled))
        skipped_count = sum(graph.jobs[0].skip_reason is not None for graph in graphs)
        return ComfyUISubmission(graphs, skipped_count)

    async def submit_prepared_submission(
        self,
        submission: ComfyUISubmission,
    ) -> ComfyUISubmissionResult:
        """Add every prepared material graph to the queue in one transaction.

        The whole batch is persisted in a single off-thread transaction that emits one structural
        change, so a subscribed job queue widget rebuilds once for the batch instead of once per
        graph. Submission is all-or-nothing: if the transaction fails, no graphs are added.

        Args:
            submission: Exact core-prepared submission accepted by the user.

        Returns:
            Exact successful and failed graph counts.

        Raises:
            RuntimeError: If extension shutdown invalidated this runtime.
        """
        self._ensure_active()
        self._begin_operation(ComfyUIOperation.QUEUE_SUBMISSION)
        try:
            graphs = submission.graphs
            try:
                await run_in_worker_thread(get_job_queue().submit_graphs, graphs)
            except (QueueSubmissionError, RuntimeError) as error:
                carb.log_warn(f"Failed to add ComfyUI material jobs to the queue: {error}")
                return ComfyUISubmissionResult(submitted_count=0, failed_count=len(graphs))
            return ComfyUISubmissionResult(submitted_count=len(graphs), failed_count=0)
        finally:
            self._finish_operation()

    def get_workflow_request(self, job: ComfyUIJob) -> ComfyUIWorkflowRequest:
        """Resolve the exact typed workflow request persisted for a queue job.

        Args:
            job: Queued ComfyUI job whose durable input should be resolved.

        Returns:
            Persisted workflow request used by execution and queue editing.

        Raises:
            RuntimeError: If the job or its request is unavailable or malformed.
            ValueError: If the job belongs to another core context.
        """
        self._ensure_active()
        self._ensure_job_context(job)
        try:
            request = get_job_queue().resolve_job_inputs(job.job_id)[ComfyUIJob.WORKFLOW_REQUEST]
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("The workflow saved with this job is unavailable") from error
        if type(request) is not ComfyUIWorkflowRequest:
            raise RuntimeError("The workflow saved with this job is unavailable")
        return request

    def get_retarget_state(self, job: ComfyUIJob) -> ComfyUIRetargetState:
        """Return queue and endpoint state needed to render Retarget.

        Args:
            job: Queued ComfyUI job whose target should be described.

        Returns:
            Current immutable retarget state.

        Raises:
            RuntimeError: If extension shutdown invalidated this runtime.
            ValueError: If the job belongs to another core context.
        """
        self._ensure_active()
        self._ensure_job_context(job)
        try:
            saved_endpoint = canonical_endpoint(job.scheme, job.host, job.port)
        except ValueError:
            saved_endpoint = None
        return ComfyUIRetargetState(
            is_queued=get_job_queue().get_job_snapshot(job.job_id).state is JobState.QUEUED,
            saved_endpoint=saved_endpoint,
            connected_endpoint=get_connected_endpoint(self._context_name),
        )

    def retarget_job(self, job: ComfyUIJob, endpoint: Endpoint) -> ComfyUIRetargetResult:
        """Atomically persist an endpoint change while a job remains queued.

        Args:
            job: Queued job whose endpoint should be replaced.
            endpoint: Connected endpoint that must still be active when mutation occurs.

        Returns:
            Exact reason the update succeeded or was rejected.

        Raises:
            RuntimeError: If extension shutdown invalidated this runtime.
            ValueError: If the job belongs to another core context or the endpoint is invalid.
        """
        self._ensure_active()
        self._ensure_job_context(job)
        expected_endpoint = canonical_endpoint(*endpoint)
        if get_connected_endpoint(self._context_name) != expected_endpoint:
            return ComfyUIRetargetResult.CONNECTION_CHANGED
        updated_job = deepcopy(job)
        updated_job.scheme, updated_job.host, updated_job.port = expected_endpoint
        if get_job_queue().try_update_queued_job(updated_job):
            return ComfyUIRetargetResult.UPDATED
        return ComfyUIRetargetResult.JOB_STARTED

    def _ensure_job_context(self, job: ComfyUIJob) -> None:
        """Reject queue operations routed through the wrong context core.

        Args:
            job: ComfyUI job whose saved context should match this core.

        Raises:
            ValueError: If the job belongs to another USD context.
        """
        if job.context_name != self._context_name:
            raise ValueError("ComfyUI job belongs to another USD context")

    async def connect(self) -> None:
        """Connect to the currently configured external ComfyUI server.

        Only the newest connection attempt may publish discovery or RUNNING.
        Endpoint changes and callback invalidation roll back to READY; current
        request and callback failures are propagated.

        Raises:
            asyncio.CancelledError: If the connection task is cancelled.
            RuntimeError: The core is destroyed or connection setup fails.
        """
        self._ensure_active()
        self._connect_generation += 1
        self._workflow_discovery_generation += 1
        self._workflow_load_generation += 1
        generation = self._connect_generation
        discovery_generation = self._workflow_discovery_generation
        api: ComfyUIAPI | None = None
        previous_workflows: list[tuple[WorkflowCategory, WorkflowSourceType, str]] | None = None
        try:
            self._set_state(ComfyUIState.STARTING, "Connecting to the configured ComfyUI server.")
            self._ensure_active()
            api = self.api
            if self._workflow_base_url is not None and self._workflow_base_url != api.base_url:
                self.set_workflow(None)
                self._ensure_active()
                if self._stop_stale_connection(generation, discovery_generation, api):
                    self._ensure_active()
                    return
            await api.ping()
            self._ensure_active()
            if self._stop_stale_connection(generation, discovery_generation, api):
                self._ensure_active()
                return
            workflows = await self._request_available_workflows(api)
            self._ensure_active()
            if self._stop_stale_connection(generation, discovery_generation, api):
                self._ensure_active()
                return
            previous_workflows = self.available_workflows
            self._restore_available_workflows(workflows, notify=True)
            self._ensure_active()
            if self._stop_stale_connection(
                generation,
                discovery_generation,
                api,
                previous_workflows,
                published=True,
            ):
                self._ensure_active()
                return
            self._connected_base_url = api.base_url
            self._set_state(ComfyUIState.RUNNING)
            self._ensure_active()
            if self._stop_stale_connection(
                generation,
                discovery_generation,
                api,
                previous_workflows,
                published=True,
            ):
                self._ensure_active()
                return
        except asyncio.CancelledError:
            if not self._destroyed and generation == self._connect_generation:
                if previous_workflows is not None:
                    self._restore_available_workflows(previous_workflows, notify=True)
                if not self._destroyed and generation == self._connect_generation:
                    self._set_state(ComfyUIState.READY)
            raise
        except RuntimeError as error:
            if not self._destroyed and generation == self._connect_generation:
                if previous_workflows is not None:
                    self._restore_available_workflows(previous_workflows, notify=True)
                if not self._destroyed and generation == self._connect_generation:
                    endpoint_changed = api is not None and api.base_url != self.base_url
                    discovery_changed = discovery_generation != self._workflow_discovery_generation
                    if endpoint_changed or discovery_changed:
                        self._set_state(ComfyUIState.READY)
                    else:
                        self._last_connection_error = str(error)
                        self._set_state(
                            ComfyUIState.ERROR,
                            "Could not connect to ComfyUI. "
                            "Check the server address and that ComfyUI is running, then try again.",
                        )
            raise

    def _is_current_runtime_endpoint(self) -> bool:
        """Check whether connection and workflow provenance match current settings.

        Returns:
            True if runtime state belongs to the configured endpoint.
        """
        if not self.is_connected:
            return False
        current_base_url = self.base_url
        return self._workflow_base_url is None or self._workflow_base_url == current_base_url

    def _is_current_discovery(self, generation: int, api: ComfyUIAPI) -> bool:
        """Check whether workflow discovery still owns cache publication.

        Args:
            generation: Generation captured by the discovery request.
            api: Client bound to the discovery endpoint.

        Returns:
            True if no newer discovery or endpoint change superseded the request.
        """
        return generation == self._workflow_discovery_generation and api.base_url == self.base_url

    def _stop_stale_discovery(
        self,
        generation: int,
        api: ComfyUIAPI,
        previous_workflows: list[tuple[WorkflowCategory, WorkflowSourceType, str]],
        *,
        published: bool = False,
    ) -> bool:
        """Reject stale workflow discovery and restore subscriber-visible cache state.

        Args:
            generation: Generation captured by the discovery request.
            api: Client bound to the discovery endpoint.
            previous_workflows: Catalog visible before discovery began.
            published: Whether the stale catalog was already published.

        Returns:
            True if the discovery request is stale and must stop.
        """
        if self._is_current_discovery(generation, api):
            return False
        if generation == self._workflow_discovery_generation:
            self._restore_available_workflows(previous_workflows, notify=published)
            if not self._destroyed and generation == self._workflow_discovery_generation:
                self._set_state(ComfyUIState.READY)
        return True

    def _stop_stale_connection(
        self,
        generation: int,
        discovery_generation: int,
        api: ComfyUIAPI,
        previous_workflows: list[tuple[WorkflowCategory, WorkflowSourceType, str]] | None = None,
        *,
        published: bool = False,
    ) -> bool:
        """Restore disconnected state when callbacks or newer work invalidate a connection.

        Args:
            generation: Generation captured by the connection attempt.
            discovery_generation: Discovery generation owned by the connection attempt.
            api: Client bound to the connection endpoint.
            previous_workflows: Catalog visible before connection discovery began.
            published: Whether the connection's catalog was already published.

        Returns:
            True if the connection attempt is stale and must stop.
        """
        if generation == self._connect_generation and self._is_current_discovery(discovery_generation, api):
            return False
        if generation == self._connect_generation:
            if previous_workflows is not None:
                self._restore_available_workflows(previous_workflows, notify=published)
            if not self._destroyed and generation == self._connect_generation:
                self._set_state(ComfyUIState.READY)
        return True

    def destroy(self) -> None:
        """Invalidate this core so stale references cannot resume work after extension shutdown."""
        if self._destroyed:
            return
        self._destroyed = True
        self._objects_changed_subscription.Revoke()
        self._objects_changed_subscription = None
        self._connect_generation += 1
        self._workflow_discovery_generation += 1
        self._workflow_load_generation += 1
        self._workflow = None
        self._workflow_base_url = None
        self._connected_base_url = None
        self._available_workflows.clear()
        self._set_state(ComfyUIState.READY)
        self._settings.destroy()

    def get_submission_block_reason(self) -> str | None:
        """Return why the current stage cannot create a new material graph.

        Existing queued work is intentionally independent of this check. A live stage is needed only while resolving
        selected materials and capturing the exact root and edit-layer identities that Apply will later validate.

        Returns:
            User-facing guidance, or ``None`` when a live stage is available.
        """
        try:
            self._get_submission_target()
        except RuntimeError as error:
            return str(error)
        return None

    def _get_submission_target(self) -> tuple[Usd.Stage, str, str]:
        """Resolve the live stage identity required to prepare new material graphs.

        Returns:
            Live stage, root-layer identifier, and current edit-layer identifier.

        Raises:
            RuntimeError: If no stage is open.
        """
        stage = get_context(self._context_name).get_stage()
        if stage is None:
            raise RuntimeError(
                "Open a project to select materials for new ComfyUI jobs. Existing queued jobs can continue."
            )
        root_layer = stage.GetRootLayer()
        edit_layer = stage.GetEditTarget().GetLayer()
        return stage, str(root_layer.identifier), str(edit_layer.identifier)

    async def _create_job_graphs(
        self,
        prim_paths: list[str] | None = None,
        progress: Callable[[int, int, Any], Any] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[JobGraph]:
        """Create one generation and processing graph per selected material.

        The stage listing and per-material graph preparation run on a worker thread (they are USD
        reads that mutate nothing) so the UI keeps painting. ``progress`` is invoked on the main
        thread with the latest listing progress and ``is_cancelled`` aborts the listing early.

        Args:
            prim_paths: Explicit selection snapshot, or the current USD selection when omitted.
            progress: Optional callback receiving current count, total count, and a status message.
            is_cancelled: Optional callback returning whether the caller requested cancellation.

        Returns:
            Material graphs containing generation and texture-processing children, or an empty list
            when the caller cancelled the listing.

        Raises:
            RuntimeError: If workflow, stage, saved layers, or eligible materials are unavailable.
        """
        if self._workflow is None:
            raise RuntimeError("No ComfyUI workflow is selected")

        workflow = deepcopy(self._workflow)
        stage, project_path, edit_target_layer = self._get_submission_target()
        context = get_context(self._context_name)
        selected_paths = (
            list(prim_paths) if prim_paths is not None else list(context.get_selection().get_selected_prim_paths())
        )
        stage_resolvers = self._get_stage_expanding_resolvers(workflow)
        endpoint = canonical_endpoint(self._settings.protocol.scheme, self._settings.host, self._settings.port)
        client_id = self._client_id

        def build_graphs(report: Callable[[int, int | None, Any | None], None]) -> list[JobGraph]:
            paths = selected_paths
            if stage_resolvers:
                report(0, INDETERMINATE_PROGRESS_TOTAL, "Listing stage textures...")
                paths = self._stage_expansion_prim_paths(
                    stage,
                    stage_resolvers,
                    report=report,
                    is_cancelled=is_cancelled,
                )
                if is_cancelled is not None and is_cancelled():
                    return []
            candidates = self._get_material_candidates(paths)
            return self._create_job_graphs_for_candidates(
                candidates,
                workflow,
                project_path,
                edit_target_layer,
                endpoint,
                client_id,
                stage=stage,
                report=report,
                is_cancelled=is_cancelled,
            )

        graphs = await run_worker_with_latest_progress(
            build_graphs,
            progress_callback=progress,
            is_cancelled=is_cancelled,
            finish_worker_on_cancel=True,
        )

        if is_cancelled is not None and is_cancelled():
            return []
        if get_context(self._context_name).get_stage() is not stage:
            raise RuntimeError("The project changed while ComfyUI jobs were being prepared. Try again.")
        if not graphs:
            raise RuntimeError("The selection does not contain any materials that can create ComfyUI jobs")

        return graphs

    @staticmethod
    def _get_stage_expanding_resolvers(workflow: Workflow) -> tuple[StageExpandingResolver, ...]:
        """Return the workflow resolvers that expand across the whole stage.

        Args:
            workflow: Detached workflow snapshot inspected by the worker.

        Returns:
            Stage-expanding resolvers in workflow-input order.
        """
        return tuple(
            workflow_input.value
            for workflow_input in workflow.inputs
            if isinstance(workflow_input.value, StageExpandingResolver)
        )

    @staticmethod
    def _stage_expansion_prim_paths(
        stage: Usd.Stage,
        resolvers: tuple[StageExpandingResolver, ...],
        *,
        report: Callable[[int, int | None, Any | None], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Iterator[str]:
        """Stream the de-duplicated seed prim paths from every stage-expanding getter.

        Args:
            stage: Live stage traversed to seed one candidate per matching prim.
            resolvers: Stage-expanding resolvers from the immutable workflow snapshot.
            report: Optional worker-thread callback receiving current count, total count, and status.
            is_cancelled: Optional thread-safe callback returning whether the caller requested cancellation.

        Yields:
            De-duplicated prim paths each stage-expanding getter expands the submission across.
        """
        paths: set[str] = set()
        for resolver in resolvers:
            for prim_path in resolver.iter_stage_prim_paths(stage):
                if is_cancelled is not None and is_cancelled():
                    return
                if prim_path in paths:
                    continue
                paths.add(prim_path)
                if report is not None:
                    report(
                        len(paths),
                        INDETERMINATE_PROGRESS_TOTAL,
                        f"Found {len(paths)} stage texture candidate(s)...",
                    )
                yield prim_path

    def _get_material_candidates(
        self,
        prim_paths: Iterable[str],
    ) -> list[tuple[UsdShade.Material, list[str]]]:
        """Return unique selected materials and every mesh path that owns each material.

        Args:
            prim_paths: Selected prim paths to inspect for bound materials.

        Returns:
            Unique materials paired with their selected owning mesh paths.
        """
        paths = list(dict.fromkeys(prim_paths))
        material_by_path: dict[str, UsdShade.Material] = {}
        for material in get_materials_from_prim_paths(paths, self._context_name):
            if not material:
                continue
            material_prim = material.GetPrim()
            if not material_prim.IsValid():
                continue
            material_by_path.setdefault(str(material_prim.GetPath()), material)

        owners_by_material = self._get_material_owner_paths(paths, set(material_by_path))
        return [
            (material, owners_by_material.get(material_path, []))
            for material_path, material in material_by_path.items()
        ]

    def _get_material_owner_paths(
        self,
        prim_paths: list[str],
        material_paths: set[str],
    ) -> dict[str, list[str]]:
        """Map candidate materials to the selected mesh paths that use them.

        Args:
            prim_paths: Selected prim roots to traverse.
            material_paths: Candidate material paths to include.

        Returns:
            Candidate material paths mapped to unique owning mesh paths.
        """
        stage = get_context(self._context_name).get_stage()
        if stage is None:
            return {}

        owners: dict[str, dict[str, None]] = {material_path: {} for material_path in material_paths}
        predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
        for prim_path in dict.fromkeys(prim_paths):
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                continue
            for candidate in Usd.PrimRange(prim, predicate):
                if not (candidate.IsA(UsdGeom.Mesh) or candidate.IsA(UsdGeom.Subset)):
                    continue
                material, _ = UsdShade.MaterialBindingAPI(candidate).ComputeBoundMaterial()
                if not material:
                    continue
                material_path = str(material.GetPrim().GetPath())
                if material_path not in owners:
                    continue
                owner = candidate.GetParent() if candidate.IsA(UsdGeom.Subset) else candidate
                owner_path = str(owner.GetPath())
                owners[material_path].setdefault(owner_path, None)
        return {material_path: list(owner_paths) for material_path, owner_paths in owners.items()}

    @staticmethod
    def _get_surface_shader_paths(material: UsdShade.Material) -> list[str]:
        """Return unique shader prim paths connected to a material's surface outputs.

        Args:
            material: Material whose surface connections are inspected.

        Returns:
            Connected shader prim paths in surface-output order.
        """
        outputs = list(material.GetSurfaceOutputs())
        if not outputs:
            output = material.GetSurfaceOutput()
            if output:
                outputs = [output]

        shader_paths = []
        for output in outputs:
            for source_info in output.GetConnectedSources()[0]:
                source_prim = source_info.source.GetPrim()
                if source_prim.IsValid() and UsdShade.Shader(source_prim):
                    shader_path = str(source_prim.GetPath())
                    if shader_path not in shader_paths:
                        shader_paths.append(shader_path)
        return shader_paths

    def _capture_texture_targets(self, material: UsdShade.Material, workflow: Workflow) -> dict[str, str]:
        """Capture exactly one valid shader input for every declared workflow output.

        Args:
            material: Material whose shader inputs receive generated textures.
            workflow: Detached workflow snapshot whose outputs are captured.

        Returns:
            Workflow texture types mapped to target shader input paths.

        Raises:
            ValueError: If outputs are missing, unsupported, duplicated, or do not resolve uniquely.
        """
        if not workflow.output_specs:
            raise ValueError("The active workflow does not produce textures.")

        shader_paths = self._get_surface_shader_paths(material)
        replacements_core = TextureReplacementsCore(self._context_name)
        targets: dict[str, str] = {}
        for output in workflow.output_specs:
            texture_label = _get_texture_label(output.texture_type)
            if output.texture_type in targets:
                raise ValueError(f"The active workflow produces more than one {texture_label} texture.")
            texture_type = OUTPUT_TEXTURE_TYPE_MAP.get(output.texture_type)
            if texture_type is None:
                raise ValueError(f"The active workflow uses an unsupported texture type: {texture_label}.")
            input_name = TEXTURE_TYPE_INPUT_MAP.get(texture_type)
            if input_name is None:
                raise ValueError(f"The active workflow uses an unsupported texture type: {texture_label}.")
            candidates = [str(Sdf.Path(shader_path).AppendProperty(input_name)) for shader_path in shader_paths]
            valid_targets = replacements_core.get_valid_texture_inputs(candidates)
            if len(valid_targets) != 1:
                count = len(valid_targets)
                if count == 0:
                    raise ValueError(f"This material does not have a replaceable {texture_label} texture.")
                raise ValueError(
                    f"This material has more than one {texture_label} texture, "
                    "so RTX Remix cannot choose which one to replace."
                )
            target = valid_targets[0]
            if target in targets.values():
                raise ValueError("Two workflow outputs would replace the same material texture.")
            targets[output.texture_type] = target
        return targets

    def _create_job_graphs_for_candidates(
        self,
        candidates: Iterable[tuple[UsdShade.Material, list[str]]],
        workflow: Workflow,
        project_path: str,
        edit_target_layer: str,
        endpoint: Endpoint,
        client_id: str,
        *,
        stage: Usd.Stage | None = None,
        report: Callable[[int, int | None, Any | None], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[JobGraph]:
        """Create one independently resolved two-job graph per material.

        Args:
            candidates: Unique materials and their owning mesh paths.
            workflow: Detached workflow snapshot resolved into every graph.
            project_path: Live root-layer identifier captured before material resolution.
            edit_target_layer: Live edit-layer identifier captured before material resolution.
            endpoint: ComfyUI endpoint captured before worker execution.
            client_id: ComfyUI client identifier captured before worker execution.
            stage: Live stage used to choose project-owned or queue-owned texture publication.
            report: Optional worker-thread callback receiving current count, total count, and status.
            is_cancelled: Optional callback returning whether the caller requested cancellation.

        Returns:
            One executable or skipped generation-processing graph per material.

        """
        target_stage = stage or get_context(self._context_name).get_stage()
        if target_stage is None:
            raise RuntimeError("The stage used to prepare this ComfyUI submission is no longer open")
        candidates = list(candidates)
        total = len(candidates)
        graphs: list[JobGraph] = []
        for index, (material, owner_paths) in enumerate(candidates):
            if is_cancelled is not None and is_cancelled():
                break
            if report is not None:
                report(index, total, f"Preparing job {index + 1} of {total}...")
            material_prim = material.GetPrim()
            material_path = str(material_prim.GetPath())
            resolved: dict[str, Any] = {}
            skip_reason = None
            exclude_candidate = False
            for workflow_input in workflow.inputs:
                resolver = workflow_input.value
                try:
                    value = resolver(material_prim)
                except ResolverConfigurationError:
                    raise
                except ResolverValueError as error:
                    if isinstance(resolver, StageExpandingResolver):
                        exclude_candidate = True
                    else:
                        skip_reason = str(error)
                    break
                except (TypeError, ValueError):
                    if isinstance(resolver, StageExpandingResolver):
                        exclude_candidate = True
                    else:
                        skip_reason = (
                            f"{workflow_input.label} could not be prepared for this material. "
                            "Choose a different getter and try again."
                        )
                    break
                if isinstance(resolver, StageExpandingResolver) and not resolver.accepts_resolved_value(value):
                    exclude_candidate = True
                    break
                try:
                    resolved[workflow_input.port_id] = _normalize_json_value(value)
                except (TypeError, ValueError):
                    skip_reason = (
                        f"{workflow_input.label} has a value that this workflow cannot use. "
                        "Choose a different value and try again."
                    )
                    break

            if exclude_candidate:
                continue

            prompt = deepcopy(workflow.api)
            for port_id, value in resolved.items():
                set_prompt_value(prompt, port_id, value)

            texture_targets = {}
            if skip_reason is None:
                try:
                    texture_targets = self._capture_texture_targets(material, workflow)
                except ValueError as error:
                    skip_reason = str(error)

            input_mappings = {}
            if skip_reason is None:
                input_mappings = {
                    workflow_input.port_id: str(resolved[workflow_input.port_id])
                    for workflow_input in workflow.inputs
                    if workflow_input.port_id in resolved
                    and resolved[workflow_input.port_id]
                    and workflow_input.remix_type == RemixType.TEXTURE_FILE_PATH
                }
            generation_job = ComfyUIJob(
                name="ComfyUI generation",
                context_name=self._context_name,
                prim_paths=list(dict.fromkeys(owner_paths)),
                material_path=material_path,
                scheme=endpoint[0],
                host=endpoint[1],
                port=endpoint[2],
                skip_reason=skip_reason,
            )
            request = ComfyUIWorkflowRequest(
                prompt=prompt,
                input_bindings=tuple(input_mappings.items()),
                client_id=client_id,
                timeout=300.0,
                output_url=_get_processed_texture_output_url(target_stage, generation_job.job_id),
                workflow=deepcopy(workflow),
            )
            target = ComfyUIApplyTarget(
                context_name=self._context_name,
                project_path=project_path,
                edit_target_layer=edit_target_layer,
                material_path=material_path,
                texture_targets=tuple(texture_targets.items()),
            )
            processing_job = TextureProcessingJob(
                name="Texture optimization",
                apply_binding=ApplyBinding(
                    output_port=TextureProcessingJob.PROCESSED_TEXTURES,
                    handler_type=ComfyUIJobApplyHandler,
                    target=target,
                ),
            )
            graph = JobGraph(name=f"{workflow.name} - {workflow.active_preset or 'Custom Settings'}")
            graph.add_job(generation_job)
            graph.add_job(processing_job)
            graph.bind(generation_job, ComfyUIJob.WORKFLOW_REQUEST, request)
            graph.connect(
                generation_job.output(ComfyUIJob.GENERATED_TEXTURES),
                processing_job.input(TextureProcessingJob.SOURCE_TEXTURES),
            )
            graphs.append(graph)
        if report is not None:
            report(total, total, None)
        return graphs

    def _set_state(
        self,
        state: ComfyUIState,
        status_message: str = "",
    ) -> None:
        """Transition to a new state and emit a STATE_CHANGED event.

        Args:
            state: Target lifecycle state.
            status_message: Optional human-readable reason for the transition.
        """
        self._state = state
        self._status_message = status_message
        if state is not ComfyUIState.ERROR:
            self._last_connection_error = ""
        if state is ComfyUIState.RUNNING:
            set_connected_endpoint(
                self._context_name,
                canonical_endpoint(self._settings.protocol.scheme, self._settings.host, self._settings.port),
            )
        else:
            self._connected_base_url = None
            set_connected_endpoint(self._context_name, None)
        publish_comfyui_event(
            self._context_name,
            ComfyUIEventType.STATE_CHANGED,
            {"state": state, "status_message": status_message},
        )

    def handle_settings_changed(self, key: str, value: object) -> None:
        """Invalidate endpoint-owned state and notify this context of a setting change.

        Args:
            key: Short settings key name that changed.
            value: New value for the setting.

        Raises:
            RuntimeError: If extension shutdown invalidated this runtime.
        """
        self._ensure_active()
        self._connect_generation += 1
        self._workflow_discovery_generation += 1
        self._workflow_load_generation += 1
        self._connected_base_url = None
        self._workflow_base_url = None
        self._available_workflows.clear()
        self._workflow = None
        self._set_state(ComfyUIState.READY)
        publish_comfyui_event(
            self._context_name,
            ComfyUIEventType.WORKFLOWS_LOADED,
            {"workflows": []},
        )
        publish_comfyui_event(
            self._context_name,
            ComfyUIEventType.WORKFLOW_CHANGED,
            {"workflow": None},
        )
        publish_comfyui_event(
            self._context_name,
            ComfyUIEventType.SETTINGS_CHANGED,
            {"key": key, "value": value},
        )

    def _begin_operation(self, operation: ComfyUIOperation) -> None:
        """Claim exclusive preparation/submission ownership for this core.

        Args:
            operation: User-facing operation name used in an overlap error.

        Raises:
            RuntimeError: If another preparation or submission owns the core.
        """
        if self._active_operation is not None:
            raise RuntimeError(f"ComfyUI {self._active_operation.value} is already in progress")
        self._active_operation = operation

    def _finish_operation(self) -> None:
        """Release preparation/submission ownership for this core."""
        self._active_operation = None

    def _ensure_active(self) -> None:
        """Raise when an extension shutdown invalidated this core instance.

        Raises:
            RuntimeError: If this runtime has been destroyed.
        """
        if self._destroyed:
            raise RuntimeError("ComfyUI core instance has been destroyed")

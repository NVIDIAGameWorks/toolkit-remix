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
import json
import math
import pathlib
import re
import uuid
from collections.abc import Callable, Iterable, Iterator
from copy import deepcopy
from typing import Any

import carb
from lightspeed.common.constants import REGEX_INSTANCE_PATH, REGEX_IN_INSTANCE_PATH, REMIX_INGESTED_ASSETS_FOLDER
from lightspeed.trex.asset_pipeline.core.jobs import TextureOptimizationJob, add_asset_optimization_jobs
from lightspeed.trex.asset_pipeline.core.jobs.apply_handler import SaveTextureMetadataHandler
from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.core.enums import JobState
from omni.flux.job_queue.core.errors import QueueSubmissionError
from omni.flux.job_queue.core.job import ApplyBinding, JobGraph
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.common.materials import get_materials_from_prim_paths
from omni.flux.utils.common.progress import INDETERMINATE_PROGRESS_TOTAL, run_worker_with_latest_progress
from omni.usd import get_composed_references_from_prim, get_context
from pxr import Sdf, Tf, Usd, UsdGeom, UsdShade

from lightspeed.trex.asset_replacements.core.shared.data_models import AssetReplacementsValidators
from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from lightspeed.trex.utils.common.prim_utils import get_prototype

from .api import ComfyUIAPI
from .connection import get_connected_endpoint, set_connected_endpoint
from .constants import COMFYUI_PROCESSED_FOLDER
from .enums import (
    WORKFLOW_TYPES_BY_CATEGORY,
    ComfyUIEventType,
    ComfyUIOperation,
    ComfyUIRetargetResult,
    ComfyUIState,
    MeshReferenceSelection,
    OutputApplyBehavior,
    RemixType,
)
from .apply_handler import ComfyUIAssetApplyHandler, ComfyUITextureApplyHandler
from .events import publish_comfyui_event
from .job import ComfyUIAssetJob, ComfyUIJob
from .maps import OUTPUT_TEXTURE_TYPE_MAP
from .models import (
    ComfyUIApplyTarget,
    ComfyUIAssetApplyTarget,
    ComfyUIInputBinding,
    ComfyUIWorkflowRequest,
    MeshCandidate,
    ReferenceTarget,
    Workflow,
    WorkflowOutput,
    WorkflowTypeCategory,
    WorkflowTypeOption,
)
from .prompt import set_prompt_value
from .resolvers import (
    ConstantResolver,
    LayerIdentifierResolver,
    ResolverConfigurationError,
    ResolverValueError,
    SelectedMeshResolver,
    StageExpandingResolver,
    is_remix_reference,
)
from .settings import ComfyUISettings
from .url import Endpoint, build_url, canonical_endpoint

# A viewport selection is an instance root (inst_<hash>_N) or one of its children.
_INSTANCE_PATH_PATTERN = re.compile(f"{REGEX_INSTANCE_PATH}|{REGEX_IN_INSTANCE_PATH}")


def _stage_references(prim: Usd.Prim, layer_stack: list[Sdf.Layer]) -> list[tuple[Sdf.Reference, Sdf.Layer]]:
    """Return the composed references of one prim that a layer of this stage introduces."""
    return [(reference, layer) for reference, layer in get_composed_references_from_prim(prim) if layer in layer_stack]


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


_GraphCandidate = tuple[UsdShade.Material | None, Usd.Prim, list[str], tuple[ReferenceTarget, ...], dict[str, str]]


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


def _to_file_source_url(value: str | pathlib.Path) -> str:
    """Return a URL-preserving string for one resolved semantic file."""
    source = str(value).replace("\\", "/")
    scheme, separator, remainder = source.partition(":/")
    if separator and len(scheme) > 1 and remainder and not remainder.startswith("/"):
        return f"{scheme}://{remainder}"
    return source


def _get_processed_output_url(stage: Usd.Stage, job_id: uuid.UUID) -> str | None:
    """Build the durable destination for one workflow's processed files.

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
    return str(project_directory / REMIX_INGESTED_ASSETS_FOLDER / COMFYUI_PROCESSED_FOLDER / str(job_id))


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
        stage_event_callback: Callable[[Any], None] | None = None,
    ):
        """Initialize the ComfyUI runtime for one USD context.

        Args:
            context_name: USD context this runtime operates on.
            settings_changed_callback: Optional process-wide settings change observer.
            stage_event_callback: Optional observer for this context stage lifecycle.

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
        self._available_workflows: list[Workflow] = []
        self._workflow_type_categories: list[WorkflowTypeCategory] = []
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
        self._stage_event_subscription = (
            get_context(context_name)
            .get_stage_event_stream()
            .create_subscription_to_pop(
                stage_event_callback, name=f"ComfyUIApplyProjectState:{context_name or 'default'}"
            )
            if stage_event_callback is not None
            else None
        )

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
    def available_workflows(self) -> list[Workflow]:
        """Return a snapshot of the last successfully fetched workflow catalog.

        Returns:
            Catalog workflows in a list safe for caller mutation.
        """
        return list(self._available_workflows)

    @property
    def workflow_type_categories(self) -> list[WorkflowTypeCategory]:
        """Return the workflow type vocabulary published by the connected server.

        The picker groups workflows by these categories. A server running an older node pack
        does not publish ``workflows/types``; this property then falls back to the local
        mirror of the vocabulary, with no description for any type, so the picker still works.

        Returns:
            Published categories in server order, or the ``WORKFLOW_TYPES_BY_CATEGORY`` mirror
            converted to the same type when the server has not published any.
        """
        if self._workflow_type_categories:
            return list(self._workflow_type_categories)
        return [
            WorkflowTypeCategory(
                name=category_name,
                types=tuple(WorkflowTypeOption(workflow_type) for workflow_type in workflow_types),
            )
            for category_name, workflow_types in WORKFLOW_TYPES_BY_CATEGORY.items()
        ]

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

    async def fetch_available_workflows(self) -> list[Workflow]:
        """Fetch available workflows and workflow types from the ComfyUI server.

        Calls the /rtx-remix/v1/workflows endpoint via api.get_workflow_list(), then the
        /rtx-remix/v1/workflows/types endpoint via api.get_workflow_types(). Returns API and
        full workflow categories from RTX Remix and user sources. The catalog and the type
        vocabulary commit as one snapshot and emit WORKFLOWS_LOADED once, after both requests
        complete. Results made stale by newer discovery, shutdown, or endpoint changes are
        rejected. A callback that changes the endpoint after publication causes the previous
        cache to be restored.

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
        previous_type_categories = list(self._workflow_type_categories)
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
        type_categories = await self._request_workflow_types(api)
        self._ensure_active()
        if self._stop_stale_discovery(generation, api, previous_workflows, previous_type_categories):
            self._ensure_active()
            return self.available_workflows
        self._restore_available_workflows(workflows, type_categories, notify=True)
        published = self.available_workflows
        self._ensure_active()
        if self._stop_stale_discovery(generation, api, previous_workflows, previous_type_categories, published=True):
            self._ensure_active()
            return self.available_workflows
        return published

    async def _request_available_workflows(self, api: ComfyUIAPI) -> list[Workflow]:
        """Request workflows through a client captured by the caller.

        Args:
            api: Client bound to the endpoint that owns the discovery request.

        Returns:
            Catalog workflows returned by the server.

        Raises:
            RuntimeError: If the request or response is invalid.
        """
        try:
            return await api.get_workflow_list()
        except RuntimeError as error:
            carb.log_warn(f"Failed to fetch workflows: {error}")
            raise

    async def _request_workflow_types(self, api: ComfyUIAPI) -> list[WorkflowTypeCategory]:
        """Request the workflow type vocabulary through a client captured by the caller.

        A server running an older node pack does not publish this endpoint; this method treats
        the resulting ``RuntimeError`` as "no vocabulary published" so a missing endpoint never
        blocks discovery from committing the fetched catalog.

        Args:
            api: Client bound to the endpoint that owns the discovery request.

        Returns:
            Type categories returned by the server, or an empty list when the server does not
            publish the endpoint.
        """
        try:
            return await api.get_workflow_types()
        except RuntimeError as error:
            carb.log_warn(f"Failed to fetch workflow types: {error}")
            return []

    def _restore_available_workflows(
        self,
        workflows: list[Workflow],
        type_categories: list[WorkflowTypeCategory],
        *,
        notify: bool,
    ) -> None:
        """Restore a workflow-list and type-vocabulary snapshot, optionally notifying subscribers.

        The catalog and the vocabulary commit as one discovery snapshot so a subscriber that
        reads ``workflow_type_categories`` while handling ``WORKFLOWS_LOADED`` always sees the
        categories that belong to this catalog, never a stale or empty value.

        Args:
            workflows: Workflow catalog snapshot to restore.
            type_categories: Workflow type vocabulary snapshot to restore.
            notify: Whether to emit a workflows-loaded event.
        """
        self._available_workflows = list(workflows)
        self._workflow_type_categories = list(type_categories)
        if notify:
            publish_comfyui_event(
                self._context_name,
                ComfyUIEventType.WORKFLOWS_LOADED,
                {
                    "workflows": self.available_workflows,
                },
            )

    async def load_workflow(self, workflow: Workflow) -> None:
        """Fetch a catalog workflow's data from the server and set it as the active workflow.

        A load only commits while it remains the newest request for the captured
        endpoint. Endpoint changes restore READY without committing stale data;
        current request and parse failures are rolled back and propagated.

        Args:
            workflow: Catalog workflow to load. Its category, source, and display metadata are
                preserved on the loaded graph.

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
            api_workflow, full_workflow = await api.get_workflow_data(workflow.source_type, workflow.name)
            loaded_workflow = Workflow.from_litegraph_dict(
                api_workflow,
                full_workflow=full_workflow,
                name=workflow.name,
                context_name=self._context_name,
            )
            loaded_workflow.source_type = workflow.source_type
            loaded_workflow.category = workflow.category
            loaded_workflow.display_name = workflow.display_name
            loaded_workflow.description = workflow.description
            loaded_workflow.workflow_type = workflow.workflow_type
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
            self._publish_workflow(loaded_workflow)
            self._ensure_active()
            if generation != self._workflow_load_generation:
                return
            if self._workflow is not loaded_workflow:
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
        previous_workflows: list[Workflow] | None = None
        previous_type_categories: list[WorkflowTypeCategory] = []
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
            type_categories = await self._request_workflow_types(api)
            self._ensure_active()
            if self._stop_stale_connection(generation, discovery_generation, api):
                self._ensure_active()
                return
            previous_workflows = self.available_workflows
            previous_type_categories = list(self._workflow_type_categories)
            self._restore_available_workflows(workflows, type_categories, notify=True)
            self._ensure_active()
            if self._stop_stale_connection(
                generation,
                discovery_generation,
                api,
                previous_workflows,
                previous_type_categories,
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
                previous_type_categories,
                published=True,
            ):
                self._ensure_active()
                return
        except asyncio.CancelledError:
            if not self._destroyed and generation == self._connect_generation:
                if previous_workflows is not None:
                    self._restore_available_workflows(previous_workflows, previous_type_categories, notify=True)
                if not self._destroyed and generation == self._connect_generation:
                    self._set_state(ComfyUIState.READY)
            raise
        except RuntimeError as error:
            if not self._destroyed and generation == self._connect_generation:
                if previous_workflows is not None:
                    self._restore_available_workflows(previous_workflows, previous_type_categories, notify=True)
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
        previous_workflows: list[Workflow],
        previous_type_categories: list[WorkflowTypeCategory],
        *,
        published: bool = False,
    ) -> bool:
        """Reject stale workflow discovery and restore subscriber-visible cache state.

        Args:
            generation: Generation captured by the discovery request.
            api: Client bound to the discovery endpoint.
            previous_workflows: Catalog visible before discovery began.
            previous_type_categories: Type vocabulary visible before discovery began.
            published: Whether the stale catalog was already published.

        Returns:
            True if the discovery request is stale and must stop.
        """
        if self._is_current_discovery(generation, api):
            return False
        if generation == self._workflow_discovery_generation:
            self._restore_available_workflows(previous_workflows, previous_type_categories, notify=published)
            if not self._destroyed and generation == self._workflow_discovery_generation:
                self._set_state(ComfyUIState.READY)
        return True

    def _stop_stale_connection(
        self,
        generation: int,
        discovery_generation: int,
        api: ComfyUIAPI,
        previous_workflows: list[Workflow] | None = None,
        previous_type_categories: list[WorkflowTypeCategory] | None = None,
        *,
        published: bool = False,
    ) -> bool:
        """Restore disconnected state when callbacks or newer work invalidate a connection.

        Args:
            generation: Generation captured by the connection attempt.
            discovery_generation: Discovery generation owned by the connection attempt.
            api: Client bound to the connection endpoint.
            previous_workflows: Catalog visible before connection discovery began.
            previous_type_categories: Type vocabulary visible before connection discovery began.
            published: Whether the connection's catalog was already published.

        Returns:
            True if the connection attempt is stale and must stop.
        """
        if generation == self._connect_generation and self._is_current_discovery(discovery_generation, api):
            return False
        if generation == self._connect_generation:
            if previous_workflows is not None:
                self._restore_available_workflows(previous_workflows, previous_type_categories or [], notify=published)
            if not self._destroyed and generation == self._connect_generation:
                self._set_state(ComfyUIState.READY)
        return True

    def destroy(self) -> None:
        """Invalidate this core so stale references cannot resume work after extension shutdown."""
        if self._destroyed:
            return
        self._destroyed = True
        self._stage_event_subscription = None
        self._objects_changed_subscription.Revoke()
        self._objects_changed_subscription = None
        self._connect_generation += 1
        self._workflow_discovery_generation += 1
        self._workflow_load_generation += 1
        self._workflow = None
        self._workflow_base_url = None
        self._connected_base_url = None
        self._available_workflows.clear()
        self._workflow_type_categories.clear()
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
        """Create output-driven texture or asset graphs for one workflow.

        Args:
            prim_paths: Explicit selection snapshot, or the current USD selection when omitted.
            progress: Optional callback receiving current count, total count, and a status message.
            is_cancelled: Optional callback returning whether the caller requested cancellation.

        Returns:
            Executable graphs in deterministic candidate order.

        Raises:
            RuntimeError: If the workflow, stage, output lane, or eligible candidates are unavailable.
        """
        if self._workflow is None:
            raise RuntimeError("No ComfyUI workflow is selected")

        workflow = deepcopy(self._workflow)
        texture_outputs = tuple(
            output for output in workflow.output_specs if output.remix_type is RemixType.TEXTURE_FILE_PATH
        )
        mesh_outputs = tuple(
            output for output in workflow.output_specs if output.remix_type is RemixType.MESH_FILE_PATH
        )
        output_keys = tuple(output.node_id for output in (*texture_outputs, *mesh_outputs))
        if len(output_keys) != len(set(output_keys)):
            raise RuntimeError("Every processable ComfyUI output must have one unique node key.")
        if len(mesh_outputs) > 1:
            raise RuntimeError("A ComfyUI asset workflow must declare exactly one mesh output.")
        if not mesh_outputs and not texture_outputs:
            raise RuntimeError("The ComfyUI workflow does not declare a processable file output.")

        if mesh_outputs and mesh_outputs[0].apply_behavior is OutputApplyBehavior.REPLACE:
            mesh_inputs = [item for item in workflow.inputs if item.remix_type is RemixType.MESH_FILE_PATH]
            if not mesh_inputs:
                raise RuntimeError("Replace needs a mesh input. Add a mesh input or set the mesh output to Append.")
            if any(isinstance(item.value, ConstantResolver) for item in mesh_inputs):
                raise RuntimeError(
                    "Replace needs a mesh input that reads stage references. "
                    "Set the mesh input to Selected Mesh or All Meshes, or set the mesh output to Append."
                )

        stage, project_path, edit_target_layer = self._get_submission_target()
        context = get_context(self._context_name)
        # A viewport selection is usually an instance (/RootNode/instances/inst_<hash>_N/...). RTX Remix only
        # honors replacements authored on the prototype (/RootNode/meshes/mesh_<hash>/...), so every owner and
        # material lookup starts from the prototype prim. Paths without a prototype stay as selected.
        selected_paths = list(
            dict.fromkeys(
                self._prototype_path(stage, prim_path)
                for prim_path in (
                    prim_paths if prim_paths is not None else context.get_selection().get_selected_prim_paths()
                )
            )
        )
        endpoint = canonical_endpoint(self._settings.protocol.scheme, self._settings.host, self._settings.port)
        client_id = self._client_id

        def build_graphs(report: Callable[[int, int | None, Any | None], None]) -> list[JobGraph]:
            candidates: list[_GraphCandidate] = []
            mesh_candidates = []
            if mesh_outputs:
                report(0, INDETERMINATE_PROGRESS_TOTAL, "Listing stage model candidates...")
                mesh_input_ids = tuple(
                    workflow_input.port_id
                    for workflow_input in workflow.inputs
                    if workflow_input.remix_type is RemixType.MESH_FILE_PATH
                )
                mesh_candidates = self._get_mesh_candidates(stage, selected_paths, workflow, is_cancelled=is_cancelled)
                for candidate in mesh_candidates:
                    owner_paths = list(dict.fromkeys(owner.owner_prim_path for owner in candidate.owners))
                    input_prim_path = candidate.input_prim_path or (owner_paths[0] if owner_paths else None)
                    prim = stage.GetPrimAtPath(input_prim_path) if input_prim_path else stage.GetPseudoRoot()
                    overrides = (
                        dict.fromkeys(mesh_input_ids, candidate.source_path)
                        if candidate.source_path is not None
                        else {}
                    )
                    candidates.append((None, prim, owner_paths, candidate.owners, overrides))
                if is_cancelled is not None and is_cancelled():
                    return []
            elif any(
                workflow_input.remix_type is RemixType.TEXTURE_FILE_PATH for workflow_input in workflow.inputs
            ) and all(
                isinstance(workflow_input.value, (ConstantResolver, LayerIdentifierResolver))
                for workflow_input in workflow.inputs
            ):
                candidates.append((None, stage.GetPseudoRoot(), [], (), {}))
            else:
                paths: Iterable[str] = selected_paths
                stage_resolvers = self._get_stage_expanding_resolvers(workflow)
                if stage_resolvers:
                    report(0, INDETERMINATE_PROGRESS_TOTAL, "Listing stage texture candidates...")
                    paths = self._stage_expansion_prim_paths(
                        stage,
                        stage_resolvers,
                        report=report,
                        is_cancelled=is_cancelled,
                    )
                if is_cancelled is not None and is_cancelled():
                    return []
                candidates.extend(
                    (material, material.GetPrim(), owner_paths, (), {})
                    for material, owner_paths in self._get_material_candidates(paths)
                )
            return self._create_job_graphs_for_candidates(
                candidates,
                workflow,
                mesh_outputs[0] if mesh_outputs else None,
                project_path,
                edit_target_layer,
                endpoint,
                client_id,
                stage=stage,
                mesh_candidates=mesh_candidates,
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
            raise RuntimeError("The selection does not contain any items that can create ComfyUI jobs")
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
            if workflow_input.remix_type is not RemixType.MESH_FILE_PATH
            and isinstance(workflow_input.value, StageExpandingResolver)
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

    def _get_mesh_candidates(
        self,
        stage: Usd.Stage,
        selected_paths: list[str],
        workflow: Workflow,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[MeshCandidate]:
        """Build one candidate per unique selected model source and complete resolved input set.

        Args:
            stage: Live stage used to inspect selected reference owners.
            selected_paths: Explicit selection snapshot in user order.
            workflow: Detached workflow whose mesh input resolver selects candidate mode.
            is_cancelled: Optional callback returning whether the caller requested cancellation. A cancelled
                call returns the candidates found so far. The caller discards them.

        Returns:
            URL-preserving candidates in first-seen composed order.

        Raises:
            ResolverConfigurationError: If the workflow declares several mesh inputs.
        """
        mesh_inputs = tuple(
            workflow_input
            for workflow_input in workflow.inputs
            if workflow_input.remix_type is RemixType.MESH_FILE_PATH
        )
        if len(mesh_inputs) > 1:
            raise ResolverConfigurationError("A ComfyUI asset workflow may declare at most one mesh input.")
        ancestor_cache = {}
        reference_owners_cache = {}
        layer_stack = stage.GetLayerStack()
        if not mesh_inputs:
            # Owners keyed by path, each with the first selected prim that introduced it. Inputs such as
            # Selected Texture resolve on that prim, not on the reference owner, which may have no material.
            owners_by_path: dict[str, tuple[ReferenceTarget, str]] = {}
            for prim_path in dict.fromkeys(selected_paths):
                if is_cancelled is not None and is_cancelled():
                    break
                for owner in self._capture_mesh_owners(
                    [prim_path],
                    MeshReferenceSelection.ALL,
                    include_missing=True,
                    stage=stage,
                    ancestor_cache=ancestor_cache,
                    reference_owners_cache=reference_owners_cache,
                    layer_stack=layer_stack,
                ):
                    owners_by_path.setdefault(owner.owner_prim_path, (owner, prim_path))
            owners_by_inputs: dict[tuple, dict[ReferenceTarget, str]] = {}
            inputs_by_key = {}
            for owner, prim_path in owners_by_path.values():
                resolved, bindings, skip_reason, _excluded = self._resolve_workflow_inputs(
                    workflow, stage.GetPrimAtPath(prim_path)
                )
                input_key = (
                    json.dumps(resolved, sort_keys=True, default=str),
                    tuple((binding.port_id, binding.source) for binding in bindings),
                    skip_reason,
                )
                owners_by_inputs.setdefault(input_key, {})[owner] = prim_path
                inputs_by_key.setdefault(input_key, (resolved, bindings, skip_reason, _excluded))
            return [
                MeshCandidate(
                    source_path=None,
                    owners=tuple(group),
                    input_prim_path=next(iter(group.values())),
                    resolved_inputs=inputs_by_key[input_key],
                )
                for input_key, group in owners_by_inputs.items()
            ]

        resolver = mesh_inputs[0].value
        if isinstance(resolver, ConstantResolver):
            value = resolver(stage.GetPseudoRoot())
            if not isinstance(value, (str, pathlib.Path)):
                raise ResolverConfigurationError("Select a valid model file for the workflow mesh input.")
            source = _to_file_source_url(value)
            if all(isinstance(item.value, (ConstantResolver, LayerIdentifierResolver)) for item in workflow.inputs):
                return [MeshCandidate(source_path=source, owners=())]
            return [
                MeshCandidate(source_path=source, owners=(), input_prim_path=prim_path) for prim_path in selected_paths
            ]
        if not isinstance(resolver, SelectedMeshResolver):
            raise ResolverConfigurationError("Select a mesh getter for the workflow mesh input.")
        if isinstance(resolver, StageExpandingResolver):
            selected_paths = list(
                dict.fromkeys(
                    self._prototype_path(stage, prim_path)
                    for prim_path in self._stage_expansion_prim_paths(stage, (resolver,), is_cancelled=is_cancelled)
                )
            )

        # Two owners share one candidate only when the model source and every other resolved input match.
        # Equal model URLs alone do not make equal generation requests: a Selected Texture getter can bind a
        # different texture on each owner.
        mesh_input_ids = tuple(workflow_input.port_id for workflow_input in mesh_inputs)
        input_keys: dict[tuple[str, str], tuple] = {}
        inputs_by_request = {}
        owners_by_request: dict[tuple[str, tuple], dict[ReferenceTarget, str]] = {}
        for prim_path in selected_paths:
            if is_cancelled is not None and is_cancelled():
                break
            owners = self._get_reference_owners(stage, prim_path, ancestor_cache, reference_owners_cache, layer_stack)
            selected = resolver.select_references(owners, resolver.reference_selection, stage.GetPrimAtPath(prim_path))
            if owners and not selected:
                raise ResolverValueError(
                    "Reference Selection is Selected, but the picked prim is not under one reference. "
                    "Pick a prim under the reference in the Selection panel, or set Reference Selection to All."
                )
            for owner_prim, reference, layer in selected:
                if not reference.assetPath:
                    raise ResolverValueError("The selected mesh uses an internal reference that ComfyUI cannot upload.")
                source = Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath)
                request_key = (prim_path, source)
                if request_key not in input_keys:
                    resolved, bindings, skip_reason, _excluded = self._resolve_workflow_inputs(
                        workflow, stage.GetPrimAtPath(prim_path), overrides=dict.fromkeys(mesh_input_ids, source)
                    )
                    input_keys[request_key] = (
                        json.dumps(resolved, sort_keys=True, default=str),
                        tuple((binding.port_id, binding.source) for binding in bindings),
                        skip_reason,
                    )
                    inputs_by_request[request_key] = (resolved, bindings, skip_reason, _excluded)
                owner = ReferenceTarget(
                    owner_prim_path=str(owner_prim.GetPath()),
                    source_reference=reference,
                    source_layer_identifier=str(layer.identifier),
                )
                owners_by_request.setdefault((source, input_keys[request_key]), {}).setdefault(owner, prim_path)
        return [
            MeshCandidate(
                source_path=source,
                owners=tuple(owners),
                input_prim_path=next(iter(owners.values())),
                resolved_inputs=inputs_by_request[(next(iter(owners.values())), source)],
            )
            for (source, _inputs), owners in owners_by_request.items()
        ]

    @staticmethod
    def _prototype_path(stage: Usd.Stage, prim_path: str) -> str:
        """Return the prototype (``mesh_<hash>``) path of one selected prim, or the path itself.

        Args:
            stage: Live stage that holds the selection.
            prim_path: Selected prim path, possibly under an instance.

        Returns:
            The prototype path when the prim is an instance with a live prototype. Otherwise the input path.
        """
        if not _INSTANCE_PATH_PATTERN.match(prim_path):
            return prim_path
        prototype = get_prototype(stage.GetPrimAtPath(prim_path))
        return str(prototype.GetPath()) if prototype is not None else prim_path

    def _get_reference_owner(
        self,
        stage: Usd.Stage,
        prim_path: str,
        ancestor_cache: dict[Sdf.Path, tuple[Usd.Prim | None, list[tuple[Sdf.Reference, Sdf.Layer]]]],
        layer_stack: list[Sdf.Layer] | None = None,
    ) -> tuple[Usd.Prim, list[tuple[Sdf.Reference, Sdf.Layer]]]:
        """Return the prim that owns the selected prim's model references, with those references.

        The Selection panel lists reference children, not the mesh prim. A child inside a referenced model can
        carry several prim specs (nested layers, overrides), which makes the shared prim-stack rule stop at the
        child and synthesize one reference. This walk stops at the first ancestor that introduces a reference
        from a layer of this stage, so a mesh prim with four references yields four sources. It falls back to
        the shared rule when no ancestor does.

        Args:
            stage: Captured stage.
            prim_path: Selected prim path.
            ancestor_cache: Shared ancestor results for this discovery operation.
            layer_stack: Captured stage layers, or the current stack if omitted.

        Returns:
            The owning prim and its ``(reference, introducing layer)`` pairs.
        """
        if layer_stack is None:
            layer_stack = stage.GetLayerStack()
        visited = []
        owner = stage.GetPrimAtPath(prim_path)
        while owner and not owner.IsPseudoRoot():
            path = owner.GetPath()
            if path in ancestor_cache:
                cached_owner, references = ancestor_cache[path]
                if cached_owner is not None:
                    for visited_path in visited:
                        ancestor_cache[visited_path] = (cached_owner, references)
                    return cached_owner, references
                break
            visited.append(path)
            references = _stage_references(owner, layer_stack)
            if references:
                for visited_path in visited:
                    ancestor_cache[visited_path] = (owner, references)
                return owner, references
            owner = owner.GetParent()
        return AssetReplacementsValidators.get_prim_references(
            prim_path, self._context_name, stage=stage, ancestor_cache=ancestor_cache
        )

    def _get_reference_owners(
        self,
        stage: Usd.Stage,
        prim_path: str,
        ancestor_cache: dict[Sdf.Path, tuple[Usd.Prim | None, list[tuple[Sdf.Reference, Sdf.Layer]]]],
        reference_owners_cache: dict[Sdf.Path, list[tuple[Usd.Prim, Sdf.Reference, Sdf.Layer]]],
        layer_stack: list[Sdf.Layer],
    ) -> list[tuple[Usd.Prim, Sdf.Reference, Sdf.Layer]]:
        """Return every model reference of the mesh that holds the selected prim, each with its owning prim.

        Remix authors an added reference on a marked ``ref_<id>`` child of the mesh prim, because USD cannot
        hold the same reference twice on one prim. The Selection panel shows those children as references of
        the mesh. This returns the mesh prim's own stage references first, then each marked child's, in child
        order, the way the Selection panel lists them, so a mesh with four references yields four sources.

        Args:
            stage: Captured stage.
            prim_path: Selected prim path.
            ancestor_cache: Shared ancestor results for this discovery operation.
            reference_owners_cache: Complete reference groups by mesh path for this discovery operation.
            layer_stack: Captured stage layers for this discovery operation.

        Returns:
            ``(owner prim, reference, introducing layer)`` triples in Selection panel order.
        """
        owner, references = self._get_reference_owner(stage, prim_path, ancestor_cache, layer_stack)
        if not owner:
            return []
        mesh = owner
        if is_remix_reference(owner) and owner.GetParent():
            mesh = owner.GetParent()
        mesh_path = mesh.GetPath()
        if mesh_path in reference_owners_cache:
            return reference_owners_cache[mesh_path]
        if mesh != owner:
            references = _stage_references(mesh, layer_stack)
        groups = [(mesh, references)]
        groups.extend(
            (child, _stage_references(child, layer_stack)) for child in mesh.GetChildren() if is_remix_reference(child)
        )
        result = [(prim, reference, layer) for prim, prim_references in groups for reference, layer in prim_references]
        reference_owners_cache[mesh_path] = result
        return result

    def _capture_mesh_owners(
        self,
        prim_paths: Iterable[str],
        selection: MeshReferenceSelection,
        *,
        include_missing: bool,
        stage: Usd.Stage | None = None,
        ancestor_cache: dict[Sdf.Path, tuple[Usd.Prim | None, list[tuple[Sdf.Reference, Sdf.Layer]]]] | None = None,
        reference_owners_cache: dict[Sdf.Path, list[tuple[Usd.Prim, Sdf.Reference, Sdf.Layer]]] | None = None,
        layer_stack: list[Sdf.Layer] | None = None,
    ) -> tuple[ReferenceTarget, ...]:
        """Capture selected reference owners without changing the stage.

        Args:
            prim_paths: Selected prim paths in stable order.
            selection: All references of the mesh, or only the Selected one.
            include_missing: Whether a prim with no external reference remains an Append target.
            stage: Captured stage, or the current stage if omitted.
            ancestor_cache: Shared ancestor results for this discovery operation.
            reference_owners_cache: Complete reference groups by mesh path for this discovery operation.
            layer_stack: Captured stage layers, or the current stack if omitted.

        Returns:
            Unique owner records in first-seen order.
        """
        owners: dict[ReferenceTarget, None] = {}
        if stage is None:
            stage = get_context(self._context_name).get_stage()
        if ancestor_cache is None:
            ancestor_cache = {}
        if reference_owners_cache is None:
            reference_owners_cache = {}
        if layer_stack is None:
            layer_stack = stage.GetLayerStack()
        for prim_path in dict.fromkeys(prim_paths):
            selected = SelectedMeshResolver.select_references(
                self._get_reference_owners(stage, prim_path, ancestor_cache, reference_owners_cache, layer_stack),
                selection,
                stage.GetPrimAtPath(prim_path),
            )
            if selected:
                candidates = (
                    ReferenceTarget(
                        owner_prim_path=str(owner_prim.GetPath()),
                        source_reference=reference,
                        source_layer_identifier=str(layer.identifier),
                    )
                    for owner_prim, reference, layer in selected
                )
            elif include_missing and stage is not None and stage.GetPrimAtPath(prim_path).IsValid():
                candidates = (
                    ReferenceTarget(
                        owner_prim_path=prim_path,
                        source_reference=None,
                        source_layer_identifier=None,
                    ),
                )
            else:
                candidates = ()
            for owner in candidates:
                owners[owner] = None
        return tuple(owners)

    def _resolve_workflow_inputs(
        self,
        workflow: Workflow,
        prim: Usd.Prim,
        *,
        overrides: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], tuple[ComfyUIInputBinding, ...], str | None, bool]:
        """Resolve prompt values and semantic file bindings for one candidate.

        Args:
            workflow: Detached workflow snapshot to resolve.
            prim: Candidate prim supplied to semantic getters.
            overrides: Exact URL-preserving values that replace selected semantic getters.

        Returns:
            Resolved JSON values, semantic bindings, skip reason, and exclusion flag.

        Raises:
            ResolverConfigurationError: If one configured getter cannot run.
        """
        resolved: dict[str, Any] = {}
        bindings: list[ComfyUIInputBinding] = []
        overrides = overrides or {}
        for workflow_input in workflow.inputs:
            resolver = workflow_input.value
            try:
                value = overrides.get(workflow_input.port_id)
                if value is None:
                    value = resolver(prim)
            except ResolverConfigurationError:
                raise
            except ResolverValueError as error:
                return {}, (), str(error), isinstance(resolver, StageExpandingResolver)
            except (TypeError, ValueError):
                return (
                    {},
                    (),
                    (
                        f"{workflow_input.label} could not be prepared for this item. "
                        "Choose a different getter and try again."
                    ),
                    isinstance(resolver, StageExpandingResolver),
                )
            if isinstance(resolver, StageExpandingResolver) and not resolver.accepts_resolved_value(value):
                return {}, (), None, True
            if workflow_input.remix_type in {RemixType.TEXTURE_FILE_PATH, RemixType.MESH_FILE_PATH}:
                source = _to_file_source_url(value)
                try:
                    binding = ComfyUIInputBinding(
                        port_id=workflow_input.port_id,
                        remix_type=workflow_input.remix_type,
                        source=source,
                    )
                except (TypeError, ValueError):
                    return (
                        {},
                        (),
                        (
                            f"{workflow_input.label} has a file that this workflow cannot use. "
                            "Choose a different file and try again."
                        ),
                        False,
                    )
                bindings.append(binding)
                resolved[workflow_input.port_id] = source
                continue
            try:
                resolved[workflow_input.port_id] = _normalize_json_value(value)
            except (TypeError, ValueError):
                return (
                    {},
                    (),
                    (
                        f"{workflow_input.label} has a value that this workflow cannot use. "
                        "Choose a different value and try again."
                    ),
                    False,
                )
        return resolved, tuple(bindings), None, False

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

    def _capture_texture_targets(
        self,
        materials: Iterable[UsdShade.Material],
        workflow: Workflow,
    ) -> tuple[tuple[str, str], ...]:
        """Capture one shader input per material for each texture output configured as Replace.

        Args:
            materials: Materials whose shader inputs receive generated textures.
            workflow: Detached workflow snapshot whose output settings are captured.

        Returns:
            Stable texture output keys paired with exact shader input paths, in material then output order.

        Raises:
            ValueError: If a Replace output is duplicated, unsupported, or does not resolve uniquely.
        """
        replacements_core = TextureReplacementsCore(self._context_name)
        targets: dict[tuple[str, str], None] = {}
        for material in materials:
            shader_paths = self._get_surface_shader_paths(material)
            material_targets: dict[str, str] = {}
            for output in workflow.output_specs:
                if (
                    output.remix_type is not RemixType.TEXTURE_FILE_PATH
                    or output.apply_behavior is not OutputApplyBehavior.REPLACE
                ):
                    continue
                texture_type_key = output.texture_type
                if texture_type_key is None:
                    raise ValueError("The active workflow has a texture output without a Texture Type.")
                texture_label = _get_texture_label(texture_type_key)
                texture_type = OUTPUT_TEXTURE_TYPE_MAP.get(texture_type_key)
                input_name = TEXTURE_TYPE_INPUT_MAP.get(texture_type) if texture_type is not None else None
                if input_name is None:
                    raise ValueError(f"The active workflow uses an unsupported texture type: {texture_label}.")
                candidates = [str(Sdf.Path(shader_path).AppendProperty(input_name)) for shader_path in shader_paths]
                valid_targets = replacements_core.get_valid_texture_inputs(candidates)
                if not valid_targets:
                    raise ValueError(f"This material does not have a replaceable {texture_label} texture.")
                if len(valid_targets) != 1:
                    raise ValueError(
                        f"This material has more than one {texture_label} texture, "
                        "so RTX Remix cannot choose which one to replace."
                    )
                if valid_targets[0] in material_targets.values():
                    raise ValueError("Two workflow outputs would replace the same material texture.")
                material_targets[output.node_id] = valid_targets[0]
            for item in material_targets.items():
                targets[item] = None
        return tuple(targets)

    def _create_job_graphs_for_candidates(
        self,
        candidates: list[_GraphCandidate],
        workflow: Workflow,
        mesh_output: WorkflowOutput | None,
        project_path: str,
        edit_target_layer: str,
        endpoint: Endpoint,
        client_id: str,
        *,
        stage: Usd.Stage,
        mesh_candidates: list[MeshCandidate] | None = None,
        report: Callable[[int, int | None, Any | None], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[JobGraph]:
        """Create one graph per candidate: generation, texture processing, and the asset branch for a mesh output.

        Args:
            candidates: Material, input prim, owner prim paths, reference owners, and exact input overrides per
                candidate. A material marks a stage-backed texture candidate. Reference owners mark a stage-backed
                asset candidate. Otherwise the graph is processing-only.
            workflow: Detached workflow snapshot resolved into every graph.
            mesh_output: Sole mesh output that owns Apply Behavior, or None for a texture workflow.
            project_path: Root-layer identifier captured before resolution.
            edit_target_layer: Edit-layer identifier captured before resolution.
            endpoint: ComfyUI endpoint captured before worker execution.
            client_id: ComfyUI client identifier captured before worker execution.
            stage: Live stage used for target capture and publication paths.
            mesh_candidates: Mesh candidates with input results from candidate discovery, in the same order.
            report: Optional worker-thread progress callback.
            is_cancelled: Optional callback returning whether preparation was cancelled.

        Returns:
            One graph per accepted candidate.
        """
        total = len(candidates)
        graphs: list[JobGraph] = []
        for index, (material, prim, owner_paths, owners, overrides) in enumerate(candidates):
            if is_cancelled is not None and is_cancelled():
                break
            if report is not None:
                report(index, total, f"Preparing job {index + 1} of {total}...")
            stage_backed = material is not None or bool(owners)
            inputs = mesh_candidates[index].resolved_inputs if mesh_candidates else None
            if inputs is None:
                inputs = self._resolve_workflow_inputs(workflow, prim, overrides=overrides)
            resolved, input_bindings, skip_reason, exclude_candidate = inputs
            if exclude_candidate:
                continue
            prompt = deepcopy(workflow.api)
            for port_id, value in resolved.items():
                set_prompt_value(prompt, port_id, value)

            texture_targets: tuple[tuple[str, str], ...] = ()
            if stage_backed and skip_reason is None:
                materials = (
                    [material]
                    if material is not None
                    else [item for item, _ in self._get_material_candidates(owner_paths)]
                )
                if mesh_output is not None and mesh_output.apply_behavior is OutputApplyBehavior.REPLACE:
                    # Replace composes the generated model, which carries its own processed textures, in place
                    # of the source. A material inside the replaced model no longer exists after Apply, so it
                    # is not a texture target.
                    replaced = {Sdf.Path(owner.owner_prim_path) for owner in owners if owner.source_reference}
                    materials = [
                        item
                        for item in materials
                        if not replaced.intersection(Sdf.Path(str(item.GetPrim().GetPath())).GetPrefixes())
                    ]
                try:
                    texture_targets = self._capture_texture_targets(materials, workflow)
                except ValueError as error:
                    skip_reason = str(error)

            generation_job = (ComfyUIAssetJob if mesh_output is not None else ComfyUIJob)(
                name="ComfyUI generation",
                context_name=self._context_name,
                prim_paths=owner_paths,
                material_path=str(prim.GetPath()) if material is not None else "",
                scheme=endpoint[0],
                host=endpoint[1],
                port=endpoint[2],
                skip_reason=skip_reason,
            )
            request = ComfyUIWorkflowRequest(
                prompt=prompt,
                input_bindings=input_bindings if skip_reason is None else (),
                client_id=client_id,
                timeout=300.0,
                output_url=_get_processed_output_url(stage, generation_job.job_id),
                workflow=deepcopy(workflow),
            )
            graph = JobGraph(name=workflow.display_name)
            graph.add_job(generation_job)
            graph.bind(generation_job, ComfyUIJob.WORKFLOW_REQUEST, request)

            if mesh_output is not None:
                target = ComfyUIAssetApplyTarget(
                    context_name=self._context_name,
                    project_path=project_path,
                    edit_target_layer=edit_target_layer,
                    reference_targets=owners,
                    texture_targets=texture_targets,
                    mesh_apply_behavior=mesh_output.apply_behavior,
                )
                add_asset_optimization_jobs(
                    graph,
                    generation_job.output(ComfyUIAssetJob.MESH_REQUEST),
                    handler_type=ComfyUIAssetApplyHandler,
                    target=target,
                )
            else:
                if stage_backed:
                    texture_binding = ApplyBinding(
                        output_port=TextureOptimizationJob.PROCESSED_TEXTURES,
                        handler_type=ComfyUITextureApplyHandler,
                        target=ComfyUIApplyTarget(
                            context_name=self._context_name,
                            project_path=project_path,
                            edit_target_layer=edit_target_layer,
                            material_path=str(prim.GetPath()),
                            texture_targets=texture_targets,
                        ),
                    )
                else:
                    texture_binding = ApplyBinding(
                        output_port=TextureOptimizationJob.PROCESSED_TEXTURES,
                        handler_type=SaveTextureMetadataHandler,
                        target=None,
                    )
                texture_job = TextureOptimizationJob(name="Texture optimization", apply_binding=texture_binding)
                graph.add_job(texture_job)
                graph.connect(
                    generation_job.output(ComfyUIJob.GENERATED_TEXTURES),
                    texture_job.input(TextureOptimizationJob.SOURCE_TEXTURES),
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
        self._workflow_type_categories.clear()
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

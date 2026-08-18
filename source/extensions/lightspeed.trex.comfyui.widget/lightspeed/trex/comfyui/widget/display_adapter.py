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

__all__ = ["ComfyUIDisplayAdapter"]

from copy import deepcopy
from functools import partial
from typing import TYPE_CHECKING, ClassVar

import carb
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni.flux.job_queue.core.job import JobProgress
from omni.flux.job_queue.core.models import QueueJobDetailsSnapshot
from omni.flux.job_queue.widget.constants import ADAPTER_ERRORS
from omni.flux.job_queue.widget.display_adapter_base import (
    JobAction,
    JobDetailField,
    JobDetailSection,
    JobDisplayAdapter,
    is_standalone,
)
from omni.flux.job_queue.widget.enums import DisplayState, JobDetailSectionPlacement
from omni.flux.utils.common import EventSubscription
from omni.usd import get_context
from pxr import UsdGeom

if TYPE_CHECKING:
    from omni.flux.job_queue.widget.model import QueueModel

    from .workspace import ComfySetupWorkspace, WorkflowSetupWorkspace

try:
    from lightspeed.trex.viewports.shared.widget import get_active_viewport as _get_active_viewport
except ModuleNotFoundError as error:
    module_name = "lightspeed.trex.viewports.shared.widget"
    if error.name != module_name and not module_name.startswith(f"{error.name}."):
        raise
    _get_active_viewport = None

from lightspeed.trex.comfyui.core.connection import get_connected_endpoint
from lightspeed.trex.comfyui.core.core import ComfyUICore
from lightspeed.trex.comfyui.core.enums import ComfyUIEventType, ComfyUIRetargetResult
from lightspeed.trex.comfyui.core.events import ComfyUIEventPayload, subscribe_comfyui_event
from lightspeed.trex.comfyui.core.extension import get_comfyui_core_instance
from lightspeed.trex.comfyui.core.job import ComfyUIJob
from lightspeed.trex.comfyui.core.url import Endpoint, build_url, canonical_endpoint


class ComfyUIDisplayAdapter(JobDisplayAdapter):
    """Adapt ComfyUI jobs for display and interaction in the job queue."""

    name = "comfyui"
    job_type = ComfyUIJob
    source_name = "ComfyUI"
    display_name = "ComfyUI generation"
    active_status_label = "Generating textures"
    _FOCUS_ACTION_ID = "focus_in_viewport"
    _OPEN_WORKFLOW_ACTION_ID = "open_workflow"
    _RETARGET_ACTION_ID = "retarget_comfyui"
    _setup_workspace: ClassVar[ComfySetupWorkspace | None] = None
    _workflow_workspace: ClassVar[WorkflowSetupWorkspace | None] = None

    @classmethod
    def set_workspaces(
        cls,
        setup_workspace: ComfySetupWorkspace | None,
        workflow_workspace: WorkflowSetupWorkspace | None,
    ) -> None:
        """Set the paired workspaces used by queue row actions.

        Args:
            setup_workspace: Connection workspace to target when editing jobs, or None during shutdown.
            workflow_workspace: Workflow workspace to open when editing jobs, or None during shutdown.
        """
        cls._setup_workspace = setup_workspace
        cls._workflow_workspace = workflow_workspace

    def get_name_tooltip(self, job: ComfyUIJob) -> str:
        """Return the full target prim paths shown in the name tooltip.

        Args:
            job: Job whose target tooltip is requested.

        Returns:
            Newline-separated target prim paths.
        """
        return "\n".join(self._get_prim_paths(job))

    def get_active_progress_label(self, job: ComfyUIJob, progress: JobProgress | None) -> str | None:
        """Format structured generation step progress.

        Args:
            job: Active ComfyUI job.
            progress: Latest structured generation progress.

        Returns:
            Completed generation-step count, or None before progress begins.
        """
        if progress is None or progress.completed is None or progress.total is None:
            return None
        return f"{progress.completed} of {progress.total} generation steps"

    def subscribe_action_events(self, model: QueueModel) -> EventSubscription:
        """Subscribe one visible queue model to ComfyUI action changes.

        Args:
            model: Queue model whose ComfyUI actions should refresh.

        Returns:
            Core event subscription owned by the queue widget.
        """
        get_comfyui_core_instance(model.context_name)
        return subscribe_comfyui_event(model.context_name, partial(self._on_core_event, model))

    @staticmethod
    def _on_core_event(model: QueueModel, payload: ComfyUIEventPayload) -> None:
        """Refresh ComfyUI rows when stage visibility changes.

        Args:
            model: Queue model containing the affected ComfyUI rows.
            payload: Typed ComfyUI event from the core extension.
        """
        if payload.event_type is ComfyUIEventType.STAGE_VISIBILITY_CHANGED:
            model.refresh_schedule_conditions({ComfyUIJob})

    def get_waiting_reason(self, job: ComfyUIJob, context_name: str) -> str | None:
        """Return the job-owned reason its saved ComfyUI server is unavailable.

        Args:
            job: Queued ComfyUI job whose saved endpoint controls scheduling.
            context_name: Caller context retained for the adapter contract; the job's saved context is used.

        Returns:
            Safe endpoint guidance, or None when the job can run.
        """
        return job.get_schedule_block_reason()

    def _focus(self, job: ComfyUIJob) -> None:
        """Select the next focusable job prim and frame it when a viewport is available.

        Args:
            job: Job whose target prims should be focused.
        """
        if _get_active_viewport is None:
            return

        try:
            paths = self._get_xformable_paths(job)
            if not paths:
                return
            viewport = _get_active_viewport()
            if viewport is None:
                return
            ctx = get_context(job.context_name)
            selection = ctx.get_selection()
            selected_paths = selection.get_selected_prim_paths()
            if len(selected_paths) == 1 and selected_paths[0] in paths:
                next_path = paths[(paths.index(selected_paths[0]) + 1) % len(paths)]
            else:
                next_path = paths[0]
            selection.set_selected_prim_paths([next_path], True)
            viewport.frame_viewport_selection([next_path])
        except RuntimeError as error:
            carb.log_warn(f"Failed to focus in viewport: {error}")

    def get_state_tooltip(
        self,
        job: ComfyUIJob,
        state: DisplayState,
        state_reason: str | None,
    ) -> str | None:
        """Return product guidance for each ComfyUI job state.

        Args:
            job: Job whose current state is being described.
            state: Current queue display state.
            state_reason: Existing state detail supplied by the queue.

        Returns:
            Product-specific status guidance, or None when the queue's generic guidance is sufficient.
        """
        if state is DisplayState.IN_PROGRESS:
            return "ComfyUI is generating textures."
        if state is DisplayState.SKIPPED:
            return state_reason or "ComfyUI generation was skipped because a required input was unavailable."
        if state is DisplayState.FAILED:
            return state_reason or "ComfyUI could not generate these textures. Edit and submit this step again."
        return None

    def get_graph_actions(self, job: ComfyUIJob, context_name: str) -> tuple[JobAction, ...]:
        """Return the workflow actions owned by the material graph.

        Args:
            job: Generation job contributing its workflow actions to the graph.
            context_name: Caller context retained for the display-adapter contract; the job's saved context is used.

        Returns:
            Focus, Open Workflow, and Retarget actions in stable display order.
        """
        return (
            self._get_focus_action(job),
            self._get_open_workflow_action(job),
            self._get_retarget_action(job),
        )

    def _get_focus_action(self, job: ComfyUIJob) -> JobAction:
        """Build the graph-owned viewport action and its exact disabled reason.

        Args:
            job: Generation job whose material owners may be focused.

        Returns:
            Current Focus in Viewport action state.
        """
        if is_standalone():
            tooltip = "Focus in Viewport is unavailable in the standalone job queue."
            enabled = False
        elif _get_active_viewport is None or _get_active_viewport() is None:
            tooltip = "Focus in Viewport requires an active Remix viewport."
            enabled = False
        else:
            try:
                paths = self._get_xformable_paths(job)
            except ADAPTER_ERRORS as error:
                carb.log_warn(f"Could not resolve viewport targets for queue job {job.job_id}: {error}")
                return JobAction(
                    self._FOCUS_ACTION_ID,
                    "Focus in Viewport",
                    "FocusInViewport",
                    "The objects saved with this graph are unavailable in the viewport.",
                    False,
                )
            enabled = bool(paths)
            if len(paths) > 1:
                tooltip = (
                    f"Focus one of {len(paths)} visible objects in the viewport. "
                    "Repeated clicks cycle through the visible objects."
                )
            elif paths:
                tooltip = "Focus this visible object in the viewport."
            else:
                tooltip = "No visible object is available to focus in the viewport."
        return JobAction(self._FOCUS_ACTION_ID, "Focus in Viewport", "FocusInViewport", tooltip, enabled)

    def _get_open_workflow_action(self, job: ComfyUIJob) -> JobAction:
        """Build the graph-owned workflow action and its exact disabled reason.

        Args:
            job: Generation job whose saved workflow may be reopened.

        Returns:
            Current Open Workflow action state.
        """
        enabled, tooltip = self._get_open_workflow_state(job)
        return JobAction(self._OPEN_WORKFLOW_ACTION_ID, "Open Workflow", "EditJob", tooltip, enabled)

    def _get_retarget_action(self, job: ComfyUIJob) -> JobAction:
        """Build the graph-owned server action and its exact disabled reason.

        Args:
            job: Generation job that may be retargeted.

        Returns:
            Current Retarget action state.
        """
        try:
            state = get_comfyui_core_instance(job.context_name).get_retarget_state(job)
        except ADAPTER_ERRORS as error:
            carb.log_warn(f"Could not resolve Retarget state for queue job {job.job_id}: {error}")
            return JobAction(
                self._RETARGET_ACTION_ID,
                "Retarget",
                "RetargetComfyUI",
                "ComfyUI is unavailable, so this graph cannot be retargeted.",
                False,
            )
        saved_server = (
            build_url(*state.saved_endpoint) if state.saved_endpoint is not None else "an invalid saved server address"
        )
        if not state.is_queued:
            return JobAction(
                self._RETARGET_ACTION_ID,
                "Retarget",
                "RetargetComfyUI",
                f"Retarget is available only while generation is waiting in the queue. This graph targets {saved_server}.",
                False,
            )
        if state.connected_endpoint is None:
            return JobAction(
                self._RETARGET_ACTION_ID,
                "Retarget",
                "RetargetComfyUI",
                f"Connect to a ComfyUI server before retargeting this graph. This graph targets {saved_server}.",
                False,
            )
        if state.saved_endpoint == state.connected_endpoint:
            return JobAction(
                self._RETARGET_ACTION_ID,
                "Retarget",
                "RetargetComfyUI",
                f"This graph already uses {saved_server}.",
                False,
            )
        connected_server = build_url(*state.connected_endpoint)
        return JobAction(
            self._RETARGET_ACTION_ID,
            "Retarget",
            "RetargetComfyUI",
            f"Use {connected_server} instead of {saved_server} for this graph's generation step.",
            True,
        )

    def get_detail_sections(
        self,
        job: ComfyUIJob,
        details: QueueJobDetailsSnapshot,
        context_name: str,
    ) -> tuple[JobDetailSection, ...]:
        """Expose the job's exact saved and currently connected ComfyUI servers.

        Args:
            job: Persisted ComfyUI job whose saved endpoint controls execution.
            details: Typed queue details retained for the adapter contract.
            context_name: Caller context retained for the adapter contract; the job's saved context is used.

        Returns:
            One server section placed before generic Inputs.
        """
        try:
            saved_server = build_url(*canonical_endpoint(job.scheme, job.host, job.port))
        except ValueError:
            saved_server = "Invalid saved server address"
        connected = get_connected_endpoint(job.context_name)
        connected_server = build_url(*connected) if connected is not None else "Not connected"
        return (
            JobDetailSection(
                "comfyui_server",
                "ComfyUI server",
                (
                    JobDetailField(
                        "comfyui.saved_server",
                        "Saved server",
                        saved_server,
                        "This exact server address is persisted with the queued generation job.",
                    ),
                    JobDetailField(
                        "comfyui.connected_server",
                        "Connected server",
                        connected_server,
                        "The ComfyUI server currently connected for this job's USD context.",
                    ),
                ),
                JobDetailSectionPlacement.BEFORE_INPUTS,
            ),
        )

    def execute_action(self, action_id: str, job: ComfyUIJob, context_name: str) -> None:
        """Execute one declared graph action against its contributing generation job.

        Args:
            action_id: Stable graph action identifier.
            job: Generation job contributing the action.
            context_name: Caller context retained for the display-adapter contract; the job's saved context is used.

        Raises:
            KeyError: If the action was not declared by this adapter.
        """
        actions = {action.action_id: action for action in self.get_graph_actions(job, context_name)}
        action = actions.get(action_id)
        if action is None:
            raise KeyError(action_id)
        if not action.enabled:
            return
        if action_id == self._FOCUS_ACTION_ID:
            self._focus(job)
            return
        if action_id == self._OPEN_WORKFLOW_ACTION_ID:
            self._open_workflow(job)
            return
        self._confirm_retarget(job)

    def _confirm_retarget(self, job: ComfyUIJob) -> None:
        """Confirm retargeting this graph's queued generation step.

        Args:
            job: Queued generation job to retarget after confirmation.
        """
        core = get_comfyui_core_instance(job.context_name)
        state = core.get_retarget_state(job)
        if not state.can_retarget or state.connected_endpoint is None:
            return
        source = (
            build_url(*state.saved_endpoint) if state.saved_endpoint is not None else "the invalid saved server address"
        )
        destination = build_url(*state.connected_endpoint)
        _TrexMessageDialog(
            f"Use {destination} for this graph instead of {source}?\n\n"
            "Only this graph's waiting ComfyUI generation step will change.",
            "Change ComfyUI Server",
            ok_handler=lambda: self._retarget_job(core, job, state.connected_endpoint),
            ok_label="Change Server",
        )

    @staticmethod
    def _retarget_job(core: ComfyUICore, job: ComfyUIJob, endpoint: Endpoint) -> None:
        """Emit a retarget intent and render the returned core result.

        Args:
            core: Context-qualified ComfyUI core that owns the queued job.
            job: Queued job whose endpoint should be replaced.
            endpoint: Connected endpoint that must still be active when the update occurs.
        """
        try:
            result = core.retarget_job(job, endpoint)
        except (RuntimeError, ValueError) as error:
            carb.log_warn(f"Failed to retarget ComfyUI job {job.job_id}: {error}")
            _TrexMessageDialog(
                "This graph's ComfyUI state changed while Retarget was open. Open Retarget again and try again.",
                "ComfyUI Server Not Changed",
                disable_cancel_button=True,
            )
            return
        if result is ComfyUIRetargetResult.UPDATED:
            return
        if result is ComfyUIRetargetResult.CONNECTION_CHANGED:
            _TrexMessageDialog(
                "The ComfyUI connection changed before this job could be updated. No changes were made.",
                "ComfyUI Connection Changed",
                disable_cancel_button=True,
            )
            return
        _TrexMessageDialog(
            "This job started before its server could be changed. No changes were made.",
            "ComfyUI Server Not Changed",
            disable_cancel_button=True,
        )

    @staticmethod
    def _get_xformable_paths(job: ComfyUIJob) -> list[str]:
        """Return live, effectively visible Xformable owner paths that the viewport can frame.

        Args:
            job: Job containing candidate prim paths.

        Returns:
            Candidate paths that resolve to effectively visible Xformable prims on the stage.

        Raises:
            RuntimeError: If the requested USD context is invalid.
        """
        stage = get_context(job.context_name).get_stage()
        if not stage:
            return []

        return [
            path
            for path in job.prim_paths
            if (prim := stage.GetPrimAtPath(path))
            and prim.IsA(UsdGeom.Xformable)
            and UsdGeom.Imageable(prim).ComputeVisibility() != UsdGeom.Tokens.invisible
        ]

    @staticmethod
    def _get_prim_paths(job: ComfyUIJob) -> list[str]:
        """Return a copy of the job's target prim paths.

        Args:
            job: Job containing owner prim paths or a captured material target.

        Returns:
            Saved owner prim paths, falling back to the captured material target when needed.
        """
        return list(job.prim_paths) or ([job.material_path] if job.material_path else [])

    def _get_open_workflow_state(self, job: ComfyUIJob) -> tuple[bool, str]:
        """Return the enabled state and tooltip for Open Workflow.

        Args:
            job: Job whose saved workflow determines edit availability.

        Returns:
            Enabled state and exact user-facing explanation.
        """
        if is_standalone():
            return False, "Open Workflow is unavailable in the standalone job queue."
        if self._setup_workspace is None or self._workflow_workspace is None:
            return False, "The ComfyUI workflow workspace is unavailable."
        try:
            connected_endpoint = get_connected_endpoint(job.context_name)
        except ADAPTER_ERRORS as error:
            carb.log_warn(f"Could not resolve ComfyUI connection state for queue job {job.job_id}: {error}")
            return False, "ComfyUI connection information is unavailable."
        if connected_endpoint is None:
            return False, "Connect to a ComfyUI server before opening this workflow."
        try:
            core = get_comfyui_core_instance(job.context_name)
        except ADAPTER_ERRORS as error:
            carb.log_warn(f"Could not access ComfyUI for queue job {job.job_id}: {error}")
            return False, "ComfyUI is unavailable, so this workflow cannot be opened."
        try:
            core.get_workflow_request(job)
        except ADAPTER_ERRORS as error:
            carb.log_warn(f"Could not load the saved workflow for queue job {job.job_id}: {error}")
            return False, "The workflow saved with this job is unavailable."
        return True, "Open this graph's workflow and inputs to submit it again."

    def _open_workflow(self, job: ComfyUIJob) -> None:
        """Re-open the ComfyUI submit widget with the graph's original inputs.

        Args:
            job: Job whose workflow and target selection should be restored.
        """
        try:
            if self._setup_workspace is None or self._workflow_workspace is None:
                raise RuntimeError("ComfyUI workspaces are unavailable")
            self._setup_workspace.set_context_name(job.context_name)
            self._workflow_workspace.set_context_name(job.context_name)
            core = get_comfyui_core_instance(job.context_name)
            request = core.get_workflow_request(job)
            core.set_workflow(deepcopy(request.workflow))
            prim_paths = self._get_prim_paths(job)
            if prim_paths:
                ctx = get_context(job.context_name)
                ctx.get_selection().set_selected_prim_paths(prim_paths, True)
            self._workflow_workspace.show_window_fn(True)
        except RuntimeError as error:
            carb.log_warn(f"Failed to edit job: {error}")

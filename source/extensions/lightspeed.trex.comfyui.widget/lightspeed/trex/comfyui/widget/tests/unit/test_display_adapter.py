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

from unittest.mock import MagicMock, call, patch

from lightspeed.trex.comfyui.core.core import ComfyUIRetargetState
from lightspeed.trex.comfyui.core.enums import ComfyUIEventType, ComfyUIRetargetResult
from lightspeed.trex.comfyui.core.events import ComfyUIEventPayload
from lightspeed.trex.comfyui.core.job import ComfyUIJob
from lightspeed.trex.comfyui.core.models import ComfyUIWorkflowRequest, Workflow
from lightspeed.trex.comfyui.widget.display_adapter import ComfyUIDisplayAdapter
from omni.flux.job_queue.core.job import JobProgress
from omni.flux.job_queue.widget.display_adapter_base import JobAction, JobDetailField, JobDetailSection
from omni.flux.job_queue.widget.display_adapter_registry import DisplayAdapterRegistry
from omni.flux.job_queue.widget.enums import DisplayState, JobDetailSectionPlacement
from omni.kit.test import AsyncTestCase
from pxr import UsdGeom


def _request_for_workflow(workflow: Workflow) -> ComfyUIWorkflowRequest:
    """Create one typed ComfyUI workflow request.

    Args:
        workflow: Workflow restored by the display adapter.

    Returns:
        Typed request exposed by the ComfyUI core.
    """
    return ComfyUIWorkflowRequest(
        prompt={},
        input_bindings=(),
        client_id="",
        timeout=300.0,
        output_url="C:/project/assets/ingested/comfyui/test",
        workflow=workflow,
    )


class TestComfyUIDisplayAdapter(AsyncTestCase):
    """Test queue display and interaction behavior for ComfyUI jobs."""

    async def test_state_tooltip_describes_generation_only(self):
        """The producer child describes ComfyUI generation without Apply guidance."""
        # Arrange
        adapter = ComfyUIDisplayAdapter()
        job = ComfyUIJob()

        # Act
        result = (
            adapter.get_state_tooltip(job, DisplayState.IN_PROGRESS, "Technical details"),
            adapter.get_state_tooltip(
                job,
                DisplayState.FAILED,
                "The ComfyUI connection stopped before generation finished. Check the server and try again.",
            ),
            adapter.get_state_tooltip(job, DisplayState.SKIPPED, "This material has no albedo texture."),
        )

        # Assert
        self.assertEqual(
            result,
            (
                "ComfyUI is generating textures.",
                "The ComfyUI connection stopped before generation finished. Check the server and try again.",
                "This material has no albedo texture.",
            ),
        )

    async def test_display_contract_identifies_generation_job(self):
        """The adapter provides stable product-facing identity for the exact generation type."""
        # Arrange
        adapter = ComfyUIDisplayAdapter()
        job = ComfyUIJob(prim_paths=["/World/MeshA", "/World/Group/MeshB"])

        # Act
        result = (
            adapter.name,
            adapter.job_type,
            adapter.get_source_name(job),
            adapter.get_name_display(job),
            adapter.get_name_tooltip(job),
        )

        # Assert
        self.assertEqual(result[0], "comfyui")
        self.assertIs(result[1], ComfyUIJob)
        self.assertEqual(result[2:], ("ComfyUI", "ComfyUI generation", "/World/MeshA\n/World/Group/MeshB"))

    async def test_registers_with_real_exact_type_registry(self):
        """The production registry accepts and resolves the explicit adapter contract."""
        # Arrange
        registry = DisplayAdapterRegistry()
        job = ComfyUIJob()

        # Act
        registry.register(ComfyUIDisplayAdapter)
        adapter = registry.get_adapter(job)

        # Assert
        self.assertIs(type(adapter), ComfyUIDisplayAdapter)

    async def test_visibility_event_refreshes_only_comfyui_schedule_conditions(self):
        """The adapter directly requests a ComfyUI row refresh only for visibility changes."""
        # Arrange
        core_subscription = MagicMock()
        model = MagicMock(context_name="texturecraft")

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance") as get_core,
            patch(
                "lightspeed.trex.comfyui.widget.display_adapter.subscribe_comfyui_event",
                return_value=core_subscription,
            ) as subscribe_event,
        ):
            adapter = ComfyUIDisplayAdapter()
            action_subscription = adapter.subscribe_action_events(model)
            event_callback = subscribe_event.call_args.args[1]
            event_callback(ComfyUIEventPayload("texturecraft", ComfyUIEventType.SETTINGS_CHANGED))
            event_callback(ComfyUIEventPayload("texturecraft", ComfyUIEventType.STAGE_VISIBILITY_CHANGED))

        # Assert
        self.assertIs(action_subscription, core_subscription)
        get_core.assert_called_once_with("texturecraft")
        subscribe_event.assert_called_once()
        self.assertEqual(subscribe_event.call_args.args[0], "texturecraft")
        model.refresh_schedule_conditions.assert_called_once_with({ComfyUIJob})

    async def test_active_labels_use_structured_generation_progress(self):
        """Active graph aggregation receives product-facing generation labels."""
        # Arrange
        job = ComfyUIJob()
        adapter = ComfyUIDisplayAdapter()
        progress = JobProgress(completed=2, total=4, detail="Waiting for ComfyUI")

        # Act
        result = (
            adapter.get_active_status_label(job, progress),
            adapter.get_active_progress_label(job, progress),
            adapter.get_active_progress_label(job, JobProgress(detail="Uploading input")),
        )

        # Assert
        self.assertEqual(result, ("Generating textures", "2 of 4 generation steps", None))

    async def test_waiting_reason_uses_saved_job_context(self):
        """Queue scheduling describes the exact ComfyUI server required by the job."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", scheme="http", host="comfy-a", port=8188)

        # Act
        with patch("lightspeed.trex.comfyui.core.job.get_connected_endpoint", return_value=None):
            result = ComfyUIDisplayAdapter().get_waiting_reason(job, "wrong-context")

        # Assert
        self.assertEqual(result, "Connect to the ComfyUI server at http://comfy-a:8188 to run this job.")

    async def test_detail_sections_distinguish_saved_and_connected_servers(self):
        """Details distinguish the persisted execution target from the live connection."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", scheme="http", host="saved.example.com", port=8188)

        # Act
        with patch(
            "lightspeed.trex.comfyui.widget.display_adapter.get_connected_endpoint",
            return_value=("https", "connected.example.com", 443),
        ):
            result = ComfyUIDisplayAdapter().get_detail_sections(job, MagicMock(), "wrong-context")

        # Assert
        self.assertEqual(
            result,
            (
                JobDetailSection(
                    "comfyui_server",
                    "ComfyUI server",
                    (
                        JobDetailField(
                            "comfyui.saved_server",
                            "Saved server",
                            "http://saved.example.com:8188",
                            "This exact server address is persisted with the queued generation job.",
                        ),
                        JobDetailField(
                            "comfyui.connected_server",
                            "Connected server",
                            "https://connected.example.com:443",
                            "The ComfyUI server currently connected for this job's USD context.",
                        ),
                    ),
                    JobDetailSectionPlacement.BEFORE_INPUTS,
                ),
            ),
        )

    @patch("lightspeed.trex.comfyui.widget.display_adapter._get_active_viewport")
    @patch.object(ComfyUIDisplayAdapter, "_get_xformable_paths", return_value=["/World/Mesh"])
    @patch.object(ComfyUIDisplayAdapter, "_get_open_workflow_state", return_value=(True, "Open this workflow."))
    async def test_graph_actions_are_complete_and_stably_ordered(
        self, _mock_open_state, _mock_paths, _mock_get_active_viewport
    ):
        """The graph owns Focus, Open Workflow, and Retarget in stable order.

        Args:
            _mock_open_state: Patched workflow availability lookup.
            _mock_paths: Patched viewport target lookup.
            _mock_get_active_viewport: Patched active-viewport lookup.
        """
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", scheme="http", host="old.example.com", port=8188)
        core = MagicMock()
        core.get_retarget_state.return_value = ComfyUIRetargetState(
            is_queued=True,
            saved_endpoint=("http", "old.example.com", 8188),
            connected_endpoint=("https", "new.example.com", 443),
        )

        # Act
        with patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance", return_value=core):
            actions = ComfyUIDisplayAdapter().get_graph_actions(job, "wrong-context")

        # Assert
        self.assertEqual(
            [(action.action_id, action.label, action.style_name, action.enabled) for action in actions],
            [
                ("focus_in_viewport", "Focus in Viewport", "FocusInViewport", True),
                ("open_workflow", "Open Workflow", "EditJob", True),
                ("retarget_comfyui", "Retarget", "RetargetComfyUI", True),
            ],
        )
        self.assertEqual(
            actions[2].tooltip,
            "Use https://new.example.com:443 instead of http://old.example.com:8188 for this graph's generation step.",
        )
        self.assertEqual(ComfyUIDisplayAdapter().get_job_actions(job, ""), ())

    async def test_open_workflow_action_disables_when_saved_input_is_unavailable(self):
        """A graph without its saved workflow cannot advertise Open Workflow."""
        # Arrange
        job = ComfyUIJob()
        core = MagicMock()
        core.get_workflow_request.side_effect = RuntimeError("saved workflow unavailable")

        # Act
        with (
            patch.object(ComfyUIDisplayAdapter, "_setup_workspace", MagicMock()),
            patch.object(ComfyUIDisplayAdapter, "_workflow_workspace", MagicMock()),
            patch(
                "lightspeed.trex.comfyui.widget.display_adapter.get_connected_endpoint",
                return_value=("http", "127.0.0.1", 8188),
            ),
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance", return_value=core),
        ):
            action = ComfyUIDisplayAdapter()._get_open_workflow_action(job)

        # Assert
        self.assertFalse(action.enabled)
        self.assertEqual(action.tooltip, "The workflow saved with this job is unavailable.")

    async def test_open_workflow_action_disables_when_comfyui_is_disconnected(self):
        """A disconnected context cannot advertise an editor that has no server."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft")
        core = MagicMock()
        core.get_workflow_request.return_value = _request_for_workflow(Workflow(name="Saved workflow", api={}))

        # Act
        with (
            patch.object(ComfyUIDisplayAdapter, "_setup_workspace", MagicMock()),
            patch.object(ComfyUIDisplayAdapter, "_workflow_workspace", MagicMock()),
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_connected_endpoint", return_value=None),
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance", return_value=core),
        ):
            action = ComfyUIDisplayAdapter()._get_open_workflow_action(job)

        # Assert
        self.assertFalse(action.enabled)
        self.assertEqual(action.tooltip, "Connect to a ComfyUI server before opening this workflow.")

    async def test_open_workflow_action_explains_when_comfyui_is_unavailable(self):
        """A missing ComfyUI runtime keeps the action visible with its exact disabled reason."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft")

        # Act
        with (
            patch.object(ComfyUIDisplayAdapter, "_setup_workspace", MagicMock()),
            patch.object(ComfyUIDisplayAdapter, "_workflow_workspace", MagicMock()),
            patch(
                "lightspeed.trex.comfyui.widget.display_adapter.get_connected_endpoint",
                return_value=("http", "127.0.0.1", 8188),
            ),
            patch(
                "lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance",
                side_effect=RuntimeError("ComfyUI unavailable"),
            ),
        ):
            action = ComfyUIDisplayAdapter()._get_open_workflow_action(job)

        # Assert
        self.assertFalse(action.enabled)
        self.assertEqual(action.tooltip, "ComfyUI is unavailable, so this workflow cannot be opened.")

    async def test_open_workflow_action_enables_when_connected_with_saved_input(self):
        """A connected context with a saved workflow exposes the graph editor action."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft")
        core = MagicMock()
        core.get_workflow_request.return_value = _request_for_workflow(Workflow(name="Saved workflow", api={}))

        # Act
        with (
            patch.object(ComfyUIDisplayAdapter, "_setup_workspace", MagicMock()),
            patch.object(ComfyUIDisplayAdapter, "_workflow_workspace", MagicMock()),
            patch(
                "lightspeed.trex.comfyui.widget.display_adapter.get_connected_endpoint",
                return_value=("http", "127.0.0.1", 8188),
            ),
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance", return_value=core),
        ):
            action = ComfyUIDisplayAdapter()._get_open_workflow_action(job)

        # Assert
        self.assertTrue(action.enabled)
        self.assertEqual(action.tooltip, "Open this graph's workflow and inputs to submit it again.")

    @patch("lightspeed.trex.comfyui.widget.display_adapter._get_active_viewport")
    @patch("lightspeed.trex.comfyui.widget.display_adapter.get_context")
    async def test_focus_action_uses_job_context_and_only_live_xformable_owner_paths(
        self, mock_get_context, _mock_get_active_viewport
    ):
        """Focus uses the job's context and excludes hidden descendants and non-Xformable owners.

        Args:
            mock_get_context: Patched USD context lookup.
            _mock_get_active_viewport: Patched active-viewport lookup.
        """
        # Arrange
        stage = mock_get_context.return_value.get_stage.return_value
        hidden_object = MagicMock()
        visible_object = MagicMock()
        scope = MagicMock()
        for prim in (hidden_object, visible_object):
            prim.IsA.return_value = True
        scope.IsA.return_value = False
        stage.GetPrimAtPath.side_effect = (hidden_object, visible_object, scope)
        hidden_imageable = MagicMock()
        hidden_imageable.ComputeVisibility.return_value = UsdGeom.Tokens.invisible
        visible_imageable = MagicMock()
        visible_imageable.ComputeVisibility.return_value = UsdGeom.Tokens.inherited
        job = ComfyUIJob(
            context_name="saved-context",
            prim_paths=["/World/Hidden/Object", "/World/VisibleObject", "/World/Scope"],
            material_path="/World/Looks/Material",
        )

        # Act
        with (
            patch(
                "lightspeed.trex.comfyui.widget.display_adapter.UsdGeom.Imageable",
                side_effect=(hidden_imageable, visible_imageable),
            ),
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance") as get_core,
        ):
            get_core.return_value.get_retarget_state.return_value = ComfyUIRetargetState(
                is_queued=False,
                saved_endpoint=None,
                connected_endpoint=None,
            )
            action = ComfyUIDisplayAdapter().get_graph_actions(job, "viewport-context")[0]

        # Assert
        self.assertTrue(action.enabled)
        self.assertEqual(action.tooltip, "Focus this visible object in the viewport.")
        mock_get_context.assert_called_once_with("saved-context")

    @patch("lightspeed.trex.comfyui.widget.display_adapter._get_active_viewport")
    @patch("lightspeed.trex.comfyui.widget.display_adapter.get_context")
    async def test_focus_action_disables_when_all_owner_paths_are_hidden(
        self, mock_get_context, _mock_get_active_viewport
    ):
        """Focus clearly explains when no saved owner is effectively visible.

        Args:
            mock_get_context: Patched USD context lookup.
            _mock_get_active_viewport: Patched active-viewport lookup.
        """
        # Arrange
        hidden_object = MagicMock()
        hidden_object.IsA.return_value = True
        mock_get_context.return_value.get_stage.return_value.GetPrimAtPath.return_value = hidden_object
        hidden_imageable = MagicMock()
        hidden_imageable.ComputeVisibility.return_value = UsdGeom.Tokens.invisible

        # Act
        with patch("lightspeed.trex.comfyui.widget.display_adapter.UsdGeom.Imageable", return_value=hidden_imageable):
            action = ComfyUIDisplayAdapter()._get_focus_action(
                ComfyUIJob(context_name="saved-context", prim_paths=["/World/Hidden/Object"])
            )

        # Assert
        self.assertFalse(action.enabled)
        self.assertEqual(action.tooltip, "No visible object is available to focus in the viewport.")

    @patch("lightspeed.trex.comfyui.widget.display_adapter._get_active_viewport")
    @patch("lightspeed.trex.comfyui.widget.display_adapter.get_context")
    @patch.object(ComfyUIDisplayAdapter, "_get_xformable_paths", return_value=["/World/A", "/World/B"])
    async def test_focus_cycles_selection_and_frames_viewport(
        self,
        _mock_paths,
        mock_get_context,
        mock_get_active_viewport,
    ):
        """Repeated Focus cycles one target at a time through the active Remix viewport.

        Args:
            _mock_paths: Patched xformable-path lookup.
            mock_get_context: Patched USD context lookup.
            mock_get_active_viewport: Patched active-viewport lookup.
        """
        # Arrange
        selection = mock_get_context.return_value.get_selection.return_value
        selected_paths: list[str] = []
        selection.get_selected_prim_paths.side_effect = lambda: list(selected_paths)
        selection.set_selected_prim_paths.side_effect = lambda paths, _replace: selected_paths.__setitem__(
            slice(None), paths
        )
        viewport = mock_get_active_viewport.return_value
        adapter = ComfyUIDisplayAdapter()
        job = ComfyUIJob(context_name="saved-context")
        action = adapter._get_focus_action(job)
        mock_get_active_viewport.reset_mock()

        # Act
        with patch.object(adapter, "get_graph_actions", return_value=(action,)):
            for _ in range(3):
                adapter.execute_action(action.action_id, job, "caller-context")

        # Assert
        self.assertEqual(
            selection.set_selected_prim_paths.call_args_list,
            [call(["/World/A"], True), call(["/World/B"], True), call(["/World/A"], True)],
        )
        self.assertEqual(mock_get_active_viewport.call_args_list, [call(), call(), call()])
        self.assertEqual(
            viewport.frame_viewport_selection.call_args_list,
            [call(["/World/A"]), call(["/World/B"]), call(["/World/A"])],
        )
        self.assertEqual(
            action.tooltip,
            "Focus one of 2 visible objects in the viewport. Repeated clicks cycle through the visible objects.",
        )
        self.assertEqual(_mock_paths.call_args_list, [call(job)] * 4)
        self.assertEqual(mock_get_context.call_args_list, [call("saved-context")] * 3)

    @patch("lightspeed.trex.comfyui.widget.display_adapter._get_active_viewport", return_value=None)
    @patch("lightspeed.trex.comfyui.widget.display_adapter.get_context")
    @patch.object(ComfyUIDisplayAdapter, "_get_xformable_paths", return_value=["/World/A"])
    async def test_focus_without_active_viewport_does_not_change_stage_selection(
        self,
        _mock_paths,
        mock_get_context,
        _mock_get_active_viewport,
    ):
        """Focus does not degrade into a Stage Manager selection-only action.

        Args:
            _mock_paths: Patched xformable-path lookup.
            mock_get_context: Patched USD context lookup.
            _mock_get_active_viewport: Patched active-viewport lookup.
        """
        # Arrange
        selection = mock_get_context.return_value.get_selection.return_value
        adapter = ComfyUIDisplayAdapter()

        # Act
        adapter._focus(ComfyUIJob(context_name="saved-context"))

        # Assert
        selection.set_selected_prim_paths.assert_not_called()

    @patch("lightspeed.trex.comfyui.widget.display_adapter._get_active_viewport", return_value=None)
    @patch("lightspeed.trex.comfyui.widget.display_adapter.is_standalone", return_value=False)
    async def test_focus_action_explains_missing_active_viewport(self, _mock_standalone, _mock_get_active_viewport):
        """Focus stays visible but disabled when the app has no active Remix viewport.

        Args:
            _mock_standalone: Patched standalone-app lookup.
            _mock_get_active_viewport: Patched active-viewport lookup.
        """
        # Arrange
        adapter = ComfyUIDisplayAdapter()

        # Act
        action = adapter._get_focus_action(ComfyUIJob())

        # Assert
        self.assertFalse(action.enabled)
        self.assertEqual(action.tooltip, "Focus in Viewport requires an active Remix viewport.")

    async def test_retarget_action_disables_when_graph_cannot_change_server(self):
        """Retarget explains why a graph cannot change server in each stable condition."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", scheme="https", host="new.example.com", port=443)
        core = MagicMock()
        core.get_retarget_state.return_value = ComfyUIRetargetState(
            is_queued=False,
            saved_endpoint=("https", "new.example.com", 443),
            connected_endpoint=("https", "new.example.com", 443),
        )

        # Act
        with patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance", return_value=core):
            action = ComfyUIDisplayAdapter()._get_retarget_action(job)

        # Assert
        self.assertFalse(action.enabled)
        self.assertEqual(
            action.tooltip,
            "Retarget is available only while generation is waiting in the queue. This graph targets https://new.example.com:443.",
        )

    async def test_graph_actions_remain_visible_when_retarget_state_is_unavailable(self):
        """One unavailable action state cannot remove the graph's other stable action slots."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft")
        core = MagicMock()
        core.get_retarget_state.side_effect = RuntimeError("ComfyUI is unavailable")

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance", return_value=core),
            patch.object(ComfyUIDisplayAdapter, "_get_focus_action") as get_focus,
            patch.object(ComfyUIDisplayAdapter, "_get_open_workflow_action") as get_open_workflow,
        ):
            get_focus.return_value = JobAction("focus_in_viewport", "Focus", "FocusInViewport", "Focus.", True)
            get_open_workflow.return_value = JobAction("open_workflow", "Open", "EditJob", "Open.", True)
            actions = ComfyUIDisplayAdapter().get_graph_actions(job, "texturecraft")

        # Assert
        self.assertEqual(
            [action.action_id for action in actions],
            ["focus_in_viewport", "open_workflow", "retarget_comfyui"],
        )
        self.assertFalse(actions[-1].enabled)
        self.assertEqual(actions[-1].tooltip, "ComfyUI is unavailable, so this graph cannot be retargeted.")

    async def test_execute_retarget_action_confirms_graph_only_change(self):
        """Retarget confirms both endpoints and identifies the exact graph step that changes."""
        # Arrange
        adapter = ComfyUIDisplayAdapter()
        job = ComfyUIJob(context_name="texturecraft", scheme="http", host="old.example.com", port=8188)
        action = JobAction("retarget_comfyui", "Retarget", "RetargetComfyUI", "Change server.", True)
        core = MagicMock()
        core.get_retarget_state.return_value = ComfyUIRetargetState(
            is_queued=True,
            saved_endpoint=("http", "old.example.com", 8188),
            connected_endpoint=("https", "new.example.com", 443),
        )

        # Act
        with (
            patch.object(adapter, "get_graph_actions", return_value=(action,)),
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance", return_value=core),
            patch("lightspeed.trex.comfyui.widget.display_adapter._TrexMessageDialog") as dialog,
        ):
            adapter.execute_action(action.action_id, job, "wrong-context")

        # Assert
        message = dialog.call_args.args[0]
        self.assertIn("http://old.example.com:8188", message)
        self.assertIn("https://new.example.com:443", message)
        self.assertIn("Only this graph's waiting ComfyUI generation step will change.", message)
        self.assertEqual(dialog.call_args.args[1], "Change ComfyUI Server")
        self.assertEqual(dialog.call_args.kwargs["ok_label"], "Change Server")

    async def test_execute_action_rejects_undeclared_identifier(self):
        """The adapter never guesses how to execute an unknown action identifier."""
        # Arrange
        adapter = ComfyUIDisplayAdapter()
        job = ComfyUIJob()

        # Act
        with (
            patch.object(adapter, "get_graph_actions", return_value=()),
            self.assertRaises(KeyError) as error,
        ):
            adapter.execute_action("unknown", job, "")

        # Assert
        self.assertEqual(error.exception.args, ("unknown",))

    async def test_retarget_job_emits_core_intent_with_confirmed_endpoint(self):
        """A confirmed retarget emits the exact job and endpoint to the core."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", scheme="http", host="old.example.com", port=8188)
        core = MagicMock()
        core.retarget_job.return_value = ComfyUIRetargetResult.UPDATED

        # Act
        ComfyUIDisplayAdapter()._retarget_job(core, job, ("https", "new.example.com", 443))

        # Assert
        core.retarget_job.assert_called_once_with(job, ("https", "new.example.com", 443))

    async def test_retarget_job_rejects_connection_change_after_confirmation(self):
        """A changed connection cannot silently replace the endpoint shown in the dialog."""
        # Arrange
        core = MagicMock()
        core.retarget_job.return_value = ComfyUIRetargetResult.CONNECTION_CHANGED
        displayed_endpoint = ("https", "new.example.com", 443)

        # Act
        with patch("lightspeed.trex.comfyui.widget.display_adapter._TrexMessageDialog") as dialog:
            job = ComfyUIJob()
            ComfyUIDisplayAdapter()._retarget_job(core, job, displayed_endpoint)

        # Assert
        core.retarget_job.assert_called_once_with(job, displayed_endpoint)
        self.assertEqual(dialog.call_args.args[1], "ComfyUI Connection Changed")

    async def test_retarget_job_reports_stale_dialog_errors(self):
        """A stale Retarget dialog reports declared core failures instead of leaking callback errors."""
        cases = (RuntimeError("core destroyed"), ValueError("wrong context"))

        for error in cases:
            with self.subTest(error=type(error).__name__):
                # Arrange
                core = MagicMock()
                core.retarget_job.side_effect = error
                job = ComfyUIJob()

                # Act
                with (
                    patch("lightspeed.trex.comfyui.widget.display_adapter.carb.log_warn") as log_warn,
                    patch("lightspeed.trex.comfyui.widget.display_adapter._TrexMessageDialog") as dialog,
                ):
                    ComfyUIDisplayAdapter()._retarget_job(core, job, ("https", "new.example.com", 443))

                # Assert
                log_warn.assert_called_once_with(f"Failed to retarget ComfyUI job {job.job_id}: {error}")
                self.assertEqual(dialog.call_args.args[1], "ComfyUI Server Not Changed")

    @patch("lightspeed.trex.comfyui.widget.display_adapter.get_context")
    @patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance")
    async def test_open_workflow_restores_independent_values_and_selection(self, mock_get_core, mock_get_context):
        """Open Workflow restores a copied request, its context, and its saved target selection.

        Args:
            mock_get_core: Patched ComfyUI core lookup.
            mock_get_context: Patched USD context lookup.
        """
        # Arrange
        workflow = Workflow(name="Upscale", api={"1": {"inputs": {"strength": 0.5}}})
        job = ComfyUIJob(context_name="texturecraft", prim_paths=["/World/Mesh", "/World/Mesh2"])
        setup_workspace = MagicMock()
        workflow_workspace = MagicMock()
        adapter = ComfyUIDisplayAdapter()
        action = JobAction("open_workflow", "Open Workflow", "EditJob", "Open this workflow.", True)
        mock_get_core.return_value.get_workflow_request.return_value = _request_for_workflow(workflow)

        # Act
        with (
            patch.object(ComfyUIDisplayAdapter, "_setup_workspace", setup_workspace),
            patch.object(ComfyUIDisplayAdapter, "_workflow_workspace", workflow_workspace),
            patch.object(adapter, "get_graph_actions", return_value=(action,)),
        ):
            adapter.execute_action(action.action_id, job, "wrong-context")

        # Assert
        restored_workflow = mock_get_core.return_value.set_workflow.call_args.args[0]
        self.assertEqual(restored_workflow, workflow)
        self.assertIsNot(restored_workflow, workflow)
        setup_workspace.set_context_name.assert_called_once_with("texturecraft")
        workflow_workspace.set_context_name.assert_called_once_with("texturecraft")
        workflow_workspace.show_window_fn.assert_called_once_with(True)
        mock_get_context.return_value.get_selection.return_value.set_selected_prim_paths.assert_called_once_with(
            ["/World/Mesh", "/World/Mesh2"], True
        )

    async def test_open_workflow_does_not_mutate_state_without_workspaces(self):
        """Unavailable UI cannot leave the core workflow or selection partially changed."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", prim_paths=["/World/Mesh"])

        # Act
        with (
            patch.object(ComfyUIDisplayAdapter, "_setup_workspace", None),
            patch.object(ComfyUIDisplayAdapter, "_workflow_workspace", None),
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance") as get_core,
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_context") as get_context,
            patch("lightspeed.trex.comfyui.widget.display_adapter.carb.log_warn") as log_warn,
        ):
            ComfyUIDisplayAdapter()._open_workflow(job)

        # Assert
        get_core.assert_not_called()
        get_context.assert_not_called()
        log_warn.assert_called_once_with("Failed to edit job: ComfyUI workspaces are unavailable")

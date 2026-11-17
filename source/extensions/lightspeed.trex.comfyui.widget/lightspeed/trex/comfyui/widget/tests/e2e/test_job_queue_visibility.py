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

import asyncio
import json
import pathlib
from unittest.mock import patch

import omni.usd
from lightspeed.common.constants import WindowNames
from lightspeed.trex.comfyui.core import get_comfyui_core_instance
from lightspeed.trex.comfyui.core.api import ComfyUIAPI
from lightspeed.trex.comfyui.widget.display_adapter import ComfyUIDisplayAdapter
from lightspeed.trex.contexts.setup import Contexts
from omni import ui
from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.core.enums import JobState
from omni.flux.job_queue.core.execute import JobExecutor
from omni.flux.job_queue.core.models import UsageSnapshot
from omni.flux.job_queue.core.settings import JobQueueSettings
from omni.flux.utils.tests.context_managers import open_test_project
from omni.flux.utils.widget.resources import get_test_data
from omni.kit import ui_test
from omni.kit.notification_manager import NotificationStatus, destroy_all_notifications, get_all_notifications
from omni.kit.test import AsyncTestCase
from pxr import Sdf, UsdShade
from requests import Response

__all__ = ("TestJobQueueVisibilityE2E",)

_CONTEXT_NAME = Contexts.STAGE_CRAFT.value
_PROJECT_EXTENSION = "lightspeed.trex.app.resources"
_TEST_STAGE = "usd/project_example/combined.usda"
_WIDGET_EXTENSION = "lightspeed.trex.comfyui.widget"
_SERVER_RESPONSES = "comfyui_pbrify_responses.json"

_SELECTED_MATERIAL = "/RootNode/Looks/mat_BC868CE5A075ABB1"
_SHADER_PATH = f"{_SELECTED_MATERIAL}/Shader"
_WORKFLOW_LABEL = "PBRify"
_COMPLETION_TIMEOUT = 30

# Texture inputs that the PBR workflow replaces, with the ingested project textures they start from.
_AUTHORED_TEXTURE_INPUTS = (
    ("height_texture", "sources/textures/ingested/16px_Diffuse.dds"),
    ("normalmap_texture", "sources/textures/ingested/16px_normal_OTH_Normal.n.rtex.dds"),
    ("reflectionroughness_texture", "sources/textures/ingested/16px_metallic.m.rtex.dds"),
)


class TestJobQueueVisibilityE2E(AsyncTestCase):
    """Show ComfyUI submissions in the registered Job Queue workspace window."""

    async def setUp(self) -> None:
        """Hold queue dispatch so no job executes, and record the graphs that already exist."""
        self._settings = JobQueueSettings()
        self._restore_scheduler = self._settings.scheduler_enabled
        self._restore_auto_apply = self._settings.auto_apply
        self._settings.set_scheduler_enabled(False)
        self._settings.set_auto_apply(False)
        self._known_graph_ids = {snapshot.graph_id for snapshot in get_job_queue().get_graph_snapshots()}
        destroy_all_notifications()

    async def tearDown(self) -> None:
        """Close every opened window, remove submitted graphs, and restore queue dispatch."""
        try:
            for title in (
                WindowNames.JOB_QUEUE.value,
                WindowNames.COMFYUI_WORKFLOW.value,
                WindowNames.COMFYUI_SETUP.value,
            ):
                ui.Workspace.show_window(title, False)
            await get_comfyui_core_instance(_CONTEXT_NAME).shutdown()
            workspace = ComfyUIDisplayAdapter._workflow_workspace
            if workspace is not None and workspace._content is not None:
                submissions = workspace._content._submissions
                submissions.cancel_all()
                await asyncio.gather(*submissions._tasks.values(), return_exceptions=True)
            submitted = [
                graph.graph_id
                for graph in get_job_queue().get_graph_snapshots()
                if graph.graph_id not in self._known_graph_ids
            ]
            if submitted:
                get_job_queue().delete_graphs(submitted, UsageSnapshot())
            destroy_all_notifications()
        finally:
            self._settings.set_auto_apply(self._restore_auto_apply)
            self._settings.set_scheduler_enabled(self._restore_scheduler)

    async def test_comfyui_submission_appears_in_reopened_job_queue_window(self) -> None:
        """Show a submitted job and its result in the reopened queue with captured ComfyUI HTTP responses."""
        queue = get_job_queue()
        queue_title = WindowNames.JOB_QUEUE.value
        setup_title = WindowNames.COMFYUI_SETUP.value
        workflow_title = WindowNames.COMFYUI_WORKFLOW.value
        run_query = f"{workflow_title}//Frame/**/Button[*].identifier=='ComfyWorkflowRun'"
        responses = json.loads(
            pathlib.Path(get_test_data(_SERVER_RESPONSES, ext_name=_WIDGET_EXTENSION)).read_text(encoding="utf-8")
        )
        image = pathlib.Path(
            get_test_data("textures/Normal_Map_Test_DirectX.png", ext_name="omni.flux.utils.octahedral_converter")
        ).read_bytes()
        responses.update(
            {
                "/view": image,
                "/prompt": {"prompt_id": "notification-workflow"},
                "/queue": {"queue_running": [], "queue_pending": []},
                "/interrupt": {},
                "/history/notification-workflow": {
                    "notification-workflow": {
                        "status": {"completed": True},
                        "outputs": {
                            node: {"images": [{"filename": f"{node}.png", "type": "output"}]}
                            for node in ("178", "179", "180", "181")
                        },
                    }
                },
            }
        )

        async def serve_captured_response(_api, _method, endpoint, **kwargs):
            """Return external HTTP responses through the real client."""
            payload = (
                {"name": kwargs["files"]["image"][0], **kwargs["data"]}
                if endpoint == "/upload/image"
                else responses[endpoint]
            )
            response = Response()
            response.status_code = 200
            response._content_consumed = True
            response._content = payload if endpoint == "/view" else json.dumps(payload).encode("utf-8")
            return response

        async with open_test_project(
            _TEST_STAGE,
            ext_name=_PROJECT_EXTENSION,
            context_name=_CONTEXT_NAME,
        ) as project_url:
            context = omni.usd.get_context(_CONTEXT_NAME)

            # Author the PBR texture inputs that this workflow replaces on the selected material.
            shader = UsdShade.Shader.Get(context.get_stage(), _SHADER_PATH)
            for input_name, texture_path in _AUTHORED_TEXTURE_INPUTS:
                shader.CreateInput(input_name, Sdf.ValueTypeNames.Asset).Set(
                    Sdf.AssetPath(f"{project_url.parent_url}/{texture_path}")
                )

            # A layout opens the Job Queue window, hides it, and opens it again before any submission.
            for visible in (True, False, True):
                ui.Workspace.show_window(queue_title, visible)
                await ui_test.human_delay()

            # Connect through Setup so the workflow picker can load the captured service catalog.
            with patch.object(ComfyUIAPI, "_request", new=serve_captured_response):
                ui.Workspace.show_window(setup_title, True)
                connect_button = await ui_test.find_with_retry(
                    f"{setup_title}//Frame/**/Button[*].identifier=='ComfySetupConnect'"
                )
                await connect_button.click()
                core = get_comfyui_core_instance(_CONTEXT_NAME)
                async with asyncio.timeout(_COMPLETION_TIMEOUT):
                    while not core.is_connected:
                        await ui_test.human_delay()
                # Select PBRify through the picker so its inputs enable Run in the workflow panel.
                ui.Workspace.show_window(workflow_title, True)
                picker = await ui_test.find_with_retry(
                    f"{workflow_title}//Frame/**/SectionedComboBox[*].identifier=='ComfyWorkflowPicker'"
                )
                await picker.click()
                entries = ui_test.find_all("SectionedComboPopup//Frame/**/Label[*].name=='SectionedComboItemLabel'")
                entry = next(candidate for candidate in entries if candidate.widget.text == _WORKFLOW_LABEL)
                await entry.click()
                self.assertTrue(ComfyUIDisplayAdapter._workflow_workspace.get_window().focused)
                async with asyncio.timeout(_COMPLETION_TIMEOUT):
                    while not (ui_test.find(run_query) and ui_test.find(run_query).widget.enabled):
                        await ui_test.human_delay()

                # Run the selected material through the actual UI, queue, and result notification.
                context.get_selection().set_selected_prim_paths([_SELECTED_MATERIAL], True)
                await ui_test.find(run_query).click()
                async with asyncio.timeout(_COMPLETION_TIMEOUT):
                    while not get_all_notifications() or not ui_test.find(run_query).widget.enabled:
                        await ui_test.human_delay()
                (notification,) = get_all_notifications()
                self.assertEqual(notification.info.text, "Submitted 1 job(s) to the job queue.")
                self.assertEqual(notification.info.status, NotificationStatus.INFO)
                (graph,) = [
                    graph for graph in queue.get_graph_snapshots() if graph.graph_id not in self._known_graph_ids
                ]
                self.assertEqual(queue.get_job(graph.jobs[0].job_id).material_path, _SELECTED_MATERIAL)
                self.assertIsNotNone(
                    await ui_test.find_with_retry(
                        f"{queue_title}//Frame/**/Image[*].identifier=='queue_graph_drag_handle_{graph.graph_id}'"
                    )
                )
                # Complete the generation job and expect one shared result notification before Apply runs.
                destroy_all_notifications()
                claimed_jobs = queue.claim_runnable_jobs()
                try:
                    self.assertIn(graph.jobs[0].job_id, claimed_jobs)
                    await JobExecutor(queue).execute(graph.jobs[0].job_id)
                finally:
                    queue.release_scheduled_jobs(claimed_jobs)
                async with asyncio.timeout(_COMPLETION_TIMEOUT):
                    while not get_all_notifications():
                        await ui_test.human_delay()
                self.assertIs(queue.get_job_snapshot(graph.jobs[0].job_id).state, JobState.DONE)
                self.assertEqual([item.info.text for item in get_all_notifications()], ["PBRify: DONE"])
                self.assertEqual(get_all_notifications()[0].info.status, NotificationStatus.INFO)

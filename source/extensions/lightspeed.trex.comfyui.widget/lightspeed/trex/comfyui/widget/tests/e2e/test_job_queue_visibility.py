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

import json
import pathlib
import time
from unittest.mock import patch

import omni.usd
from lightspeed.common.constants import WindowNames
from lightspeed.trex.comfyui.core.api import ComfyUIAPI
from lightspeed.trex.contexts.setup import Contexts
from omni import ui
from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.core.settings import JobQueueSettings
from omni.flux.utils.tests.context_managers import open_test_project
from omni.flux.utils.widget.resources import get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from pxr import Sdf, UsdShade

__all__ = ("TestJobQueueVisibilityE2E",)

_CONTEXT_NAME = Contexts.STAGE_CRAFT.value
_PROJECT_EXTENSION = "lightspeed.trex.app.resources"
_TEST_STAGE = "usd/project_example/combined.usda"
_WIDGET_EXTENSION = "lightspeed.trex.comfyui.widget"
_SERVER_RESPONSES = "comfyui_pbrify_responses.json"

_SELECTED_MATERIAL = "/RootNode/Looks/mat_BC868CE5A075ABB1"
_SHADER_PATH = f"{_SELECTED_MATERIAL}/Shader"
_WORKFLOW_LABEL = "PBRify"

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
        self._settings.set_scheduler_enabled(False)
        self._known_graph_ids = {snapshot.graph_id for snapshot in get_job_queue().get_graph_snapshots()}

    async def tearDown(self) -> None:
        """Close every opened window, remove submitted graphs, and restore queue dispatch."""
        for title in (WindowNames.JOB_QUEUE.value, WindowNames.COMFYUI_WORKFLOW.value, WindowNames.COMFYUI_SETUP.value):
            ui.Workspace.show_window(title, False)
        await ui_test.wait_n_updates(2)
        queue = get_job_queue()
        submitted = [
            snapshot.graph_id
            for snapshot in queue.get_graph_snapshots()
            if snapshot.graph_id not in self._known_graph_ids
        ]
        if submitted:
            queue.delete_graphs(submitted)
        self._settings.set_scheduler_enabled(self._restore_scheduler)

    async def test_comfyui_submission_appears_in_reopened_job_queue_window(self) -> None:
        """A ComfyUI submission shows in the Job Queue window after a layout reopens that window."""
        queue_title = WindowNames.JOB_QUEUE.value
        setup_title = WindowNames.COMFYUI_SETUP.value
        workflow_title = WindowNames.COMFYUI_WORKFLOW.value
        run_query = f"{workflow_title}//Frame/**/Button[*].identifier=='ComfyWorkflowRun'"
        responses = json.loads(
            pathlib.Path(get_test_data(_SERVER_RESPONSES, ext_name=_WIDGET_EXTENSION)).read_text(encoding="utf-8")
        )

        async def serve_captured_response(_api, _method, endpoint, **_kwargs):
            """Answer one client request with a captured real ComfyUI response."""
            self.assertIn(endpoint, responses, f"No captured ComfyUI response for {endpoint}")
            return responses[endpoint]

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
            ui.Workspace.show_window(queue_title, True)
            await ui_test.wait_n_updates(3)
            ui.Workspace.show_window(queue_title, False)
            await ui_test.wait_n_updates(2)
            ui.Workspace.show_window(queue_title, True)
            await ui_test.wait_n_updates(3)

            with patch.object(ComfyUIAPI, "_send_request", new=serve_captured_response):
                # Connect to the ComfyUI server through the real Setup window control.
                ui.Workspace.show_window(setup_title, True)
                await ui_test.wait_n_updates(3)
                connect_button = ui_test.find(f"{setup_title}//Frame/**/Button[*].identifier=='ComfySetupConnect'")
                self.assertIsNotNone(connect_button)
                await connect_button.click()
                await ui_test.wait_n_updates(20)

                # Select the captured material of the report.
                ui.Workspace.show_window(workflow_title, True)
                await ui_test.wait_n_updates(5)
                context.get_selection().set_selected_prim_paths([_SELECTED_MATERIAL], True)

                # Select the workflow of the report in the real picker popup.
                picker = ui_test.find(
                    f"{workflow_title}//Frame/**/SectionedComboBox[*].identifier=='ComfyWorkflowPicker'"
                )
                self.assertIsNotNone(picker, "The Workflow window stayed disconnected, so no workflow was selectable.")
                await picker.click()
                await ui_test.human_delay()
                entries = ui_test.find_all("SectionedComboPopup//Frame/**/Label[*].name=='SectionedComboItemLabel'")
                entry = next(candidate for candidate in entries if candidate.widget.text == _WORKFLOW_LABEL)
                await entry.click()
                await ui_test.human_delay()

                # Run the workflow once the real button reports that submission can start.
                run_button = ui_test.find(run_query)
                for _ in range(60):
                    run_button = ui_test.find(run_query)
                    if run_button is not None and run_button.widget.enabled:
                        break
                    await ui_test.wait_n_updates(5)
                self.assertIsNotNone(run_button)
                self.assertTrue(run_button.widget.enabled, f"Run stayed disabled: {run_button.widget.tooltip}")
                await run_button.click()

                # The submission reaches the durable queue that the Job Queue window reads.
                submitted = []
                deadline = time.monotonic() + 60.0
                while time.monotonic() < deadline:
                    submitted = [
                        snapshot
                        for snapshot in get_job_queue().get_graph_snapshots()
                        if snapshot.graph_id not in self._known_graph_ids
                    ]
                    if submitted:
                        break
                    await ui_test.wait_n_updates(5)
                self.assertEqual(len(submitted), 1, "The ComfyUI submission never reached the durable job queue.")
                await ui_test.wait_n_updates(10)

                # The reopened Job Queue window shows a row for the submitted graph.
                row = ui_test.find(
                    f"{queue_title}//Frame/**/Image[*].identifier=='queue_graph_drag_handle_{submitted[0].graph_id}'"
                )
                self.assertIsNotNone(row, "The Job Queue window shows no row for the submitted ComfyUI graph.")

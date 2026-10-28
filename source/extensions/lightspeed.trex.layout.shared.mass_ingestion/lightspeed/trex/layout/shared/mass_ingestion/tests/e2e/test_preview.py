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
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import omni.ui as ui
import omni.usd
from lightspeed.trex.contexts.setup import Contexts
from lightspeed.trex.layout.shared.mass_ingestion import SetupUI
from lightspeed.trex.utils.widget import WorkspaceWindowBase
from lightspeed.trex.viewports.shared.widget import get_instance
from omni.flux.utils.widget.resources import get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase


class _PreviewWindow(WorkspaceWindowBase):
    """Host the production ingestion layout with a small real ingestion schema."""

    def __init__(self, schema_path: str):
        super().__init__(usd_context_name=Contexts.INGEST_CRAFT.value)
        self._schema_path = schema_path
        self.layout = None

    @property
    def title(self) -> str:
        """Return the isolated test window title."""
        return "TestIngestionPreview"

    @property
    def flags(self) -> int:
        """Return the standard window flags."""
        return ui.WINDOW_FLAGS_NONE

    def menu_path(self) -> None:
        """Keep the test host out of the application menu."""
        return

    def _create_window_ui(self) -> SetupUI:
        """Build the production layout using the test schema."""
        self.layout = SetupUI([{"path": self._schema_path}], context=Contexts.INGEST_CRAFT)
        return self.layout


class TestIngestionPreview(AsyncTestCase):
    """Exercise preview visibility through a real ingestion queue and window."""

    async def test_reopen_preview_after_pending_initialization_is_cancelled_renders_stage(self):
        """Resume a real viewport after its owner cancels pending initialization."""
        with TemporaryDirectory() as directory:
            schema_path = Path(directory) / "preview.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "name": "Preview",
                        "resultor_plugins": [],
                        "context_plugin": {
                            "name": "AssetImporter",
                            "data": {
                                "context_name": Contexts.INGEST_CRAFT.value,
                                "input_files": [
                                    get_test_data(
                                        "usd/project_example/ingested_assets/source/cube.usda",
                                        "lightspeed.trex.app.resources",
                                    )
                                ],
                                "output_directory": str(Path(directory) / "output"),
                                "output_usd_extension": "usda",
                                "expose_mass_ui": True,
                                "expose_mass_queue_action_ui": True,
                                "cook_mass_template": True,
                            },
                        },
                        "check_plugins": [
                            {
                                "name": "PrintPrims",
                                "data": {},
                                "context_plugin": {"name": "CurrentStage", "data": {}},
                                "selector_plugins": [{"name": "AllMeshes", "data": {}}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            window = _PreviewWindow(str(schema_path))
            window.create_window(width=1400, height=900)
            subscriptions = []
            finished = asyncio.get_running_loop().create_future()

            def on_core_added(core):
                subscriptions.append(
                    core.subscribe_run_finished(lambda result, message=None: finished.set_result(result))
                )

            try:
                # Open the real owner window; its preview starts collapsed and cannot initialize.
                window.show_window_fn(True)
                await ui_test.human_delay()
                viewport = get_instance(Contexts.INGEST_CRAFT.value)
                self.assertIsNotNone(viewport)
                self.assertFalse(viewport.viewport_api.updates_enabled)
                self.assertIsNone(viewport._remix_renderer_activation_task)
                subscriptions.append(window.layout._mass_ingest_widget.core.subscribe_core_added(on_core_added))

                # Submit a real cube through the queue UI using the current-process executor.
                executor = ui_test.find(f"{window.title}//Frame/**/ComboBox[*].identifier=='executors_combo_box'")
                self.assertIsNotNone(executor)
                await executor.click()
                await ui_test.human_delay()
                await ui_test.emulate_mouse_move_and_click(executor.position + ui_test.Vec2(30, 25))
                await ui_test.human_delay()
                add_to_queue = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='AddToQueue'")
                self.assertIsNotNone(add_to_queue)
                await add_to_queue.click()
                await ui_test.human_delay()
                self.assertTrue(await asyncio.wait_for(finished, timeout=60))
                self.assertIsNotNone(viewport.viewport_api.stage)
                self.assertFalse(viewport.viewport_api.updates_enabled)
                self.assertIsNone(viewport._remix_renderer_activation_task)

                # Reveal the completed asset through its actual queue preview control.
                preview = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='ShowInViewport'")
                self.assertIsNotNone(preview)
                await preview.click()
                await ui_test.human_delay()
                self.assertTrue(viewport.viewport_api.updates_enabled)

                # Reopen an expanded preview, then close before its newly scheduled task can run.
                window.show_window_fn(False)
                await ui_test.human_delay()
                window.show_window_fn(True)
                pending_task = viewport._remix_renderer_activation_task
                self.assertIsNotNone(pending_task)
                self.assertFalse(pending_task.done())
                window.show_window_fn(False)
                await ui_test.human_delay()
                self.assertTrue(pending_task.cancelled())
                self.assertFalse(viewport.viewport_api.updates_enabled)
                self.assertIsNone(viewport._remix_renderer_activation_task)

                # Reopening schedules fresh initialization and the real viewport produces a frame.
                window.show_window_fn(True)
                resumed_task = viewport._remix_renderer_activation_task
                self.assertIsNotNone(resumed_task)
                self.assertIsNot(resumed_task, pending_task)
                await ui_test.human_delay()
                await asyncio.wait_for(resumed_task, timeout=60)
                await asyncio.wait_for(viewport.viewport_api.wait_for_rendered_frames(1), timeout=60)
                self.assertTrue(viewport.viewport_api.updates_enabled)
                self.assertIsNotNone(viewport.viewport_api.stage.GetDefaultPrim())
            finally:
                subscriptions.clear()
                viewport = get_instance(Contexts.INGEST_CRAFT.value)
                if viewport is not None:
                    viewport.destroy()
                window.cleanup()
                context = omni.usd.get_context(Contexts.INGEST_CRAFT.value)
                if context is not None and context.get_stage() is not None:
                    await context.close_stage_async()

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

__all__ = ["TestAssetModifiersWidgetE2E"]

import asyncio
from unittest import mock

from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardEventType, KeyboardInput
from carb.settings import get_settings
from lightspeed.common.constants import WindowNames
from lightspeed.trex.asset_modifiers.factory import get_instance as _get_asset_modifier_factory
from lightspeed.trex.asset_modifiers.core import AssetModifiersCore
from lightspeed.trex.asset_modifiers.core.constants import FILE_INPUT, SOURCE_INPUT
from lightspeed.trex.asset_modifiers.core.enums import SourceGetter
from lightspeed.trex.asset_modifiers.core.settings import AssetModifierSettings
from lightspeed.trex.asset_modifiers.core.tests.e2e.scale_mesh_job import ScaleMeshTestJob
from lightspeed.trex.asset_modifiers.core.tests.e2e.scale_mesh_modifier import ScaleMeshTestModifier
from lightspeed.trex.asset_modifiers.widget.submitter import AssetModifierSubmitter
from lightspeed.trex.contexts.setup import Contexts
from omni import ui, usd
from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.core.settings import JobQueueSettings
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test.input import emulate_keyboard

_TITLE = WindowNames.ASSET_MODIFIERS.value


class TestAssetModifiersWidgetE2E(AsyncTestCase):
    """Exercise the registered Asset Modifiers window with the real core and job queue."""

    async def setUp(self) -> None:
        """Show the window with the scheduler stopped."""
        self._queue_settings = JobQueueSettings()
        self._scheduler_enabled = self._queue_settings.scheduler_enabled
        self._queue_settings.set_scheduler_enabled(False)
        self._known_graph_ids = {graph.graph_id for graph in get_job_queue().get_graph_snapshots()}
        ui.Workspace.show_window(_TITLE, True)
        window = ui.Workspace.get_window(_TITLE)
        window.width, window.height = 600, 500
        window.focus()
        await ui_test.human_delay(5)

    async def tearDown(self) -> None:
        """Remove the test jobs, modifier, and settings."""
        ui.Workspace.show_window(_TITLE, False)
        # A submission still preparing after a failure must not add a graph after the cleanup below.
        AssetModifierSubmitter.cancel_pending_submissions()
        await ui_test.human_delay(3)
        _get_asset_modifier_factory().unregister_plugins([ScaleMeshTestModifier])
        get_settings().destroy_item(AssetModifierSettings.get_modifier_key(ScaleMeshTestModifier))
        AssetModifierSettings().set_active_modifier_name("")
        self._queue_settings.set_scheduler_enabled(self._scheduler_enabled)
        # The scheduler is stopped, so no queued job is running when its graph is deleted.
        queue = get_job_queue()
        snapshots = queue.get_graph_snapshots()
        if added := [graph.graph_id for graph in snapshots if graph.graph_id not in self._known_graph_ids]:
            queue.delete_graphs(added)

    async def test_cancelled_submission_keeps_its_context_until_it_settles(self) -> None:
        """A cancelled submission blocks a new one for its context until its cancellation settles."""
        started = asyncio.Event()
        preparations = []

        async def wait_for_cancellation(*_args, **_kwargs) -> None:
            preparations.append(_kwargs)
            started.set()
            await asyncio.Event().wait()

        with mock.patch.object(AssetModifiersCore, "prepare_submission", new=wait_for_cancellation):
            # 1. A cancelled submission still owns its context, so a new submit does not start a second one.
            AssetModifierSubmitter.submit("")
            await started.wait()
            AssetModifierSubmitter.cancel_pending_submissions()
            AssetModifierSubmitter.submit("")
            self.assertTrue(AssetModifierSubmitter._submissions.is_running(""))

            # 2. Once it settles, the context is free and the next submit starts a new preparation.
            await asyncio.gather(*AssetModifierSubmitter._submissions._tasks.values(), return_exceptions=True)
            await asyncio.sleep(0)
            self.assertFalse(AssetModifierSubmitter._submissions.is_running(""))
            started.clear()
            AssetModifierSubmitter.submit("")
            await started.wait()
            self.assertEqual(len(preparations), 2)
            AssetModifierSubmitter.cancel_pending_submissions()

    async def test_without_modifiers_shows_empty_state(self) -> None:
        """Show the empty state and disable the picker and Run until a provider registers a modifier."""
        # No provider is registered, so the picker and Run are disabled and Run explains why. No inputs are built.
        picker = ui_test.find(f"{_TITLE}//Frame/**/SectionedComboBox[*].identifier=='AssetModifierPicker'")
        run_button = ui_test.find(f"{_TITLE}//Frame/**/Button[*].identifier=='AssetModifierRun'")

        self.assertFalse(picker.widget.enabled)
        self.assertFalse(run_button.widget.enabled)
        self.assertEqual(run_button.widget.tooltip, "No asset modifiers are installed.")
        self.assertIsNone(ui_test.find(f"{_TITLE}//Frame/**/TreeView[*].identifier=='AssetModifierInputs'"))

    async def test_edit_scale_and_run_a_file_source_without_project(self) -> None:
        """Select the modifier, edit Scale, choose a File Path Constant source, and run it after the project closes."""
        settings = AssetModifierSettings()
        # 1. A provider registers the test modifier while a project is open.
        _get_asset_modifier_factory().register_plugins([ScaleMeshTestModifier])
        async with open_test_project(
            "usd/project_example/combined.usda",
            ext_name="lightspeed.trex.app.resources",
            context_name=Contexts.STAGE_CRAFT.value,
        ) as project_url:
            await ui_test.human_delay(3)

            # 2. The picker lists the modifier with its Experimental label. Selecting it builds its inputs.
            picker = ui_test.find(f"{_TITLE}//Frame/**/SectionedComboBox[*].identifier=='AssetModifierPicker'")
            self.assertTrue(picker.widget.enabled)
            await picker.click()
            await ui_test.human_delay(2)
            entries = ui_test.find_all("SectionedComboPopup//Frame/**/Label[*].name=='SectionedComboItemLabel'")
            (entry,) = [entry for entry in entries if entry.widget.text == "Scale Mesh (Test) (Experimental)"]
            await entry.click()
            await ui_test.human_delay(3)

            # 3. Scale shows the declared bounds, and a typed value is stored in the modifier settings.
            scale = ui_test.find(f"{_TITLE}//Frame/**/FloatBoundedDrag[*].identifier=='AssetModifierInput_scale'")
            self.assertAlmostEqual(scale.widget.min, 0.1)
            self.assertAlmostEqual(scale.widget.max, 10.0)
            # A Ctrl click on the focused drag field opens its text editor.
            await scale.click()
            await ui_test.human_delay()
            await emulate_keyboard(
                KeyboardEventType.KEY_PRESS, KeyboardInput.LEFT_CONTROL, KEYBOARD_MODIFIER_FLAG_CONTROL
            )
            await ui_test.human_delay()
            await scale.click()
            await ui_test.human_delay()
            await emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.LEFT_CONTROL, 0)
            await ui_test.human_delay()
            for key, modifier in ((KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL), (KeyboardInput.BACKSPACE, 0)):
                await ui_test.emulate_keyboard_press(key, modifier)
                await ui_test.human_delay()
            await ui_test.emulate_char_press("2.0")
            await ui_test.human_delay()
            await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await ui_test.human_delay(2)
            self.assertEqual(settings.get_value(ScaleMeshTestModifier, ScaleMeshTestModifier.inputs[0]), 2.0)

            # 4. A File Path Constant source runs without a project. The File row appears once the source changes.
            settings.set_value(ScaleMeshTestModifier, SOURCE_INPUT, SourceGetter.CONSTANT)
            settings.set_value(ScaleMeshTestModifier, FILE_INPUT, project_url.path)
            await usd.get_context(Contexts.STAGE_CRAFT.value).close_stage_async()
            await ui_test.human_delay(3)
            self.assertIsNotNone(ui_test.find(f"{_TITLE}//Frame/**/StringField[*].identifier=='NativePropertyValue'"))

            # 5. Run queues one graph whose modifier job has the file source and the edited Scale.
            await ui_test.find(f"{_TITLE}//Frame/**/Button[*].identifier=='AssetModifierRun'").click()
            async with asyncio.timeout(30):
                while not (
                    graphs := [
                        graph
                        for graph in get_job_queue().get_graph_snapshots()
                        if graph.graph_id not in self._known_graph_ids
                    ]
                ):
                    await ui_test.human_delay()
            jobs = [get_job_queue().get_job(job.job_id) for job in graphs[0].jobs]
            (job,) = [job for job in jobs if isinstance(job, ScaleMeshTestJob)]
            self.assertEqual((job.prim_paths, job.values), ((), {"scale": 2.0}))
            self.assertEqual(job.source_url, project_url.path.replace("\\", "/"))

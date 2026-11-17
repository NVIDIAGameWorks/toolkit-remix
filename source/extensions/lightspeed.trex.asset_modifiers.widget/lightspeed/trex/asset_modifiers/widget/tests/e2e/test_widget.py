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

from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardEventType, KeyboardInput
from carb.settings import get_settings
from lightspeed.common.constants import WindowNames
from lightspeed.trex.asset_modifiers.core.constants import FILE_INPUT, SOURCE_INPUT
from lightspeed.trex.asset_modifiers.core.enums import SourceGetter
from lightspeed.trex.asset_modifiers.core.settings import AssetModifierSettings
from lightspeed.trex.asset_modifiers.core.tests.e2e.scale_mesh_job import ScaleMeshTestJob
from lightspeed.trex.asset_modifiers.core.tests.e2e.scale_mesh_modifier import ScaleMeshTestModifier
from lightspeed.trex.asset_modifiers.factory import get_instance as _get_asset_modifier_factory
from lightspeed.trex.asset_modifiers.widget.submitter import AssetModifierSubmitter
from lightspeed.trex.asset_modifiers.widget.workspace import AssetModifiersWorkspace
from lightspeed.trex.contexts.setup import Contexts
from omni import ui, usd
from omni.flux.job_queue.core import get_job_queue, handlers
from omni.flux.job_queue.core.enums import EXECUTING_JOB_STATES
from omni.flux.job_queue.core.handlers import get_apply_executor
from omni.flux.job_queue.core.models import QueueJob, UsageSnapshot
from omni.flux.job_queue.core.settings import JobQueueSettings
from omni.flux.job_queue.widget import get_display_adapter_registry
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test.input import emulate_keyboard

_TITLE = WindowNames.ASSET_MODIFIERS.value


class _InputRowsWorkspace(AssetModifiersWorkspace):
    """Own the input-row fixture under a separate workspace title."""

    @property
    def title(self) -> str:
        """Return the fixture's window title."""
        return "AssetModifierRowLifecycle"


class TestAssetModifiersWidgetE2E(AsyncTestCase):
    """Exercise the registered Asset Modifiers window with the real core and job queue."""

    async def setUp(self) -> None:
        """Show the window with the scheduler stopped."""
        self._queue_settings = JobQueueSettings()
        self._scheduler_enabled = self._queue_settings.scheduler_enabled
        self.addCleanup(self._queue_settings.set_scheduler_enabled, self._scheduler_enabled)
        self.addCleanup(AssetModifierSettings().set_active_modifier_name, "")
        self.addCleanup(get_settings().destroy_item, AssetModifierSettings.get_modifier_key(ScaleMeshTestModifier))
        self.addCleanup(_get_asset_modifier_factory().unregister_plugins, [ScaleMeshTestModifier])
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
        await self._settle_test_jobs()
        queue = get_job_queue()
        if added := [
            graph.graph_id for graph in queue.get_graph_snapshots() if graph.graph_id not in self._known_graph_ids
        ]:
            queue.delete_graphs(added, UsageSnapshot())

    async def _settle_test_jobs(self) -> None:
        """Stop test work before its project or graph disappears."""
        self._queue_settings.set_scheduler_enabled(False)
        AssetModifierSubmitter.cancel_pending_submissions()
        await asyncio.gather(*AssetModifierSubmitter._submissions._tasks.values(), return_exceptions=True)
        queue = get_job_queue()
        handlers._scheduler.pause()
        for graph in queue.get_graph_snapshots():
            for job in graph.jobs:
                if graph.graph_id not in self._known_graph_ids and job.state in EXECUTING_JOB_STATES:
                    queue.cancel_job(job.job_id)
        async with asyncio.timeout(30):
            await handlers._scheduler.stop()
            await get_apply_executor().wait_idle()

    async def test_input_rows_release_when_rebuilt_and_destroyed(self) -> None:
        """Release input models when a source rebuilds the form or its widget closes."""
        # Open the real workspace owner so Source changes and cleanup use the application's control paths.
        context_name = "asset_modifier_row_lifecycle"
        usd.create_context(context_name)
        self.addCleanup(usd.destroy_context, context_name)
        owner = _InputRowsWorkspace(context_name)
        self.addCleanup(owner.cleanup)
        _get_asset_modifier_factory().register_plugins([ScaleMeshTestModifier])
        owner.create_window(width=600, height=500)
        owner.show_window_fn(True)
        widget = owner._content
        async with asyncio.timeout(10):
            while not widget._input_items:
                await ui_test.human_delay()
        rows = list(widget._input_items)

        # Select File Path Constant in the Source ComboBox so the old rows release their parent and value models.
        # The ComboBox popup is drawn natively, so the test sets the selection the popup writes to the widget model.
        source = await ui_test.find_with_retry(f"{owner.title}//Frame/**/ComboBox[*].identifier=='NativePropertyValue'")
        model = source.widget.model
        labels = [model.get_item_value_model(item).as_string for item in model.get_item_children()]
        model.get_item_value_model().set_value(labels.index(SourceGetter.CONSTANT.value))
        async with asyncio.timeout(10):
            while widget._input_items == rows:
                await ui_test.human_delay()
        for row in rows:
            self.assertEqual((row.parent, row.value_models), (None, None))

        # Owner cleanup must also release the rows that the test retains from the replacement form.
        rows = tuple(widget._input_items)
        owner.cleanup()
        for row in rows:
            self.assertEqual((row.parent, row.value_models), (None, None))

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
            run_button = ui_test.find(f"{_TITLE}//Frame/**/Button[*].identifier=='AssetModifierRun'")
            self.assertTrue(run_button.widget.enabled)

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
            self.assertEqual(settings.get_value(ScaleMeshTestModifier, ScaleMeshTestModifier.inputs[1]), 2.0)
            # The picker tooltip and the (i) icon beside the picker show the modifier description.
            self.assertEqual(picker.widget.tooltip, ScaleMeshTestModifier.description)
            icons = ui_test.find_all(f"{_TITLE}//Frame/**/Image[*].identifier=='info_icon_image_id'")
            (info_icon,) = [
                icon for icon in icons if abs(icon.center.y - picker.center.y) <= 2 and icon.center.x > picker.center.x
            ]
            await ui_test.emulate_mouse_move(info_icon.center)
            async with asyncio.timeout(10):
                while (
                    not (popup := ui_test.find("Context Info//Frame/**/Label[*].identifier=='context_tooltip'"))
                    or popup.widget.text != ScaleMeshTestModifier.description
                ):
                    await ui_test.human_delay()
            await ui_test.emulate_mouse_move(ui_test.Vec2(0, 0))
            scale_path = f"{_TITLE}//Frame/**/FloatBoundedDrag[*].identifier=='AssetModifierInput_scale'"
            # Scale follows its toggle. Hiding and showing it must preserve the edited value.
            toggle_path = f"{_TITLE}//Frame/**/CheckBox[*].identifier=='NativePropertyValue'"
            self.assertLess(ui_test.find(toggle_path).center.y, ui_test.find(scale_path).center.y)
            for visible in (False, True, False):
                await ui_test.find(toggle_path).click()
                async with asyncio.timeout(10):
                    while (ui_test.find(scale_path) is not None) != visible:
                        await ui_test.human_delay()

            # 4. A stage source needs a project, but a File Path Constant source does not.
            await usd.get_context(Contexts.STAGE_CRAFT.value).close_stage_async()
            await ui_test.human_delay(3)
            self.assertFalse(run_button.widget.enabled)
            self.assertEqual(run_button.widget.tooltip, "Open a project to run an asset modifier.")
            settings.set_value(ScaleMeshTestModifier, SOURCE_INPUT, SourceGetter.CONSTANT)
            settings.set_value(ScaleMeshTestModifier, FILE_INPUT, project_url.path)
            await ui_test.human_delay(3)
            self.assertTrue(run_button.widget.enabled)
            self.assertIsNotNone(ui_test.find(f"{_TITLE}//Frame/**/StringField[*].identifier=='NativePropertyValue'"))

            # Cancel submission and deferred focus, then reopen and resubmit through Run.
            AssetModifierSubmitter.submit(Contexts.STAGE_CRAFT.value)
            AssetModifierSubmitter.show_window(_TITLE)
            pending_focus = AssetModifierSubmitter._focus_requests._tasks[_TITLE]
            AssetModifierSubmitter.cancel_pending_submissions()
            AssetModifierSubmitter.submit(Contexts.STAGE_CRAFT.value)
            await asyncio.gather(
                *AssetModifierSubmitter._submissions._tasks.values(), pending_focus, return_exceptions=True
            )
            self.assertTrue(pending_focus.cancelled())
            self.assertEqual({graph.graph_id for graph in get_job_queue().get_graph_snapshots()}, self._known_graph_ids)
            ui.Workspace.show_window(_TITLE, False)
            AssetModifierSubmitter.show_window(_TITLE)
            await AssetModifierSubmitter._focus_requests._tasks[_TITLE]
            self.assertTrue(ui.Workspace.get_window(_TITLE).visible)
            await ui_test.find(f"{_TITLE}//Frame/**/Button[*].identifier=='AssetModifierRun'").click()
            await asyncio.gather(*AssetModifierSubmitter._submissions._tasks.values())
            async with asyncio.timeout(30):
                while not (
                    graphs := [
                        graph
                        for graph in get_job_queue().get_graph_snapshots()
                        if graph.graph_id not in self._known_graph_ids
                    ]
                ):
                    await ui_test.human_delay()
            self.assertEqual(len(graphs), 1)
            jobs = [get_job_queue().get_job(job.job_id) for job in graphs[0].jobs]
            (job,) = [job for job in jobs if isinstance(job, ScaleMeshTestJob)]
            self.assertEqual((job.prim_paths, job.values), ((), {"scale": 2.0, "show_scale": False}))
            self.assertEqual(job.source_url, project_url.path.replace("\\", "/"))
            # A File Path Constant source has no prim, so the Target column shows the model file.
            self.assertEqual(get_display_adapter_registry().get_adapter(job).get_targets(job), (job.source_url,))

            # Complete the modifier job so Last Run displays its result summary.
            self._queue_settings.set_scheduler_enabled(True)
            try:
                await QueueJob(get_job_queue(), graphs[0].graph_id, job.job_id).outputs(timeout=120)
                async with asyncio.timeout(10):
                    while (
                        not (result := ui_test.find(f"{_TITLE}//Frame/**/Label[*].identifier=='AssetModifierLastRun'"))
                        or result.widget.text != "Scaled model: scaled.usda"
                    ):
                        await ui_test.human_delay()
            finally:
                await self._settle_test_jobs()

"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import asyncio
import pathlib
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

from lightspeed.trex.comfyui.core.core import ComfyUISubmission, ComfyUISubmissionResult
from lightspeed.trex.comfyui.core.enums import ComfyUIEventType, ComfyUIState, WorkflowCategory, WorkflowSourceType
from lightspeed.trex.comfyui.core.events import ComfyUIEventPayload
from lightspeed.trex.comfyui.core.job import ComfyUIJob
from lightspeed.trex.comfyui.core.models import ComfyUIWorkflowRequest, Workflow, WorkflowInput
from lightspeed.trex.comfyui.core.preset import Preset
from lightspeed.trex.comfyui.core.resolvers import ConstantResolver, ResolverConfigurationError
from lightspeed.trex.comfyui.widget.display_adapter import ComfyUIDisplayAdapter
from lightspeed.trex.comfyui.widget.workflow.items import InputItemGroup
from lightspeed.trex.comfyui.widget.workflow.widget import WorkflowSetupWidget
from omni import usd
from omni.flux.job_queue.widget.display_adapter_base import JobAction
from omni.kit.test import AsyncTestCase


def _make_input(
    label: str,
    value,
    *,
    group: str = "",
    order: int = 0,
) -> WorkflowInput:
    """Create a configurable workflow input for widget tests.

    Args:
        label: User-facing input label and source for the synthetic port name.
        value: Native default wrapped by the constant resolver.
        group: Optional display group containing the input.
        order: Relative display order within the workflow.

    Returns:
        The configured workflow input.
    """
    port_name = label.lower().replace(" ", "_")
    native_type = pathlib.Path if isinstance(value, pathlib.Path) else type(value)
    return WorkflowInput(
        port_id=f"1.inputs.{port_name}",
        label=label,
        native_type=native_type,
        default_value=value,
        value=ConstantResolver(value),
        order=order,
        group=group,
        tooltip=f"Configure {label}",
    )


def _make_workflow(name: str = "Material Workflow") -> Workflow:
    """Create a representative workflow for widget tests.

    Args:
        name: Workflow name shown by the selection controls.

    Returns:
        The workflow with grouped inputs, presets, and captured defaults.
    """
    inputs = [
        _make_input("Strength", 0.5, group="Material", order=2),
        _make_input("Enabled", True, order=1),
    ]
    workflow = Workflow(
        name=name,
        source_type=WorkflowSourceType.RTX_REMIX,
        category=WorkflowCategory.API,
        inputs=inputs,
        presets={
            "quality": Preset("quality", inputs={"1.strength": 0.9}),
            "default": Preset("default", inputs={"1.strength": 0.5}),
        },
        group_order=["Material"],
    )
    workflow.workflow_defaults = {item.port_id: deepcopy(item.value) for item in inputs}
    return workflow


def _make_core(workflow=None):
    """Create a mocked running ComfyUI core for widget tests.

    Args:
        workflow: Optional workflow exposed as the current selection.

    Returns:
        The mocked connected core and its representative workflow catalog.
    """
    core = MagicMock()
    core.state = ComfyUIState.RUNNING
    core.status_message = ""
    core.workflow = workflow
    core.is_connected = True
    core.is_ready = workflow is not None
    core.get_submission_block_reason.return_value = None
    core.available_workflows = [
        Workflow(name="Material Workflow", source_type=WorkflowSourceType.RTX_REMIX, category=WorkflowCategory.API),
        Workflow(name="UI Only", source_type=WorkflowSourceType.USER, category=WorkflowCategory.FULL),
    ]
    return core


def _make_bare_widget(core=None) -> WorkflowSetupWidget:
    """Create a workflow widget without constructing its UI tree.

    Args:
        core: Mocked core bound to the widget, or a default running core when omitted.

    Returns:
        The workflow widget configured for the texturecraft context.
    """
    with (
        patch(
            "lightspeed.trex.comfyui.widget.workflow.widget.get_comfyui_core_instance",
            return_value=core or _make_core(),
        ),
        patch("lightspeed.trex.comfyui.widget.workflow.widget.subscribe_comfyui_event", return_value=MagicMock()),
        patch("lightspeed.trex.comfyui.widget.workflow.widget.usd.get_context", return_value=MagicMock()),
        patch.object(WorkflowSetupWidget, "_build_ui"),
        patch.object(WorkflowSetupWidget, "_on_workflow_changed"),
    ):
        return WorkflowSetupWidget("texturecraft")


class TestWorkflowSetupWidgetUnit(AsyncTestCase):
    """Test workflow-widget branching without constructing rendered controls."""

    async def test_create_input_items_sorts_groups_and_passes_context(self):
        """Input items are grouped in display order with the widget context."""
        # Arrange
        workflow = _make_workflow()
        widget = _make_bare_widget(_make_core(workflow))

        # Act
        items = widget._create_input_items(workflow)

        # Assert
        self.assertEqual([item.name_models[0].get_value_as_string() for item in items], ["Ungrouped", "Material"])
        self.assertTrue(items[0].expanded)
        self.assertEqual(items[0].children[0].workflow_input.label, "Enabled")
        self.assertEqual(len(widget._getter_subscriptions), 2)

    async def test_project_requirement_disables_only_new_graph_submission(self) -> None:
        """Run explains the missing project while the connected workflow remains available."""
        # Arrange
        core = _make_core(_make_workflow())
        core.get_submission_block_reason.return_value = (
            "Open a project to select materials for new ComfyUI jobs. Existing queued jobs can continue."
        )
        widget = _make_bare_widget(core)
        widget._submit_button = MagicMock()

        # Act
        widget._update_submit_button_state()

        # Assert
        self.assertFalse(widget._submit_button.enabled)
        self.assertEqual(
            widget._submit_button.tooltip,
            "Open a project to select materials for new ComfyUI jobs. Existing queued jobs can continue.",
        )

    async def test_closed_stage_refreshes_submission_availability(self) -> None:
        """A fully closed project refreshes Run from the core submission requirement."""
        # Arrange
        core = _make_core(_make_workflow())
        core.get_submission_block_reason.return_value = (
            "Open a project to select materials for new ComfyUI jobs. Existing queued jobs can continue."
        )
        widget = _make_bare_widget(core)
        widget._submit_button = MagicMock()

        # Act
        widget._on_stage_event(MagicMock(type=int(usd.StageEventType.CLOSED)))

        # Assert
        self.assertFalse(widget._submit_button.enabled)
        self.assertEqual(
            widget._submit_button.tooltip,
            "Open a project to select materials for new ComfyUI jobs. Existing queued jobs can continue.",
        )

    async def test_opened_stage_refreshes_submission_availability(self) -> None:
        """A fully opened project refreshes Run from the current live stage."""
        # Arrange
        core = _make_core(_make_workflow())
        widget = _make_bare_widget(core)
        widget._submit_button = MagicMock()

        # Act
        widget._on_stage_event(MagicMock(type=int(usd.StageEventType.OPENED)))

        # Assert
        self.assertTrue(widget._submit_button.enabled)

    async def test_edit_preserves_saved_job_snapshot_missing_from_server_catalog(self):
        """Queue Edit keeps the persisted workflow until the user explicitly selects another one."""
        # Arrange
        saved_workflow = _make_workflow("Removed Workflow")
        core = _make_core()
        core.available_workflows = [
            Workflow(name="Available Workflow", source_type=WorkflowSourceType.USER, category=WorkflowCategory.API)
        ]
        job = ComfyUIJob(context_name="texturecraft")
        request = ComfyUIWorkflowRequest(
            prompt={},
            input_bindings=(),
            client_id="",
            timeout=300.0,
            output_url="C:/project/assets/ingested/comfyui/test",
            workflow=saved_workflow,
        )
        core.get_workflow_request.return_value = request
        widget = _make_bare_widget(core)
        widget._workflow_dropdown = MagicMock()

        def publish_workflow_changed(workflow):
            """Publish the restored workflow through the mocked core.

            Args:
                workflow: Independent workflow snapshot restored by queue editing.
            """
            core.workflow = workflow
            widget._on_workflow_changed()

        core.set_workflow.side_effect = publish_workflow_changed
        adapter = ComfyUIDisplayAdapter()
        action = JobAction("open_workflow", "Open Workflow", "EditJob", "Open this workflow.", True)

        with (
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance", return_value=core),
            patch.object(adapter, "get_graph_actions", return_value=(action,)),
            patch.object(adapter._workflow_workspace, "show_window_fn") as show_workflow,
        ):
            # Act
            adapter.execute_action(action.action_id, job, "texturecraft")

        # Assert
        self.assertEqual(core.workflow.name, "Removed Workflow")
        self.assertIsNot(core.workflow, saved_workflow)
        core.load_workflow.assert_not_called()
        items, selected_index = widget._workflow_dropdown.set_items.call_args.args
        self.assertEqual(selected_index, 0)
        self.assertEqual(items[0].section, "Saved Job")
        self.assertIsNone(items[0].data)
        show_workflow.assert_called_once_with(True)

    async def test_selection_change_selects_matching_input(self):
        """Selecting an input group stores its sorted workflow index."""
        # Arrange
        workflow = _make_workflow()
        widget = _make_bare_widget(_make_core(workflow))
        selected = InputItemGroup(workflow.inputs[0])
        widget._rebuild_properties_panel = MagicMock()

        # Act
        widget._on_input_selection_changed([selected])

        # Assert
        self.assertEqual(widget._selected_input_index, 1)
        widget._rebuild_properties_panel.assert_called_once_with()

    async def test_selection_change_clears_stale_input(self):
        """Selecting an input absent from the workflow clears stale detail state."""
        # Arrange
        workflow = _make_workflow()
        widget = _make_bare_widget(_make_core(workflow))
        stale = InputItemGroup(_make_input("Stale", 1))
        widget._selected_input_index = 1
        widget._rebuild_properties_panel = MagicMock()

        # Act
        widget._on_input_selection_changed([stale])

        # Assert
        self.assertIsNone(widget._selected_input_index)
        widget._rebuild_properties_panel.assert_called_once_with()

    async def test_selection_change_ignores_group(self):
        """Selecting a container group clears the input detail selection."""
        # Arrange
        workflow = _make_workflow()
        widget = _make_bare_widget(_make_core(workflow))
        widget._selected_input_index = 0
        widget._rebuild_properties_panel = MagicMock()

        # Act
        widget._on_input_selection_changed([MagicMock()])

        # Assert
        self.assertIsNone(widget._selected_input_index)
        widget._rebuild_properties_panel.assert_called_once_with()

    async def test_selection_change_ignores_empty_selection(self):
        """Clearing the tree selection clears the input detail selection."""
        # Arrange
        workflow = _make_workflow()
        widget = _make_bare_widget(_make_core(workflow))
        widget._selected_input_index = 0
        widget._rebuild_properties_panel = MagicMock()

        # Act
        widget._on_input_selection_changed([])

        # Assert
        self.assertIsNone(widget._selected_input_index)
        widget._rebuild_properties_panel.assert_called_once_with()

    async def test_getter_change_rebuilds_only_selected_input(self):
        """A resolver change rebuilds details only for the selected input."""
        # Arrange
        workflow = _make_workflow()
        widget = _make_bare_widget(_make_core(workflow))
        group = InputItemGroup(workflow.inputs[0])
        widget._selected_input_index = 1
        widget._rebuild_properties_panel = MagicMock()

        # Act
        widget._on_getter_changed(group)

        # Assert
        widget._rebuild_properties_panel.assert_called_once_with()

    async def test_getter_change_clears_active_preset(self):
        """Changing a getter removes the stale active-preset claim."""
        # Arrange
        workflow = _make_workflow()
        workflow.active_preset = "default"
        widget = _make_bare_widget(_make_core(workflow))
        widget._update_preset_combo = MagicMock()
        group = InputItemGroup(workflow.inputs[0])

        # Act
        widget._on_getter_changed(group)

        # Assert
        self.assertIsNone(workflow.active_preset)
        widget._update_preset_combo.assert_called_once_with()

    async def test_workflow_dropdown_loads_selected_workflow(self):
        """Selecting a workflow retains a named owner for its source and name."""
        # Arrange
        core = _make_core()
        widget = _make_bare_widget(core)
        owner_coroutine = MagicMock()
        scheduled_task = MagicMock()
        custom_workflow = Workflow(name="Custom", source_type=WorkflowSourceType.USER, category=WorkflowCategory.API)
        item = MagicMock(data=custom_workflow)

        # Act
        with (
            patch.object(widget, "_load_workflow", new=MagicMock(return_value=owner_coroutine)) as load_workflow,
            patch(
                "lightspeed.trex.comfyui.widget.workflow.widget.asyncio.ensure_future",
                return_value=scheduled_task,
            ) as ensure_future,
        ):
            widget._on_workflow_dropdown_changed(2, item)

        # Assert
        load_workflow.assert_called_once_with(custom_workflow)
        ensure_future.assert_called_once_with(owner_coroutine)
        scheduled_task.set_name.assert_called_once_with("ComfyUIWorkflowLoad")
        self.assertIs(widget._workflow_load_task, scheduled_task)
        self.assertIs(widget._selected_workflow_identity, custom_workflow)

    async def test_workflow_dropdown_cancels_in_flight_load_for_latest_selection(self):
        """Selecting a new workflow cancels the older UI load task."""
        # Arrange
        core = _make_core()
        widget = _make_bare_widget(core)
        previous_task = MagicMock()
        previous_task.done.return_value = False
        replacement_task = MagicMock()
        widget._workflow_load_task = previous_task
        latest_workflow = Workflow(name="Latest", source_type=WorkflowSourceType.USER, category=WorkflowCategory.API)
        item = MagicMock(data=latest_workflow)

        # Act
        with (
            patch.object(widget, "_load_workflow", new=MagicMock(return_value=MagicMock())),
            patch(
                "lightspeed.trex.comfyui.widget.workflow.widget.asyncio.ensure_future",
                return_value=replacement_task,
            ),
        ):
            widget._on_workflow_dropdown_changed(1, item)

        # Assert
        previous_task.cancel.assert_called_once_with()
        self.assertIs(widget._workflow_load_task, replacement_task)
        self.assertIs(widget._selected_workflow_identity, latest_workflow)

    async def test_failed_workflow_load_clears_selected_identity(self):
        """A failed active workflow load clears its pending identity."""
        # Arrange
        core = _make_core()
        core.load_workflow = AsyncMock(side_effect=TypeError("invalid workflow value"))
        widget = _make_bare_widget(core)
        widget._workflow_load_task = asyncio.current_task()
        failed_workflow = Workflow(name="Failed", source_type=WorkflowSourceType.USER, category=WorkflowCategory.API)
        widget._selected_workflow_identity = failed_workflow

        # Act
        with patch("lightspeed.trex.comfyui.widget.workflow.widget.carb.log_error"):
            await widget._load_workflow(failed_workflow)

        # Assert
        self.assertIsNone(widget._workflow_load_task)
        self.assertIsNone(widget._selected_workflow_identity)

    async def test_failed_workflow_load_resets_dropdown_for_explicit_retry(self):
        """A failed workflow remains selectable again without an automatic retry loop."""
        # Arrange
        identity = Workflow(name="Failed", source_type=WorkflowSourceType.USER, category=WorkflowCategory.API)
        widget = _make_bare_widget()
        widget._workflow_list = [identity]
        widget._workflow_dropdown = MagicMock()
        widget._selected_workflow_identity = identity
        widget._core.load_workflow = AsyncMock(side_effect=RuntimeError("load failed"))
        widget._workflow_load_task = asyncio.current_task()

        # Act
        with patch("lightspeed.trex.comfyui.widget.workflow.widget.carb.log_error"):
            await widget._load_workflow(identity)

        # Assert
        items = widget._workflow_dropdown.set_items.call_args.args[0]
        self.assertIsNone(items[0].data)
        self.assertIs(items[1].data, identity)
        widget._core.load_workflow.assert_awaited_once_with(identity)

    async def test_failed_workflow_load_is_not_retried_by_later_events(self):
        """A failed automatic load waits for an explicit dropdown selection."""
        # Arrange
        identity = Workflow(name="Failed", source_type=WorkflowSourceType.USER, category=WorkflowCategory.API)
        core = _make_core()
        core.available_workflows = [identity]
        widget = _make_bare_widget(core)
        widget._workflow_dropdown = MagicMock()
        core.load_workflow = AsyncMock(side_effect=RuntimeError("load failed"))
        widget._workflow_load_task = asyncio.current_task()
        widget._selected_workflow_identity = identity
        with patch("lightspeed.trex.comfyui.widget.workflow.widget.carb.log_error"):
            await widget._load_workflow(identity)
        core.load_workflow.reset_mock()
        widget._schedule_workflow_load = MagicMock()

        # Act
        widget._update_workflow_combo()

        # Assert
        widget._schedule_workflow_load.assert_not_called()
        items, selected_index = widget._workflow_dropdown.set_items.call_args.args
        self.assertEqual(selected_index, 0)
        self.assertIsNone(items[0].data)

    async def test_workflow_dropdown_ignores_section_headers(self):
        """Section header selections never request a workflow load."""
        # Arrange
        core = _make_core()
        widget = _make_bare_widget(core)
        item = MagicMock(data=None)

        # Act
        widget._on_workflow_dropdown_changed(0, item)

        # Assert
        core.load_workflow.assert_not_called()

    async def test_update_workflow_combo_filters_ui_workflows_and_autoloads_first(self):
        """The workflow combo filters UI-only entries and autoloads its first API workflow."""
        # Arrange
        core = _make_core()
        widget = _make_bare_widget(core)
        widget._workflow_dropdown = MagicMock()
        widget._schedule_workflow_load = MagicMock()

        # Act
        widget._update_workflow_combo()

        # Assert
        items, selected_index = widget._workflow_dropdown.set_items.call_args.args

        self.assertEqual(len(widget._workflow_list), 1)
        self.assertEqual(widget._workflow_list[0].name, "Material Workflow")
        self.assertEqual(widget._workflow_list[0].source_type, WorkflowSourceType.RTX_REMIX)
        self.assertEqual(widget._workflow_list[0].category, WorkflowCategory.API)
        self.assertEqual(selected_index, 0)
        self.assertEqual(items[0].label, "Material Workflow")
        self.assertEqual(items[0].section, "Built-in")
        widget._schedule_workflow_load.assert_called_once_with(widget._workflow_list[0])

    async def test_update_workflow_combo_uses_full_identity_for_duplicate_names(self):
        """Duplicate workflow names restore selection by category and source type."""
        # Arrange
        core = _make_core()
        core.state = ComfyUIState.STARTING
        core.is_connected = False
        core.available_workflows = [
            Workflow(name="Shared", source_type=WorkflowSourceType.RTX_REMIX, category=WorkflowCategory.API),
            Workflow(name="Shared", source_type=WorkflowSourceType.USER, category=WorkflowCategory.API),
        ]
        widget = _make_bare_widget(core)
        widget._workflow_dropdown = MagicMock()
        widget._selected_workflow_identity = core.available_workflows[1]

        # Act
        widget._update_workflow_combo()

        # Assert
        self.assertEqual(widget._workflow_dropdown.set_items.call_args.args[1], 1)

    async def test_update_workflow_combo_without_workflows_uses_disabled_placeholder(self):
        """An empty catalog displays its actual state instead of a fake default workflow."""
        # Arrange
        core = _make_core()
        core.available_workflows = []
        widget = _make_bare_widget(core)
        widget._workflow_dropdown = MagicMock()

        # Act
        widget._update_workflow_combo()

        # Assert
        items = widget._workflow_dropdown.set_items.call_args.args[0]
        self.assertEqual(items[0].label, widget._NO_WORKFLOWS_TEXT)
        self.assertFalse(widget._workflow_dropdown.enabled)
        core.load_workflow.assert_not_called()

    async def test_reopened_widget_restores_persisted_identity_for_duplicate_names(self):
        """A new widget restores the workflow source persisted by the core model."""
        # Arrange
        workflow = _make_workflow("Shared")
        workflow.category = WorkflowCategory.API
        workflow.source_type = WorkflowSourceType.USER
        core = _make_core(workflow)
        core.available_workflows = [
            Workflow(name="Shared", source_type=WorkflowSourceType.RTX_REMIX, category=WorkflowCategory.API),
            Workflow(name="Shared", source_type=WorkflowSourceType.USER, category=WorkflowCategory.API),
        ]
        widget = _make_bare_widget(core)
        widget._workflow_dropdown = MagicMock()

        # Act
        widget._update_workflow_combo()

        # Assert
        self.assertEqual(widget._workflow_dropdown.set_items.call_args.args[1], 1)

    async def test_preset_change_applies_selection_and_rebuilds_panels(self):
        """Selecting a preset applies it and rebuilds both dynamic panels."""
        # Arrange
        workflow = MagicMock()
        preset = MagicMock()
        workflow.presets = {"quality": preset}
        widget = _make_bare_widget(_make_core(workflow))
        widget._preset_names = ["quality"]
        widget._selected_input_index = 1
        widget._rebuild_inputs_property_widget = MagicMock()
        widget._rebuild_properties_panel = MagicMock()
        model = MagicMock()
        model.get_item_value_model.return_value.as_int = 0

        # Act
        widget._on_preset_changed(model, None)

        # Assert
        workflow.apply_preset.assert_called_once_with(preset)
        self.assertEqual(workflow.active_preset, "quality")
        self.assertIsNone(widget._selected_input_index)
        widget._rebuild_inputs_property_widget.assert_called_once_with()
        widget._rebuild_properties_panel.assert_called_once_with()

    async def test_invalid_preset_keeps_selection_and_explains_the_failure(self):
        """A malformed preset leaves the current workflow visible and gives actionable guidance."""
        # Arrange
        workflow = MagicMock()
        preset = MagicMock()
        workflow.presets = {"broken": preset}
        workflow.active_preset = "current"
        workflow.apply_preset.side_effect = TypeError("wrong value type")
        widget = _make_bare_widget(_make_core(workflow))
        widget._preset_names = ["broken"]
        widget._selected_input_index = 1
        widget._rebuild_inputs_property_widget = MagicMock()
        widget._rebuild_properties_panel = MagicMock()
        model = MagicMock()
        model.get_item_value_model.return_value.as_int = 0

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.workflow.widget.carb.log_error"),
            patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog,
        ):
            widget._on_preset_changed(model, None)

        # Assert
        self.assertEqual(workflow.active_preset, "current")
        self.assertEqual(widget._selected_input_index, 1)
        widget._rebuild_inputs_property_widget.assert_not_called()
        widget._rebuild_properties_panel.assert_not_called()
        self.assertEqual(dialog.call_args.args[1], "ComfyUI Preset Not Applied")

    async def test_preset_change_ignores_selection_from_replaced_workflow(self):
        """A delayed ComboBox callback cannot apply a preset to a replacement workflow."""
        # Arrange
        workflow = MagicMock()
        workflow.presets = {"current": MagicMock()}
        widget = _make_bare_widget(_make_core(workflow))
        widget._preset_names = ["previous"]
        model = MagicMock()
        model.get_item_value_model.return_value.as_int = 0

        # Act
        widget._on_preset_changed(model, None)

        # Assert
        workflow.apply_preset.assert_not_called()

    async def test_update_preset_combo_preserves_real_names_and_active_preset(self):
        """The preset selector shows exact authored names and selects the active preset."""
        # Arrange
        workflow = _make_workflow()
        workflow.presets = {
            "High Quality": MagicMock(),
            "Default": MagicMock(),
        }
        widget = _make_bare_widget(_make_core(workflow))
        widget._preset_combo = MagicMock()
        widget._rebuild_combo = MagicMock()
        workflow.active_preset = "High Quality"

        # Act
        widget._update_preset_combo()

        # Assert
        self.assertEqual(widget._preset_names, ["Default", "High Quality"])
        options, selected_index = widget._rebuild_combo.call_args.args[1:]
        self.assertEqual(options, ["Default", "High Quality"])
        self.assertEqual(selected_index, 1)

    async def test_update_preset_combo_without_presets_uses_disabled_placeholder(self):
        """A workflow without presets shows one disabled placeholder instead of a fake selection."""
        # Arrange
        workflow = _make_workflow()
        workflow.presets = {}
        workflow.active_preset = None
        widget = _make_bare_widget(_make_core(workflow))
        widget._preset_combo = MagicMock()
        widget._rebuild_combo = MagicMock()

        # Act
        widget._update_preset_combo()

        # Assert
        widget._rebuild_combo.assert_called_once_with(widget._preset_combo, [widget._NO_PRESETS_TEXT], 0)
        self.assertFalse(widget._preset_combo.enabled)

    async def test_update_preset_combo_without_workflow_uses_disabled_placeholder(self):
        """No loaded workflow displays an instruction instead of a fake default preset."""
        # Arrange
        widget = _make_bare_widget(_make_core())
        widget._preset_combo = MagicMock()
        widget._rebuild_combo = MagicMock()

        # Act
        widget._update_preset_combo()

        # Assert
        widget._rebuild_combo.assert_called_once_with(widget._preset_combo, [widget._NO_WORKFLOW_PRESET_TEXT], 0)
        self.assertFalse(widget._preset_combo.enabled)

    async def test_update_preset_combo_without_active_preset_uses_prompt(self):
        """A workflow with no exact active preset does not display any preset as selected."""
        # Arrange
        workflow = _make_workflow()
        workflow.active_preset = None
        widget = _make_bare_widget(_make_core(workflow))
        widget._preset_combo = MagicMock()
        widget._rebuild_combo = MagicMock()

        # Act
        widget._update_preset_combo()

        # Assert
        self.assertEqual(widget._preset_names, [None, "default", "quality"])
        widget._rebuild_combo.assert_called_once_with(
            widget._preset_combo,
            ["Select a preset", "default", "quality"],
            0,
        )

    async def test_refresh_schedules_core_action(self):
        """Refresh retains one named owner task."""
        # Arrange
        core = _make_core()
        widget = _make_bare_widget(core)
        owner_coroutine = MagicMock()
        refresh_task = MagicMock()

        # Act
        with (
            patch.object(
                widget,
                "_refresh_workflows",
                new=MagicMock(return_value=owner_coroutine),
            ),
            patch(
                "lightspeed.trex.comfyui.widget.workflow.widget.asyncio.ensure_future",
                return_value=refresh_task,
            ) as ensure_future,
        ):
            widget._on_refresh_clicked()

        # Assert
        ensure_future.assert_called_once_with(owner_coroutine)
        refresh_task.set_name.assert_called_once_with("ComfyUIWorkflowRefresh")
        self.assertIs(widget._workflow_refresh_task, refresh_task)

    async def test_submit_prepares_current_selection_when_enabled(self):
        """An enabled submit action retains one named owner task."""
        # Arrange
        core = _make_core(_make_workflow())
        widget = _make_bare_widget(core)
        owner_coroutine = MagicMock()
        prepare_task = MagicMock()

        # Act
        with (
            patch.object(
                widget,
                "_prepare_and_submit",
                new=MagicMock(return_value=owner_coroutine),
            ),
            patch(
                "lightspeed.trex.comfyui.widget.workflow.widget.asyncio.ensure_future",
                return_value=prepare_task,
            ) as ensure_future,
        ):
            widget._on_submit_clicked()

        # Assert
        ensure_future.assert_called_once_with(owner_coroutine)
        prepare_task.set_name.assert_called_once_with("ComfyUIWorkflowSubmission")
        self.assertIs(widget._submit_task, prepare_task)

    async def test_queue_submission_routes_through_core(self):
        """Prepared submissions are passed unchanged to the owning core."""
        # Arrange
        submission = ComfyUISubmission((MagicMock(),), 0)
        core = _make_core(_make_workflow())
        core.submit_prepared_submission = AsyncMock(return_value=ComfyUISubmissionResult(1, 0))
        widget = _make_bare_widget(core)

        # Act
        await widget._submit_prepared_submission(submission)

        # Assert
        core.submit_prepared_submission.assert_awaited_once_with(submission)

    async def test_queue_submission_preserves_all_material_graphs(self):
        """Every prepared material graph is submitted in its resolved order."""
        # Arrange
        submission = ComfyUISubmission((MagicMock(), MagicMock()), 0)
        core = _make_core(_make_workflow())
        core.submit_prepared_submission = AsyncMock(return_value=ComfyUISubmissionResult(2, 0))
        widget = _make_bare_widget(core)

        # Act
        await widget._submit_prepared_submission(submission)

        # Assert
        core.submit_prepared_submission.assert_awaited_once_with(submission)

    async def test_confirmed_queue_submission_failure_reports_recovery_and_reenables_run(self):
        """A confirmed submission failure reports recovery and releases the Run action."""
        # Arrange
        submission = ComfyUISubmission((MagicMock(),), 1)
        error = RuntimeError("queue unavailable")
        core = _make_core(_make_workflow())
        core.submit_prepared_submission = AsyncMock(side_effect=error)
        widget = _make_bare_widget(core)
        widget._submit_button = MagicMock()
        widget._submit_task = asyncio.current_task()

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog,
            patch("lightspeed.trex.comfyui.widget.workflow.widget.carb.log_error") as log_error,
        ):
            await widget._submit_confirmed(submission)

        # Assert
        core.submit_prepared_submission.assert_awaited_once_with(submission)
        self.assertEqual(
            dialog.call_args.args,
            (
                "These jobs could not be added to the queue. Check that the job queue is available, then try again.",
                "ComfyUI Jobs Not Submitted",
            ),
        )
        log_error.assert_called_once_with(f"Failed to submit ComfyUI jobs: {error}")
        self.assertIsNone(widget._submit_task)
        self.assertTrue(widget._submit_button.enabled)

    async def test_prepare_skips_show_exact_active_workflow_warning(self):
        """Skipped materials use the exact active-workflow confirmation wording."""
        # Arrange
        core = _make_core(_make_workflow())
        core.prepare_submission = AsyncMock(return_value=ComfyUISubmission((MagicMock(),), 1))
        widget = _make_bare_widget(core)

        # Act
        with patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog:
            await widget._prepare_and_submit()

        # Assert
        self.assertEqual(
            dialog.call_args.args[0],
            "1 selected material does not provide the inputs required by the active workflow.\n\n"
            "These jobs will be skipped.\n\n"
            "Do you want to proceed anyway?",
        )

    async def test_prepare_failure_reports_recovery_without_technical_details(self):
        """A preparation failure gives recovery guidance while retaining technical details in the log."""
        # Arrange
        error = ValueError("No valid ComfyUI workflow selected")
        core = _make_core(_make_workflow())
        core.prepare_submission = AsyncMock(side_effect=error)
        widget = _make_bare_widget(core)

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog,
            patch("lightspeed.trex.comfyui.widget.workflow.widget.carb.log_error") as log_error,
        ):
            await widget._prepare_and_submit()

        # Assert
        self.assertEqual(
            dialog.call_args.args[0],
            "These jobs could not be prepared. Check the selected materials, workflow inputs, "
            "and ComfyUI connection, then try again.",
        )
        self.assertEqual(dialog.call_args.args[1], "ComfyUI Jobs Not Prepared")
        log_error.assert_called_once_with(f"Failed to prepare ComfyUI jobs: {error}")
        core.prepare_submission.assert_awaited_once()

    async def test_invalid_constant_reports_exact_recovery_before_queue_submission(self):
        """Invalid Constant configuration names the required correction without submitting."""
        # Arrange
        error = ResolverConfigurationError("Select a valid file for this workflow input, then try again.")
        core = _make_core(_make_workflow())
        core.prepare_submission = AsyncMock(side_effect=error)
        widget = _make_bare_widget(core)
        widget._submit_prepared_submission = AsyncMock()

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog,
            patch("lightspeed.trex.comfyui.widget.workflow.widget.carb.log_error") as log_error,
        ):
            await widget._prepare_and_submit()

        # Assert
        self.assertEqual(dialog.call_args.args[0], str(error))
        self.assertEqual(dialog.call_args.args[1], "Invalid ComfyUI Workflow Input")
        log_error.assert_called_once_with(f"Invalid ComfyUI workflow input: {error}")
        widget._submit_prepared_submission.assert_not_awaited()

    async def test_prepared_jobs_without_skips_submit_exact_graph(self):
        """A fully resolvable prepared graph is queued without an extra confirmation."""
        # Arrange
        submission = ComfyUISubmission((MagicMock(),), 0)
        core = _make_core(_make_workflow())
        core.prepare_submission = AsyncMock(return_value=submission)
        widget = _make_bare_widget(core)
        widget._submit_prepared_submission = AsyncMock()

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog,
        ):
            await widget._prepare_and_submit()

        # Assert
        widget._submit_prepared_submission.assert_awaited_once_with(submission)
        dialog.assert_not_called()

    async def test_prepared_jobs_with_skips_require_confirmation(self):
        """Skipped prepared jobs are shown before the graph can be queued."""
        # Arrange
        core = _make_core(_make_workflow())
        core.prepare_submission = AsyncMock(return_value=ComfyUISubmission((MagicMock(),), 1))
        widget = _make_bare_widget(core)

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog,
        ):
            await widget._prepare_and_submit()

        # Assert
        message = dialog.call_args.args[0]
        self.assertIn("1 selected material does not provide the inputs required by the active workflow", message)
        self.assertIn("These jobs will be skipped", message)
        self.assertIn("Do you want to proceed anyway?", message)

    async def test_skip_confirmation_disables_submit(self):
        """Opening the skipped-job dialog disables Run until the dialog closes."""
        # Arrange
        core = _make_core(_make_workflow())
        core.prepare_submission = AsyncMock(return_value=ComfyUISubmission((MagicMock(),), 1))
        widget = _make_bare_widget(core)
        widget._submit_button = MagicMock()

        # Act
        with patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog:
            await widget._prepare_and_submit()

        # Assert
        self.assertTrue(widget._submission_confirmation_open)
        self.assertFalse(widget._submit_button.enabled)
        self.assertEqual(dialog.call_args.kwargs["on_window_closed_fn"], widget._on_submission_confirmation_closed)

    async def test_submit_is_ignored_while_skip_confirmation_is_open(self):
        """Repeated Run clicks cannot prepare a second graph behind the confirmation."""
        # Arrange
        widget = _make_bare_widget(_make_core(_make_workflow()))
        widget._submission_confirmation_open = True

        # Act
        with patch("lightspeed.trex.comfyui.widget.workflow.widget.asyncio.ensure_future") as ensure_future:
            widget._on_submit_clicked()

        # Assert
        ensure_future.assert_not_called()

    async def test_closing_skip_confirmation_reenables_submit(self):
        """Closing the skipped-job dialog releases the Run action."""
        # Arrange
        widget = _make_bare_widget(_make_core(_make_workflow()))
        widget._submission_confirmation_open = True
        widget._submit_button = MagicMock()

        # Act
        widget._on_submission_confirmation_closed()

        # Assert
        self.assertFalse(widget._submission_confirmation_open)
        self.assertTrue(widget._submit_button.enabled)

    async def test_confirming_skipped_jobs_submits_prepared_graph(self):
        """Confirming the warning queues the same graph that produced it."""
        # Arrange
        submission = ComfyUISubmission((MagicMock(),), 1)
        widget = _make_bare_widget(_make_core(_make_workflow()))
        widget._submission_confirmation_open = True
        owner_coroutine = MagicMock()
        scheduled_task = MagicMock()

        # Act
        with (
            patch.object(
                widget,
                "_submit_confirmed",
                new=MagicMock(return_value=owner_coroutine),
            ),
            patch(
                "lightspeed.trex.comfyui.widget.workflow.widget.asyncio.ensure_future",
                return_value=scheduled_task,
            ) as ensure_future,
        ):
            widget._on_skipped_jobs_confirmed(submission)

        # Assert
        ensure_future.assert_called_once_with(owner_coroutine)
        scheduled_task.set_name.assert_called_once_with("ComfyUIConfirmedSubmission")
        self.assertIs(widget._submit_task, scheduled_task)

    async def test_stale_skip_confirmation_cannot_submit_after_cancellation(self):
        """Disconnect or destroy invalidates a retained dialog confirmation callback."""
        # Arrange
        submission = ComfyUISubmission((MagicMock(),), 1)
        widget = _make_bare_widget(_make_core(_make_workflow()))
        widget._submission_confirmation_open = True
        widget._cancel_action_tasks()

        # Act
        with patch("lightspeed.trex.comfyui.widget.workflow.widget.asyncio.ensure_future") as ensure_future:
            widget._on_skipped_jobs_confirmed(submission)

        # Assert
        ensure_future.assert_not_called()

    async def test_queue_submission_all_failures_reports_exact_counts(self):
        """An entirely failed batch can be retried without duplicating queued work."""
        # Arrange
        submission = ComfyUISubmission((MagicMock(),), 0)
        core = _make_core(_make_workflow())
        core.submit_prepared_submission = AsyncMock(return_value=ComfyUISubmissionResult(0, 1))
        widget = _make_bare_widget(core)

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog,
        ):
            await widget._submit_prepared_submission(submission)

        # Assert
        core.submit_prepared_submission.assert_awaited_once_with(submission)
        self.assertEqual(
            dialog.call_args.args[0],
            "0 prepared jobs were added to the queue.\n\n"
            "1 prepared job was not added. Check that the job queue is available, then try again.",
        )
        self.assertEqual(dialog.call_args.args[1], "ComfyUI Jobs Not Submitted")

    async def test_queue_submission_partial_failure_continues_and_reports_exact_counts(self):
        """A failed material does not block later graphs or invite retrying successful work."""
        # Arrange
        submission = ComfyUISubmission((MagicMock(), MagicMock(), MagicMock()), 0)
        core = _make_core(_make_workflow())
        core.submit_prepared_submission = AsyncMock(return_value=ComfyUISubmissionResult(2, 1))
        widget = _make_bare_widget(core)

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog") as dialog,
        ):
            await widget._submit_prepared_submission(submission)

        # Assert
        core.submit_prepared_submission.assert_awaited_once_with(submission)
        self.assertEqual(
            dialog.call_args.args,
            (
                "2 prepared jobs were added to the queue.\n\n"
                "1 prepared job was not added. To avoid duplicates, select only the failed material before "
                "submitting again.",
                "Some ComfyUI Jobs Not Submitted",
            ),
        )

    async def test_refresh_replaces_in_flight_task_to_prevent_stale_result(self):
        """The latest workflow refresh cancels an older request before it can publish stale data."""
        # Arrange
        core = _make_core()
        widget = _make_bare_widget(core)
        previous_task = MagicMock()
        previous_task.done.return_value = False
        replacement_task = MagicMock()
        widget._workflow_refresh_task = previous_task

        # Act
        with (
            patch.object(widget, "_refresh_workflows", new=MagicMock(return_value=MagicMock())),
            patch(
                "lightspeed.trex.comfyui.widget.workflow.widget.asyncio.ensure_future",
                return_value=replacement_task,
            ),
        ):
            widget._on_refresh_clicked()

        # Assert
        previous_task.cancel.assert_called_once_with()
        self.assertIs(widget._workflow_refresh_task, replacement_task)

    async def test_submit_ignores_click_while_submission_is_in_flight(self):
        """Repeated Run clicks create only one submission task."""
        # Arrange
        core = _make_core(_make_workflow())
        widget = _make_bare_widget(core)
        pending_task = MagicMock()
        pending_task.done.return_value = False
        widget._submit_task = pending_task

        # Act
        with patch("lightspeed.trex.comfyui.widget.workflow.widget.asyncio.ensure_future") as ensure_future:
            widget._on_submit_clicked()

        # Assert
        ensure_future.assert_not_called()

    async def test_state_event_updates_frames_and_submit_button(self):
        """Connection events synchronize workspace frames and submit state."""
        # Arrange
        core = _make_core(_make_workflow())
        widget = _make_bare_widget(core)
        widget._connected_frame = MagicMock()
        widget._disconnected_frame = MagicMock()
        widget._submit_button = MagicMock()
        event = ComfyUIEventPayload("texturecraft", ComfyUIEventType.STATE_CHANGED)

        # Act
        widget._on_core_event(event)

        # Assert
        self.assertTrue(widget._connected_frame.visible)
        self.assertFalse(widget._disconnected_frame.visible)
        self.assertTrue(widget._submit_button.enabled)

    async def test_settings_event_invalidates_stale_connected_frames_and_submission(self):
        """A shared endpoint edit immediately disconnects another context's workflow UI."""
        # Arrange
        core = _make_core(_make_workflow())
        core.is_connected = False
        core.is_ready = False
        widget = _make_bare_widget(core)
        widget._connected_frame = MagicMock(visible=True)
        widget._disconnected_frame = MagicMock(visible=False)
        widget._submit_button = MagicMock(enabled=True)
        event = ComfyUIEventPayload("texturecraft", ComfyUIEventType.SETTINGS_CHANGED)

        # Act
        widget._on_core_event(event)

        # Assert
        self.assertFalse(widget._connected_frame.visible)
        self.assertTrue(widget._disconnected_frame.visible)
        self.assertFalse(widget._submit_button.enabled)

    async def test_running_state_event_autoloads_workflow_discovered_during_startup(self):
        """Entering RUNNING retries a deferred autoload from the cached workflow list."""
        # Arrange
        core = _make_core()
        core.available_workflows = [
            Workflow(name="Material Workflow", source_type=WorkflowSourceType.RTX_REMIX, category=WorkflowCategory.API)
        ]
        widget = _make_bare_widget(core)
        widget._workflow_dropdown = MagicMock()
        widget._schedule_workflow_load = MagicMock()
        event = ComfyUIEventPayload("texturecraft", ComfyUIEventType.STATE_CHANGED)

        # Act
        widget._on_core_event(event)

        # Assert
        widget._schedule_workflow_load.assert_called_once_with(core.available_workflows[0])

    async def test_disconnected_state_event_cancels_active_workflow_actions(self):
        """Leaving RUNNING cancels refresh, load, and submit work tied to the connection."""
        # Arrange
        core = _make_core(_make_workflow())
        core.state = ComfyUIState.READY
        core.is_connected = False
        core.is_ready = False
        widget = _make_bare_widget(core)
        widget._connected_frame = MagicMock()
        widget._disconnected_frame = MagicMock()
        widget._submit_button = MagicMock()
        refresh_task = MagicMock()
        load_task = MagicMock()
        submit_task = MagicMock()
        widget._workflow_refresh_task = refresh_task
        widget._workflow_load_task = load_task
        widget._submit_task = submit_task

        # Act
        widget._on_core_event(ComfyUIEventPayload("texturecraft", ComfyUIEventType.STATE_CHANGED))

        # Assert
        refresh_task.cancel.assert_called_once_with()
        load_task.cancel.assert_called_once_with()
        submit_task.cancel.assert_called_once_with()
        self.assertIsNone(widget._workflow_refresh_task)
        self.assertIsNone(widget._workflow_load_task)
        self.assertIsNone(widget._submit_task)
        self.assertFalse(widget._submission_confirmation_open)

    async def test_workflow_change_resets_selection_and_rebuilds_all_sections(self):
        """A workflow change clears selection and rebuilds every dependent section."""
        # Arrange
        widget = _make_bare_widget(_make_core(_make_workflow()))
        widget._selected_input_index = 1
        widget._update_workflow_combo = MagicMock()
        widget._update_preset_combo = MagicMock()
        widget._rebuild_inputs_property_widget = MagicMock()
        widget._rebuild_properties_panel = MagicMock()
        widget._update_submit_button_state = MagicMock()

        # Act
        widget._on_workflow_changed()

        # Assert
        self.assertIsNone(widget._selected_input_index)
        widget._update_workflow_combo.assert_called_once_with()
        widget._update_preset_combo.assert_called_once_with()
        widget._rebuild_inputs_property_widget.assert_called_once_with()
        widget._rebuild_properties_panel.assert_called_once_with()
        widget._update_submit_button_state.assert_called_once_with()

    async def test_destroy_cancels_tasks_and_releases_widgets(self):
        """Destroy cancels retained work and clears owned widget references."""
        # Arrange
        widget = _make_bare_widget(_make_core(_make_workflow()))
        tasks = [MagicMock(), MagicMock(), MagicMock()]
        widget._workflow_refresh_task, widget._workflow_load_task, widget._submit_task = tasks
        widget._event_subscription = MagicMock()
        widget._inputs_property_widget = MagicMock()
        widget._property_widget = MagicMock()
        widget._workflow_dropdown = MagicMock()
        widget._getter_subscriptions = [MagicMock()]

        # Act
        widget.destroy()

        # Assert
        for task in tasks:
            task.cancel.assert_called_once_with()
        self.assertIsNone(widget._workflow_refresh_task)
        self.assertIsNone(widget._workflow_load_task)
        self.assertIsNone(widget._submit_task)
        self.assertIsNone(widget._event_subscription)
        self.assertIsNone(widget._inputs_property_widget)
        self.assertIsNone(widget._property_widget)
        self.assertIsNone(widget._workflow_dropdown)

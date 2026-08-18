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

import pathlib
from copy import deepcopy
from unittest.mock import MagicMock, patch

from carb.input import MouseEventType
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from lightspeed.trex.comfyui.core.enums import (
    ComfyUIEventType,
    ComfyUIState,
    RemixType,
    WorkflowCategory,
    WorkflowSourceType,
)
from lightspeed.trex.comfyui.core.events import ComfyUIEventPayload
from lightspeed.trex.comfyui.core.models import Workflow, WorkflowInput
from lightspeed.trex.comfyui.core.preset import Preset
from lightspeed.trex.comfyui.core.resolvers import ConstantResolver, SelectedTextureResolver
from lightspeed.trex.comfyui.widget.workflow.widget import WorkflowSetupWidget
from omni import ui, usd
from omni.flux.utils.widget.resources import get_icons


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


def _make_texture_workflow() -> Workflow:
    """Create a workflow whose texture input defaults to the Remix getter.

    Returns:
        The texture workflow with its resolver default captured.
    """
    workflow_input = WorkflowInput(
        port_id="1.inputs.texture",
        label="Texture",
        native_type=pathlib.Path,
        default_value="",
        value=SelectedTextureResolver(context_name="texturecraft"),
        remix_type=RemixType.TEXTURE_FILE_PATH,
        tooltip="Texture source",
    )
    workflow = Workflow(
        name="Texture Workflow",
        source_type=WorkflowSourceType.RTX_REMIX,
        category=WorkflowCategory.API,
        inputs=[workflow_input],
    )
    workflow.workflow_defaults = {workflow_input.port_id: deepcopy(workflow_input.value)}
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
        (WorkflowCategory.API, WorkflowSourceType.RTX_REMIX, "Material Workflow"),
        (WorkflowCategory.FULL, WorkflowSourceType.USER, "UI Only"),
    ]
    return core


async def _wait_for_widget(selector: str, max_attempts: int = 20):
    """Wait for a dynamically rebuilt widget to enter the UI query tree.

    Args:
        selector: UI test query identifying the expected widget.
        max_attempts: Maximum human-delay intervals to wait.

    Returns:
        The matching UI test widget, or None when the frame budget expires.
    """
    for _ in range(max_attempts):
        matches = ui_test.find_all(selector)
        if matches:
            return matches[0]
        await ui_test.human_delay()
    return None


class TestWorkflowSetupWidgetE2E(AsyncTestCase):
    """Tests workflow selection, input editing, and submission UI behavior."""

    async def setUp(self):
        """Create a visible UI window for each workflow-widget test."""
        self._context = usd.get_context("texturecraft")
        self._owns_context = self._context is None
        self._context = self._context or usd.create_context("texturecraft")
        self._event_callback = None

        def subscribe(_context_name, callback):
            """Capture the production event boundary used by the rendered widget.

            Args:
                _context_name: Context whose ComfyUI events are observed.
                callback: Widget callback registered with the event source.

            Returns:
                Subscription handle retained by the widget.
            """
            self._event_callback = callback
            return MagicMock()

        self._event_subscription_patch = patch(
            "lightspeed.trex.comfyui.widget.workflow.widget.subscribe_comfyui_event",
            side_effect=subscribe,
        )
        self._event_subscription_patch.start()
        self.addCleanup(self._event_subscription_patch.stop)
        self._window = ui.Window(
            f"TestWorkflowSetupWidget_{self._testMethodName}",
            visible=True,
            width=800,
            height=800,
        )
        self._real_widget = None

    async def tearDown(self):
        """Destroy any real widget and its test window."""
        if self._real_widget is not None:
            self._real_widget.destroy()
        self._window.destroy()
        if self._owns_context:
            if self._context.get_stage() is not None:
                await self._context.close_stage_async()
            usd.destroy_context("texturecraft")
        await ui_test.human_delay()

    async def _build_real_widget(self, workflow: Workflow, core=None):
        """Build the workflow UI with a running core and wait for rendering.

        Args:
            workflow: Workflow rendered in the test window.
            core: Optional core whose current connection state is rendered.

        Returns:
            Mocked running core backing the rendered widget.
        """
        if self._real_widget is not None:
            self._real_widget.destroy()
            self._real_widget = None
            await ui_test.human_delay()

        core = core or _make_core(workflow)
        with patch(
            "lightspeed.trex.comfyui.widget.workflow.widget.get_comfyui_core_instance",
            return_value=core,
        ):
            with self._window.frame:
                self._real_widget = WorkflowSetupWidget(context_name="texturecraft")
        await ui_test.human_delay()
        return core

    async def _click_input(self, label: str) -> None:
        """Select one rendered workflow-input row by its user-facing label.

        Args:
            label: Exact input label visible in the workflow tree.
        """
        input_label = next(
            (
                candidate
                for candidate in ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='WorkflowInputName'")
                if candidate.widget.text == label
            ),
            None,
        )
        self.assertIsNotNone(input_label)
        await input_label.click()
        await ui_test.human_delay()

    async def _expand_group(self, label: str) -> None:
        """Expand one rendered workflow group through its branch control.

        Args:
            label: Exact group label visible in the workflow tree.
        """
        group_label = next(
            (
                candidate
                for candidate in ui_test.find_all(
                    f"{self._window.title}//Frame/**/Label[*].name=='PropertiesWidgetLabel'"
                )
                if candidate.widget.text == label
            ),
            None,
        )
        self.assertIsNotNone(group_label)
        branches = ui_test.find_all(f"{self._window.title}//Frame/**/Image[*].identifier=='property_branch'")
        self.assertTrue(branches)
        branch = min(branches, key=lambda candidate: abs(candidate.center.y - group_label.center.y))
        await branch.click()
        await ui_test.human_delay()

    async def test_build_real_widget_uses_context_and_builds_inputs(self):
        """A user sees the workflow inputs and stable workflow controls."""
        workflow = _make_workflow()

        # Render the real workflow widget and expose the material input group.
        await self._build_real_widget(workflow)
        await self._expand_group("Material")

        # The workflow, preset, run, and declared input controls are all visible together.
        self.assertIsNotNone(
            ui_test.find(f"{self._window.title}//Frame/**/SectionedComboBox[*].identifier=='ComfyWorkflowPicker'")
        )
        self.assertIsNotNone(
            ui_test.find(f"{self._window.title}//Frame/**/ComboBox[*].identifier=='ComfyPresetPicker'")
        )
        self.assertIsNotNone(ui_test.find(f"{self._window.title}//Frame/**/Button[*].identifier=='ComfyWorkflowRun'"))
        for workflow_input in workflow.inputs:
            labels = ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='WorkflowInputName'")
            self.assertIn(workflow_input.label, [label.widget.text for label in labels])

    async def test_disconnected_workflow_shows_broken_link_icon_above_guidance(self):
        """A disconnected workflow presents the real broken-link resource before its guidance."""
        core = _make_core()
        core.state = ComfyUIState.ERROR
        core.workflow = None
        core.is_connected = False
        core.is_ready = False

        # Render the disconnected workflow instead of constructing the empty state directly.
        await self._build_real_widget(_make_workflow(), core)

        # The broken-link icon leads the recovery guidance and uses the shipped resource.
        icon = ui_test.find(f"{self._window.title}//Frame/**/Image[*].name=='LinkOff'")
        title = ui_test.find(f"{self._window.title}//Frame/**/Label[*].text=='ComfyUI is not connected'")
        self.assertIsNotNone(icon)
        self.assertIsNotNone(title)
        icon_path = pathlib.Path(get_icons("link-off"))
        self.assertTrue(icon_path.is_file())
        self.assertEqual(icon_path.name, "link-off.svg")
        self.assertLess(icon.center.y, title.center.y)

    async def test_select_real_widget_builds_properties_and_breadcrumb(self):
        """Clicking an input row renders its native properties and breadcrumb."""
        # Open the real widget and select the Boolean input through its rendered row.
        await self._build_real_widget(_make_workflow())

        await self._click_input("Enabled")

        # The visible breadcrumb and editor reflect the selected input.
        breadcrumb_text = [
            label.widget.text
            for label in ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='Breadcrumb'")
        ]
        self.assertEqual(breadcrumb_text, ["Enabled", "Boolean Constant"])
        self.assertIsNotNone(
            ui_test.find(f"{self._window.title}//Frame/**/CheckBox[*].identifier=='NativePropertyValue'")
        )

    async def test_rendered_texture_input_exposes_stable_controls_and_all_getters(self):
        """Opening a texture getter offers the Remix getter and Constant, never File Path."""
        # Render a texture workflow and inspect the getter choices exposed by its real combo box.
        await self._build_real_widget(_make_texture_workflow())
        getter = await _wait_for_widget(f"{self._window.title}//Frame/**/ComboBox[*].identifier=='ComfyGetterPicker'")

        getter_model = getter.widget.model
        labels = [getter_model.get_item_value_model(item).as_string for item in getter_model.get_item_children(None)]

        # The user receives one semantic getter and one typed Constant fallback without a duplicate file-path getter.
        self.assertEqual(labels, ["Selected Texture", "All Textures", "File Path Constant"])
        self.assertNotIn("File Path", labels)

    async def test_getter_columns_restore_proportions_after_window_resize(self):
        """The getter returns to its proportional column after a narrow-window layout."""
        # Capture the rendered two-column proportions at the normal panel width.
        await self._build_real_widget(_make_texture_workflow())
        getter = await _wait_for_widget(f"{self._window.title}//Frame/**/ComboBox[*].identifier=='ComfyGetterPicker'")
        input_label = next(
            label
            for label in ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='WorkflowInputName'")
            if label.widget.text == "Texture"
        )
        self.assertIsNotNone(getter)
        initial_column_gap = getter.position.x - input_label.position.x
        initial_width = getter.size.x

        # Collapse and restore the real window so layout must recompute from available width.
        self._window.width = 240
        await ui_test.human_delay()
        self._window.width = 800
        await ui_test.human_delay()
        resized_getter = await _wait_for_widget(
            f"{self._window.title}//Frame/**/ComboBox[*].identifier=='ComfyGetterPicker'"
        )
        resized_input_label = next(
            label
            for label in ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='WorkflowInputName'")
            if label.widget.text == "Texture"
        )

        # Both the column boundary and getter width return to their original proportions.
        self.assertAlmostEqual(
            resized_getter.position.x - resized_input_label.position.x,
            initial_column_gap,
            delta=1,
        )
        self.assertAlmostEqual(resized_getter.size.x, initial_width, delta=1)

    async def test_selecting_file_path_constant_getter_selects_row_and_shows_native_editor(self):
        """Choosing File Path Constant selects its row and exposes the shared file editor."""
        core = await self._build_real_widget(_make_texture_workflow())
        getter = await _wait_for_widget(f"{self._window.title}//Frame/**/ComboBox[*].identifier=='ComfyGetterPicker'")

        # Choose Constant from the rendered getter selector, as a user would.
        getter.widget.model.get_item_value_model().set_value(2)
        await ui_test.human_delay()

        # Selection follows the changed row and the native path editor replaces getter properties.
        self.assertIsInstance(core.workflow.inputs[0].value, ConstantResolver)
        self.assertEqual(core.workflow.inputs[0].value.value, pathlib.Path())
        selected_rows = self._real_widget._inputs_property_widget.tree_view.selection
        self.assertEqual([item.workflow_input for item in selected_rows], [core.workflow.inputs[0]])
        self.assertEqual(
            [
                label.widget.text
                for label in ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='Breadcrumb'")
            ],
            ["Texture", "File Path Constant"],
        )
        self.assertIsNotNone(
            ui_test.find(f"{self._window.title}//Frame/**/StringField[*].identifier=='NativePropertyValue'")
        )
        self.assertIsNotNone(
            ui_test.find(f"{self._window.title}//Frame/**/Image[*].identifier=='NativePropertyFilePicker'")
        )
        value_field = ui_test.find(f"{self._window.title}//Frame/**/StringField[*].identifier=='NativePropertyValue'")
        self.assertEqual(value_field.widget.model.as_string, "")

    async def test_each_constant_uses_its_native_editor_and_type_specific_label(self):
        """Every native Constant renders a typed editor without repeating the input label."""
        expected_editors = (
            ("Source File", pathlib.Path("source.png"), "File Path Constant", "StringField"),
            ("Enabled", True, "Boolean Constant", "CheckBox"),
            ("Iterations", 4, "Integer Constant", "IntDrag"),
            ("Strength", 0.5, "Number Constant", "FloatDrag"),
            ("Prompt", "restore detail", "Text Constant", "StringField"),
        )

        # Exercise every supported constant through the same rendered property-editor path.
        for input_label, value, property_label, widget_type in expected_editors:
            with self.subTest(input_label=input_label):
                workflow_input = _make_input(input_label, value)
                workflow = Workflow(
                    name=f"{input_label} Workflow",
                    source_type=WorkflowSourceType.RTX_REMIX,
                    category=WorkflowCategory.API,
                    inputs=[workflow_input],
                )
                workflow.workflow_defaults = {workflow_input.port_id: deepcopy(workflow_input.value)}
                await self._build_real_widget(workflow)
                await self._click_input(input_label)

                self.assertIsNotNone(
                    ui_test.find(f"{self._window.title}//Frame/**/{widget_type}[*].identifier=='NativePropertyValue'")
                )
                property_labels = [
                    label.widget.text
                    for label in ui_test.find_all(
                        f"{self._window.title}//Frame/**/Label[*].name=='PropertiesWidgetLabel'"
                    )
                ]
                self.assertIn(property_label, property_labels)
                self.assertNotIn(input_label, property_labels)
                if input_label == "Source File":
                    self.assertIsNotNone(
                        ui_test.find(f"{self._window.title}//Frame/**/Image[*].identifier=='NativePropertyFilePicker'")
                    )

    async def test_selecting_rendered_texture_getter_shows_typed_properties(self):
        """Clicking a texture row exposes the typed texture-choice editor."""
        # Open the real texture workflow and select its input row.
        await self._build_real_widget(_make_texture_workflow())

        await self._click_input("Texture")

        # The visible properties panel exposes the selected-texture controls.
        self.assertIsNotNone(
            await _wait_for_widget(f"{self._window.title}//Frame/**/ComboBox[*].identifier=='NativePropertyValue'")
        )
        self.assertIsNotNone(ui_test.find(f"{self._window.title}//Frame/**/Label[*].text=='Selected Texture'"))

    async def test_connected_workflow_without_selection_shows_input_guidance(self):
        """A connected user without a selected workflow sees actionable input guidance."""
        core = _make_core()
        core.available_workflows = []

        # Open the connected workflow panel before any workflow has been selected.
        await self._build_real_widget(_make_workflow(), core)

        # The rendered panel explains the next user action instead of showing an empty tree.
        self.assertTrue(
            ui_test.find_all(
                f"{self._window.title}//Frame/**/Label[*].text=='Select a workflow above to configure its inputs'"
            )
        )

    async def test_editing_rendered_parameter_clears_active_preset(self):
        """Editing a rendered input leaves the preset picker in its custom-value state."""
        workflow = _make_workflow()
        workflow.active_preset = "default"
        await self._build_real_widget(workflow)
        await self._expand_group("Material")
        await self._click_input("Strength")
        value_editor = await _wait_for_widget(
            f"{self._window.title}//Frame/**/FloatDrag[*].identifier=='NativePropertyValue'"
        )

        # Change the value through the same model driven by the rendered editor.
        value_editor.widget.model.set_value(0.75)
        await ui_test.human_delay()

        # The visible preset picker identifies the edited values as custom rather than a saved preset.
        preset_picker = ui_test.find(f"{self._window.title}//Frame/**/ComboBox[*].identifier=='ComfyPresetPicker'")
        preset_model = preset_picker.widget.model
        selected_index = preset_model.get_item_value_model().as_int
        selected_item = preset_model.get_item_children(None)[selected_index]
        self.assertEqual(preset_model.get_item_value_model(selected_item).as_string, "Select a preset")

    async def test_dragging_splitter_down_gives_workflow_inputs_more_room(self):
        """Dragging the rendered divider down gives workflow inputs more room."""
        # Render both panels and record their sizes before interacting with the divider.
        await self._build_real_widget(_make_workflow())
        await self._click_input("Enabled")
        splitter = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].identifier=='ComfyWorkflowInputSplitter'")
        inputs = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyWorkflowInputsPanel'")
        properties = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyInputPropertiesPanel'")
        self.assertIsNotNone(splitter)
        self.assertIsNotNone(inputs)
        self.assertIsNotNone(properties)
        inputs_height = inputs.size.y
        properties_height = properties.size.y
        splitter_y = splitter.center.y

        # Drag the real divider and wait for Kit to lay out both adjacent panels.
        await ui_test.emulate_mouse_drag_and_drop(splitter.center, splitter.center + ui_test.Vec2(0, 20))
        await ui_test.human_delay()

        splitter_travel = splitter.center.y - splitter_y
        self.assertGreater(splitter_travel, 10)
        self.assertAlmostEqual(inputs.size.y - inputs_height, splitter_travel, delta=2)
        self.assertAlmostEqual(properties_height - properties.size.y, splitter_travel, delta=2)

    async def test_dragging_splitter_after_connecting_gives_workflow_inputs_more_room(self):
        """The real disconnected-to-connected workflow keeps an interactive divider."""
        # Build the disconnected view, then publish the same state change used by a live connection.
        workflow = _make_workflow()
        core = _make_core(workflow)
        core.state = ComfyUIState.READY
        core.is_connected = False
        core.is_ready = False
        await self._build_real_widget(workflow, core)
        core.state = ComfyUIState.RUNNING
        core.is_connected = True
        core.is_ready = True
        self.assertIsNotNone(self._event_callback)
        self._event_callback(ComfyUIEventPayload("texturecraft", ComfyUIEventType.STATE_CHANGED))
        await ui_test.human_delay()
        splitter = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].identifier=='ComfyWorkflowInputSplitter'")
        inputs = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyWorkflowInputsPanel'")
        properties = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyInputPropertiesPanel'")
        self.assertIsNotNone(splitter)
        self.assertIsNotNone(inputs)
        self.assertIsNotNone(properties)
        for _ in range(10):
            if abs(splitter.center.y - inputs.position.y - inputs.size.y - 10) <= 1:
                break
            await ui_test.human_delay()
        else:
            self.fail("Splitter did not align with the workflow-input panel after connection")
        inputs_height = inputs.size.y
        properties_height = properties.size.y
        splitter_y = splitter.center.y

        # Drag after the connection rebuild and verify the handle follows the resized panels.
        await ui_test.emulate_mouse_drag_and_drop(splitter.center, splitter.center + ui_test.Vec2(0, 20))
        await ui_test.human_delay()

        input_growth = inputs.size.y - inputs_height
        self.assertGreater(input_growth, 0)
        self.assertAlmostEqual(properties_height - properties.size.y, input_growth, delta=1)
        self.assertAlmostEqual(splitter.center.y - splitter_y, input_growth, delta=1)

    async def test_splitter_starts_high_and_dragging_up_gives_properties_more_room(self):
        """The divider remains at its upper bound while a drag continues above it."""
        # Begin a real pointer drag far beyond the upper limit without releasing the mouse.
        await self._build_real_widget(_make_workflow())
        await self._click_input("Enabled")
        splitter = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].identifier=='ComfyWorkflowInputSplitter'")
        inputs = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyWorkflowInputsPanel'")
        properties = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyInputPropertiesPanel'")
        self.assertIsNotNone(splitter)
        self.assertIsNotNone(inputs)
        self.assertIsNotNone(properties)
        inputs_height = inputs.size.y
        properties_height = properties.size.y
        splitter_y = splitter.center.y
        splitter_start = splitter.center
        splitter_target = splitter_start - ui_test.Vec2(0, 150)
        self.assertLess(inputs_height, properties.size.y)

        await ui_test.input.emulate_mouse(MouseEventType.MOVE, splitter_start)
        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, splitter_start)
        await ui_test.human_delay()
        await ui_test.input.emulate_mouse_slow_move(splitter_start, splitter_target)

        try:
            # The divider and both panels clamp together while the pointer remains out of bounds.
            upward_travel = inputs_height - 100
            self.assertAlmostEqual(inputs.size.y, 100, delta=1)
            self.assertAlmostEqual(properties.size.y - properties_height, upward_travel, delta=1)
            self.assertAlmostEqual(splitter_y - splitter.center.y, upward_travel, delta=1)
        finally:
            await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP, splitter_target)
            await ui_test.human_delay()

        self.assertAlmostEqual(splitter_y - splitter.center.y, upward_travel, delta=1)

    async def test_splitter_stops_at_maximum_workflow_inputs_height(self):
        """The divider remains at its lower bound while a drag continues below it."""
        # Begin a real pointer drag far beyond the lower limit without releasing the mouse.
        await self._build_real_widget(_make_workflow())
        await self._click_input("Enabled")
        splitter = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].identifier=='ComfyWorkflowInputSplitter'")
        inputs = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyWorkflowInputsPanel'")
        properties = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyInputPropertiesPanel'")
        self.assertIsNotNone(splitter)
        self.assertIsNotNone(inputs)
        self.assertIsNotNone(properties)
        inputs_height = inputs.size.y
        properties_height = properties.size.y
        splitter_y = splitter.center.y
        splitter_start = splitter.center
        splitter_target = splitter_start + ui_test.Vec2(0, 300)

        await ui_test.input.emulate_mouse(MouseEventType.MOVE, splitter_start)
        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, splitter_start)
        await ui_test.human_delay()
        await ui_test.input.emulate_mouse_slow_move(splitter_start, splitter_target)

        try:
            # The divider and both panels clamp together while the pointer remains out of bounds.
            maximum_inputs_height = inputs_height + properties_height - 100
            maximum_downward_travel = properties_height - 100
            self.assertAlmostEqual(inputs.size.y, maximum_inputs_height, delta=1)
            self.assertAlmostEqual(properties.size.y, 100, delta=1)
            self.assertAlmostEqual(splitter.center.y - splitter_y, maximum_downward_travel, delta=1)
            self.assertAlmostEqual(splitter.center.y - inputs.position.y - inputs.size.y, 10, delta=1)
        finally:
            await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP, splitter_target)
            await ui_test.human_delay()

        self.assertAlmostEqual(splitter.center.y - splitter_y, maximum_downward_travel, delta=1)

    async def test_splitter_recomputes_its_maximum_after_window_resize(self):
        """Shrinking the window keeps both panels usable and the divider aligned."""
        await self._build_real_widget(_make_workflow())
        await self._click_input("Enabled")
        splitter = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].identifier=='ComfyWorkflowInputSplitter'")
        inputs = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyWorkflowInputsPanel'")
        properties = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyInputPropertiesPanel'")
        self.assertIsNotNone(splitter)
        self.assertIsNotNone(inputs)
        self.assertIsNotNone(properties)

        # Put the divider at its lower bound so the next shrink must recompute it.
        await ui_test.emulate_mouse_drag_and_drop(splitter.center, splitter.center + ui_test.Vec2(0, 300))
        await ui_test.human_delay()
        self.assertGreater(inputs.size.y, 200)
        self.assertAlmostEqual(properties.size.y, 100, delta=1)

        # Rapid real window resizes must recompute from the final rendered panel bounds.
        for height in (750, 700, 650):
            self._window.height = height
        for _ in range(10):
            await ui_test.human_delay()
            if properties.size.y >= 99 and abs(splitter.center.y - inputs.position.y - inputs.size.y - 10) <= 1:
                break
        else:
            self.fail("Splitter did not recompute its bounds after the window resize")

        self.assertGreaterEqual(inputs.size.y, 100)
        self.assertGreaterEqual(properties.size.y, 100)
        self.assertAlmostEqual(splitter.center.y - inputs.position.y - inputs.size.y, 10, delta=1)
        splitter = ui_test.find(f"{self._window.title}//Frame/**/Rectangle[*].identifier=='ComfyWorkflowInputSplitter'")
        inputs = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyWorkflowInputsPanel'")
        properties = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='ComfyInputPropertiesPanel'")
        inputs_height = inputs.size.y
        properties_height = properties.size.y
        splitter_y = splitter.center.y

        # The recomputed handle remains the source of truth for the next real drag.
        await ui_test.emulate_mouse_drag_and_drop(splitter.center, splitter.center - ui_test.Vec2(0, 20))
        await ui_test.human_delay()

        splitter_travel = splitter_y - splitter.center.y
        self.assertGreater(splitter_travel, 10)
        self.assertAlmostEqual(inputs_height - inputs.size.y, splitter_travel, delta=2)
        self.assertAlmostEqual(properties.size.y - properties_height, splitter_travel, delta=2)

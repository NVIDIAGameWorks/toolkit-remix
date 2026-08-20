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

__all__ = ["WorkflowSetupWidget"]

import asyncio
import functools
import threading

import carb
from lightspeed.trex.comfyui.core.core import ComfyUISubmission
from lightspeed.trex.comfyui.core.enums import (
    ComfyUIEventType,
    ComfyUIState,
    WorkflowCategory,
    WorkflowType,
)
from lightspeed.trex.comfyui.core.events import subscribe_comfyui_event
from lightspeed.trex.comfyui.core.extension import get_comfyui_core_instance
from lightspeed.trex.comfyui.core.models import Workflow
from lightspeed.trex.comfyui.core.resolvers import ConstantResolver, ResolverConfigurationError
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from lightspeed.trex.utils.widget.workspace import WorkspaceWidget
from omni import ui, usd
from omni.flux.property_widget_builder.model.native import NativeDelegate
from omni.flux.property_widget_builder.widget import Model, PropertyWidget
from omni.flux.utils.common.decorators import ignore_function_decorator
from omni.flux.utils.dialog.progress_popup import ProgressPopup
from omni.flux.utils.widget.collapsable_frame import PropertyCollapsableFrameWithInfoPopup
from omni.flux.utils.widget.combo_box import SectionedComboBox, SectionedComboItem
from omni.flux.utils.widget.hover import CursorShapesEnum, hover_helper
from omni.kit.app import get_app

from .constants import WORKFLOW_SOURCE_LABELS, get_native_constant_label
from .delegate import WorkflowInputDelegate
from .items import (
    InputItemGroup,
    ResolverParamItem,
    WorkflowGroupItem,
)
from .model import SimpleComboModel


class WorkflowSetupWidget(WorkspaceWidget):
    """Master-detail widget for selecting a ComfyUI workflow and configuring its inputs."""

    _CONTENT_PADDING = ui.Pixel(5)
    _SECTION_SPACING = ui.Pixel(16)
    _FORM_SPACING = ui.Pixel(8)

    _DISCONNECTED_ICON_SIZE = ui.Pixel(40)
    _DISCONNECTED_GAP = ui.Pixel(8)
    _DISCONNECTED_SUB_GAP = ui.Pixel(4)
    _REFRESH_ICON_SIZE = ui.Pixel(16)
    _BREADCRUMB_DOT_SIZE = ui.Pixel(4)
    _BREADCRUMB_SPACING = ui.Pixel(6)
    _DEFAULT_INPUTS_PANEL_HEIGHT = 200
    _MINIMUM_INPUTS_PANEL_HEIGHT = 100
    _MINIMUM_PROPERTIES_PANEL_HEIGHT = 100
    _SPLITTER_TOP_SPACING = 8
    _SPLITTER_HEIGHT = 4

    _NAME_COLUMN_PERCENT = 40

    _DEFAULT_GROUP_NAME = "Ungrouped"

    _EMPTY_WORKFLOW_TEXT = "Select a workflow above to configure its inputs"
    _EMPTY_SELECTION_TEXT = "Select an input above to view its properties"
    _NO_PROPERTIES_TEXT = "No properties to configure"
    _NO_WORKFLOWS_TEXT = "No workflows available"
    _ALL_WORKFLOW_TYPES_TEXT = "All"
    _SELECT_WORKFLOW_TEXT = "Select a workflow"
    _NO_WORKFLOW_PRESET_TEXT = "Select a workflow first"
    _NO_PRESETS_TEXT = "No presets available for this workflow"
    _TYPE_FILTER_TOOLTIP = "Filter workflows by type"

    def __init__(self, context_name: str):
        """Initialize workflow controls for a USD context.

        Args:
            context_name: USD context whose selections and ComfyUI workflow state are edited.
        """
        self._context_name = context_name
        self._core = get_comfyui_core_instance(context_name=context_name)

        self._selected_input_index: int | None = None

        self._inputs_frame: ui.Frame | None = None
        self._inputs_panel_frame: ui.Frame | None = None
        self._properties_panel_frame: ui.Frame | None = None
        self._inputs_section: PropertyCollapsableFrameWithInfoPopup | None = None
        self._inputs_property_widget: PropertyWidget | None = None
        self._inputs_model: Model | None = None
        self._inputs_delegate: WorkflowInputDelegate | None = None
        self._getter_subscriptions: list = []

        self._properties_container: ui.VStack | None = None
        self._properties_section: PropertyCollapsableFrameWithInfoPopup | None = None
        self._breadcrumb_container: ui.Frame | None = None
        self._breadcrumb_input_text: str = ""
        self._breadcrumb_getter_text: str = ""
        self._submit_button: ui.Button | None = None
        self._property_widget: PropertyWidget | None = None
        self._property_model: Model | None = None
        self._property_delegate: NativeDelegate | None = None
        self._property_subscriptions: list = []

        self._workflow_dropdown: SectionedComboBox | None = None
        self._workflow_list: list[Workflow] = []
        self._workflow_type_combo: SectionedComboBox | None = None
        self._selected_workflow_type: WorkflowType | None = None
        self._preset_combo: ui.ComboBox | None = None
        self._preset_names: list[str | None] = []

        self._connected_frame: ui.Frame | None = None
        self._disconnected_frame: ui.Frame | None = None
        self._root_stack: ui.ZStack | None = None
        self._panels_frame: ui.Frame | None = None
        self._panels_splitter: ui.Placer | None = None
        self._normalize_splitter_drag = False

        self._event_subscription = None
        self._stage_event_subscription = None
        self._workflow_refresh_task: asyncio.Task | None = None
        self._workflow_load_task: asyncio.Task | None = None
        self._submit_task: asyncio.Task | None = None
        self._splitter_layout_task: asyncio.Task | None = None
        self._selected_workflow_identity: Workflow | None = None
        self._workflow_load_failed = False
        self._submission_confirmation_open = False

        super().__init__()

        self._build_ui()
        self._event_subscription = subscribe_comfyui_event(context_name, self._on_core_event)
        context = usd.get_context(context_name)
        self._stage_event_subscription = context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event,
            name="ComfyUIWorkflowProjectState",
        )
        self._on_workflow_changed()

    def _build_ui(self):
        """Construct the full master-detail layout."""
        self._root_stack = ui.ZStack()
        with self._root_stack:
            ui.Rectangle(name="WorkspaceBackground")

            self._connected_frame = ui.Frame(visible=self._core.is_connected)
            with self._connected_frame:
                self._build_content()

            self._disconnected_frame = ui.Frame(visible=not self._core.is_connected)
            with self._disconnected_frame:
                self._build_disconnected_ui()

            self._panels_splitter = ui.Placer(
                draggable=True,
                height=ui.Pixel(self._SPLITTER_HEIGHT),
                drag_axis=ui.Axis.Y,
                stable_size=True,
                visible=self._core.is_connected,
                offset_y_changed_fn=self._on_panels_splitter_changed,
                identifier="ComfyWorkflowInputSplitter",
            )
            with self._panels_splitter:
                with ui.HStack(height=ui.Pixel(self._SPLITTER_HEIGHT)):
                    ui.Spacer(width=self._CONTENT_PADDING)
                    with ui.Frame(build_fn=self._synchronize_panels_splitter):
                        splitter_manipulator = ui.Rectangle(
                            width=ui.Percent(100),
                            height=ui.Pixel(self._SPLITTER_HEIGHT),
                            name="PropertiesPaneSectionTreeManipulator",
                            identifier="ComfyWorkflowInputSplitter",
                            mouse_pressed_fn=self._on_panels_splitter_pressed,
                            mouse_released_fn=self._on_panels_splitter_released,
                        )
                        hover_helper(splitter_manipulator, CursorShapesEnum.VERTICAL_RESIZE)
                    ui.Spacer(width=self._CONTENT_PADDING)

    def _build_content(self):
        """Build the connected-state content: workflow selector, split panels, and submit button."""
        with ui.VStack(spacing=0):
            with ui.HStack(height=0):
                ui.Spacer(width=self._CONTENT_PADDING)
                with ui.VStack(spacing=self._SECTION_SPACING):
                    ui.Spacer(height=self._CONTENT_PADDING)
                    self._build_workflow_section()
                ui.Spacer(width=self._CONTENT_PADDING)

            ui.Spacer(height=self._SECTION_SPACING)

            self._panels_frame = ui.Frame(height=ui.Fraction(1))
            self._panels_frame.set_computed_content_size_changed_fn(self._on_panels_frame_size_changed)
            with self._panels_frame:
                with ui.ZStack():
                    with ui.HStack():
                        ui.Spacer(width=self._CONTENT_PADDING)
                        with ui.VStack(spacing=0):
                            self._inputs_panel_frame = ui.Frame(
                                height=ui.Pixel(self._DEFAULT_INPUTS_PANEL_HEIGHT),
                                identifier="ComfyWorkflowInputsPanel",
                            )
                            with self._inputs_panel_frame:
                                self._inputs_section = PropertyCollapsableFrameWithInfoPopup(
                                    "WORKFLOW INPUTS",
                                    info_text=(
                                        "Each row is a workflow parameter. Use the dropdown to choose how its "
                                        "value is resolved."
                                    ),
                                )
                                self._inputs_section.root.height = ui.Fraction(1)
                                self._inputs_section.root.set_collapsed_changed_fn(
                                    functools.partial(self._on_collapsable_section_changed, self._inputs_section.root)
                                )
                                with self._inputs_section:
                                    with ui.ScrollingFrame(
                                        name="PropertiesPaneSection",
                                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                    ):
                                        self._inputs_frame = ui.Frame()
                                        with self._inputs_frame:
                                            self._build_empty_inputs_state()

                            ui.Spacer(height=ui.Pixel(self._SPLITTER_TOP_SPACING + self._SPLITTER_HEIGHT))
                            ui.Spacer(height=self._SECTION_SPACING)

                            self._properties_panel_frame = ui.Frame(
                                height=ui.Fraction(1),
                                identifier="ComfyInputPropertiesPanel",
                            )
                            with self._properties_panel_frame:
                                self._properties_section = PropertyCollapsableFrameWithInfoPopup(
                                    "INPUT PROPERTIES",
                                    info_text="Fine-tune the parameters of the selected input's value resolver.",
                                    header_actions_fn=self._build_properties_breadcrumb,
                                )
                                self._properties_section.root.height = ui.Fraction(1)
                                self._properties_section.root.set_collapsed_changed_fn(
                                    functools.partial(
                                        self._on_collapsable_section_changed, self._properties_section.root
                                    )
                                )
                                with self._properties_section:
                                    with ui.ScrollingFrame(
                                        name="PropertiesPaneSection",
                                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                    ):
                                        self._properties_container = ui.VStack(
                                            spacing=self._FORM_SPACING,
                                        )
                                        self._rebuild_properties_panel()
                        ui.Spacer(width=self._CONTENT_PADDING)

            with ui.HStack(height=0):
                ui.Spacer(width=self._CONTENT_PADDING)
                self._submit_button = ui.Button(
                    "Run Workflow",
                    identifier="ComfyWorkflowRun",
                    height=0,
                    clicked_fn=self._on_submit_clicked,
                )
                ui.Spacer(width=self._CONTENT_PADDING)
            ui.Spacer(height=self._CONTENT_PADDING)
            self._update_submit_button_state()

    def _synchronize_panels_splitter(self) -> None:
        """Align the divider with the current panel geometry and bounds."""
        if self._inputs_panel_frame is None:
            return
        inputs_height = self._inputs_panel_frame.computed_height or self._DEFAULT_INPUTS_PANEL_HEIGHT
        self._set_inputs_panel_height(inputs_height)

    def _on_panels_frame_size_changed(self) -> None:
        """Schedule a divider update after the panels frame changes size."""
        if not self._core.is_connected:
            return
        if self._splitter_layout_task is not None:
            self._splitter_layout_task.cancel()
        self._splitter_layout_task = asyncio.ensure_future(self._synchronize_panels_splitter_after_layout())
        self._splitter_layout_task.set_name("ComfyUIWorkflowSplitterLayout")

    async def _synchronize_panels_splitter_after_layout(self) -> None:
        """Align the divider after a layout change has been applied."""
        task = asyncio.current_task()
        try:
            await get_app().next_update_async()
            await get_app().next_update_async()
            if self._splitter_layout_task is task and self._core.is_connected:
                self._synchronize_panels_splitter()
        finally:
            if self._splitter_layout_task is task:
                self._splitter_layout_task = None

    def _on_panels_splitter_changed(self, offset_y: ui.Length) -> None:
        """Resize the workflow-input panel from the native tree manipulator.

        Args:
            offset_y: Current vertical placement reported by the drag handle.
        """
        if (
            self._root_stack is None
            or self._panels_frame is None
            or self._inputs_panel_frame is None
            or self._panels_splitter is None
        ):
            return
        panels_origin = self._panels_frame.screen_position_y - self._root_stack.screen_position_y
        if self._normalize_splitter_drag:
            self._normalize_splitter_drag = False
            requested_height = self._inputs_panel_frame.computed_height
        else:
            requested_height = offset_y.value - panels_origin - self._SPLITTER_TOP_SPACING
        self._set_inputs_panel_height(requested_height)

    @ignore_function_decorator(attrs=["_ignore_panels_splitter_change"])
    def _set_inputs_panel_height(self, requested_height: float) -> None:
        """Clamp both panels to their minimums and place the divider between them.

        Args:
            requested_height: Desired workflow-input panel height in pixels.
        """
        if (
            self._root_stack is None
            or self._panels_frame is None
            or self._inputs_panel_frame is None
            or self._panels_splitter is None
            or self._panels_frame.computed_height <= 0
        ):
            return

        panels_origin = self._panels_frame.screen_position_y - self._root_stack.screen_position_y
        maximum_height = max(
            self._MINIMUM_INPUTS_PANEL_HEIGHT,
            (
                self._panels_frame.computed_height
                - self._MINIMUM_PROPERTIES_PANEL_HEIGHT
                - self._SECTION_SPACING.value
                - self._SPLITTER_HEIGHT
                - self._SPLITTER_TOP_SPACING
            ),
        )
        panel_height = min(max(requested_height, self._MINIMUM_INPUTS_PANEL_HEIGHT), maximum_height)
        clamped_offset = panels_origin + panel_height + self._SPLITTER_TOP_SPACING
        self._panels_splitter.offset_y = ui.Pixel(clamped_offset)
        self._inputs_panel_frame.height = ui.Pixel(panel_height)

    def _on_panels_splitter_pressed(self, _x: float, _y: float, button: int, _modifiers: int) -> None:
        """Normalize the native drag handle to its layout coordinates on press.

        Args:
            _x: Unused horizontal pointer position.
            _y: Unused vertical pointer position.
            button: Pressed mouse button.
            _modifiers: Unused keyboard modifiers.
        """
        if button == 0:
            self._normalize_splitter_drag = True

    def _on_panels_splitter_released(self, _x: float, _y: float, button: int, _modifiers: int) -> None:
        """Clear pending drag normalization after a left-button release.

        Args:
            _x: Unused horizontal pointer position.
            _y: Unused vertical pointer position.
            button: Released mouse button.
            _modifiers: Unused keyboard modifiers.
        """
        if button == 0:
            self._normalize_splitter_drag = False

    @staticmethod
    def _on_collapsable_section_changed(widget: ui.CollapsableFrame, collapsed: bool) -> None:
        """Release a collapsed panel's flexible height allocation.

        Args:
            widget: Collapsible frame whose height should be updated.
            collapsed: Whether the frame has entered its collapsed state.
        """
        widget.height = ui.Pixel(0) if collapsed else ui.Fraction(1)

    def _build_disconnected_ui(self):
        """Build the disconnected-state overlay matching the job details empty pattern."""
        with ui.VStack():
            ui.Spacer()
            with ui.HStack(height=self._DISCONNECTED_ICON_SIZE):
                ui.Spacer()
                ui.Image(
                    "",
                    name="LinkOff",
                    width=self._DISCONNECTED_ICON_SIZE,
                    height=self._DISCONNECTED_ICON_SIZE,
                )
                ui.Spacer()
            ui.Spacer(height=self._DISCONNECTED_GAP)
            ui.Label(
                "ComfyUI is not connected",
                name="QueueDetailEmptyLabel",
                alignment=ui.Alignment.CENTER,
                height=0,
            )
            ui.Spacer(height=self._DISCONNECTED_SUB_GAP)
            ui.Label(
                "Open ComfyUI Setup to connect",
                name="QueueDetailEmptySubLabel",
                alignment=ui.Alignment.CENTER,
                height=0,
                tooltip="Go to AI Tools > ComfyUI Setup to configure the connection",
            )
            ui.Spacer()

    def _build_workflow_section(self):
        """Build the workflow and preset selection section with a refresh button in the header."""
        with PropertyCollapsableFrameWithInfoPopup(
            "WORKFLOW",
            info_text="Select a ComfyUI workflow and optionally apply a preset to pre-fill inputs.",
            header_actions_fn=self._build_refresh_icon,
        ):
            with ui.VStack(spacing=self._FORM_SPACING):
                with ui.HStack(spacing=self._FORM_SPACING, height=0):
                    ui.Label(
                        "Workflow Type",
                        width=ui.Percent(self._NAME_COLUMN_PERCENT),
                        word_wrap=False,
                        tooltip=self._TYPE_FILTER_TOOLTIP,
                    )
                    self._workflow_type_combo = SectionedComboBox(
                        on_selection_changed_fn=self._on_workflow_type_changed,
                        identifier="ComfyWorkflowTypePicker",
                        tooltip=self._TYPE_FILTER_TOOLTIP,
                        width=ui.Fraction(1),
                    )

                with ui.HStack(spacing=self._FORM_SPACING, height=0):
                    ui.Label(
                        "Workflow",
                        width=ui.Percent(self._NAME_COLUMN_PERCENT),
                        word_wrap=False,
                        tooltip="Select the ComfyUI workflow to run",
                    )
                    self._workflow_dropdown = SectionedComboBox(
                        on_selection_changed_fn=self._on_workflow_dropdown_changed,
                        identifier="ComfyWorkflowPicker",
                        tooltip="Select the ComfyUI workflow to run",
                        width=ui.Fraction(1),
                    )

                with ui.HStack(spacing=self._FORM_SPACING, height=0):
                    ui.Label(
                        "Preset",
                        width=ui.Percent(self._NAME_COLUMN_PERCENT),
                        word_wrap=False,
                        tooltip="Apply a preset to pre-fill workflow inputs",
                    )
                    self._preset_combo = ui.ComboBox(
                        0,
                        identifier="ComfyPresetPicker",
                        enabled=False,
                        width=ui.Fraction(1),
                        tooltip=self._NO_WORKFLOW_PRESET_TEXT,
                    )

    def _build_refresh_icon(self):
        """Build the refresh icon for the WORKFLOW header, matching the pin button pattern."""
        ui.Spacer()
        with ui.VStack(width=self._REFRESH_ICON_SIZE, content_clipping=True):
            ui.Spacer()
            ui.Image(
                "",
                name="Refresh",
                identifier="ComfyWorkflowRefresh",
                width=self._REFRESH_ICON_SIZE,
                height=self._REFRESH_ICON_SIZE,
                tooltip="Refresh available workflows",
                mouse_pressed_fn=lambda *_: self._on_refresh_clicked(),
            )
            ui.Spacer()
        ui.Spacer(width=self._FORM_SPACING)

    def _build_properties_breadcrumb(self):
        """Build the breadcrumb container inline with the INPUT PROPERTIES header.

        Called on every header build/rebuild (collapse/expand). The container
        uses ``Fraction(1)`` to claim the space the Spacer would have taken.
        Reads from stored text state so the breadcrumb survives header rebuilds.
        """
        self._breadcrumb_container = ui.HStack(width=ui.Fraction(1), spacing=self._BREADCRUMB_SPACING)
        with self._breadcrumb_container:
            self._render_breadcrumb()

    def _render_breadcrumb(self):
        """Render the breadcrumb labels from stored text state."""
        if not self._breadcrumb_input_text:
            ui.Spacer()
            return
        ui.Label(
            self._breadcrumb_input_text,
            name="Breadcrumb",
            width=ui.Fraction(1),
            elided_text=True,
            word_wrap=False,
            alignment=ui.Alignment.RIGHT_CENTER,
            tooltip=self._breadcrumb_input_text,
        )
        with ui.VStack(width=self._BREADCRUMB_DOT_SIZE):
            ui.Spacer()
            ui.Circle(
                radius=self._BREADCRUMB_DOT_SIZE.value / 2,
                name="QueueFooterDot",
                width=self._BREADCRUMB_DOT_SIZE,
                height=self._BREADCRUMB_DOT_SIZE,
                size_policy=ui.CircleSizePolicy.FIXED,
            )
            ui.Spacer()
        ui.Label(
            self._breadcrumb_getter_text,
            name="Breadcrumb",
            width=0,
            tooltip=self._breadcrumb_getter_text,
        )
        ui.Spacer(width=self._FORM_SPACING)

    def _build_empty_inputs_state(self):
        """Build placeholder when no workflow is selected."""
        ui.Label(
            self._EMPTY_WORKFLOW_TEXT,
            alignment=ui.Alignment.CENTER,
            word_wrap=True,
            name="QueueDetailEmptyLabel",
        )

    def _rebuild_inputs_property_widget(self):
        """Rebuild the inputs PropertyWidget from the current workflow."""
        self._destroy_inputs_property_widget()
        self._getter_subscriptions.clear()

        workflow = self._core.workflow
        if workflow is None or not workflow.inputs:
            if self._inputs_frame is not None:
                self._inputs_frame.clear()
                with self._inputs_frame:
                    self._build_empty_inputs_state()
            return

        items = self._create_input_items(workflow)

        self._inputs_model = Model()
        self._inputs_delegate = WorkflowInputDelegate(self._select_input_group)
        self._inputs_model.set_items(items)
        self._inputs_delegate.resolve_claims(self._inputs_model)

        if self._inputs_frame is not None:
            self._inputs_frame.clear()
            with self._inputs_frame:
                self._inputs_property_widget = PropertyWidget(
                    model=self._inputs_model,
                    delegate=self._inputs_delegate,
                    tree_column_widths=[ui.Percent(self._NAME_COLUMN_PERCENT), ui.Fraction(1)],
                    tree_min_column_widths=[ui.Pixel(0), ui.Pixel(0)],
                    select_all_children=False,
                )
                self._inputs_property_widget.tree_view.identifier = "ComfyWorkflowInputs"
                self._inputs_property_widget.tree_view.set_selection_changed_fn(self._on_input_selection_changed)

    def _create_input_items(self, workflow) -> list[WorkflowGroupItem]:
        """Create grouped property items for a workflow's inputs.

        Args:
            workflow: Workflow whose inputs should populate the master list.

        Returns:
            Ordered workflow groups containing input rows without detail-panel properties.
        """
        grouped_inputs = self._get_sorted_grouped_inputs(workflow)
        items: list[WorkflowGroupItem] = []

        for group_index, (group_name, group_inputs) in enumerate(grouped_inputs.items()):
            is_first_group = group_index == 0
            workflow_group = WorkflowGroupItem(group_name, expanded=is_first_group)

            for workflow_input in group_inputs:
                tooltip = workflow_input.tooltip or workflow_input.label
                input_group = InputItemGroup(
                    workflow_input,
                    expanded=False,
                    tooltip=tooltip,
                    context_name=self._context_name,
                )
                input_group.parent = workflow_group

                self._subscribe_getter_change(input_group)

            items.append(workflow_group)

        return items

    def _subscribe_getter_change(self, group: InputItemGroup):
        """Subscribe to resolver-selector changes for a workflow input.

        Args:
            group: Input group whose resolver selector should trigger property refreshes.
        """
        getter_model = group.getter_model
        subscription = getter_model.subscribe_item_changed_fn(
            lambda model, item, grp=group: self._on_getter_changed(grp)
        )
        self._getter_subscriptions.append(subscription)

    def _destroy_inputs_property_widget(self):
        """Destroy the inputs PropertyWidget and its model/delegate."""
        if self._inputs_property_widget is not None:
            self._inputs_property_widget.destroy()
            self._inputs_property_widget = None
        self._inputs_model = None
        self._inputs_delegate = None

    def _rebuild_properties_panel(self):
        """Rebuild the properties detail panel for the currently selected input."""
        self._property_subscriptions.clear()
        if self._property_widget is not None:
            self._property_widget.destroy()
            self._property_widget = None
        self._property_model = None
        self._property_delegate = None

        if self._properties_container is None:
            return

        self._properties_container.clear()

        # Update breadcrumb in header
        self._update_properties_breadcrumb()

        workflow = self._core.workflow
        if workflow is None or not workflow.inputs:
            with self._properties_container:
                ui.Label(
                    self._EMPTY_WORKFLOW_TEXT,
                    name="QueueDetailEmptyLabel",
                    alignment=ui.Alignment.CENTER,
                    height=0,
                )
            return

        if self._selected_input_index is None:
            with self._properties_container:
                ui.Label(
                    self._EMPTY_SELECTION_TEXT,
                    name="QueueDetailEmptyLabel",
                    alignment=ui.Alignment.CENTER,
                    height=0,
                )
            return

        sorted_inputs = self._get_sorted_inputs(workflow)
        selected_input = sorted_inputs[self._selected_input_index]
        resolver = selected_input.value

        with self._properties_container:
            field_label = selected_input.label
            if type(resolver) is ConstantResolver:
                field_label = get_native_constant_label(selected_input.native_type)
            items = ResolverParamItem.from_resolver(
                resolver,
                field_labels={"value": field_label},
                fallback_value_type=selected_input.native_type,
            )
            if items:
                self._property_model = Model()
                self._property_delegate = NativeDelegate(right_aligned_labels=False)
                self._property_model.set_items(items)
                self._property_delegate.resolve_claims(self._property_model)
                self._property_widget = PropertyWidget(
                    self._property_model,
                    self._property_delegate,
                    tree_column_widths=[ui.Percent(self._NAME_COLUMN_PERCENT), ui.Fraction(1)],
                    tree_min_column_widths=[ui.Pixel(0), ui.Pixel(0)],
                )
                self._property_widget.tree_view.identifier = "ComfyInputProperties"
                self._property_subscriptions = [
                    value_model.subscribe_value_changed_fn(lambda _: self._invalidate_active_preset())
                    for item in items
                    for value_model in item.value_models
                ]
            else:
                ui.Label(
                    self._NO_PROPERTIES_TEXT,
                    name="QueueDetailEmptyLabel",
                    alignment=ui.Alignment.CENTER,
                    height=0,
                )

    def _update_properties_breadcrumb(self):
        """Update the breadcrumb state and re-render the frame content."""
        workflow = self._core.workflow
        if workflow is None or self._selected_input_index is None:
            self._breadcrumb_input_text = ""
            self._breadcrumb_getter_text = ""
        else:
            sorted_inputs = self._get_sorted_inputs(workflow)
            selected_input = sorted_inputs[self._selected_input_index]
            self._breadcrumb_input_text = selected_input.label
            self._breadcrumb_getter_text = (
                get_native_constant_label(selected_input.native_type)
                if type(selected_input.value) is ConstantResolver
                else selected_input.value.label
            )

        if self._breadcrumb_container is not None:
            self._breadcrumb_container.clear()
            with self._breadcrumb_container:
                self._render_breadcrumb()

    def _on_input_selection_changed(self, selected_items):
        """Handle tree selection changes to update the properties panel.

        Shows properties for the first InputItemGroup in the selection.
        Group items (WorkflowGroupItem) are ignored.

        Args:
            selected_items: List of selected tree items from the TreeView.
        """
        if not selected_items:
            self._selected_input_index = None
            self._rebuild_properties_panel()
            return

        # Find the first InputItemGroup in the selection
        selected = None
        for item in selected_items:
            if isinstance(item, InputItemGroup):
                selected = item
                break

        if selected is None:
            self._selected_input_index = None
            self._rebuild_properties_panel()
            return

        sorted_inputs = self._get_sorted_inputs(self._core.workflow) if self._core.workflow else []
        for index, workflow_input in enumerate(sorted_inputs):
            if workflow_input is selected.workflow_input:
                self._selected_input_index = index
                self._rebuild_properties_panel()
                return

        self._selected_input_index = None
        self._rebuild_properties_panel()

    def _on_getter_changed(self, group: InputItemGroup):
        """Refresh the properties panel when a resolver type changes.

        Args:
            group: The InputItemGroup whose resolver type changed.
        """
        sorted_inputs = self._get_sorted_inputs(self._core.workflow) if self._core.workflow else []
        for workflow_input in sorted_inputs:
            if workflow_input is group.workflow_input:
                self._invalidate_active_preset()
                self._select_input_group(group)
                break

    def _select_input_group(self, group: InputItemGroup) -> None:
        """Select the workflow input whose getter picker is being used.

        Args:
            group: Workflow input row to select and show in Input Properties.
        """
        tree_view = self._inputs_property_widget.tree_view if self._inputs_property_widget else None
        if tree_view is not None and tree_view.selection != [group]:
            tree_view.selection = [group]
        else:
            self._on_input_selection_changed([group])

    def _invalidate_active_preset(self) -> None:
        """Clear a preset selection after the user changes an input."""
        workflow = self._core.workflow
        if workflow is None or workflow.active_preset is None:
            return
        workflow.active_preset = None
        self._update_preset_combo()

    def _on_workflow_dropdown_changed(self, index: int, item: SectionedComboItem):
        """Load the workflow corresponding to the selected SectionedComboBox item.

        Args:
            index: The selected item index.
            item: The selected SectionedComboItem (data holds the catalog workflow).
        """
        if item.data is not None:
            self._workflow_load_failed = False
            if self._workflow_dropdown is not None:
                self._workflow_dropdown.tooltip = item.data.description
            self._schedule_workflow_load(item.data)

    def _on_workflow_type_changed(self, index: int, item: SectionedComboItem):
        """Filter the workflow picker by the selected workflow type.

        Args:
            index: The selected item index.
            item: The selected SectionedComboItem (data holds the workflow type, or None for All).
        """
        if item.data == self._selected_workflow_type:
            return
        self._selected_workflow_type = item.data
        if self._workflow_type_combo is not None:
            self._workflow_type_combo.tooltip = item.tooltip or self._TYPE_FILTER_TOOLTIP
        self._update_workflow_combo()

    def _on_preset_changed(self, model, item):
        """Apply the selected preset and rebuild inputs.

        Args:
            model: The ComboBox item model.
            item: The changed item (unused).
        """
        workflow = self._core.workflow
        if workflow is None or not workflow.presets or not self._preset_names:
            return

        index = model.get_item_value_model().as_int
        if 0 <= index < len(self._preset_names):
            preset_name = self._preset_names[index]
            if preset_name is None or preset_name not in workflow.presets:
                return
            try:
                workflow.apply_preset(workflow.presets[preset_name])
            except (TypeError, ValueError) as error:
                carb.log_error(f"Failed to apply ComfyUI preset: {error}")
                _TrexMessageDialog(
                    "This preset contains values that do not match the workflow inputs. "
                    "Update the preset in ComfyUI and try again.",
                    "ComfyUI Preset Not Applied",
                    disable_cancel_button=True,
                )
                return
            workflow.active_preset = preset_name
            self._selected_input_index = None
            self._rebuild_inputs_property_widget()
            self._rebuild_properties_panel()

    def _on_refresh_clicked(self):
        """Re-fetch available workflows from the server."""
        if self._workflow_refresh_task and not self._workflow_refresh_task.done():
            self._workflow_refresh_task.cancel()
        self._workflow_refresh_task = asyncio.ensure_future(self._refresh_workflows())
        self._workflow_refresh_task.set_name("ComfyUIWorkflowRefresh")

    async def _refresh_workflows(self) -> None:
        """Refresh workflow discovery and release task ownership."""
        task = asyncio.current_task()
        try:
            await self._core.fetch_available_workflows()
        except (OSError, RuntimeError, ValueError) as error:
            carb.log_error(f"Failed to refresh ComfyUI workflows: {error}")
        finally:
            if self._workflow_refresh_task is task:
                self._workflow_refresh_task = None

    def _on_submit_clicked(self):
        """Prepare the current selection before it can enter the queue."""
        self._update_submit_button_state()
        if self._get_submit_block_reason() is not None:
            return
        self._submit_task = asyncio.ensure_future(self._prepare_and_submit())
        self._submit_task.set_name("ComfyUIWorkflowSubmission")
        self._update_submit_button_state()

    async def _prepare_and_submit(self) -> None:
        """Prepare jobs, request skip confirmation, and submit eligible graphs."""
        task = asyncio.current_task()
        try:
            submission, cancelled = await self._prepare_with_progress()
            if cancelled:
                return
            if submission.skipped_count:
                suffix = "" if submission.skipped_count == 1 else "s"
                verb = "does" if submission.skipped_count == 1 else "do"
                self._submission_confirmation_open = True
                _TrexMessageDialog(
                    f"{submission.skipped_count} selected material{suffix} {verb} not provide the inputs required by "
                    "the "
                    "active workflow.\n\n"
                    "These jobs will be skipped.\n\n"
                    "Do you want to proceed anyway?",
                    "Skipped ComfyUI Jobs",
                    ok_handler=functools.partial(self._on_skipped_jobs_confirmed, submission),
                    ok_label="Proceed",
                    on_window_closed_fn=self._on_submission_confirmation_closed,
                )
            else:
                await self._submit_prepared_submission(submission)
        except ResolverConfigurationError as error:
            carb.log_error(f"Invalid ComfyUI workflow input: {error}")
            _TrexMessageDialog(
                str(error),
                "Invalid ComfyUI Workflow Input",
                disable_cancel_button=True,
            )
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            carb.log_error(f"Failed to prepare ComfyUI jobs: {error}")
            _TrexMessageDialog(
                "These jobs could not be prepared. Check the selected materials, workflow inputs, "
                "and ComfyUI connection, then try again.",
                "ComfyUI Jobs Not Prepared",
                disable_cancel_button=True,
            )
        finally:
            if self._submit_task is task:
                self._submit_task = None
            self._update_submit_button_state()

    async def _prepare_with_progress(self) -> tuple[ComfyUISubmission, bool]:
        """Prepare a submission behind a cancellable progress popup.

        Returns:
            The prepared submission and whether the user cancelled preparation.
        """
        cancel_event = threading.Event()
        progress_popup = ProgressPopup(title="Preparing ComfyUI Jobs", status_text="Preparing jobs...")
        progress_popup.set_cancel_fn(cancel_event.set)
        progress_popup.show()
        try:
            submission = await self._core.prepare_submission(
                progress=functools.partial(self._update_prepare_progress, progress_popup),
                is_cancelled=cancel_event.is_set,
            )
            return submission, cancel_event.is_set()
        finally:
            progress_popup.hide()
            progress_popup.destroy()

    @staticmethod
    def _update_prepare_progress(progress_popup: ProgressPopup, current: int, total: int, status: object) -> None:
        """Render the latest preparation progress on the main thread.

        Args:
            progress_popup: Popup rendering job-preparation progress.
            current: Latest processed count reported by the worker.
            total: Latest total count, or a non-positive value while the total is unknown.
            status: Latest status message, if any.
        """
        if status:
            progress_popup.set_status_text(str(status))
        if total and total > 0:
            progress_popup.set_progress(max(0.0, min(1.0, current / total)))

    def _on_submission_confirmation_closed(self) -> None:
        """Release the Run action after the skipped-job dialog closes."""
        self._submission_confirmation_open = False
        self._update_submit_button_state()

    def _on_skipped_jobs_confirmed(self, submission: ComfyUISubmission) -> None:
        """Schedule a submission accepted by the skip dialog.

        Args:
            submission: Prepared material submission accepted despite skipped jobs.
        """
        if not self._submission_confirmation_open:
            return
        self._submission_confirmation_open = False
        self._submit_task = asyncio.ensure_future(self._submit_confirmed(submission))
        self._submit_task.set_name("ComfyUIConfirmedSubmission")
        self._update_submit_button_state()

    async def _submit_confirmed(self, submission: ComfyUISubmission) -> None:
        """Submit a confirmed request and release task ownership.

        Args:
            submission: Prepared material submission accepted by the skipped-job confirmation.
        """
        task = asyncio.current_task()
        try:
            await self._submit_prepared_submission(submission)
        finally:
            if self._submit_task is task:
                self._submit_task = None
            self._update_submit_button_state()

    async def _submit_prepared_submission(self, submission: ComfyUISubmission) -> None:
        """Submit one core-prepared request and render its exact result.

        Args:
            submission: Fully prepared material submission to add to the shared queue.
        """
        try:
            result = await self._core.submit_prepared_submission(submission)
        except RuntimeError as error:
            carb.log_error(f"Failed to submit ComfyUI jobs: {error}")
            _TrexMessageDialog(
                "These jobs could not be added to the queue. Check that the job queue is available, then try again.",
                "ComfyUI Jobs Not Submitted",
                disable_cancel_button=True,
            )
            return
        if result.failed_count:
            submitted_suffix = "" if result.submitted_count == 1 else "s"
            submitted_verb = "was" if result.submitted_count == 1 else "were"
            failed_suffix = "" if result.failed_count == 1 else "s"
            failed_verb = "was" if result.failed_count == 1 else "were"
            message = (
                f"{result.submitted_count} prepared job{submitted_suffix} {submitted_verb} added to the queue.\n\n"
                f"{result.failed_count} prepared job{failed_suffix} {failed_verb} not added."
            )
            if result.submitted_count:
                message += (
                    f" To avoid duplicates, select only the failed material{failed_suffix} before submitting again."
                )
            else:
                message += " Check that the job queue is available, then try again."
            _TrexMessageDialog(
                message,
                "Some ComfyUI Jobs Not Submitted" if result.submitted_count else "ComfyUI Jobs Not Submitted",
                disable_cancel_button=True,
            )

    def _schedule_workflow_load(self, workflow: Workflow) -> None:
        """Cancel any stale load and schedule the latest workflow selection.

        Args:
            workflow: Catalog workflow selected by the user.
        """
        if self._workflow_load_task and not self._workflow_load_task.done():
            self._workflow_load_task.cancel()
        self._selected_workflow_identity = workflow
        self._workflow_load_task = asyncio.ensure_future(self._load_workflow(workflow))
        self._workflow_load_task.set_name("ComfyUIWorkflowLoad")

    async def _load_workflow(self, workflow: Workflow) -> None:
        """Load one catalog workflow and expose retry state after expected failures.

        Args:
            workflow: Catalog workflow to load from its registry source.
        """
        task = asyncio.current_task()
        try:
            await self._core.load_workflow(workflow)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            if self._workflow_load_task is task:
                carb.log_error(f"Failed to load ComfyUI workflow: {error}")
                self._selected_workflow_identity = None
                self._workflow_load_failed = True
                if self._workflow_dropdown is not None:
                    retry_items = [
                        SectionedComboItem(label=self._SELECT_WORKFLOW_TEXT),
                        *self._get_workflow_combo_items(),
                    ]
                    self._workflow_dropdown.set_items(retry_items, 0)
        finally:
            if self._workflow_load_task is task:
                self._workflow_load_task = None

    def _on_core_event(self, event):
        """Handle events from the ComfyUI core event stream.

        Args:
            event: The event payload from the core event stream.
        """
        if event.event_type in {
            ComfyUIEventType.STATE_CHANGED,
            ComfyUIEventType.SETTINGS_CHANGED,
        }:
            connected = self._core.is_connected
            if self._connected_frame is not None:
                self._connected_frame.visible = connected
            if self._disconnected_frame is not None:
                self._disconnected_frame.visible = not connected
            if self._panels_splitter is not None:
                self._panels_splitter.visible = connected
            if connected:
                self._on_panels_frame_size_changed()
                self._update_workflow_combo()
            else:
                self._cancel_action_tasks()
            self._update_submit_button_state()
        elif event.event_type == ComfyUIEventType.WORKFLOW_CHANGED:
            self._on_workflow_changed()
        elif event.event_type == ComfyUIEventType.WORKFLOWS_LOADED:
            self._update_workflow_combo()

    def _on_stage_event(self, event) -> None:
        """Refresh submission availability after a project closes or finishes opening.

        Args:
            event: USD stage event from the widget's configured context.
        """
        if event.type in {int(usd.StageEventType.CLOSED), int(usd.StageEventType.OPENED)}:
            self._update_submit_button_state()

    def _on_workflow_changed(self):
        """Respond to a workflow change by rebuilding all dynamic sections."""
        if self._core.workflow is not None:
            self._workflow_load_failed = False
        self._selected_input_index = None
        self._update_workflow_combo()
        self._update_preset_combo()
        self._rebuild_inputs_property_widget()
        self._rebuild_properties_panel()
        self._update_submit_button_state()

    def _cancel_action_tasks(self) -> None:
        """Cancel connection-bound workflow actions and clear their active slots."""
        for task in (
            self._workflow_refresh_task,
            self._workflow_load_task,
            self._submit_task,
            self._splitter_layout_task,
        ):
            if task is not None:
                task.cancel()
        self._workflow_refresh_task = None
        self._workflow_load_task = None
        self._submit_task = None
        self._splitter_layout_task = None
        self._submission_confirmation_open = False

    def _update_workflow_combo(self):
        """Populate the workflow dropdown from the server's available workflow list."""
        if self._workflow_dropdown is None:
            return

        self._workflow_list = [
            workflow for workflow in self._core.available_workflows if workflow.category == WorkflowCategory.API
        ]
        self._update_workflow_type_combo()
        filtered_workflows = self._get_filtered_workflows()
        current_workflow = self._core.workflow

        if current_workflow is not None:
            selected_workflow = next(
                (workflow for workflow in filtered_workflows if self._is_same_workflow(workflow, current_workflow)),
                None,
            )
            if selected_workflow is not None:
                self._selected_workflow_identity = selected_workflow
                self._workflow_dropdown.set_items(
                    self._get_workflow_combo_items(), filtered_workflows.index(selected_workflow)
                )
                self._workflow_dropdown.enabled = bool(self._workflow_list)
                self._workflow_dropdown.tooltip = selected_workflow.description
                return
            if not any(self._is_same_workflow(workflow, current_workflow) for workflow in self._workflow_list):
                self._selected_workflow_identity = None
                items = [
                    SectionedComboItem(
                        label=current_workflow.display_name or "Saved Job",
                        section="Saved Job",
                    ),
                    *self._get_workflow_combo_items(),
                ]
                self._workflow_dropdown.set_items(items, 0)
                self._workflow_dropdown.enabled = bool(self._workflow_list)
                self._workflow_dropdown.tooltip = (
                    "Select another ComfyUI workflow to replace the workflow saved with this job."
                    if self._workflow_list
                    else "The workflow saved with this job is not available from the connected ComfyUI server."
                )
                return
            # The type filter hides the loaded workflow. Offer the filtered catalog with nothing selected, and
            # load nothing: the user filtered the list, so the loaded workflow stays.
            self._selected_workflow_identity = None
            self._workflow_dropdown.set_items(
                [SectionedComboItem(label=self._SELECT_WORKFLOW_TEXT), *self._get_workflow_combo_items()], 0
            )
            self._workflow_dropdown.enabled = bool(self._workflow_list)
            self._workflow_dropdown.tooltip = (
                f"{current_workflow.display_name} stays loaded. Select a workflow of this type to replace it."
            )
            return

        if not self._workflow_list:
            self._workflow_dropdown.set_items([SectionedComboItem(label=self._NO_WORKFLOWS_TEXT)])
            self._workflow_dropdown.enabled = False
            self._workflow_dropdown.tooltip = (
                "No workflows are available. Check that the RTX Remix ComfyUI nodes are installed, then refresh."
            )
            self._selected_workflow_identity = None
            return

        if self._workflow_load_failed:
            self._selected_workflow_identity = None
            self._workflow_dropdown.set_items(
                [SectionedComboItem(label=self._SELECT_WORKFLOW_TEXT), *self._get_workflow_combo_items()],
                0,
            )
            self._workflow_dropdown.enabled = True
            self._workflow_dropdown.tooltip = "Select a workflow to retry loading"
            return

        selected_workflow = next(
            (
                workflow
                for workflow in filtered_workflows
                if self._selected_workflow_identity is not None
                and self._is_same_workflow(workflow, self._selected_workflow_identity)
            ),
            None,
        )
        if selected_workflow is None:
            selected_workflow = filtered_workflows[0]
        self._selected_workflow_identity = selected_workflow
        selected_index = filtered_workflows.index(selected_workflow)

        self._workflow_dropdown.set_items(self._get_workflow_combo_items(), selected_index)
        self._workflow_dropdown.enabled = True
        self._workflow_dropdown.tooltip = selected_workflow.description

        if self._core.state != ComfyUIState.RUNNING:
            return
        if not self._workflow_load_task or self._workflow_load_task.done():
            self._schedule_workflow_load(selected_workflow)

    def _update_workflow_type_combo(self):
        """Rebuild the workflow type options from the vocabulary of the server and keep a valid selection.

        Every option carries the description that the server publishes as its hover text. The field shows the
        description of the selected type, or the filter text while `All` is selected.
        """
        if self._workflow_type_combo is None:
            return

        available_types = {workflow.workflow_type for workflow in self._workflow_list if workflow.workflow_type}
        if self._selected_workflow_type not in available_types:
            self._selected_workflow_type = None

        items = [SectionedComboItem(label=self._ALL_WORKFLOW_TYPES_TEXT, data=None)]
        selected_index = 0
        for category in self._core.workflow_type_categories:
            for option in category.types:
                if option.workflow_type not in available_types:
                    continue
                if option.workflow_type == self._selected_workflow_type:
                    selected_index = len(items)
                items.append(
                    SectionedComboItem(
                        label=option.workflow_type.value,
                        section=category.name,
                        data=option.workflow_type,
                        tooltip=option.description,
                    )
                )

        self._workflow_type_combo.set_items(items, selected_index)
        self._workflow_type_combo.tooltip = items[selected_index].tooltip or self._TYPE_FILTER_TOOLTIP

    def _get_filtered_workflows(self) -> list[Workflow]:
        """Return the catalog workflows visible under the selected workflow type.

        Returns:
            Every API catalog workflow, or only the ones matching the selected workflow type.
        """
        if self._selected_workflow_type is None:
            return self._workflow_list
        return [workflow for workflow in self._workflow_list if workflow.workflow_type == self._selected_workflow_type]

    @staticmethod
    def _is_same_workflow(first: Workflow, second: Workflow) -> bool:
        """Return whether two workflows share one catalog identity.

        Args:
            first: Workflow to compare.
            second: Workflow to compare against.

        Returns:
            True when category, source type, and name all match.
        """
        return (
            first.category == second.category and first.source_type == second.source_type and first.name == second.name
        )

    def _get_workflow_combo_items(self) -> list[SectionedComboItem]:
        """Return display items for the catalog workflows visible under the selected type.

        Returns:
            Sectioned ComboBox items carrying each visible catalog workflow.
        """
        return [
            SectionedComboItem(
                label=workflow.display_name,
                section=WORKFLOW_SOURCE_LABELS.get(
                    workflow.source_type, workflow.source_type.value.replace("-", " ").title()
                ),
                data=workflow,
            )
            for workflow in self._get_filtered_workflows()
        ]

    def _update_preset_combo(self):
        """Update the preset ComboBox to reflect available presets for the current workflow."""
        if self._preset_combo is None:
            return

        workflow = self._core.workflow
        if workflow is None:
            self._preset_names = []
            self._rebuild_combo(self._preset_combo, [self._NO_WORKFLOW_PRESET_TEXT], 0)
            self._preset_combo.enabled = False
            self._preset_combo.tooltip = self._NO_WORKFLOW_PRESET_TEXT
            return

        if not workflow.presets:
            self._preset_names = []
            self._rebuild_combo(self._preset_combo, [self._NO_PRESETS_TEXT], 0)
            self._preset_combo.enabled = False
            self._preset_combo.tooltip = self._NO_PRESETS_TEXT
            return

        preset_names = sorted(workflow.presets, key=str.casefold)
        default_name = next((name for name in preset_names if name.casefold() == "default"), None)
        if default_name is not None:
            preset_names.remove(default_name)
            preset_names.insert(0, default_name)
        if workflow.active_preset in preset_names:
            selectable_presets: list[str | None] = preset_names
            options = preset_names
            active_index = preset_names.index(workflow.active_preset)
        else:
            selectable_presets = [None, *preset_names]
            options = ["Select a preset", *preset_names]
            active_index = 0

        self._preset_names = selectable_presets
        self._rebuild_combo(self._preset_combo, options, active_index)
        self._preset_combo.enabled = True
        self._preset_combo.tooltip = "Apply a saved preset configuration"
        self._preset_combo.model.add_item_changed_fn(self._on_preset_changed)

    def _rebuild_combo(self, combo: ui.ComboBox, options: list[str], selected_index: int):
        """Replace a ComboBox's options and selected index.

        Since omni.ui.ComboBox does not support dynamically changing options
        after construction, we rebuild its underlying model.

        Args:
            combo: The ComboBox widget to update.
            options: The new list of string options.
            selected_index: The index to select after rebuilding.
        """
        model = SimpleComboModel(options, selected_index)
        combo.model = model

    def _update_submit_button_state(self):
        """Update the enabled state and tooltip of the submit button."""
        if self._submit_button is None:
            return

        reason = self._get_submit_block_reason()
        self._submit_button.enabled = reason is None
        self._submit_button.tooltip = (
            reason or "Run this workflow for the selected materials and add the jobs to the queue."
        )

    def _get_submit_block_reason(self) -> str | None:
        """Return why Run cannot prepare and submit new material graphs.

        Returns:
            User-facing guidance, or ``None`` when submission can start.
        """
        if not self._core.is_connected:
            return "Connect to ComfyUI first"
        if self._core.workflow is None:
            return "Select a workflow first"
        if not self._core.is_ready:
            return "Reconnect to ComfyUI and select a workflow again"
        if project_reason := self._core.get_submission_block_reason():
            return project_reason
        if self._submit_task and not self._submit_task.done():
            return "Preparing the selected materials."
        if self._submission_confirmation_open:
            return "Close the confirmation message before starting another job."
        return None

    @staticmethod
    def _get_sorted_inputs(workflow) -> list:
        """Sort workflow inputs by group order, then by input order within each group.

        Args:
            workflow: The Workflow instance whose inputs to sort.

        Returns:
            A list of WorkflowInput instances sorted by group and order.
        """
        ordered = {name: index for index, name in enumerate(workflow.group_order)}
        unordered = len(ordered) + 1

        def sort_key(workflow_input):
            """Return a stable group and item order tuple for one workflow input.

            Args:
                workflow_input: Input whose declared group and item order should be ranked.

            Returns:
                Group-order and input-order values used by the stable sort.
            """
            if not workflow_input.group:
                return (-1, workflow_input.order)
            return (ordered.get(workflow_input.group, unordered), workflow_input.order)

        return sorted(workflow.inputs, key=sort_key)

    @classmethod
    def _get_sorted_grouped_inputs(cls, workflow) -> dict:
        """Sort workflow inputs by group order and return them grouped by name.

        Inputs with an empty group string are placed under an "Ungrouped" group.

        Args:
            workflow: The Workflow instance whose inputs to sort.

        Returns:
            An ordered dict of group_name to list of WorkflowInput instances.
        """
        sorted_inputs = cls._get_sorted_inputs(workflow)
        groups: dict[str, list] = {}
        for workflow_input in sorted_inputs:
            group_name = workflow_input.group or cls._DEFAULT_GROUP_NAME
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(workflow_input)
        return groups

    def destroy(self):
        """Clean up all resources, subscriptions, and widget references."""
        self._event_subscription = None
        self._stage_event_subscription = None
        self._cancel_action_tasks()
        self._selected_workflow_identity = None
        self._workflow_load_failed = False
        self._submission_confirmation_open = False
        self._getter_subscriptions.clear()
        self._destroy_inputs_property_widget()

        self._property_subscriptions.clear()
        if self._property_widget is not None:
            self._property_widget.destroy()
            self._property_widget = None

        self._property_model = None
        self._property_delegate = None
        self._inputs_frame = None
        self._inputs_panel_frame = None
        self._properties_panel_frame = None
        if self._inputs_section is not None:
            self._inputs_section.root.set_collapsed_changed_fn(None)
            self._inputs_section.destroy()
            self._inputs_section = None
        self._properties_container = None
        if self._properties_section is not None:
            self._properties_section.root.set_collapsed_changed_fn(None)
            self._properties_section.destroy()
            self._properties_section = None
        self._breadcrumb_container = None
        self._submit_button = None
        if self._workflow_dropdown is not None:
            self._workflow_dropdown.destroy()
            self._workflow_dropdown = None
        self._preset_combo = None
        self._workflow_type_combo = None
        self._selected_workflow_type = None
        if self._panels_frame is not None:
            self._panels_frame.set_computed_content_size_changed_fn(None)
            self._panels_frame = None
        if self._panels_splitter is not None:
            self._panels_splitter.set_offset_y_changed_fn(None)
            self._panels_splitter = None
        self._normalize_splitter_drag = False
        self._connected_frame = None
        self._disconnected_frame = None
        self._root_stack = None

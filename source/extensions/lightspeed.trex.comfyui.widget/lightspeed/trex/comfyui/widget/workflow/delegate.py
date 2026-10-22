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

__all__ = ["WorkflowItemDelegate"]

import functools
from collections.abc import Callable

from omni import ui
from omni.flux.property_widget_builder.delegates import FloatDragFieldGroup
from omni.flux.property_widget_builder.model.native import NativeDelegate
from omni.flux.property_widget_builder.widget import FieldBuilder, Model, claim_each

from .items import InputItemGroup, JobTimeoutItem, OutputItemGroup, WorkflowGroupItem

_ROW_ITEM_TYPES = (InputItemGroup, OutputItemGroup, JobTimeoutItem)


class WorkflowItemDelegate(NativeDelegate):
    """Delegate for workflow input and output property items.

    Extends ``NativeDelegate`` with a resolver picker for input rows and
    shared list rendering for selectable input and output rows.
    """

    # 2px taller than default (24) to create visual spacing between rows
    DEFAULT_IMAGE_ICON_SIZE = ui.Pixel(26)

    def __init__(self, item_pressed_fn: Callable[[InputItemGroup | OutputItemGroup], None]):
        """Initialize workflow-specific field builders and label alignment.

        Args:
            item_pressed_fn: Callback that selects a clicked workflow item row.
        """
        self._item_pressed_fn = item_pressed_fn
        super().__init__(
            field_builders=[
                FieldBuilder(
                    claim_func=claim_each(lambda item: isinstance(item, InputItemGroup)),
                    build_func=functools.partial(_build_getter_combo, item_pressed_fn=item_pressed_fn),
                ),
                FieldBuilder(
                    claim_func=claim_each(lambda item: isinstance(item, JobTimeoutItem)),
                    build_func=_build_job_timeout_drag,
                ),
            ],
            right_aligned_labels=False,
        )

    def build_branch(self, model, item, column_id, level, expanded):
        """Render reduced branch indentation for workflow item rows.

        Args:
            model: Property tree model that owns the item.
            item: Property item whose branch column is being rendered.
            column_id: Tree column being rendered.
            level: Depth of the item in the property tree.
            expanded: Whether the item is currently expanded.
        """
        if column_id == 0 and isinstance(item, _ROW_ITEM_TYPES):
            with ui.HStack(width=ui.Pixel(32), height=self.DEFAULT_IMAGE_ICON_SIZE):
                ui.Spacer()
            return
        super().build_branch(model, item, column_id, level, expanded)

    def _build_item_widgets(self, model: Model, item, column_id: int, level: int, expanded: bool):
        """Build workflow rows with the shared property name labels.

        Args:
            model: Property tree model that owns the item.
            item: Property item whose cells are being built.
            column_id: Tree column being built.
            level: Depth of the item in the property tree.
            expanded: Whether the item is currently expanded.

        Returns:
            Widgets for the requested cell, or None for cells without an editor.
        """
        if column_id == 1 and isinstance(item, (WorkflowGroupItem, OutputItemGroup)):
            return None
        if column_id == 0 and isinstance(item, _ROW_ITEM_TYPES):
            return _build_workflow_name_label(item, self._item_pressed_fn)
        return super()._build_item_widgets(model, item, column_id, level, expanded)


def _build_workflow_name_label(
    item: InputItemGroup | OutputItemGroup | JobTimeoutItem,
    item_pressed_fn: Callable[[InputItemGroup | OutputItemGroup | JobTimeoutItem], None],
) -> list[ui.Widget]:
    """Build a workflow item label with the shared property label style.

    Args:
        item: Workflow item whose label and tooltip should be displayed.
        item_pressed_fn: Callback that selects the item row.

    Returns:
        A single-element list containing the item label widget.
    """
    text = item.workflow_input.label if isinstance(item, InputItemGroup) else item.name_models[0].get_value_as_string()
    tooltip_text = item.tooltip

    label = ui.Label(
        text,
        name="PropertiesWidgetLabel",
        style_type_name_override="PropertiesWidgetLabel",
        identifier="ComfyWorkflowItemName",
        elided_text=True,
        tooltip=tooltip_text or text,
        mouse_pressed_fn=lambda _x, _y, button, _modifier: item_pressed_fn(item) if button == 0 else None,
    )
    return [label]


def _build_getter_combo(
    item: InputItemGroup,
    item_pressed_fn: Callable[[InputItemGroup | OutputItemGroup], None],
) -> list[ui.Widget] | None:
    """Build a centered ComboBox for selecting the input resolver type.

    Args:
        item: Workflow input group whose resolver selector should be displayed.
        item_pressed_fn: Callback that selects the workflow input row.
    Returns:
        A single-element list containing the centered ComboBox container.
    """
    with ui.VStack() as container:
        ui.Spacer()
        ui.ComboBox(
            item.getter_model,
            identifier="ComfyGetterPicker",
            tooltip=item.tooltip or "Choose how this input gets its value",
            mouse_pressed_fn=lambda _x, _y, button, _modifier: item_pressed_fn(item) if button == 0 else None,
        )
        ui.Spacer()
    return [container]


def _build_job_timeout_drag(item: JobTimeoutItem) -> list[ui.Widget]:
    """Build the timeout drag with the input-row value inset and a soft minute range.

    Args:
        item: Job timeout row whose value model edits the persisted timeout in minutes.

    Returns:
        A single-element list containing the drag widget.
    """
    field = FloatDragFieldGroup(
        min_value=JobTimeoutItem.SOFT_MIN_MINUTES,
        max_value=JobTimeoutItem.SOFT_MAX_MINUTES,
        hard_min_value=JobTimeoutItem.HARD_MIN_MINUTES,
        identifier="ComfyJobTimeoutField",
    )
    value_model = item.value_models[0]
    with ui.VStack(height=ui.Pixel(24)):
        ui.Spacer(height=ui.Pixel(2))
        widget = field.build_drag_widget(
            value_model,
            field.style_name,
            False,
            JobTimeoutItem.SOFT_MIN_MINUTES,
            JobTimeoutItem.SOFT_MAX_MINUTES,
            JobTimeoutItem.HARD_MIN_MINUTES,
            None,
            field.step,
        )
        field.set_dynamic_tooltip_fn(widget, value_model)
        ui.Spacer(height=ui.Pixel(2))
    return [widget]

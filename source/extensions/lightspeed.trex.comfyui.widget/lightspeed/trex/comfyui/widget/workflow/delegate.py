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

__all__ = ["WorkflowInputDelegate"]

import functools
from collections.abc import Callable

from omni import ui
from omni.flux.property_widget_builder.model.native import NativeDelegate
from omni.flux.property_widget_builder.widget import FieldBuilder, Model, claim_each

from .items import InputItemGroup, WorkflowGroupItem


class WorkflowInputDelegate(NativeDelegate):
    """Delegate for workflow input property widgets.

    Extends ``NativeDelegate`` (which handles native Python type dispatch)
    with workflow-specific builders and layout overrides:
    - Getter ComboBox for InputItemGroup items
    - Reduced indentation for input rows (no expand arrow)
    - Regular-weight label style for input names
    """

    # 2px taller than default (24) to create visual spacing between rows
    DEFAULT_IMAGE_ICON_SIZE = ui.Pixel(26)

    def __init__(self, input_pressed_fn: Callable[[InputItemGroup], None]):
        """Initialize workflow-specific field builders and label alignment.

        Args:
            input_pressed_fn: Callback that selects a clicked workflow input row.
        """
        self._input_pressed_fn = input_pressed_fn
        super().__init__(
            field_builders=[
                FieldBuilder(
                    claim_func=claim_each(lambda item: isinstance(item, InputItemGroup)),
                    build_func=functools.partial(_build_getter_combo, input_pressed_fn=input_pressed_fn),
                ),
            ],
            right_aligned_labels=False,
        )

    def build_branch(self, model, item, column_id, level, expanded):
        """Render reduced branch indentation for non-expandable input items.

        Args:
            model: Property tree model that owns the item.
            item: Property item whose branch column is being rendered.
            column_id: Tree column being rendered.
            level: Depth of the item in the property tree.
            expanded: Whether the item is currently expanded.
        """
        if column_id == 0 and isinstance(item, InputItemGroup):
            with ui.HStack(width=ui.Pixel(32), height=self.DEFAULT_IMAGE_ICON_SIZE):
                ui.Spacer()
            return
        super().build_branch(model, item, column_id, level, expanded)

    def _build_item_widgets(self, model: Model, item, column_id: int, level: int, expanded: bool):
        """Build workflow input rows with regular-weight name labels.

        Args:
            model: Property tree model that owns the item.
            item: Property item whose cells are being built.
            column_id: Tree column being built.
            level: Depth of the item in the property tree.
            expanded: Whether the item is currently expanded.

        Returns:
            Widgets for the requested cell, or None for hidden workflow-group value cells.
        """
        if column_id == 1 and isinstance(item, WorkflowGroupItem):
            return None
        if column_id == 0 and isinstance(item, InputItemGroup):
            return _build_workflow_name_label(item, self._input_pressed_fn)
        return super()._build_item_widgets(model, item, column_id, level, expanded)


def _build_workflow_name_label(
    item: InputItemGroup, input_pressed_fn: Callable[[InputItemGroup], None]
) -> list[ui.Widget]:
    """Build a regular-weight name label for a workflow input.

    Args:
        item: Workflow input group whose label and tooltip should be displayed.
        input_pressed_fn: Callback that selects the input row.

    Returns:
        A single-element list containing the input label widget.
    """
    text = item.workflow_input.label
    tooltip_text = item.tooltip

    label = ui.Label(
        text,
        name="WorkflowInputName",
        elided_text=True,
        tooltip=tooltip_text or text,
        mouse_pressed_fn=lambda _x, _y, button, _modifier: input_pressed_fn(item) if button == 0 else None,
    )
    return [label]


def _build_getter_combo(
    item: InputItemGroup, input_pressed_fn: Callable[[InputItemGroup], None]
) -> list[ui.Widget] | None:
    """Build a centered ComboBox for selecting the input resolver type.

    Args:
        item: Workflow input group whose resolver selector should be displayed.
        input_pressed_fn: Callback that selects the workflow input row.

    Returns:
        A single-element list containing the centered ComboBox container.
    """
    with ui.VStack() as container:
        ui.Spacer()

        def on_mouse_pressed(_x: float, _y: float, button: int, _modifier: int) -> None:
            """Select the owning input on a primary getter press."""
            if button == 0:
                input_pressed_fn(item)

        ui.ComboBox(
            item.getter_model,
            identifier="ComfyGetterPicker",
            tooltip=item.tooltip or "Choose how this input gets its value",
            mouse_pressed_fn=on_mouse_pressed,
        )
        ui.Spacer()
    return [container]

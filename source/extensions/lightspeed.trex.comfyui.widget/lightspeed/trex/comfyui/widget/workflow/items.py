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

__all__ = [
    "InputItemGroup",
    "OutputItemGroup",
    "ResolverParamItem",
    "WorkflowGroupItem",
]

from typing import Any, Literal

from lightspeed.trex.comfyui.core.enums import OutputApplyBehavior, RemixType
from lightspeed.trex.comfyui.core.maps import OUTPUT_TEXTURE_TYPE_MAP
from lightspeed.trex.comfyui.core.models import WorkflowInput, WorkflowOutput
from lightspeed.trex.comfyui.core.resolvers import ValueResolver
from omni.flux.property_widget_builder.model.native import NativeChoiceModel, NativeItem
from omni.flux.property_widget_builder.widget import ItemGroup
from omni.flux.property_widget_builder.widget.tree.item_model import ItemGroupNameModel

from .model import GetterValueModel, _ResolverFieldValueModel, _WorkflowOutputFieldValueModel


class _ParameterNameModel(ItemGroupNameModel):
    """Name model that carries a workflow field's explanatory tooltip.

    The property-widget name field renders ``get_tool_tip()`` next to the field
    name, so this model exposes the tooltip without delegate customization.
    """

    def __init__(self, name: str, tooltip: str = ""):
        """Initialize the name model with its display text and tooltip.

        Args:
            name: Text shown in the property name column.
            tooltip: Hover text that explains the workflow field.
        """
        super().__init__(name)
        self._tooltip = tooltip

    def get_tool_tip(self) -> str | None:
        """Return the workflow field's explanatory tooltip.

        Returns:
            The tooltip text, or None when the field has no tooltip.
        """
        return self._tooltip or None


class ResolverParamItem(NativeItem):
    """PropertyWidget item representing one editable workflow field.

    Each instance binds a display name to a live field model. It carries the
    runtime ``value_type`` so the delegate can select the correct editor.
    """

    def __init__(
        self,
        name_model: ItemGroupNameModel,
        value_model: _ResolverFieldValueModel[Any] | NativeChoiceModel,
        value_type: type = str,
        field_model: _WorkflowOutputFieldValueModel | None = None,
    ):
        """Initialize a workflow property row and its editor metadata.

        Args:
            name_model: Read-only model displayed in the property name column.
            value_model: Mutable model bound to the workflow field.
            value_type: Python type used to select the field editor.
            field_model: Output field model wrapped by a choice ``value_model``, released on destroy.
        """
        super().__init__()
        self._name_models = [name_model]
        self._value_models = [value_model]
        self._value_type = value_type
        self._field_model = field_model

    @property
    def default_attr(self) -> dict[str, None]:
        """Return the attributes released by the base item cleanup, including the owned field model."""
        default_attr = super().default_attr
        default_attr["_field_model"] = None
        return default_attr

    @property
    def value_type(self) -> type:
        """Return the Python type used to select the field editor.

        Returns:
            Runtime type of the resolver parameter value.
        """
        return self._value_type

    @classmethod
    def from_resolver(
        cls,
        resolver: ValueResolver,
        field_labels: dict[str, str] | None = None,
        fallback_value_type: type = str,
    ) -> list["ResolverParamItem"]:
        """Create items for the resolver's declared editable parameters.

        Resolver classes expose strongly typed bindings so the delegate can
        render type-appropriate widgets without dynamic attribute access.

        Args:
            resolver: The resolver instance to inspect.
            field_labels: Optional mapping of field name to display label.
                For example, ``{"value": "Metallic Strength"}`` replaces the
                generic "value" label with the workflow input's name.
            fallback_value_type: Editor type for null fields without a concrete annotation.

        Returns:
            A list of ResolverParamItem instances, one per editable parameter.
        """
        labels = field_labels or {}
        items: list[ResolverParamItem] = []
        for parameter in resolver.parameters:
            display_name = labels.get(parameter.name, parameter.label or parameter.name)
            name_model = _ParameterNameModel(display_name, tooltip=parameter.tooltip)
            value_type = parameter.value_type if parameter.value_type is not object else fallback_value_type
            value_model = _ResolverFieldValueModel(parameter, value_type)
            if parameter.choices is not None:
                value_model = NativeChoiceModel(value_model, parameter.choices)
            items.append(cls(name_model, value_model, value_type=value_type))
        return items

    @classmethod
    def from_workflow_output(cls, workflow_output: WorkflowOutput) -> list["ResolverParamItem"]:
        """Create editable property items for a persisted workflow output.

        Args:
            workflow_output: Output whose settings the property widget edits.

        Returns:
            Ordered property items supported by the output semantic.
        """
        if workflow_output.remix_type is RemixType.TEXTURE_FILE_PATH:
            apply_choices = (OutputApplyBehavior.REPLACE, OutputApplyBehavior.NONE)
        elif workflow_output.remix_type is RemixType.MESH_FILE_PATH:
            apply_choices = (
                OutputApplyBehavior.REPLACE,
                OutputApplyBehavior.APPEND,
                OutputApplyBehavior.NONE,
            )
        else:
            apply_choices = (OutputApplyBehavior.NONE,)

        items = [
            cls._create_output_item(
                _ParameterNameModel(
                    "Apply Behavior",
                    tooltip="Choose how this output changes the current project.",
                ),
                workflow_output,
                "apply_behavior",
                apply_choices,
                OutputApplyBehavior,
            )
        ]
        if workflow_output.remix_type is RemixType.TEXTURE_FILE_PATH:
            items.append(
                cls._create_output_item(
                    _ParameterNameModel(
                        "Texture Type",
                        tooltip="Choose the type used to process this texture output.",
                    ),
                    workflow_output,
                    "texture_type",
                    tuple(OUTPUT_TEXTURE_TYPE_MAP),
                    str,
                )
            )
        return items

    @classmethod
    def _create_output_item(
        cls,
        name_model: ItemGroupNameModel,
        workflow_output: WorkflowOutput,
        field_name: Literal["apply_behavior", "texture_type"],
        choices: tuple[Any, ...],
        value_type: type,
    ) -> "ResolverParamItem":
        """Create a labeled choice item for one persisted output field.

        Args:
            name_model: Read-only model displayed in the property name column.
            workflow_output: Output whose field the model edits.
            field_name: Name of the persisted field.
            choices: Allowed typed values in display order.
            value_type: Python type used to select the field editor.

        Returns:
            Item whose choice model writes selections to the workflow output.
        """
        value_model = _WorkflowOutputFieldValueModel(workflow_output, field_name)
        choice_model = NativeChoiceModel(value_model, choices)
        for choice_item, choice in zip(choice_model.get_item_children(), choices):
            if choice is OutputApplyBehavior.NONE:
                choice_model.get_item_value_model(choice_item).set_value("Do Nothing")
            elif choice in OUTPUT_TEXTURE_TYPE_MAP:
                choice_model.get_item_value_model(choice_item).set_value(OUTPUT_TEXTURE_TYPE_MAP[choice].value)
        return cls(name_model, choice_model, value_type=value_type, field_model=value_model)


class InputItemGroup(ItemGroup):
    """PropertyWidget group wrapping a workflow input.

    Displays the input label as the group name and provides a GetterValueModel
    in the value column for selecting the resolver type.

    Args:
        workflow_input: The workflow input this group represents.
        expanded: Whether the group should be expanded by default.
        tooltip: Optional tooltip text for the group row.
        context_name: USD context passed to the workflow input's resolver model.
    """

    def __init__(
        self,
        workflow_input: WorkflowInput,
        expanded: bool = False,
        tooltip: str = "",
        context_name: str = "",
    ):
        """Initialize a workflow input group and its resolver selector.

        Args:
            workflow_input: Workflow input represented by this property group.
            expanded: Whether the group starts expanded.
            tooltip: Tooltip displayed for the workflow input row.
            context_name: USD context passed to newly created resolver instances.
        """
        super().__init__(workflow_input.label, expanded=expanded)
        # PropertyWidget refreshes _value_models through its value-model API, while the getter
        # follows ComboBox's AbstractItemModel contract and therefore must remain separate.
        self.getter_model = GetterValueModel(workflow_input, context_name=context_name)
        self.workflow_input = workflow_input
        self.tooltip = tooltip

    @property
    def can_have_children(self) -> bool:
        """Report whether the group currently has expandable child rows.

        Returns:
            True when at least one child row is present.
        """
        return len(self.children) > 0


class OutputItemGroup(ItemGroup):
    """PropertyWidget group wrapping a persisted workflow output."""

    def __init__(self, workflow_output: WorkflowOutput, expanded: bool = False):
        """Initialize a workflow output row.

        Args:
            workflow_output: Workflow output represented by this property group.
            expanded: Whether the group starts expanded.
        """
        super().__init__("", expanded=expanded)
        self.workflow_output = workflow_output
        self.refresh()

    @property
    def can_have_children(self) -> bool:
        """Report that workflow output rows have no child rows."""
        return False

    def refresh(self) -> None:
        """Refresh the output label and tooltip from its export name and current texture type."""
        workflow_output = self.workflow_output
        if (
            workflow_output.remix_type == RemixType.TEXTURE_FILE_PATH
            and workflow_output.texture_type in OUTPUT_TEXTURE_TYPE_MAP
        ):
            kind = OUTPUT_TEXTURE_TYPE_MAP[workflow_output.texture_type].value
        elif workflow_output.remix_type == RemixType.MESH_FILE_PATH:
            kind = "Mesh"
        else:
            kind = workflow_output.remix_type.value.replace("_", " ").title()
        # The export name is what the user typed in ComfyUI, so a re-export is visible in the row.
        label = workflow_output.name or kind
        self._name_models = [ItemGroupNameModel(label)]
        self.label = label
        self.tooltip = f"Configure the {kind} output" if label == kind else f"Configure the {label} output ({kind})"


class WorkflowGroupItem(ItemGroup):
    """Tag a named workflow-item container for delegate-specific rendering.

    This item has no field model. It groups workflow input or output rows under
    one shared heading, such as "Textures", "Materials", or "Outputs".
    """

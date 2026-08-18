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
    "ResolverParamItem",
    "WorkflowGroupItem",
]

from typing import Any

from lightspeed.trex.comfyui.core.models import WorkflowInput
from lightspeed.trex.comfyui.core.resolvers import ValueResolver
from omni.flux.property_widget_builder.model.native import NativeChoiceModel, NativeItem
from omni.flux.property_widget_builder.widget import ItemGroup
from omni.flux.property_widget_builder.widget.tree.item_model import ItemGroupNameModel

from .model import GetterValueModel, _ResolverFieldValueModel


class _ParameterNameModel(ItemGroupNameModel):
    """Name model that carries a resolver parameter's explanatory tooltip.

    The property-widget name field renders ``get_tool_tip()`` next to the parameter
    name, so exposing the tooltip here shows it without any delegate customization.
    """

    def __init__(self, name: str, tooltip: str = ""):
        """Initialize the name model with its display text and tooltip.

        Args:
            name: Text shown in the parameter name column.
            tooltip: Hover text explaining what the parameter changes.
        """
        super().__init__(name)
        self._tooltip = tooltip

    def get_tool_tip(self) -> str | None:
        """Return the parameter's explanatory tooltip.

        Returns:
            The tooltip text, or None when the parameter has no tooltip.
        """
        return self._tooltip or None


class ResolverParamItem(NativeItem):
    """PropertyWidget item representing a single dataclass field on a resolver.

    Each instance binds its name column to the field name and its value column
    to a live getter/setter on the resolver instance. Carries the runtime
    ``value_type`` so the delegate can render the appropriate widget.
    """

    def __init__(
        self,
        name_model: ItemGroupNameModel,
        value_model: _ResolverFieldValueModel[Any] | NativeChoiceModel,
        value_type: type = str,
    ):
        """Initialize a resolver parameter row and its editor metadata.

        Args:
            name_model: Read-only model displayed in the parameter name column.
            value_model: Mutable model bound to the resolver parameter.
            value_type: Python type used to select the parameter editor.
        """
        super().__init__()
        self._name_models = [name_model]
        self._value_models = [value_model]
        self._value_type = value_type

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


class WorkflowGroupItem(ItemGroup):
    """Tag a named workflow-input container for delegate-specific rendering.

    Unlike InputItemGroup, this item has no getter model or value models --
    it exists purely to group InputItemGroup children under a shared heading
    (e.g. "Textures", "Materials").

    The inherited ItemGroup constructor supplies the display name and expanded state.
    """

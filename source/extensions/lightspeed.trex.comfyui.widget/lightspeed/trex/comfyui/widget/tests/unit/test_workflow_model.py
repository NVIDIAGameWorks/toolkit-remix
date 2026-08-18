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

import dataclasses
import pathlib
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

from omni.kit.test import AsyncTestCase
from lightspeed.trex.comfyui.core.enums import RemixType
from lightspeed.trex.comfyui.core.models import WorkflowInput
from lightspeed.trex.comfyui.core.resolvers import (
    ConstantResolver,
    ResolverParameter,
    SelectedTextureResolver,
    ValueResolver,
)
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.property_widget_builder.model.native import NativeChoiceModel
from lightspeed.trex.comfyui.widget.workflow.items import (
    InputItemGroup,
    ResolverParamItem,
    WorkflowGroupItem,
)
from lightspeed.trex.comfyui.widget.workflow.model import GetterValueModel, SimpleComboModel


@dataclasses.dataclass
class _TypedResolver(ValueResolver):
    """Provide representative resolver field types for model tests."""

    label: ClassVar[str] = "Typed"
    strength: float = 1.0
    count: int = 2
    enabled: bool = False
    text: str = "prompt"
    missing: object = None

    @property
    def parameters(self) -> tuple[ResolverParameter[Any], ...]:
        """Return the resolver's editable parameter bindings.

        Returns:
            Bindings for each representative typed field.
        """
        return (
            ResolverParameter("strength", float, lambda: self.strength, self._set_strength),
            ResolverParameter("count", int, lambda: self.count, self._set_count),
            ResolverParameter("enabled", bool, lambda: self.enabled, self._set_enabled),
            ResolverParameter("text", str, lambda: self.text, self._set_text),
            ResolverParameter("missing", object, lambda: self.missing, self._set_missing),
        )

    def _set_strength(self, value: float) -> None:
        """Set the representative floating-point value.

        Args:
            value: New strength stored by the resolver.
        """
        self.strength = value

    def _set_count(self, value: int) -> None:
        """Set the representative integer value.

        Args:
            value: New count stored by the resolver.
        """
        self.count = value

    def _set_enabled(self, value: bool) -> None:
        """Set the representative Boolean value.

        Args:
            value: New enabled state stored by the resolver.
        """
        self.enabled = value

    def _set_text(self, value: str) -> None:
        """Set the representative string value.

        Args:
            value: New text stored by the resolver.
        """
        self.text = value

    def _set_missing(self, value: object) -> None:
        """Set the representative untyped value.

        Args:
            value: New untyped value stored by the resolver.
        """
        self.missing = value

    def __call__(self, _prim) -> str:
        """Return the representative resolved value.

        Args:
            _prim: USD prim supplied by the resolver contract and unused by this fixture.

        Returns:
            The fixture's current text value.
        """
        return self.text


@dataclasses.dataclass
class _OptionalResolver(ValueResolver):
    """Provide an optional resolver value for type-resolution tests."""

    label: ClassVar[str] = "Optional"
    value: str | None = None

    @property
    def parameters(self) -> tuple[ResolverParameter[str | None], ...]:
        """Return the nullable string parameter binding.

        Returns:
            The binding that reads and updates the optional value.
        """
        return (ResolverParameter("value", str, lambda: self.value, self._set_value),)

    def _set_value(self, value: str | None) -> None:
        """Set the optional resolver value.

        Args:
            value: Nullable string stored by the resolver.
        """
        self.value = value

    def __call__(self, _prim) -> str | None:
        """Return the optional resolved value.

        Args:
            _prim: USD prim supplied by the resolver contract and unused by this fixture.

        Returns:
            The fixture's current nullable string value.
        """
        return self.value


def _make_input(
    value=None,
    *,
    default_value="default.png",
    remix_type=RemixType.TEXTURE_FILE_PATH,
) -> WorkflowInput:
    """Create a workflow input for resolver-model tests.

    Args:
        value: Resolver assigned to the input, or the selected-texture fixture when omitted.
        default_value: Native value restored when a resolver type is selected.
        remix_type: Remix semantic type used to choose compatible resolvers.

    Returns:
        The configured source-image workflow input.
    """
    return WorkflowInput(
        port_id="1.inputs.image",
        label="Source Image",
        native_type=pathlib.Path if remix_type is RemixType.TEXTURE_FILE_PATH else str,
        default_value=default_value,
        value=value if value is not None else SelectedTextureResolver(),
        remix_type=remix_type,
        tooltip="Texture source",
    )


class TestWorkflowModel(AsyncTestCase):
    """Tests workflow resolver and combo-box models."""

    async def test_getter_model_displays_every_catalog_option_in_order(self):
        """The resolver picker displays every shared-catalog option without UI filtering."""
        # Arrange
        workflow_input = _make_input(value=_TypedResolver())
        rule = MagicMock(options=(_TypedResolver, ConstantResolver), default=_TypedResolver)

        # Act
        with patch("lightspeed.trex.comfyui.widget.workflow.model.get_resolver_rule", return_value=rule):
            model = GetterValueModel(workflow_input)
            labels = [model.get_item_value_model(item).as_string for item in model.get_item_children()]

        # Assert
        self.assertEqual(labels, ["Typed", "File Path Constant"])

    async def test_switching_to_constant_uses_empty_native_value(self):
        """Selecting Constant discards workflow-authored sample data."""
        # Arrange
        workflow_input = _make_input(default_value="workflow-default.png")
        model = GetterValueModel(workflow_input, context_name="texturecraft")
        resolver_labels = [model.get_item_value_model(item).as_string for item in model.get_item_children()]
        constant_index = resolver_labels.index("File Path Constant")

        # Act
        model.get_item_value_model().set_value(constant_index)

        # Assert
        self.assertIsInstance(workflow_input.value, ConstantResolver)
        self.assertEqual(workflow_input.value.value, pathlib.Path())

    async def test_initial_context_resolver_preserves_parser_context_without_item_change(self):
        """An initial resolver keeps the USD context assigned by the workflow parser."""
        # Arrange
        workflow_input = _make_input(value=SelectedTextureResolver.create("default.png", "texturecraft"))

        # Act
        with patch.object(GetterValueModel, "_item_changed") as item_changed:
            GetterValueModel(workflow_input, context_name="texturecraft")

        # Assert
        self.assertEqual(workflow_input.value.context_name, "texturecraft")
        item_changed.assert_not_called()

    async def test_switching_to_context_resolver_uses_widget_context(self):
        """Switching resolver types injects the widget USD context when supported."""
        # Arrange
        workflow_input = _make_input(value=ConstantResolver("override"))
        model = GetterValueModel(workflow_input, context_name="texturecraft")

        # Act
        model.get_item_value_model().set_value(0)

        # Assert
        self.assertIsInstance(workflow_input.value, SelectedTextureResolver)
        self.assertEqual(workflow_input.value.context_name, "texturecraft")

    async def test_switching_to_catalog_resolver_constructs_selected_type(self):
        """Selecting a catalog option constructs that resolver without widget-specific branching."""
        # Arrange
        workflow_input = _make_input(value=ConstantResolver("override"))
        options = (_TypedResolver, ConstantResolver)

        # Act
        with patch(
            "lightspeed.trex.comfyui.widget.workflow.model.get_resolver_rule",
            return_value=MagicMock(options=options),
        ):
            model = GetterValueModel(workflow_input, context_name="texturecraft")
            model.get_item_value_model().set_value(0)

        # Assert
        self.assertIsInstance(workflow_input.value, _TypedResolver)

    async def test_unknown_resolver_is_rejected_without_mutating_input(self):
        """A resolver absent from the shared catalog is an explicit configuration error."""
        # Arrange
        resolver = SelectedTextureResolver()
        workflow_input = _make_input(value=resolver)
        rule = MagicMock(options=(ConstantResolver, _TypedResolver), default=_TypedResolver)

        # Act
        with patch("lightspeed.trex.comfyui.widget.workflow.model.get_resolver_rule", return_value=rule):
            with self.assertRaises(ValueError):
                GetterValueModel(workflow_input)

        # Assert
        self.assertIs(workflow_input.value, resolver)

    async def test_getter_model_does_not_rebind_initial_resolver_context(self):
        """Constructing the UI leaves the parser-owned resolver state untouched."""
        # Arrange
        resolver = SelectedTextureResolver(context_name=None)
        workflow_input = _make_input(value=resolver)

        # Act
        GetterValueModel(workflow_input, context_name="texturecraft")

        # Assert
        self.assertIsNone(resolver.context_name)

    async def test_resolver_param_item_updates_native_value(self):
        """Resolver parameter value models write native values to their fields."""
        cases = (
            ("Strength", 2.5, _TypedResolver(strength=2.5)),
            ("count", 7, _TypedResolver(count=7)),
            ("enabled", True, _TypedResolver(enabled=True)),
            ("text", "updated", _TypedResolver(text="updated")),
        )
        for label, value, expected in cases:
            with self.subTest(title=label):
                # Arrange
                resolver = _TypedResolver()
                items = ResolverParamItem.from_resolver(resolver, field_labels={"strength": "Strength"})
                values = {item.name_models[0].get_value_as_string(): item.value_models[0] for item in items}

                # Act
                values[label].set_value(value)

                # Assert
                self.assertEqual(resolver, expected)

    async def test_resolver_param_items_expose_native_types(self):
        """Resolver parameter rows preserve native editor types."""
        # Arrange
        resolver = _TypedResolver()

        # Act
        items = ResolverParamItem.from_resolver(resolver)

        # Assert
        self.assertEqual([item.value_type for item in items], [float, int, bool, str, str])

    async def test_resolver_param_items_use_declared_type_for_null_value(self):
        """A null parameter retains its declared editor type."""
        # Arrange
        resolver = _OptionalResolver()

        # Act
        items = ResolverParamItem.from_resolver(resolver, fallback_value_type=int)

        # Assert
        self.assertEqual(len(items), 1)
        self.assertIs(items[0].value_type, str)

    async def test_constant_param_item_uses_owning_workflow_type(self):
        """A polymorphic Constant uses the workflow type for native editor selection."""
        # Arrange
        resolver = ConstantResolver(pathlib.Path("texture.png"))

        # Act
        items = ResolverParamItem.from_resolver(resolver, fallback_value_type=pathlib.Path)

        # Assert
        self.assertEqual(len(items), 1)
        self.assertIs(items[0].value_type, pathlib.Path)

    async def test_resolver_param_items_hide_internal_context_name(self):
        """Resolver parameter rows omit the internal USD context field."""
        # Arrange
        resolver = SelectedTextureResolver(texture_type=TextureTypes.NORMAL_DX, context_name="texturecraft")

        # Act
        items = ResolverParamItem.from_resolver(resolver)

        # Assert
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name_models[0].get_value_as_string(), "Texture Type")

    async def test_resolver_param_items_expose_declared_choices(self):
        """Choice-backed resolver parameters retain their typed options for ComboBox rendering."""
        # Arrange
        resolver = SelectedTextureResolver()

        # Act
        item = ResolverParamItem.from_resolver(resolver)[0]

        # Assert
        choice_model = item.value_models[0]
        self.assertIsInstance(choice_model, NativeChoiceModel)
        self.assertEqual(
            tuple(choice.value for choice in choice_model.get_item_children()),
            tuple(texture_type for texture_type in TextureTypes if texture_type is not TextureTypes.OTHER),
        )

    async def test_resolver_param_name_models_expose_parameter_tooltips(self):
        """Each resolver parameter row exposes its explanatory tooltip on the name model."""
        # Arrange
        resolver = SelectedTextureResolver()
        parameter_tooltip = resolver.parameters[0].tooltip

        # Act
        item = ResolverParamItem.from_resolver(resolver)[0]

        # Assert
        self.assertTrue(parameter_tooltip)
        self.assertEqual(item.name_models[0].get_tool_tip(), parameter_tooltip)

    async def test_group_items_track_parenting_and_child_capability(self):
        """Workflow groups retain parent links and report child capability correctly."""
        # Arrange
        workflow_group = WorkflowGroupItem("Textures", expanded=True)
        input_group = InputItemGroup(_make_input(), expanded=False, tooltip="Texture")

        # Act
        input_group.parent = workflow_group

        # Assert
        self.assertTrue(input_group in workflow_group.children)
        self.assertFalse(input_group.can_have_children)
        self.assertEqual(input_group.tooltip, "Texture")

    async def test_simple_combo_model_notifies_subscribers_on_index_change(self):
        """Changing the selected index emits an item-change event."""
        # Arrange
        model = SimpleComboModel(["Default", "High Quality"])
        callback = MagicMock()
        model.add_item_changed_fn(callback)

        # Act
        model.get_item_value_model().set_value(1)

        # Assert
        callback.assert_called_once_with(model, None)

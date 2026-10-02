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

from omni.kit import undo
from omni.kit.test import AsyncTestCase
from lightspeed.trex.comfyui.core.enums import MeshReferenceSelection, OutputApplyBehavior, RemixType
from lightspeed.trex.comfyui.core.maps import OUTPUT_TEXTURE_TYPE_MAP
from lightspeed.trex.comfyui.core.models import WorkflowInput, WorkflowOutput
from lightspeed.trex.comfyui.core.resolvers import (
    AllStageMeshesResolver,
    ConstantResolver,
    ResolverParameter,
    SelectedMeshResolver,
    SelectedTextureResolver,
    ValueResolver,
)
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.flux.property_widget_builder.model.native import NativeChoiceModel
from ...workflow.items import (
    InputItemGroup,
    ResolverParamItem,
    WorkflowGroupItem,
)
from ...workflow.model import GetterValueModel, _WorkflowOutputFieldValueModel


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
            tuple(texture_type for texture_type in TEXTURE_TYPE_INPUT_MAP if texture_type is not TextureTypes.OTHER),
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

    async def test_texture_output_properties_expose_supported_labels_and_choices(self):
        """Texture output properties expose Replace and Do Nothing actions."""
        # Arrange
        workflow_output = WorkflowOutput(
            node_id="20",
            remix_type=RemixType.TEXTURE_FILE_PATH,
            texture_type="albedo",
        )

        # Act
        items = ResolverParamItem.from_workflow_output(workflow_output)

        # Assert
        self.assertEqual(
            [item.name_models[0].get_value_as_string() for item in items],
            ["Apply Behavior", "Texture Type"],
        )
        apply_model = items[0].value_models[0]
        self.assertEqual(
            tuple(choice.value for choice in apply_model.get_item_children()),
            (OutputApplyBehavior.REPLACE, OutputApplyBehavior.NONE),
        )
        self.assertEqual(
            [apply_model.get_item_value_model(choice).as_string for choice in apply_model.get_item_children()],
            ["Replace", "Do Nothing"],
        )
        texture_model = items[1].value_models[0]
        texture_labels = [
            texture_model.get_item_value_model(choice).as_string for choice in texture_model.get_item_children()
        ]
        self.assertIn("Normal - OpenGL", texture_labels)
        self.assertNotIn("normal_ogl", texture_labels)

    async def test_mesh_output_properties_expose_supported_labels_and_choices(self):
        """Mesh output properties expose only Apply Behavior."""
        # Arrange
        workflow_output = WorkflowOutput(
            node_id="20",
            remix_type=RemixType.MESH_FILE_PATH,
        )

        # Act
        items = ResolverParamItem.from_workflow_output(workflow_output)

        # Assert
        self.assertEqual(
            [item.name_models[0].get_value_as_string() for item in items],
            ["Apply Behavior"],
        )
        apply_model = items[0].value_models[0]
        self.assertEqual(
            tuple(choice.value for choice in apply_model.get_item_children()),
            (
                OutputApplyBehavior.REPLACE,
                OutputApplyBehavior.APPEND,
                OutputApplyBehavior.NONE,
            ),
        )
        self.assertEqual(
            [apply_model.get_item_value_model(choice).as_string for choice in apply_model.get_item_children()],
            ["Replace", "Append", "Do Nothing"],
        )

    async def test_output_apply_choice_mutates_persisted_workflow_output(self):
        """Changing Apply Behavior edits the same WorkflowOutput object."""
        # Arrange
        workflow_output = WorkflowOutput(
            node_id="20",
            remix_type=RemixType.TEXTURE_FILE_PATH,
            texture_type="albedo",
            apply_behavior=OutputApplyBehavior.REPLACE,
        )
        apply_model = ResolverParamItem.from_workflow_output(workflow_output)[0].value_models[0]

        # Act
        with undo.disabled():
            apply_model.get_item_value_model().set_value(1)

        # Assert
        self.assertIs(workflow_output.apply_behavior, OutputApplyBehavior.NONE)

    async def test_output_texture_type_choice_mutates_persisted_workflow_output(self):
        """Changing Texture Type edits the same WorkflowOutput object."""
        # Arrange
        workflow_output = WorkflowOutput(
            node_id="20",
            remix_type=RemixType.TEXTURE_FILE_PATH,
            texture_type="albedo",
        )
        texture_model = ResolverParamItem.from_workflow_output(workflow_output)[1].value_models[0]
        normal_index = tuple(OUTPUT_TEXTURE_TYPE_MAP).index("normal_ogl")

        # Act
        with undo.disabled():
            texture_model.get_item_value_model().set_value(normal_index)

        # Assert
        self.assertEqual(workflow_output.texture_type, "normal_ogl")

    async def test_mesh_getter_replaces_selected_mesh_resolver(self):
        """A mesh getter replaces the selected-mesh resolver."""
        # Arrange
        workflow_input = _make_input(value=SelectedMeshResolver(), remix_type=RemixType.MESH_FILE_PATH)
        getter = GetterValueModel(workflow_input, context_name="texturecraft")
        labels = [getter.get_item_value_model(item).as_string for item in getter.get_item_children()]

        # Act
        getter.get_item_value_model().set_value(labels.index("All Meshes"))

        # Assert
        self.assertIsInstance(workflow_input.value, AllStageMeshesResolver)
        self.assertEqual(workflow_input.value.context_name, "texturecraft")

    async def test_mesh_reference_choice_changes_reference_selection(self):
        """Reference Selection edits the mesh resolver."""
        # Arrange
        resolver = AllStageMeshesResolver()
        items = ResolverParamItem.from_resolver(resolver, fallback_value_type=pathlib.Path)
        reference_model = next(
            item.value_models[0] for item in items if item.name_models[0].get_value_as_string() == "Reference Selection"
        )
        choices = reference_model.get_item_children()
        selected_index = next(i for i, choice in enumerate(choices) if choice.value is MeshReferenceSelection.SELECTED)

        # Act
        reference_model.get_item_value_model().set_value(selected_index)

        # Assert
        self.assertEqual(
            [reference_model.get_item_value_model(choice).as_string for choice in choices], ["All", "Selected"]
        )
        self.assertIs(resolver.reference_selection, MeshReferenceSelection.SELECTED)

    async def test_output_choices_undo_and_redo_refresh_recreated_controls(self):
        """Undo and redo restore output values and current control selections."""
        for field_name, property_index, edited_value in (
            ("apply_behavior", 0, OutputApplyBehavior.NONE),
            ("texture_type", 1, "normal_ogl"),
        ):
            with self.subTest(field=field_name):
                # Arrange
                undo.clear_stack()
                output = WorkflowOutput(node_id="20", remix_type=RemixType.TEXTURE_FILE_PATH, texture_type="albedo")
                original_value = getattr(output, field_name)
                choice_model = ResolverParamItem.from_workflow_output(output)[property_index].value_models[0]
                choices = tuple(item.value for item in choice_model.get_item_children())
                original_index = choices.index(original_value)
                edited_index = choices.index(edited_value)
                try:
                    # Act
                    choice_model.get_item_value_model().set_value(edited_index)
                    edited_state = (getattr(output, field_name), choice_model.get_item_value_model().as_int)
                    choice_model = ResolverParamItem.from_workflow_output(output)[property_index].value_models[0]
                    undo.undo()
                    undone_state = (getattr(output, field_name), choice_model.get_item_value_model().as_int)
                    undo.redo()
                    redone_state = (getattr(output, field_name), choice_model.get_item_value_model().as_int)

                    # Assert
                    self.assertEqual(edited_state, (edited_value, edited_index))
                    self.assertEqual(undone_state, (original_value, original_index))
                    self.assertEqual(redone_state, (edited_value, edited_index))
                finally:
                    undo.clear_stack()

    async def test_destroyed_output_item_stops_following_undo(self):
        """A destroyed output item releases its undo subscription and no longer refreshes."""
        # Arrange
        undo.clear_stack()
        output = WorkflowOutput(node_id="20", remix_type=RemixType.TEXTURE_FILE_PATH, texture_type="albedo")
        item = ResolverParamItem.from_workflow_output(output)[0]
        choice_model = item.value_models[0]
        choices = tuple(choice.value for choice in choice_model.get_item_children())
        original_index = choices.index(output.apply_behavior)
        edited_index = choices.index(OutputApplyBehavior.NONE)
        try:
            choice_model.get_item_value_model().set_value(edited_index)

            # Act
            item.destroy()
            undo.undo()

            # Assert
            self.assertEqual(output.apply_behavior, choices[original_index])
            self.assertEqual(choice_model.get_item_value_model().as_int, edited_index)
        finally:
            undo.clear_stack()

    async def test_output_fields_reject_invalid_types_without_mutation(self):
        """Invalid values cannot change persisted output settings."""
        for field_name, invalid_value in (
            ("apply_behavior", "replace"),
            ("texture_type", 7),
        ):
            with self.subTest(title=field_name):
                # Arrange
                output = WorkflowOutput(node_id="20", remix_type=RemixType.TEXTURE_FILE_PATH, texture_type="albedo")
                model = _WorkflowOutputFieldValueModel(output, field_name)
                previous = model.get_value()

                # Act
                with self.assertRaises(TypeError):
                    model.set_value(invalid_value)

                # Assert
                self.assertEqual(model.get_value(), previous)

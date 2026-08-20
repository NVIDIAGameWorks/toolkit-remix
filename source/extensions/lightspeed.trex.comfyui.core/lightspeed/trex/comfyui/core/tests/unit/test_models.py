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
from unittest.mock import MagicMock, patch

from lightspeed.trex.comfyui.core.enums import (
    WORKFLOW_TYPES_BY_CATEGORY,
    RemixType,
    WorkflowCategory,
    WorkflowSourceType,
    WorkflowType,
)
from lightspeed.trex.comfyui.core.models import (
    ComfyUIWorkflowRequest,
    Workflow,
    WorkflowInput,
    WorkflowOutput,
    WorkflowTypeCategory,
    WorkflowTypeOption,
)
from lightspeed.trex.comfyui.core.preset import Preset
from lightspeed.trex.comfyui.core.resolvers import (
    ConstantResolver,
    SelectedTextureResolver,
    ValueResolver,
)
from lightspeed.trex.comfyui.core.tests.unit.fixtures import get_test_workflow_pair
from omni.kit.test import AsyncTestCase


def _editable_value(value: ValueResolver):
    """Return the value stored by an editable value resolver.

    Args:
        value: Editable resolver whose stored value is requested.

    Returns:
        The resolver's typed editable value.
    """
    return value.value


class TestComfyUIWorkflowRequest(AsyncTestCase):
    """Test the persisted ComfyUI workflow invocation model."""

    async def test_construction_with_malformed_persisted_values_raises(self):
        """Workflow requests reject ambiguous bindings and invalid persisted field types."""
        # Arrange
        valid = {
            "prompt": {},
            "input_bindings": (),
            "client_id": "client",
            "timeout": 300.0,
            "output_url": "C:/project/assets/ingested/comfyui/test",
            "workflow": Workflow(),
        }
        cases = (
            ({"prompt": []}, TypeError),
            ({"input_bindings": []}, TypeError),
            ({"input_bindings": (("port",),)}, TypeError),
            ({"input_bindings": (("", "source.png"),)}, ValueError),
            ({"input_bindings": (("port", "a.png"), ("port", "b.png"))}, ValueError),
            ({"client_id": None}, TypeError),
            ({"timeout": 0.0}, ValueError),
            ({"output_url": ""}, ValueError),
            ({"workflow": MagicMock()}, TypeError),
        )

        for override, error_type in cases:
            with self.subTest(override=override):
                # Act
                with self.assertRaises(error_type) as error_context:
                    ComfyUIWorkflowRequest(**(valid | override))

                # Assert
                self.assertIs(type(error_context.exception), error_type)


class TestWorkflowInput(AsyncTestCase):
    """Test canonical workflow input parsing."""

    async def test_value_requires_explicit_resolver(self) -> None:
        """Direct workflow input construction rejects an unresolved raw value."""
        # Arrange
        raw_value = 0.5

        # Act
        with self.assertRaises(TypeError) as error_context:
            WorkflowInput("1.inputs.strength", "Strength", float, raw_value, raw_value)

        # Assert
        self.assertIn("ValueResolver", str(error_context.exception))

    async def test_from_dict_parses_nested_metadata_and_resolver(self) -> None:
        """Canonical nested group and tooltip fields populate a typed input."""
        # Arrange
        raw = {
            "name": "Input Image",
            "type": "str",
            "remix_type": "texture_file_path",
            "order": 4,
            "additional_data": {"group": "Input", "tooltip": "Choose a source texture"},
        }

        # Act
        result = WorkflowInput.from_dict("177", "image", raw, "example.png")

        # Assert
        self.assertEqual(result.port_id, "177.inputs.image")
        self.assertEqual(result.label, "Input Image")
        self.assertIs(result.native_type, pathlib.Path)
        self.assertEqual(result.default_value, "example.png")
        self.assertIsInstance(result.value, SelectedTextureResolver)
        self.assertIs(result.remix_type, RemixType.TEXTURE_FILE_PATH)
        self.assertEqual((result.order, result.group, result.tooltip), (4, "Input", "Choose a source texture"))

    async def test_from_dict_uses_typed_constant_for_plain_input(self) -> None:
        """A plain typed input starts from its USD type default in an exact typed Constant."""
        # Arrange
        raw = {"name": "Strength", "type": "float"}

        # Act
        result = WorkflowInput.from_dict("10", "strength", raw, 0.5)

        # Assert
        self.assertIs(result.native_type, float)
        self.assertIsInstance(result.value, ConstantResolver)
        self.assertIs(result.value.value_type, float)
        self.assertEqual(result.value.value, 0.0)

    async def test_unknown_remix_type_is_rejected(self) -> None:
        """An explicit unknown semantic type cannot silently become a constant input."""
        # Arrange
        raw = {"type": "str", "remix_type": "texture_path_typo"}

        # Act
        with patch("lightspeed.trex.comfyui.core.models.carb.log_warn") as log_warn:
            result = WorkflowInput.from_dict(
                "177",
                "image",
                raw,
                "C:/textures/albedo.png",
            )

        # Assert
        self.assertIsNone(result)
        log_warn.assert_called_once()

    async def test_malformed_input_metadata_is_rejected(self) -> None:
        """Malformed canonical input fields do not produce partial models."""
        # Arrange
        cases = (
            ("", "port", {"type": "str"}),
            ("1", "", {"type": "str"}),
            ("1", "port", []),
            ("1", "port", {}),
            ("1", "port", {"type": ["str"]}),
            ("1", "port", {"type": "str", "remix_type": ["prompt"]}),
            ("1", "port", {"type": "str", "name": ["Prompt"]}),
            ("1", "port", {"type": "str", "order": True}),
            ("1", "port", {"type": "str", "additional_data": []}),
            ("1", "port", {"type": "str", "additional_data": {"group": []}}),
            ("group.1", "port", {"type": "str"}),
            ("1", "port", {"type": "unknown"}),
        )

        for node_id, port_name, raw in cases:
            with self.subTest(node_id=node_id, port_name=port_name, raw=raw):
                # Act
                with patch("lightspeed.trex.comfyui.core.models.carb.log_warn"):
                    result = WorkflowInput.from_dict(node_id, port_name, raw, "default")

                # Assert
                self.assertIsNone(result)

    async def test_native_input_default_requires_declared_type(self) -> None:
        """Workflow parsing rejects native defaults whose exact type does not match metadata."""
        # Arrange
        cases = (
            ({"type": "bool"}, 1),
            ({"type": "int"}, True),
            ({"type": "float"}, 1),
            ({"type": "str"}, pathlib.Path("prompt.txt")),
            ({"type": "Path"}, 7),
        )
        for raw, default_value in cases:
            with self.subTest(raw=raw):
                # Act
                with patch("lightspeed.trex.comfyui.core.models.carb.log_warn") as log_warn:
                    result = WorkflowInput.from_dict("1", "value", raw, default_value)

                # Assert
                self.assertIsNone(result)
                log_warn.assert_called_once()


class TestWorkflowOutput(AsyncTestCase):
    """Test the exact supported texture-output metadata contract."""

    async def test_from_dict_parses_canonical_nested_texture_type(self) -> None:
        """A canonical texture-file output becomes a compact typed model."""
        # Arrange
        raw = {
            "name": "albedo",
            "type": "str",
            "remix_type": "texture_file_path",
            "order": 3,
            "additional_data": {"texture_type": "albedo", "tooltip": "Generated color"},
        }

        # Act
        result = WorkflowOutput.from_dict("181", raw)

        # Assert
        self.assertEqual(result, WorkflowOutput(node_id="181", texture_type="albedo", order=3))

    async def test_unsupported_output_semantics_are_rejected(self) -> None:
        """Only canonical string texture-file outputs enter texture application."""
        # Arrange
        base = {
            "name": "albedo",
            "type": "str",
            "remix_type": "texture_file_path",
            "additional_data": {"texture_type": "albedo"},
        }
        cases = (
            {**base, "type": "IMAGE"},
            {**base, "remix_type": "mesh_file_path"},
            {key: value for key, value in base.items() if key != "type"},
            {key: value for key, value in base.items() if key != "remix_type"},
        )

        for raw in cases:
            with self.subTest(raw=raw):
                # Act
                with patch("lightspeed.trex.comfyui.core.models.carb.log_warn"):
                    result = WorkflowOutput.from_dict("181", raw)

                # Assert
                self.assertIsNone(result)

    async def test_malformed_output_metadata_is_rejected(self) -> None:
        """Missing and wrongly typed output fields do not create output specs."""
        # Arrange
        base = {
            "name": "albedo",
            "type": "str",
            "remix_type": "texture_file_path",
            "additional_data": {"texture_type": "albedo"},
        }
        cases = (
            ("", base),
            ("181", []),
            ("181", {**base, "name": ""}),
            ("181", {**base, "order": "first"}),
            ("181", {**base, "additional_data": []}),
            ("181", {**base, "additional_data": {}}),
            ("181", {**base, "additional_data": {"texture_type": 7}}),
            ("181", {**base, "additional_data": {"texture_type": "unsupported"}}),
            ("group.181", base),
        )

        for node_id, raw in cases:
            with self.subTest(node_id=node_id, raw=raw):
                # Act
                with patch("lightspeed.trex.comfyui.core.models.carb.log_warn"):
                    result = WorkflowOutput.from_dict(node_id, raw)

                # Assert
                self.assertIsNone(result)


class TestWorkflow(AsyncTestCase):
    """Test canonical workflow-pair parsing and preset behavior."""

    async def test_from_litegraph_dict_parses_inputs_outputs_and_presets(self) -> None:
        """The API and full halves retain their distinct canonical responsibilities."""
        # Arrange
        api_workflow, full_workflow = get_test_workflow_pair()

        # Act
        workflow = Workflow.from_litegraph_dict(api_workflow, full_workflow, name="PBRify")

        # Assert
        self.assertIs(workflow.api, api_workflow)
        self.assertEqual(workflow.name, "PBRify")
        self.assertEqual(
            [item.port_id for item in workflow.inputs],
            [
                "10.inputs.strength",
                "10.inputs.prompt",
                "177.inputs.image",
            ],
        )
        self.assertEqual(workflow.output_specs, [WorkflowOutput("181", "albedo", 3)])
        self.assertEqual(set(workflow.presets), {"Strong", "Soft"})
        self.assertEqual(workflow.group_order, ["Input", "Material"])
        self.assertEqual(workflow.active_preset, "Strong")
        strength = next(item for item in workflow.inputs if item.port_id == "10.inputs.strength")
        self.assertEqual(_editable_value(strength.value), 1.0)

    async def test_apply_preset_resets_omitted_values_to_workflow_defaults(self) -> None:
        """A preset resets omitted values before applying its overrides."""
        # Arrange
        api_workflow, full_workflow = get_test_workflow_pair()
        workflow = Workflow.from_litegraph_dict(api_workflow, full_workflow)
        prompt = next(item for item in workflow.inputs if item.port_id == "10.inputs.prompt")
        prompt.value = ConstantResolver("artist prompt")

        # Act
        workflow.apply_preset(workflow.presets["Soft"])

        # Assert
        strength = next(item for item in workflow.inputs if item.port_id == "10.inputs.strength")
        self.assertEqual(_editable_value(strength.value), 0.25)
        self.assertEqual(_editable_value(prompt.value), "")
        self.assertIsInstance(strength.value, ConstantResolver)
        self.assertIs(strength.value.value_type, float)
        self.assertIsInstance(prompt.value, ConstantResolver)
        self.assertIs(prompt.value.value_type, str)

    async def test_apply_preset_with_invalid_override_preserves_all_current_values(self) -> None:
        """A malformed override cannot leave earlier workflow inputs partially updated."""
        # Arrange
        api_workflow, full_workflow = get_test_workflow_pair()
        workflow = Workflow.from_litegraph_dict(api_workflow, full_workflow)
        strength = next(item for item in workflow.inputs if item.port_id == "10.inputs.strength")
        prompt = next(item for item in workflow.inputs if item.port_id == "10.inputs.prompt")
        original_strength = _editable_value(strength.value)
        original_prompt = _editable_value(prompt.value)
        preset = Preset(name="Invalid", inputs={"10.strength": 0.75, "10.prompt": 7})

        # Act
        with self.assertRaises(TypeError):
            workflow.apply_preset(preset)

        # Assert
        self.assertEqual(_editable_value(strength.value), original_strength)
        self.assertEqual(_editable_value(prompt.value), original_prompt)

    async def test_apply_preset_supports_dotted_port_name(self) -> None:
        """Preset keys preserve every character after the node identifier."""
        # Arrange
        workflow_input = WorkflowInput(
            port_id="10.inputs.prompt.positive",
            label="Prompt",
            native_type=str,
            default_value="default",
            value=ConstantResolver("default"),
        )
        workflow = Workflow(
            inputs=[workflow_input],
            workflow_defaults={workflow_input.port_id: ConstantResolver("default")},
        )

        # Act
        workflow.apply_preset(Preset(name="Custom", inputs={"10.prompt.positive": "updated"}))

        # Assert
        self.assertEqual(_editable_value(workflow_input.value), "updated")

    async def test_apply_preset_explicit_value_replaces_semantic_resolver(self) -> None:
        """An explicitly authored preset value selects the canonical Constant resolver."""
        # Arrange
        resolver = SelectedTextureResolver(context_name="texturecraft")
        workflow_input = WorkflowInput(
            port_id="10.inputs.texture",
            label="Texture",
            native_type=pathlib.Path,
            default_value="saved.png",
            value=resolver,
            remix_type=RemixType.TEXTURE_FILE_PATH,
        )
        workflow = Workflow(
            inputs=[workflow_input],
            workflow_defaults={workflow_input.port_id: resolver},
        )

        # Act
        workflow.apply_preset(Preset(name="Custom", inputs={"10.texture": "other.png"}))

        # Assert
        self.assertIsInstance(workflow_input.value, ConstantResolver)
        self.assertEqual(_editable_value(workflow_input.value), pathlib.Path("other.png"))

    async def test_apply_preset_updates_user_selected_constant_instead_of_workflow_default(self) -> None:
        """A preset updates the user's current Constant without restoring the workflow's semantic default."""
        # Arrange
        workflow_input = WorkflowInput(
            port_id="10.inputs.texture",
            label="Texture",
            native_type=pathlib.Path,
            default_value="saved.png",
            value=ConstantResolver(pathlib.Path("artist.png"), value_type=pathlib.Path),
            remix_type=RemixType.TEXTURE_FILE_PATH,
        )
        workflow = Workflow(
            inputs=[workflow_input],
            workflow_defaults={
                workflow_input.port_id: SelectedTextureResolver(context_name="texturecraft"),
            },
        )

        # Act
        workflow.apply_preset(Preset(name="Custom", inputs={"10.texture": "preset.png"}))

        # Assert
        self.assertIsInstance(workflow_input.value, ConstantResolver)
        self.assertEqual(_editable_value(workflow_input.value), pathlib.Path("preset.png"))

    async def test_apply_preset_omitted_value_preserves_semantic_resolver(self) -> None:
        """A semantic resolver remains selected when the preset does not author that input."""
        # Arrange
        resolver = SelectedTextureResolver(context_name="texturecraft")
        workflow_input = WorkflowInput(
            port_id="10.inputs.texture",
            label="Texture",
            native_type=pathlib.Path,
            default_value="saved.png",
            value=resolver,
            remix_type=RemixType.TEXTURE_FILE_PATH,
        )
        workflow = Workflow(inputs=[workflow_input])

        # Act
        workflow.apply_preset(Preset(name="Custom", inputs={}))

        # Assert
        self.assertIsInstance(workflow_input.value, SelectedTextureResolver)

    async def test_from_litegraph_dict_constructs_resolvers_for_the_usd_context(self) -> None:
        """Workflow parsing binds semantic resolvers to the owning USD context."""
        # Arrange
        api_workflow, full_workflow = get_test_workflow_pair()

        # Act
        workflow = Workflow.from_litegraph_dict(
            api_workflow,
            full_workflow,
            context_name="texturecraft",
        )

        # Assert
        texture_input = next(item for item in workflow.inputs if item.remix_type is RemixType.TEXTURE_FILE_PATH)
        self.assertIsInstance(texture_input.value, SelectedTextureResolver)
        self.assertEqual(texture_input.value.context_name, "texturecraft")

    async def test_workflow_defaults_do_not_alias_live_resolvers(self) -> None:
        """Editing a live resolver cannot mutate the stored reset value."""
        # Arrange
        api_workflow, full_workflow = get_test_workflow_pair()
        workflow = Workflow.from_litegraph_dict(api_workflow, full_workflow)
        strength = next(item for item in workflow.inputs if item.port_id == "10.inputs.strength")

        # Act
        strength.value.value = 0.1

        # Assert
        self.assertEqual(_editable_value(workflow.workflow_defaults[strength.port_id]), 0.0)

    async def test_from_litegraph_dict_applies_only_exact_active_preset(self) -> None:
        """Only an exact active preset name selects and applies a preset."""
        # Arrange
        cases = (
            ("Strong", "Strong"),
            ("strong", None),
            ("Missing", None),
            (None, None),
        )

        for active_preset, expected in cases:
            with self.subTest(active_preset=active_preset):
                api_workflow, full_workflow = get_test_workflow_pair()
                metadata = full_workflow["extra"]["rtx-remix"]
                if active_preset is None:
                    metadata.pop("activePreset", None)
                else:
                    metadata["activePreset"] = active_preset

                # Act
                workflow = Workflow.from_litegraph_dict(api_workflow, full_workflow)

                # Assert
                self.assertEqual(workflow.active_preset, expected)
                strength = next(item for item in workflow.inputs if item.port_id == "10.inputs.strength")
                self.assertEqual(_editable_value(strength.value), 1.0 if expected else 0.0)

    async def test_missing_api_port_is_skipped(self) -> None:
        """Metadata cannot invent an input absent from the executable prompt."""
        # Arrange
        api_workflow = {
            "1": {
                "inputs": {"present": "value"},
                "_meta": {
                    "rtx-remix": {
                        "inputs": {
                            "present": {"type": "str"},
                            "missing": {"type": "str"},
                        }
                    }
                },
            }
        }

        # Act
        with patch("lightspeed.trex.comfyui.core.models.carb.log_warn") as log_warn:
            workflow = Workflow.from_litegraph_dict(api_workflow, {})

        # Assert
        self.assertEqual([item.port_id for item in workflow.inputs], ["1.inputs.present"])
        log_warn.assert_called_once()

    async def test_workflow_identity_is_set_explicitly_by_core(self) -> None:
        """Source and category remain explicit typed fields for server-loaded workflows."""
        # Arrange
        workflow = Workflow(name="PBRify")

        # Act
        workflow.source_type = WorkflowSourceType.RTX_REMIX
        workflow.category = WorkflowCategory.API

        # Assert
        self.assertIs(workflow.source_type, WorkflowSourceType.RTX_REMIX)
        self.assertIs(workflow.category, WorkflowCategory.API)

    async def test_workflow_display_name_falls_back_to_name(self) -> None:
        """A workflow without display metadata shows its file name."""
        # Arrange
        name = "PBRify"

        # Act
        workflow = Workflow(name=name)

        # Assert
        self.assertEqual(workflow.display_name, "PBRify")

    async def test_from_catalog_entry_parses_complete_entry(self) -> None:
        """A complete catalog entry keeps its typed identity and display metadata."""
        # Arrange
        payload = {
            "name": "material",
            "path": "material.json",
            "size": 1024,
            "modified": 123.4,
            "displayName": "Material Generation",
            "description": "Generates a PBR material.",
            "workflowType": "Material Generation",
        }

        # Act
        workflow = Workflow.from_catalog_entry(WorkflowCategory.API, WorkflowSourceType.RTX_REMIX, payload)

        # Assert
        self.assertEqual(workflow.name, "material")
        self.assertIs(workflow.category, WorkflowCategory.API)
        self.assertIs(workflow.source_type, WorkflowSourceType.RTX_REMIX)
        self.assertEqual(workflow.display_name, "Material Generation")
        self.assertEqual(workflow.description, "Generates a PBR material.")
        self.assertIs(workflow.workflow_type, WorkflowType.MATERIAL_GENERATION)
        self.assertEqual(workflow.api, {})

    async def test_from_catalog_entry_resolves_metadata_fallbacks(self) -> None:
        """Missing catalog metadata falls back to the name, an empty description, and no type."""
        for title, payload, display_name, description, workflow_type in (
            ("missing_display_name", {"name": "material"}, "material", "", None),
            ("blank_display_name", {"name": "material", "displayName": "  "}, "material", "", None),
            ("non_string_description", {"name": "material", "description": 5}, "material", "", None),
            ("missing_description", {"name": "material"}, "material", "", None),
            ("blank_workflow_type", {"name": "material", "workflowType": ""}, "material", "", None),
            ("missing_workflow_type", {"name": "material"}, "material", "", None),
            ("null_workflow_type", {"name": "material", "workflowType": None}, "material", "", None),
            (
                "known_workflow_type",
                {"name": "material", "workflowType": "Texture Upscaling"},
                "material",
                "",
                WorkflowType.TEXTURE_UPSCALING,
            ),
        ):
            with self.subTest(title=title):
                # Arrange
                entry = payload

                # Act
                workflow = Workflow.from_catalog_entry(WorkflowCategory.API, WorkflowSourceType.USER, entry)

                # Assert
                self.assertEqual(workflow.display_name, display_name)
                self.assertEqual(workflow.description, description)
                self.assertEqual(workflow.workflow_type, workflow_type)

    async def test_from_catalog_entry_leaves_missing_type_silent(self) -> None:
        """A missing or null catalog workflow type resolves to no type without a warning."""
        for title, payload in (
            ("missing_workflow_type", {"name": "material"}),
            ("null_workflow_type", {"name": "material", "workflowType": None}),
        ):
            with self.subTest(title=title):
                # Arrange
                entry = payload

                # Act
                with patch("lightspeed.trex.comfyui.core.models.carb.log_warn") as log_warn:
                    workflow = Workflow.from_catalog_entry(WorkflowCategory.API, WorkflowSourceType.USER, entry)

                # Assert
                self.assertIsNone(workflow.workflow_type)
                log_warn.assert_not_called()

    async def test_from_catalog_entry_warns_on_unknown_workflow_type(self) -> None:
        """An unknown catalog workflow type, including a retired snake_case value, logs a warning and leaves no type."""
        for title, raw_type in (
            ("old_snake_case_spelling", "material_generation"),
            ("unpublished_type", "Voice Cloning"),
        ):
            with self.subTest(title=title):
                # Arrange
                payload = {"name": "material", "workflowType": raw_type}

                # Act
                with patch("lightspeed.trex.comfyui.core.models.carb.log_warn") as log_warn:
                    workflow = Workflow.from_catalog_entry(WorkflowCategory.API, WorkflowSourceType.USER, payload)

                # Assert
                self.assertIsNone(workflow.workflow_type)
                log_warn.assert_called_once()
                self.assertIn("material", log_warn.call_args.args[0])
                self.assertIn(raw_type, log_warn.call_args.args[0])

    async def test_from_catalog_entry_requires_nonblank_name(self) -> None:
        """A catalog entry without a non-blank string name is rejected."""
        for title, payload, error, message in (
            ("missing_name", {}, TypeError, "name must be a str"),
            ("non_string_name", {"name": 5}, TypeError, "name must be a str"),
            ("blank_name", {"name": "  "}, ValueError, "name must not be blank"),
        ):
            with self.subTest(title=title):
                # Arrange
                entry = payload

                # Act
                with self.assertRaises(error) as error_context:
                    Workflow.from_catalog_entry(WorkflowCategory.API, WorkflowSourceType.USER, entry)

                # Assert
                self.assertIn(message, str(error_context.exception))

    async def test_get_output_spec_returns_exact_node(self) -> None:
        """History parsing resolves outputs only by their declared node identifier."""
        # Arrange
        expected = WorkflowOutput("181", "albedo", 3)
        workflow = Workflow(output_specs=[expected])

        # Act
        result = workflow.get_output_spec("181")
        missing = workflow.get_output_spec("missing")

        # Assert
        self.assertIs(result, expected)
        self.assertIsNone(missing)


class TestWorkflowTypesByCategory(AsyncTestCase):
    """Test the picker grouping the node pack publishes for every workflow type."""

    async def test_lists_every_workflow_type_exactly_once(self) -> None:
        """Every WorkflowType member appears in exactly one category, in node pack order."""
        # Arrange
        expected = list(WorkflowType)

        # Act
        listed = [workflow_type for types in WORKFLOW_TYPES_BY_CATEGORY.values() for workflow_type in types]

        # Assert
        self.assertEqual(listed, expected)


class TestWorkflowTypeCategory(AsyncTestCase):
    """Test parsing of the workflows/types endpoint payload into ordered categories."""

    async def test_list_from_payload_parses_ordered_categories_with_descriptions(self) -> None:
        """Categories and their type options keep server order and carry server descriptions."""
        # Arrange
        payload = [
            {
                "name": "Generation",
                "types": [
                    {"value": "Asset Generation", "description": "Server description of the asset type."},
                    {"value": "Material Generation", "description": "Server description of the material type."},
                ],
            },
            {"name": "Other", "types": [{"value": "Other", "description": "Anything else."}]},
        ]

        # Act
        categories = WorkflowTypeCategory.list_from_payload(payload)

        # Assert
        self.assertEqual(
            categories,
            [
                WorkflowTypeCategory(
                    name="Generation",
                    types=(
                        WorkflowTypeOption(WorkflowType.ASSET_GENERATION, "Server description of the asset type."),
                        WorkflowTypeOption(
                            WorkflowType.MATERIAL_GENERATION, "Server description of the material type."
                        ),
                    ),
                ),
                WorkflowTypeCategory(name="Other", types=(WorkflowTypeOption(WorkflowType.OTHER, "Anything else."),)),
            ],
        )

    async def test_list_from_payload_skips_unknown_type_value_and_logs(self) -> None:
        """A type value the enum does not hold is skipped and logged, other types stay."""
        # Arrange
        payload = [
            {
                "name": "Generation",
                "types": [
                    {"value": "Asset Generation", "description": "Server description of the asset type."},
                    {"value": "Future Type", "description": "Not supported yet."},
                ],
            }
        ]

        # Act
        with patch("lightspeed.trex.comfyui.core.models.carb.log_warn") as log_warn:
            categories = WorkflowTypeCategory.list_from_payload(payload)

        # Assert
        self.assertEqual(
            categories,
            [
                WorkflowTypeCategory(
                    name="Generation",
                    types=(WorkflowTypeOption(WorkflowType.ASSET_GENERATION, "Server description of the asset type."),),
                )
            ],
        )
        log_warn.assert_called_once()
        self.assertIn("Future Type", log_warn.call_args.args[0])

    async def test_list_from_payload_skips_blank_non_string_or_malformed_entries(self) -> None:
        """A blank value, a non-string value, or a non-dict entry is skipped instead of raising."""
        # Arrange
        payload = [{"name": "Other", "types": [{"value": ""}, {"value": 7}, {}, "not-a-dict", None]}]

        # Act
        with patch("lightspeed.trex.comfyui.core.models.carb.log_warn"):
            categories = WorkflowTypeCategory.list_from_payload(payload)

        # Assert
        self.assertEqual(categories, [WorkflowTypeCategory(name="Other", types=())])

    async def test_list_from_payload_returns_empty_list_for_non_list_payload(self) -> None:
        """A payload that is not a list of categories yields no category, not an error."""
        # Arrange
        cases = (None, {"categories": []}, "Generation")

        for payload in cases:
            with self.subTest(payload=payload):
                # Act
                categories = WorkflowTypeCategory.list_from_payload(payload)

                # Assert
                self.assertEqual(categories, [])

    async def test_list_from_payload_missing_description_reads_as_blank(self) -> None:
        """A type entry without a description reads as an empty string, not None."""
        # Arrange
        payload = [{"name": "Other", "types": [{"value": "Other"}]}]

        # Act
        categories = WorkflowTypeCategory.list_from_payload(payload)

        # Assert
        expected = [WorkflowTypeCategory(name="Other", types=(WorkflowTypeOption(WorkflowType.OTHER, ""),))]
        self.assertEqual(categories, expected)

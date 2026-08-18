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

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

import carb
import omni.usd
from lightspeed.trex.texture_replacements.core.shared.data_models import ReplaceTexturesRequestModel
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.flux.material_api import ShaderInfoAPI
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import commands, undo
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Tf, UsdShade

from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from lightspeed.trex.texture_replacements.core.shared.commands import REPLACE_TEXTURES_COMMAND, ReplaceTexturesCommand
from lightspeed.trex.texture_replacements.core.shared.data_models.models import TextureReplacement


_CONTEXT_NAME = "texture_replacements_core_e2e"
_TEST_DATA_EXTENSION = "lightspeed.trex.app.resources"
_TEST_STAGE = "usd/project_example/combined.usda"


class TestTextureReplacementsCoreE2E(AsyncTestCase):
    """Test texture replacement queries and authoring against a real USD project."""

    async def test_get_expected_texture_material_inputs_filters_authored_shader_inputs(self):
        """Texture type filters select the expected inputs from a real shader prim."""
        for texture_type, expected_attributes in (
            (None, sorted(set(TEXTURE_TYPE_INPUT_MAP.values()))),
            (TextureTypes.DIFFUSE, ["inputs:diffuse_texture"]),
        ):
            with self.subTest(title=f"texture_type={texture_type}"):
                # Open the real sample project and query its authored shader through the core.
                async with open_test_project(
                    _TEST_STAGE,
                    ext_name=_TEST_DATA_EXTENSION,
                    context_name=_CONTEXT_NAME,
                ):
                    context = omni.usd.get_context(_CONTEXT_NAME)
                    core = TextureReplacementsCore(_CONTEXT_NAME)
                    prim_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader"
                    expected_prim = context.get_stage().GetPrimAtPath(Sdf.Path(prim_path).GetPrimPath())
                    input_properties = []
                    for input_property in TEXTURE_TYPE_INPUT_MAP.values():
                        property_mock = Mock()
                        property_mock.GetName.return_value = input_property
                        input_properties.append(property_mock)

                    with (
                        patch.object(ShaderInfoAPI, "__init__", return_value=None) as initialize_shader_info,
                        patch.object(ShaderInfoAPI, "get_input_properties", return_value=input_properties),
                    ):
                        shader_inputs = await core.get_expected_texture_material_inputs(
                            prim_path,
                            texture_type=texture_type,
                        )

                    # The filter returns only authored inputs matching the requested semantic type.
                    self.assertEqual(initialize_shader_info.call_args, call(expected_prim))
                    self.assertEqual(
                        sorted(shader_input.split(".")[-1] for shader_input in shader_inputs),
                        expected_attributes,
                    )


_TRANSACTION_CONTEXT_NAME = "texture_replacements_transaction_e2e"


class TestTextureReplacementTransactionsE2E(AsyncTestCase):
    """Verify real USD authoring and transactional Kit command behavior."""

    async def setUp(self):
        """Create a real stage, layer, shader inputs, and replacement files."""
        self.context = omni.usd.get_context(_TRANSACTION_CONTEXT_NAME) or omni.usd.create_context(
            _TRANSACTION_CONTEXT_NAME
        )
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self.layer = self.stage.GetRootLayer()
        self.core = TextureReplacementsCore(_TRANSACTION_CONTEXT_NAME)
        shader = UsdShade.Shader.Define(self.stage, "/World/Shader")
        self.diffuse_input = shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset)
        self.normal_input = shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset)
        self.diffuse_path = str(self.diffuse_input.GetAttr().GetPath())
        self.normal_path = str(self.normal_input.GetAttr().GetPath())
        self.diffuse_original = "C:/missing/original_diffuse.dds"
        self.normal_original = "C:/missing/original_normal.dds"
        self.diffuse_input.Set(Sdf.AssetPath(self.diffuse_original))
        self.normal_input.Set(Sdf.AssetPath(self.normal_original))
        self.temporary_directory = TemporaryDirectory()  # pylint: disable=consider-using-with
        self.diffuse_replacement = Path(self.temporary_directory.name) / "diffuse.png"
        self.normal_replacement = Path(self.temporary_directory.name) / "normal.png"
        self.diffuse_replacement.touch()
        self.normal_replacement.touch()
        undo.clear_stack()

    async def tearDown(self):
        """Release the stage, files, core, and command history."""
        undo.clear_stack()
        self.core.destroy()
        self.temporary_directory.cleanup()
        if self.context.can_close_stage():
            await self.context.close_stage_async()
        omni.usd.destroy_context(_TRANSACTION_CONTEXT_NAME)

    def _force_replace_from_current_values(self, textures: list[tuple[str, str | Path | None]]) -> None:
        """Force one batch after confirming every current target-layer value."""
        expected = []
        for property_path, _ in textures:
            attribute_spec = self.layer.GetAttributeAtPath(property_path)
            value = attribute_spec.default if attribute_spec is not None else None
            expected.append((property_path, value.path if isinstance(value, Sdf.AssetPath) else value))
        self.core.replace_textures(
            textures,
            force=True,
            target_layer=self.layer,
            expected_current_textures=expected,
        )

    def _run_batch_with_second_mutation_failure(self) -> None:
        """Run two real replacements while injecting a deterministic second-mutation failure.

        Raises:
            RuntimeError: Always, before the second replacement is authored.
        """
        apply_replacement = ReplaceTexturesCommand._apply_replacement
        replacement_count = 0

        def fail_second_replacement(command, target_layer, replacement):
            """Apply the first replacement and fail the second.

            Args:
                command: Active replacement command.
                target_layer: Layer receiving the batch.
                replacement: Prepared replacement to apply.

            Returns:
                The first real mutation result.

            Raises:
                RuntimeError: For the second replacement.
            """
            nonlocal replacement_count
            replacement_count += 1
            if replacement_count == 2:
                raise RuntimeError("Injected second replacement failure")
            return apply_replacement(command, target_layer, replacement)

        with patch.object(
            ReplaceTexturesCommand, "_apply_replacement", autospec=True, side_effect=fail_second_replacement
        ):
            command = ReplaceTexturesCommand(
                replacements=[
                    TextureReplacement(
                        Sdf.Path(self.diffuse_path), str(self.diffuse_replacement), Sdf.ValueTypeNames.Asset
                    ),
                    TextureReplacement(
                        Sdf.Path(self.normal_path), str(self.normal_replacement), Sdf.ValueTypeNames.Asset
                    ),
                ],
                target_layer_identifier=self.layer.identifier,
                expected_replacements=[
                    TextureReplacement(
                        Sdf.Path(self.diffuse_path), self.diffuse_input.Get().path, Sdf.ValueTypeNames.Asset
                    ),
                    TextureReplacement(
                        Sdf.Path(self.normal_path), self.normal_input.Get().path, Sdf.ValueTypeNames.Asset
                    ),
                ],
            )
            command.do()

    async def test_forced_service_replacement_authors_without_shader_registry(self):
        """A forced service request authors a real input without source metadata or shader registry access."""
        # Build the validated service request from a confirmed current layer value.
        request = ReplaceTexturesRequestModel.model_construct(
            force=True,
            textures=[(self.diffuse_path, self.diffuse_replacement)],
            expected_current_textures=[(self.diffuse_path, self.diffuse_original)],
        )

        # Execute against the live stage while the shader registry is unavailable.
        with patch(
            "lightspeed.trex.texture_replacements.core.shared.data_models.validators.ShaderInfoAPI",
            side_effect=Tf.ErrorException("Shader registry unavailable"),
        ) as shader_info_api:
            self.core.replace_texture_with_data_models(request)

        self.assertEqual(self.diffuse_input.Get().path, str(self.diffuse_replacement))
        self.assertEqual(self.layer.GetAttributeAtPath(self.diffuse_path).default.path, str(self.diffuse_replacement))
        shader_info_api.assert_not_called()

    async def test_successful_replacement_is_one_undoable_user_action(self):
        """One undo restores the real authored value from a successful replacement batch."""
        # Apply through the core, then undo through Kit's real command stack.
        self._force_replace_from_current_values([(self.diffuse_path, self.diffuse_replacement)])

        undo_succeeded = undo.undo()

        self.assertTrue(undo_succeeded)
        self.assertEqual(self.diffuse_input.Get().path, self.diffuse_original)

    async def test_forced_replacement_accepts_resolved_baseline_for_relative_authored_value(self):
        """A discovered resolved path round-trips to the same relative authored opinion."""
        # Author a relative texture path in a file-backed edit layer.
        edit_layer_path = Path(self.temporary_directory.name) / "replacement.usda"
        edit_layer = Sdf.Layer.CreateNew(str(edit_layer_path))
        self.layer.subLayerPaths.append(edit_layer.identifier)
        self.stage.SetEditTarget(edit_layer)
        authored_value = "textures/original.dds"
        self.diffuse_input.Set(Sdf.AssetPath(authored_value))
        resolved_value = Sdf.ComputeAssetPathRelativeToLayer(edit_layer, authored_value)

        # Confirm with the resolved path returned to clients and apply a real replacement.
        self.core.replace_textures(
            [(self.diffuse_path, self.diffuse_replacement)],
            force=True,
            target_layer=edit_layer,
            expected_current_textures=[(self.diffuse_path, resolved_value)],
        )

        authored_replacement = edit_layer.GetAttributeAtPath(self.diffuse_path).default.path
        self.assertEqual(
            Path(Sdf.ComputeAssetPathRelativeToLayer(edit_layer, authored_replacement)),
            self.diffuse_replacement,
        )

    async def test_successful_replacement_redo_reapplies_the_batch(self):
        """Redo reapplies the complete replacement batch after undo."""
        # Apply two replacements as one action and return to their original values.
        self._force_replace_from_current_values(
            [
                (self.diffuse_path, self.diffuse_replacement),
                (self.normal_path, self.normal_replacement),
            ]
        )
        undo.undo()

        # Redo must replay the complete batch rather than only its final mutation.
        redo_succeeded = undo.redo()

        self.assertTrue(redo_succeeded)
        self.assertEqual(self.diffuse_input.Get().path, str(self.diffuse_replacement))
        self.assertEqual(self.normal_input.Get().path, str(self.normal_replacement))

    async def test_successful_replacement_undo_emits_one_change_notification(self):
        """Undo notifies listeners once with only the atomic parent command."""
        notifications = []

        def record_notification(command_names):
            """Record command names emitted by the Kit undo system.

            Args:
                command_names: Names included in one undo change notification.
            """
            notifications.append(tuple(command_names))

        # Observe the real Kit undo stack while a replacement is applied and undone.
        undo.subscribe_on_change(record_notification)
        try:
            self._force_replace_from_current_values([(self.diffuse_path, self.diffuse_replacement)])
            notifications.clear()

            undo_succeeded = undo.undo()
        finally:
            undo.unsubscribe_on_change(record_notification)

        self.assertTrue(undo_succeeded)
        self.assertEqual(notifications, [("ReplaceTexturesCommand",)])

    async def test_failed_batch_restores_every_authored_value(self):
        """A later mutation failure rolls every earlier mutation back to its baseline."""
        # Fail the second mutation after the first has touched the live layer.
        with self.assertRaises(RuntimeError):
            self._run_batch_with_second_mutation_failure()

        self.assertEqual(self.diffuse_input.Get().path, self.diffuse_original)
        self.assertEqual(self.normal_input.Get().path, self.normal_original)

    async def test_undo_reports_and_preserves_a_conflicting_direct_edit(self):
        """Undo reports rather than overwriting a same-property edit authored outside the command stack."""
        # Apply through the command stack, then author an external conflicting value.
        self._force_replace_from_current_values([(self.diffuse_path, self.diffuse_replacement)])
        conflicting_value = Sdf.AssetPath("C:/external/conflicting_diffuse.dds")
        self.diffuse_input.Set(conflicting_value)

        # Undo detects the newer opinion and leaves it untouched.
        with patch.object(carb, "log_error") as log_error:
            undo.undo()

        self.assertEqual(self.diffuse_input.Get(), conflicting_value)
        self.assertIn("Cannot undo texture replacements", log_error.call_args.args[0])

    async def test_redo_reports_and_preserves_a_conflicting_direct_edit(self):
        """Redo reports rather than overwriting a same-property edit authored outside the command stack."""
        # Undo a real replacement, then author a conflict before redo.
        self._force_replace_from_current_values([(self.diffuse_path, self.diffuse_replacement)])
        undo.undo()
        conflicting_value = Sdf.AssetPath("C:/external/conflicting_diffuse.dds")
        self.diffuse_input.Set(conflicting_value)

        # Redo detects the newer opinion and leaves it untouched.
        with patch.object(carb, "log_error") as log_error:
            undo.redo()

        self.assertEqual(self.diffuse_input.Get(), conflicting_value)
        self.assertIn(
            "Cannot redo texture replacements", "\n".join(call_.args[0] for call_ in log_error.call_args_list)
        )

    async def test_failed_batch_preserves_prior_undo_history(self):
        """A failed batch restores itself without disturbing an earlier action."""
        # Commit one successful action before injecting a later batch failure.
        self._force_replace_from_current_values([(self.diffuse_path, self.diffuse_replacement)])

        with self.assertRaises(RuntimeError):
            self._run_batch_with_second_mutation_failure()

        # The failed batch rolls back locally and the earlier action remains undoable.
        self.assertEqual(self.diffuse_input.Get().path, str(self.diffuse_replacement))
        self.assertEqual(self.normal_input.Get().path, self.normal_original)
        self.assertTrue(undo.undo())
        self.assertEqual(self.diffuse_input.Get().path, self.diffuse_original)

    async def test_removed_property_undo_restores_the_original_spec(self):
        """Undo restores a removed property and its original authored value."""
        # Remove a documented shader input through the replacement command.
        documentation = "Original diffuse texture input"
        self.diffuse_input.GetAttr().SetDocumentation(documentation)
        self._force_replace_from_current_values([(self.diffuse_path, None)])

        # Undo restores the complete property spec, including its metadata.
        undo_succeeded = undo.undo()

        self.assertTrue(undo_succeeded)
        self.assertIsNotNone(self.layer.GetAttributeAtPath(self.diffuse_path))
        self.assertEqual(self.diffuse_input.Get().path, self.diffuse_original)
        self.assertEqual(self.diffuse_input.GetAttr().GetDocumentation(), documentation)

    async def test_removal_preserves_a_preexisting_inert_ancestor_spec(self):
        """Removing a property's last opinion does not delete its preexisting ancestor over."""
        # Create an inert prim spec that predates the removable texture property.
        prim_path = Sdf.Path("/World/Unused")
        prim_spec = Sdf.CreatePrimInLayer(self.layer, prim_path)
        property_name = "inputs:diffuse_texture"
        property_path = prim_path.AppendProperty(property_name)
        attribute_spec = Sdf.AttributeSpec(prim_spec, property_name, Sdf.ValueTypeNames.Asset)
        attribute_spec.default = Sdf.AssetPath(self.diffuse_original)

        # Remove the property through the real command without pruning its ancestor.
        succeeded, _ = commands.execute(
            REPLACE_TEXTURES_COMMAND,
            replacements=[TextureReplacement(property_path, None, None)],
            target_layer_identifier=self.layer.identifier,
        )

        self.assertTrue(succeeded)
        self.assertIsNone(self.layer.GetAttributeAtPath(property_path))
        self.assertIsNotNone(self.layer.GetPrimAtPath(prim_path))

    async def test_force_restores_missing_original_path(self):
        """Force restores a recorded original texture opinion after its source disappears."""
        # Simulate an applied replacement whose original source no longer exists on disk.
        self.diffuse_input.Set(Sdf.AssetPath(str(self.diffuse_replacement)))
        undo.clear_stack()

        self.core.replace_textures(
            [(self.diffuse_path, self.diffuse_original)],
            force=True,
            target_layer=self.layer,
            expected_current_textures=[(self.diffuse_path, str(self.diffuse_replacement))],
        )

        self.assertEqual(self.diffuse_input.Get().path, self.diffuse_original)

    async def test_force_rejects_stale_expected_current_value_without_mutating(self):
        """Force cannot overwrite a target layer that differs from its confirmed baseline."""
        # Author a newer value than the stale baseline supplied by the caller.
        current_value = str(self.diffuse_replacement)
        self.diffuse_input.Set(Sdf.AssetPath(current_value))

        with self.assertRaisesRegex(ValueError, "differs from its expected current value"):
            self.core.replace_textures(
                [(self.diffuse_path, self.diffuse_original)],
                force=True,
                target_layer=self.layer,
                expected_current_textures=[(self.diffuse_path, "C:/stale/applied.dds")],
            )

        self.assertEqual(self.diffuse_input.Get().path, current_value)

    async def test_command_rejects_duplicate_targets_without_mutating(self):
        """Direct command dispatch cannot resolve duplicate targets by input order."""
        # Construct an ambiguous batch that addresses the same USD property twice.
        before = self.diffuse_input.Get()
        command = ReplaceTexturesCommand(
            replacements=[
                TextureReplacement(Sdf.Path(self.diffuse_path), "first.dds", Sdf.ValueTypeNames.Asset),
                TextureReplacement(Sdf.Path(self.diffuse_path), "second.dds", Sdf.ValueTypeNames.Asset),
            ],
            target_layer_identifier=self.layer.identifier,
        )

        with self.assertRaisesRegex(RuntimeError, "target paths must be unique"):
            command.do()

        self.assertEqual(self.diffuse_input.Get(), before)

    async def test_default_replacement_rejects_missing_source(self):
        """Normal replacement remains strict when a source texture is unavailable."""
        # Request a non-forced replacement whose source file is missing.
        current_value = str(self.diffuse_replacement)
        self.diffuse_input.Set(Sdf.AssetPath(current_value))

        with self.assertRaises(ValueError):
            self.core.replace_textures(
                [(self.diffuse_path, self.diffuse_original)],
                force=False,
                target_layer=self.layer,
            )

        self.assertEqual(self.diffuse_input.Get().path, current_value)

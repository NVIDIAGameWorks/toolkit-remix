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

__all__ = ["TestUsdAttributePreviewOwnership"]

import omni.kit.app
import omni.kit.commands
import omni.kit.test
import omni.kit.undo
import omni.usd
from omni.flux.property_widget_builder.model.usd.item_model.attr_value import UsdAttributeValueModel
from pxr import Sdf, Usd


def _create_value_model(stage, value):
    """Create a real float property and the production value model representing it.

    Args:
        stage: Stage that owns the test property.
        value: Original authored float value.

    Returns:
        Production value model bound to the test property.
    """
    attribute = stage.DefinePrim("/DragTestPrim").CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
    attribute.Set(value)
    return UsdAttributeValueModel("", [attribute.GetPath()], 0)


class TestUsdAttributePreviewOwnership(omni.kit.test.AsyncTestCase):
    """Exercise preview ownership through public value-model and USD APIs."""

    async def setUp(self):
        """Create an isolated in-memory stage for property editing workflows."""
        self.context = omni.usd.get_context("")
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        """Release command history and the temporary stage after every workflow."""
        omni.kit.undo.clear_stack()
        await self.context.close_stage_async()
        self.stage = None
        self.context = None

    async def test_undo_with_multiple_active_batches_restores_all_previews_before_previous_command(self):
        """Every batch cancels when one Undo dispatch reaches their shared command callbacks."""
        # Arrange
        first = _create_value_model(self.stage, value=3.0)
        prim = self.stage.DefinePrim("/OtherPreview")
        second_attribute = prim.CreateAttribute("value", Sdf.ValueTypeNames.Float)
        second_attribute.Set(4.0)
        prior_attribute = prim.CreateAttribute("prior", Sdf.ValueTypeNames.Float)
        prior_attribute.Set(1.0)
        second = UsdAttributeValueModel("", [second_attribute.GetPath()], 0)
        omni.kit.undo.clear_stack()
        omni.kit.commands.execute(
            "ChangeProperty", prop_path=prior_attribute.GetPath(), value=2.0, prev=1.0, usd_context_name=""
        )
        try:
            for model in (first, second):
                model.begin_batch_edit()
                model.set_value(7.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()

            # Act
            omni.kit.undo.undo()

            # Assert
            self.assertEqual(self.stage.GetAttributeAtPath(first.attribute_paths[0]).Get(), 3.0)
            self.assertEqual(second_attribute.Get(), 4.0)
            self.assertEqual(prior_attribute.Get(), 1.0)
            self.assertFalse(first.is_batch_editing)
            self.assertFalse(second.is_batch_editing)
        finally:
            first.destroy()
            second.destroy()

    async def test_external_command_after_published_preview_undo_redo_preserves_committed_history(self):
        """External command history excludes the preview canceled by that command."""
        for command_context, history_action in (
            ("", "undo"),
            ("", "redo"),
            (self.context, "undo"),
            (self.stage, "undo"),
        ):
            with self.subTest(command_context=command_context, history_action=history_action):
                # Arrange
                model = _create_value_model(self.stage, value=3.0)
                attribute = self.stage.GetAttributeAtPath(model.attribute_paths[0])
                omni.kit.undo.clear_stack()
                try:
                    model.begin_batch_edit()
                    model.set_value(7.0)
                    await omni.kit.app.get_app().next_update_async()
                    await omni.kit.app.get_app().next_update_async()
                    self.assertEqual(attribute.Get(), 7.0)
                    succeeded, _result = omni.kit.commands.execute(
                        "ChangeProperty",
                        prop_path=attribute.GetPath(),
                        value=9.0,
                        prev=None,
                        usd_context_name=command_context,
                    )
                    self.assertTrue(succeeded)
                    self.assertEqual(attribute.Get(), 9.0)
                    self.assertFalse(model.is_batch_editing)
                    if history_action == "redo":
                        omni.kit.undo.undo()

                    # Act
                    if history_action == "undo":
                        omni.kit.undo.undo()
                    else:
                        omni.kit.undo.redo()

                    # Assert
                    self.assertEqual(attribute.Get(), 3.0 if history_action == "undo" else 9.0)
                    self.assertEqual(omni.kit.undo.can_undo(), history_action == "redo")
                finally:
                    model.destroy()

    async def test_external_command_on_other_property_or_stage_preserves_active_preview(self):
        """Commands outside this property's stage leave its preview transaction active."""
        for other_stage in (False, True):
            with self.subTest(other_stage=other_stage):
                # Arrange
                model = _create_value_model(self.stage, value=3.0)
                attribute = self.stage.GetAttributeAtPath(model.attribute_paths[0])
                command_stage = Usd.Stage.CreateInMemory() if other_stage else self.stage
                external_attribute = command_stage.DefinePrim(
                    "/DragTestPrim" if other_stage else "/UnrelatedPrim"
                ).CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
                external_attribute.Set(4.0)
                omni.kit.undo.clear_stack()
                try:
                    model.begin_batch_edit()
                    model.set_value(7.0)
                    await omni.kit.app.get_app().next_update_async()
                    await omni.kit.app.get_app().next_update_async()

                    # Act
                    succeeded, _result = omni.kit.commands.execute(
                        "ChangeProperty",
                        prop_path=external_attribute.GetPath(),
                        value=9.0,
                        prev=None,
                        usd_context_name=command_stage,
                    )

                    # Assert
                    self.assertTrue(succeeded)
                    self.assertEqual(external_attribute.Get(), 9.0)
                    self.assertEqual(attribute.Get(), 7.0)
                    self.assertTrue(model.is_batch_editing)
                finally:
                    model.destroy()

    async def test_external_write_during_multi_target_preview_preserves_external_spec_and_restores_other_target(self):
        """External value and spec changes survive cancellation of other target previews."""
        for operation in ("default", "time_samples", "erase_time_samples", "type", "delete_attribute", "delete_prim"):
            with self.subTest(operation=operation):
                # Arrange
                first = _create_value_model(self.stage, value=3.0)
                first_path = first.attribute_paths[0]
                first_attribute = self.stage.GetAttributeAtPath(first_path)
                if operation == "erase_time_samples":
                    first_attribute.Set(5.0, Usd.TimeCode(1.0))
                second_attribute = self.stage.DefinePrim("/OtherPreview").CreateAttribute(
                    "value", Sdf.ValueTypeNames.Float
                )
                second_attribute.Set(4.0)
                model = UsdAttributeValueModel("", [first_path, second_attribute.GetPath()], 0)
                try:
                    model.begin_batch_edit()
                    model.set_value(7.0)
                    await omni.kit.app.get_app().next_update_async()
                    await omni.kit.app.get_app().next_update_async()

                    # Act
                    if operation == "default":
                        first_attribute.Set(9.0)
                    elif operation == "time_samples":
                        first_attribute.Set(9.0, Usd.TimeCode(1.0))
                    elif operation == "erase_time_samples":
                        self.stage.GetRootLayer().EraseTimeSample(first_path, 1.0)
                    elif operation == "type":
                        self.stage.GetRootLayer().GetPropertyAtPath(first_path).SetInfo("typeName", "double")
                    elif operation == "delete_attribute":
                        first_attribute.GetPrim().RemoveProperty(first_path.name)
                    else:
                        self.stage.RemovePrim(first_path.GetPrimPath())

                    # Assert
                    if operation.startswith("delete_"):
                        self.assertFalse(self.stage.GetAttributeAtPath(first_path).IsValid())
                    else:
                        self.assertEqual(first_attribute.Get(), 9.0 if operation == "default" else 3.0)
                        if operation == "time_samples":
                            self.assertEqual(first_attribute.Get(Usd.TimeCode(1.0)), 9.0)
                        if operation == "erase_time_samples":
                            self.assertEqual(first_attribute.GetTimeSamples(), [])
                        if operation == "type":
                            self.assertEqual(first_attribute.GetTypeName(), Sdf.ValueTypeNames.Double)
                    self.assertEqual(second_attribute.Get(), 4.0)
                    self.assertFalse(model.is_batch_editing)
                finally:
                    model.destroy()
                    first.destroy()
                    self.stage.RemovePrim(first_path.GetPrimPath())
                    self.stage.RemovePrim("/OtherPreview")

    async def test_external_metadata_during_preview_retains_metadata_and_restores_unreleased_value(self):
        """External metadata survives cancellation without retaining a preview-only default."""
        for authored_override in (False, True):
            with self.subTest(authored_override=authored_override):
                # Arrange
                weak_layer = Sdf.Layer.CreateAnonymous("preview_metadata.usda")
                self.stage.GetRootLayer().subLayerPaths.append(weak_layer.identifier)
                with Usd.EditContext(self.stage, weak_layer):
                    attribute = self.stage.DefinePrim("/MetadataPreview").CreateAttribute(
                        "value", Sdf.ValueTypeNames.Float
                    )
                    attribute.Set(3.0)
                if authored_override:
                    attribute.Set(3.0)
                model = UsdAttributeValueModel("", [attribute.GetPath()], 0)
                omni.kit.undo.clear_stack()
                try:
                    model.begin_batch_edit()
                    model.set_value(7.0)
                    await omni.kit.app.get_app().next_update_async()
                    await omni.kit.app.get_app().next_update_async()

                    # Act
                    attribute.SetDocumentation("Externally updated")

                    # Assert
                    self.assertEqual(attribute.GetDocumentation(), "Externally updated")
                    self.assertEqual(attribute.Get(), 3.0)
                    self.assertFalse(model.is_batch_editing)
                    self.assertFalse(omni.kit.undo.can_undo())
                finally:
                    model.destroy()
                    self.stage.RemovePrim("/MetadataPreview")
                    self.stage.GetRootLayer().subLayerPaths.remove(weak_layer.identifier)

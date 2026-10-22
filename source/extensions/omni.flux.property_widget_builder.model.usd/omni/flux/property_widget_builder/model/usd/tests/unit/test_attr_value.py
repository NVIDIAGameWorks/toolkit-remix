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

from contextlib import nullcontext
from unittest import mock

import omni.kit.test
from omni.flux.property_widget_builder.model.usd.item_model import attr_value
from pxr import Gf, Sdf

__all__ = ["TestUsdAttributeValueModel", "TestVirtualUsdAttributeValueModel"]


def _mock_context(value, *, attribute_valid=True):
    """Create mocked USD boundaries for one attribute value.

    Args:
        value: Composed attribute value returned by the USD boundary.
        attribute_valid: Whether the attribute already exists.

    Returns:
        Context, attribute, and editable layer mocks.
    """
    attribute = mock.MagicMock()
    attribute.Get.return_value = value
    attribute.GetPath.return_value = Sdf.Path("/ColorTest.color")
    attribute.GetName.return_value = "color"
    attribute.IsHidden.return_value = False
    attribute.IsValid.return_value = attribute_valid
    attribute.HasAuthoredValue.return_value = True
    prim = mock.MagicMock()
    prim.IsValid.return_value = True
    prim.GetAttribute.return_value = attribute
    layer = mock.MagicMock(permissionToEdit=True)
    stage = mock.MagicMock()
    stage.GetPrimAtPath.return_value = prim
    stage.GetEditTarget.return_value.GetLayer.return_value = layer
    context = mock.MagicMock()
    context.get_stage.return_value = stage
    return context, attribute, layer


class TestUsdAttributeValueModel(omni.kit.test.AsyncTestCase):
    """Test whole-color conversion at the outgoing command boundary."""

    async def test_set_value_color_vector_or_tuple_sends_matching_usd_vector_without_warning(self):
        """Convert both color input forms to the declared precision and dimension."""
        for color_type, vector_type, dimension in (
            (Sdf.ValueTypeNames.Color3d, Gf.Vec3d, 3),
            (Sdf.ValueTypeNames.Color3f, Gf.Vec3f, 3),
            (Sdf.ValueTypeNames.Color3h, Gf.Vec3h, 3),
            (Sdf.ValueTypeNames.Color4d, Gf.Vec4d, 4),
            (Sdf.ValueTypeNames.Color4f, Gf.Vec4f, 4),
            (Sdf.ValueTypeNames.Color4h, Gf.Vec4h, 4),
        ):
            for input_kind in ("vector", "tuple"):
                with self.subTest(title=f"{color_type}: {input_kind}"):
                    # Arrange
                    components = (0.125, 0.25, 0.5, 0.75)[:dimension]
                    expected_value = vector_type(*components)
                    input_value = expected_value if input_kind == "vector" else components
                    context, attribute, layer = _mock_context(vector_type(0.0))
                    with (
                        mock.patch.object(attr_value.omni.usd, "get_context", return_value=context),
                        mock.patch.object(
                            attr_value.omni.usd, "find_spec_on_session_or_its_sublayers", return_value=(layer, None)
                        ),
                        mock.patch.object(attr_value, "_defer_usd_notices", side_effect=lambda _: nullcontext()),
                        mock.patch.object(
                            attr_value.omni.kit.commands, "execute", return_value=(True, None)
                        ) as execute,
                        mock.patch.object(attr_value.carb, "log_warn") as log_warning,
                    ):
                        model = attr_value.UsdAttributeValueModel(
                            "color_context", [attribute.GetPath()], 0, value_type_name=color_type
                        )

                        # Act
                        model.set_value(input_value)

                        # Assert
                        execute.assert_called_once_with(
                            "ChangeProperty",
                            prop_path="/ColorTest.color",
                            value=expected_value,
                            target_layer=layer,
                            prev=None,
                            usd_context_name="color_context",
                        )
                        self.assertIsInstance(execute.call_args.kwargs["value"], vector_type)
                        log_warning.assert_not_called()


class TestVirtualUsdAttributeValueModel(omni.kit.test.AsyncTestCase):
    """Test failed custom creation rollback without a live stage or Undo history."""

    async def test_end_batch_edit_custom_creation_error_rolls_back_only_failed_group_and_closes_batch(self):
        """Propagate custom creation failure while requesting rollback and releasing batch listeners."""
        # Arrange
        context, attribute, layer = _mock_context(None, attribute_valid=False)
        final_value = Gf.Vec3f(0.8, 0.2, 0.2)
        failure = RuntimeError("Custom color setup failed")
        listener = mock.Mock()
        command_callbacks = [object(), object(), object()]
        event_loop = mock.Mock()
        prior_command = object()
        failed_group = object()

        def create_color_then_fail(target_attribute, value):
            """Request color and companion setup commands before reporting creation failure."""
            for name, value_type, authored_value in (
                ("color", Sdf.ValueTypeNames.Color3f, value),
                ("custom_color_setup", Sdf.ValueTypeNames.Bool, True),
            ):
                attr_value.omni.kit.commands.execute(
                    "CreateUsdAttributeCommand",
                    prim=context.get_stage().GetPrimAtPath(target_attribute.GetPath().GetPrimPath()),
                    attr_name=name,
                    attr_type=value_type,
                    attr_value=authored_value,
                )
            raise failure

        with (
            mock.patch.object(attr_value.omni.usd, "get_context", return_value=context),
            mock.patch.object(attr_value.omni.usd, "find_spec_on_session_or_its_sublayers", return_value=(layer, None)),
            mock.patch.object(attr_value, "_defer_usd_notices", side_effect=lambda _: nullcontext()),
            mock.patch.object(attr_value.Sdf, "ChangeBlock", side_effect=nullcontext),
            mock.patch.object(attr_value.Tf.Notice, "Register", return_value=listener),
            mock.patch.object(attr_value.omni.kit.commands, "register_callback", side_effect=command_callbacks),
            mock.patch.object(attr_value.asyncio, "get_event_loop", return_value=event_loop),
            mock.patch.object(attr_value.omni.kit.commands, "execute", return_value=(True, None)) as execute,
            mock.patch.object(
                attr_value.omni.kit.undo,
                "get_undo_stack",
                side_effect=([prior_command], [prior_command, failed_group]),
            ) as get_undo_stack,
            mock.patch.object(attr_value.omni.kit.undo, "undo", return_value=True) as undo,
            mock.patch.object(attr_value.omni.kit.undo, "group") as undo_group,
        ):
            model = attr_value.VirtualUsdAttributeValueModel(
                "color_context",
                [attribute.GetPath()],
                0,
                Sdf.ValueTypeNames.Color3f,
                default_value=Gf.Vec3f(0.2),
                create_callback=create_color_then_fail,
            )
            model.begin_batch_edit()
            model.set_value(final_value)
            preview_command_count = execute.call_count

            # Act
            with self.assertRaisesRegex(RuntimeError, "Custom color setup failed") as raised:
                model.end_batch_edit()

            # Assert
            self.assertIs(raised.exception, failure)
            self.assertEqual(preview_command_count, 0)
            self.assertEqual(
                [(call.args[0], call.kwargs["attr_name"]) for call in execute.call_args_list],
                [("CreateUsdAttributeCommand", "color"), ("CreateUsdAttributeCommand", "custom_color_setup")],
            )
            undo.assert_called_once_with()
            self.assertEqual(get_undo_stack.call_count, 2)
            self.assertEqual(undo_group.call_args_list, [mock.call(remove_if_empty=True)] * 2)
            self.assertFalse(model.is_batch_editing)
            listener.Revoke.assert_called_once_with()
            self.assertEqual(
                event_loop.call_soon.call_args_list,
                [
                    mock.call(attr_value.omni.kit.commands.unregister_callback, callback)
                    for callback in command_callbacks
                ],
            )

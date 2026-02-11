"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import asyncio
from unittest.mock import Mock, call, patch

import omni.kit.commands
import omni.kit.test
import omni.usd
from omni.flux.utils.material_converter import MaterialConverterCore
from omni.flux.utils.material_converter.base.attribute_base import AttributeBase
from omni.flux.utils.material_converter.base.converter_base import ConverterBase
from omni.flux.utils.material_converter.base.converter_builder_base import ConverterBuilderBase
from pxr import Sdf, Usd


class TestConverterBuilder(ConverterBuilderBase):
    def build(self, input_material_prim: Usd.Prim, output_mdl_subidentifier: str) -> ConverterBase:
        attributes = [
            AttributeBase(
                input_attr_name="inputs:flip_tangent_v",
                output_attr_name="inputs:encoding",
                output_default_value=3,
                translate_fn=self._convert_test,
                translate_alt_fn=self._convert_test_alt,
            ),
        ]
        return ConverterBase(
            input_material_prim=input_material_prim,
            output_mdl_subidentifier=output_mdl_subidentifier,
            attributes=attributes,
        )

    def _convert_test(self, value: bool, input_attr: Usd.Attribute) -> int:
        return value * 2

    def _convert_test_alt(
        self, _: Sdf.ValueTypeNames, value: bool, input_attr: Usd.Attribute | None
    ) -> tuple[Sdf.ValueTypeNames, int]:
        return (Sdf.ValueTypeNames.Int, value * 2)


class TestCore(omni.kit.test.AsyncTestCase):
    async def test_convert_no_context_should_quick_return_error_and_message(self):
        # Arrange
        context_name_mock = Mock()

        with patch.object(omni.usd, "get_context") as get_context_mock:
            get_context_mock.return_value = None

            # Act
            success, message, was_skipped = await MaterialConverterCore.convert(context_name_mock, Mock())

        # Assert
        self.assertFalse(success)
        self.assertFalse(was_skipped)
        self.assertEqual(f"Unable to get the context with name {context_name_mock}", message)

        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name_mock), get_context_mock.call_args)

    async def test_convert_no_stage_should_quick_return_error_and_message(self):
        # Arrange
        context_name_mock = Mock()
        context_mock = Mock()
        context_mock.get_stage.return_value = None

        with patch.object(omni.usd, "get_context") as get_context_mock:
            get_context_mock.return_value = context_mock

            # Act
            success, message, was_skipped = await MaterialConverterCore.convert(context_name_mock, Mock())

        # Assert
        self.assertFalse(success)
        self.assertFalse(was_skipped)
        self.assertEqual(f"Unable to get the stage in context with name {context_name_mock}", message)

        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name_mock), get_context_mock.call_args)

    async def test_convert_no_prim_spec_should_return_success_and_skip_message(self):
        # Arrange
        context_name_mock = Mock()

        root_layer_mock = Mock()
        root_layer_identifier_mock = Mock()
        root_layer_mock.GetPrimAtPath.return_value = None
        root_layer_mock.identifier = root_layer_identifier_mock

        stage_mock = Mock()
        stage_mock.GetRootLayer.return_value = root_layer_mock

        context_mock = Mock()
        context_mock.get_stage.return_value = stage_mock

        with patch.object(omni.usd, "get_context") as get_context_mock:
            get_context_mock.return_value = context_mock

            # Act
            success, message, was_skipped = await MaterialConverterCore.convert(context_name_mock, Mock())

        # Assert
        self.assertTrue(success)
        self.assertTrue(was_skipped)
        self.assertEqual(f"Input material prim was not defined on layer: '{root_layer_identifier_mock}'", message)

        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name_mock), get_context_mock.call_args)

    async def test_convert_no_output_shader_prim_should_return_error_and_message(self):
        # Arrange
        context_name_mock = Mock()

        root_prim_path = "/RootNodeTest"

        root_prim_mock = Mock()
        root_prim_mock.path = root_prim_path

        root_layer_mock = Mock()
        root_layer_identifier_mock = Mock()
        root_layer_mock.GetPrimAtPath.return_value = Mock()
        root_layer_mock.identifier = root_layer_identifier_mock
        root_layer_mock.rootPrims = [root_prim_mock]

        stage_mock = Mock()
        stage_mock.GetRootLayer.return_value = root_layer_mock

        context_mock = Mock()
        context_mock.get_stage.return_value = stage_mock

        input_material_prim_mock = Mock()
        input_material_name_mock = "MaterialName"  # Need a real value to have a valid Sdf.Path
        input_material_prim_mock.GetName.return_value = input_material_name_mock
        input_material_path_mock = Sdf.Path(f"{root_prim_path}/Looks/{input_material_name_mock}")
        input_material_next_path_mock = Sdf.Path(f"{root_prim_path}/Looks/{input_material_name_mock}_1")
        input_material_prim_mock.GetPath.return_value = input_material_path_mock

        input_shader_mock = Mock()
        input_shader_prim_mock = Mock()
        input_shader_mock.GetPrim.return_value = input_shader_prim_mock

        converter_mock = Mock()
        converter_mock.input_material_prim = input_material_prim_mock

        with (
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(omni.usd, "get_stage_next_free_path") as get_free_path_mock,
            patch.object(omni.usd, "get_shader_from_material") as get_shader_mock,
            patch.object(MaterialConverterCore, "_create_material_definition_prim") as create_definition_mock,
        ):
            get_context_mock.return_value = context_mock
            get_free_path_mock.return_value = input_material_next_path_mock
            get_shader_mock.return_value = input_shader_mock
            create_definition_mock.return_value = None

            # Act
            success, message, was_skipped = await MaterialConverterCore.convert(context_name_mock, converter_mock)

        # Assert
        self.assertFalse(success)
        self.assertFalse(was_skipped)
        self.assertEqual("Unable to fetch output material shader prim", message)

        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name_mock), get_context_mock.call_args)

        self.assertEqual(1, get_free_path_mock.call_count)
        self.assertEqual(call(stage_mock, input_material_path_mock, False), get_free_path_mock.call_args)

        self.assertEqual(1, get_shader_mock.call_count)
        self.assertEqual(call(input_material_prim_mock, get_prim=False), get_shader_mock.call_args)

        self.assertEqual(1, create_definition_mock.call_count)
        self.assertEqual(
            call(context_name_mock, converter_mock, input_material_next_path_mock), create_definition_mock.call_args
        )

    async def test_convert_has_source_prop_spec_should_create_material_definition_and_fix_connections_and_return_success_and_success_message(
        self,
    ):
        await self.__run_convert_has_source_prop_spec(True)

    async def test_convert_does_not_have_source_prop_spec_should_create_material_override_and_set_specifier_and_return_success_and_success_message(
        self,
    ):
        await self.__run_convert_has_source_prop_spec(False)

    async def test_create_material_definition_prim_should_create_mdl_material_prim_and_return_material_shader(self):
        # Arrange
        output_path_mock = Mock()
        output_prim_mock = Mock()
        context_name_mock = Mock()
        shader_mock = Mock()

        converter_mock = Mock()
        output_subidentifier = "TestSubidentifier"
        converter_mock.output_mdl_subidentifier = output_subidentifier

        stage_mock = Mock()
        stage_mock.GetPrimAtPath.return_value = output_prim_mock

        with (
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(omni.kit.commands, "execute") as command_mock,
            patch.object(omni.usd, "get_shader_from_material") as get_shader_mock,
        ):
            get_context_mock.return_value.get_stage.return_value = stage_mock
            get_shader_mock.return_value = shader_mock

            # Act
            val = MaterialConverterCore._create_material_definition_prim(
                context_name_mock, converter_mock, output_path_mock
            )

        # Assert
        self.assertEqual(shader_mock, val)

        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name_mock), get_context_mock.call_args)

        self.assertEqual(1, command_mock.call_count)
        self.assertEqual(
            call(
                "CreateMdlMaterialPrim",
                mtl_url=output_subidentifier + ".mdl",
                mtl_name=output_subidentifier,
                mtl_path=output_path_mock,
                stage=stage_mock,
                context_name=context_name_mock,
            ),
            command_mock.call_args,
        )

        self.assertEqual(1, get_shader_mock.call_count)
        self.assertEqual(call(output_prim_mock, get_prim=True), get_shader_mock.call_args)

    async def test_create_material_override_prim_should_create_empty_material_prim_and_empty_shader_prim_and_return_shader_prim(
        self,
    ):
        # Arrange
        output_material_path_mock = Mock()
        output_shader_path_mock = Mock()
        context_name_mock = Mock()
        shader_mock = Mock()

        stage_mock = Mock()
        stage_mock.GetPrimAtPath.return_value = shader_mock

        with (
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(omni.kit.commands, "execute") as command_mock,
        ):
            get_context_mock.return_value.get_stage.return_value = stage_mock

            # Act
            val = MaterialConverterCore._create_material_override_prim(
                context_name_mock, output_material_path_mock, output_shader_path_mock
            )

        # Assert
        self.assertEqual(shader_mock, val)

        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name_mock), get_context_mock.call_args)

        self.assertEqual(2, command_mock.call_count)
        self.assertEqual(
            call(
                "CreatePrimCommand",
                prim_path=output_material_path_mock,
                prim_type="Material",
                select_new_prim=False,
                context_name=context_name_mock,
            ),
            command_mock.call_args_list[0],
        )
        self.assertEqual(
            call(
                "CreatePrimCommand",
                prim_path=output_shader_path_mock,
                prim_type="Shader",
                select_new_prim=False,
                context_name=context_name_mock,
            ),
            command_mock.call_args_list[1],
        )

    async def test_convert_material_attributes_should_set_output_attr_if_exists_on_input_spec(self):
        await self.__run_convert_material_attributes(True)

    async def test_convert_material_attributes_should_set_default_value_on_output_attr_if_does_not_exist_on_input(self):
        await self.__run_convert_material_attributes(False)

    async def test_create_material_attributes_should_create_output_attr_if_exists_on_input_spec(self):
        await self.__run_create_material_attributes(True)

    async def test_create_material_attributes_should_create_default_value_on_output_attr_if_does_not_exist_on_input(
        self,
    ):
        await self.__run_create_material_attributes(False)

    async def __run_convert_has_source_prop_spec(self, has_prop_spec: bool):
        # Arrange
        context_name_mock = Mock()

        root_prim_path = "/RootNodeTest"

        root_prim_mock = Mock()
        root_prim_mock.path = root_prim_path

        prim_spec_mock = Mock()

        root_layer_mock = Mock()
        root_layer_identifier_mock = Mock()
        root_layer_mock.GetPrimAtPath.return_value = prim_spec_mock
        root_layer_mock.identifier = root_layer_identifier_mock
        root_layer_mock.rootPrims = [root_prim_mock]
        root_layer_mock.GetPropertyAtPath.return_value = Mock() if has_prop_spec else None

        input_material_prim_mock = Mock()
        input_material_name_mock = "InputMaterialName"
        input_material_path_mock = Sdf.Path(f"{root_prim_path}/Looks/{input_material_name_mock}")
        input_material_path_next_mock = Sdf.Path(f"{root_prim_path}/Looks/{input_material_name_mock}_1")
        input_material_prim_mock.GetPath.return_value = input_material_path_mock

        connection_mock = Mock()
        connection_prim_name_mock = "ConnectionPrimName"
        connection_name_mock = "ConnectionName"
        connection_mock.GetPrimPath.return_value.GetParentPath.return_value = input_material_path_mock
        connection_mock.GetPrimPath.return_value.name = connection_prim_name_mock
        connection_mock.name = connection_name_mock

        final_attr_mock = Mock()
        add_connection_mock = final_attr_mock.AddConnection
        remove_connection_mock = final_attr_mock.RemoveConnection
        final_attr_mock.GetConnections.return_value = [connection_mock]
        final_attr_mock.GetName.return_value = "output:test_output"

        final_material_prim_mock = Mock()
        final_material_prim_mock.GetAttributes.return_value = [final_attr_mock]

        stage_mock = Mock()
        stage_mock.GetRootLayer.return_value = root_layer_mock
        stage_mock.GetPrimAtPath.return_value = final_material_prim_mock

        context_mock = Mock()
        context_mock.get_stage.return_value = stage_mock

        input_shader_prim_mock = Mock()
        input_shader_prim_name = "InputShaderName"
        input_shader_prim_mock.GetPath.return_value.name = input_shader_prim_name

        output_shader_prim_mock = Mock()

        input_shader_mock = Mock()
        input_shader_mock.GetPrim.return_value = input_shader_prim_mock
        input_shader_mock.GetName.return_value = "Shader"

        converter_mock = Mock()
        converter_mock.input_material_prim = input_material_prim_mock

        create_attributes_future = asyncio.Future()
        create_attributes_future.set_result(None)

        with (
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(omni.usd, "get_stage_next_free_path") as get_free_path_mock,
            patch.object(omni.usd, "get_shader_from_material") as get_shader_mock,
            patch.object(MaterialConverterCore, "_create_material_definition_prim") as create_definition_mock,
            patch.object(MaterialConverterCore, "_create_material_override_prim") as create_override_mock,
            patch.object(MaterialConverterCore, "_create_material_attributes") as create_attributes_mock,
            patch.object(omni.kit.commands, "execute") as command_mock,
        ):
            get_context_mock.return_value = context_mock
            get_free_path_mock.return_value = input_material_path_next_mock
            get_shader_mock.return_value = input_shader_mock
            create_definition_mock.return_value = output_shader_prim_mock if has_prop_spec else None
            create_override_mock.return_value = None if has_prop_spec else output_shader_prim_mock
            create_attributes_mock.return_value = create_attributes_future

            # Act
            success, message, was_skipped = await MaterialConverterCore.convert(context_name_mock, converter_mock)

        # Assert
        self.assertTrue(success)
        self.assertFalse(was_skipped)
        self.assertEqual(
            f"Completed prim '{final_material_prim_mock.GetPath()}' conversion on layer {root_layer_identifier_mock}",
            message,
        )

        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name_mock), get_context_mock.call_args)

        self.assertEqual(1, get_free_path_mock.call_count)
        self.assertEqual(call(stage_mock, input_material_path_mock, False), get_free_path_mock.call_args)

        self.assertEqual(1 if has_prop_spec else 0, create_definition_mock.call_count)
        self.assertEqual(0 if has_prop_spec else 1, create_override_mock.call_count)

        if has_prop_spec:
            self.assertEqual(
                call(context_name_mock, converter_mock, input_material_path_next_mock), create_definition_mock.call_args
            )
        else:
            self.assertEqual(
                call(
                    context_name_mock,
                    input_material_path_next_mock,
                    f"{input_material_path_next_mock}/{input_shader_prim_name}",
                ),
                create_override_mock.call_args,
            )

        self.assertEqual(1, create_attributes_mock.call_count)
        self.assertEqual(
            call(context_name_mock, converter_mock, input_shader_prim_mock, output_shader_prim_mock),
            create_attributes_mock.call_args,
        )

        self.assertEqual(1, command_mock.call_count)
        self.assertEqual(
            call(
                "RemovePrimSpecCommand",
                layer_identifier=root_layer_identifier_mock,
                prim_spec_path=input_material_path_mock,
                usd_context=context_name_mock,
            ),
            command_mock.call_args,
        )

        self.assertEqual(1 if has_prop_spec else 0, add_connection_mock.call_count)
        self.assertEqual(1 if has_prop_spec else 0, remove_connection_mock.call_count)
        if has_prop_spec:
            self.assertEqual(
                call(
                    f"{root_prim_path}/Looks/{input_material_name_mock}/{connection_prim_name_mock}."
                    f"{connection_name_mock}"
                ),
                add_connection_mock.call_args,
            )
            self.assertEqual(call(connection_mock), remove_connection_mock.call_args)
        else:
            self.assertEqual(Sdf.SpecifierOver, prim_spec_mock.specifier)

    async def __run_convert_material_attributes(self, exists_on_input: bool):
        # Arrange
        def test_translate_fn(v, _):
            return 2 * v

        context_name_mock = Mock()

        input_attr_name_mock = Mock()
        output_attr_name_mock = Mock()
        output_default_value_mock = Mock()

        input_attr_spec_mock = Mock()

        input_attr_path_mock = Mock()
        input_attr_mock = Mock()
        input_value = 2
        input_attr_mock.GetPath.return_value = input_attr_path_mock
        input_attr_mock.Get.return_value = input_value

        attribute_mock = Mock()
        attribute_mock.input_attr_name = input_attr_name_mock
        attribute_mock.output_attr_name = output_attr_name_mock
        attribute_mock.output_default_value = output_default_value_mock
        attribute_mock.translate_fn.side_effect = test_translate_fn

        attributes_mock = [Mock(), Mock(), attribute_mock]

        converter_mock = Mock()
        converter_mock.attributes = attributes_mock

        output_attr_mock = Mock()
        output_attr_path_mock = Mock()
        output_attr_mock.IsValid.side_effect = [False, True, True]
        output_attr_mock.GetPath.return_value = output_attr_path_mock

        output_shader_prim_mock = Mock()
        output_shader_prim_mock.GetAttribute.return_value = output_attr_mock

        input_shader_prim_mock = Mock()
        input_shader_prim_mock.HasAttribute.side_effect = [True, exists_on_input]
        input_shader_prim_mock.GetAttribute.return_value = input_attr_mock

        root_layer_mock = Mock()
        get_attribute_at_path_mock = root_layer_mock.GetAttributeAtPath
        get_attribute_at_path_mock.side_effect = [None, input_attr_spec_mock]

        context_mock = Mock()
        context_mock.get_stage.return_value.GetRootLayer.return_value = root_layer_mock

        with (
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(omni.kit.commands, "execute") as command_mock,
        ):
            get_context_mock.return_value = context_mock

            # Act
            await MaterialConverterCore._convert_material_attributes(
                context_name_mock, converter_mock, input_shader_prim_mock, output_shader_prim_mock
            )

        # Assert
        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name_mock), get_context_mock.call_args)

        self.assertEqual(2 if exists_on_input else 1, get_attribute_at_path_mock.call_count)
        self.assertEqual(call(input_attr_path_mock), get_attribute_at_path_mock.call_args_list[0])
        if exists_on_input:
            self.assertEqual(call(input_attr_path_mock), get_attribute_at_path_mock.call_args_list[1])

        self.assertEqual(1, command_mock.call_count)
        self.assertEqual(
            (
                call(
                    "ChangePropertyCommand",
                    prop_path=output_attr_path_mock,
                    value=test_translate_fn(input_value, None),
                    prev=None,
                    target_layer=root_layer_mock,
                    usd_context_name=context_name_mock,
                )
                if exists_on_input
                else call(
                    "ChangePropertyCommand",
                    prop_path=output_attr_path_mock,
                    value=output_default_value_mock,
                    prev=None,
                    target_layer=root_layer_mock,
                    usd_context_name=context_name_mock,
                )
            ),
            command_mock.call_args,
        )

    async def __run_create_material_attributes(self, exists_on_input: bool):
        # Arrange
        def test_translate_alt_fn(_, v, __):
            return Sdf.ValueTypeNames.Int, 2 * v if v else None

        context_name_mock = Mock()

        input_attr_name_mock = Mock()
        output_attr_name_mock = Mock()
        output_default_value_mock = Mock()

        input_attr_spec_mock = Mock()

        input_attr_path_mock = Mock()
        input_attr_mock = Mock()
        input_type = Sdf.ValueTypeNames.Asset
        input_value = 2
        input_attr_mock.GetPath.return_value = input_attr_path_mock
        input_attr_mock.GetTypeName.return_value = input_type
        input_attr_mock.Get.return_value = input_value

        attribute_mock = Mock()
        attribute_mock.input_attr_name = input_attr_name_mock
        attribute_mock.output_attr_name = output_attr_name_mock
        attribute_mock.output_default_value = output_default_value_mock
        attribute_mock.translate_alt_fn.side_effect = test_translate_alt_fn

        attributes_mock = [Mock(), attribute_mock]

        converter_mock = Mock()
        converter_mock.attributes = attributes_mock

        output_shader_prim_mock = Mock()
        output_attr_path_mock = Mock()
        output_shader_prim_mock.GetPath.return_value.AppendProperty.return_value = output_attr_path_mock

        input_shader_prim_mock = Mock()
        input_shader_prim_mock.HasAttribute.side_effect = [True, exists_on_input, False]
        input_shader_prim_mock.GetAttribute.return_value = input_attr_mock

        root_layer_mock = Mock()
        session_layer_mock = Mock()
        get_attribute_at_path_mock = root_layer_mock.GetAttributeAtPath
        get_attribute_at_path_mock_session = session_layer_mock.GetAttributeAtPath
        get_attribute_at_path_mock.side_effect = [None, input_attr_spec_mock]
        get_attribute_at_path_mock_session.side_effect = [None, input_attr_spec_mock]

        with (
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(omni.kit.commands, "execute") as command_mock,
        ):
            get_context_mock.return_value.get_stage.return_value.GetRootLayer.return_value = root_layer_mock
            get_context_mock.return_value.get_stage.return_value.GetSessionLayer.return_value = session_layer_mock

            # Act
            await MaterialConverterCore._create_material_attributes(
                context_name_mock, converter_mock, input_shader_prim_mock, output_shader_prim_mock
            )

        # Assert
        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name_mock), get_context_mock.call_args)

        self.assertEqual(2 if exists_on_input else 1, get_attribute_at_path_mock.call_count)
        self.assertEqual(call(input_attr_path_mock), get_attribute_at_path_mock.call_args_list[0])
        if exists_on_input:
            self.assertEqual(call(input_attr_path_mock), get_attribute_at_path_mock.call_args_list[1])

        expected_type, epected_value = test_translate_alt_fn(input_type, input_value, None)

        self.assertEqual(1, command_mock.call_count)
        self.assertEqual(
            (
                call(
                    "ChangePropertyCommand",
                    prop_path=str(output_attr_path_mock),
                    value=epected_value,
                    prev=None,
                    target_layer=root_layer_mock,
                    type_to_create_if_not_exist=expected_type,
                    usd_context_name=context_name_mock,
                )
                if exists_on_input
                else call(
                    "ChangePropertyCommand",
                    prop_path=str(output_attr_path_mock),
                    value=output_default_value_mock,
                    prev=None,
                    target_layer=root_layer_mock,
                    type_to_create_if_not_exist=expected_type,
                    usd_context_name=context_name_mock,
                )
            ),
            command_mock.call_args,
        )

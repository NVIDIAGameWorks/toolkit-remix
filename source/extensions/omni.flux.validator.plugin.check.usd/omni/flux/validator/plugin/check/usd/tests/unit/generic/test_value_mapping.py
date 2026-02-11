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

from unittest.mock import Mock, call, patch

import omni.kit.commands
import omni.kit.test
from omni.flux.validator.plugin.check.usd.generic.value_mapping import AttributeMapping, Operator, ValueMapping
from pxr import Sdf, Usd, UsdShade


class TestValueMappingUnit(omni.kit.test.AsyncTestCase):
    async def test_not_empty_attribute_name_empty_should_raise_value_error(self):
        # Arrange
        pass

        # Act
        with self.assertRaises(ValueError) as cm_0:
            ValueMapping.Data.not_empty_attribute_name({"   ": {}})
        with self.assertRaises(ValueError) as cm_1:
            ValueMapping.Data.not_empty_attribute_name({None: {}})

        # Assert
        self.assertEqual("Attribute name cannot be empty", str(cm_0.exception))
        self.assertEqual("Attribute name cannot be empty", str(cm_1.exception))

    async def test_not_empty_attribute_name_not_empty_should_return_value(self):
        # Arrange
        input_val = {"AttrName": {}}

        # Act
        val = ValueMapping.Data.not_empty_attribute_name(input_val)

        # Assert
        self.assertEqual(input_val, val)

    async def test_input_output_same_type_not_same_should_raise_value_error(self):
        # Arrange
        mapping = AttributeMapping.construct()
        mapping.input_value = 0.1
        mapping.output_value = "A"

        # Act
        with self.assertRaises(ValueError) as cm:
            ValueMapping.Data.input_output_same_type({"Test": [mapping]})

        # Assert
        self.assertEqual("Input and Output value types do not match for mapping -> 0", str(cm.exception))

    async def test_input_output_same_type_same_should_return_value(self):
        # Arrange
        mapping = AttributeMapping.construct()
        mapping.input_value = 0.1
        mapping.output_value = 2.0

        input_val = {"Test": [mapping]}

        # Act
        val = ValueMapping.Data.input_output_same_type(input_val)

        # Assert
        self.assertEqual(input_val, val)

    async def test_iterable_input_output_same_length_not_same_should_raise_value_error(self):
        # Arrange
        mapping = AttributeMapping.construct()
        mapping.input_value = ["a", "b"]
        mapping.output_value = ["A", "B", "C"]

        # Act
        with self.assertRaises(ValueError) as cm:
            ValueMapping.Data.iterable_input_output_same_length({"Test": [mapping]})

        # Assert
        self.assertEqual("Input and Output values do not have the same number of items -> 0", str(cm.exception))

    async def test_iterable_input_output_same_length_same_should_return_value(self):
        # Arrange
        mapping = AttributeMapping.construct()
        mapping.input_value = ["a", "b", "c"]
        mapping.output_value = ["A", "B", "C"]

        input_val = {"Test": [mapping]}

        # Act
        val = ValueMapping.Data.iterable_input_output_same_length(input_val)

        # Assert
        self.assertEqual(input_val, val)

    async def test_check_no_selector_data_should_skip_check(self):
        # Arrange
        emissive_intensity = ValueMapping()

        with patch.object(ValueMapping, "on_progress") as progress_mock:
            # Act
            success, message, data = await emissive_intensity._check(Mock(), Mock(), [])

        # Assert
        self.assertTrue(success)
        self.assertEqual("Check:\n- SKIP: No selected prims", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

    async def test_check_mapping_match_return_failure_and_message(self):
        await self.__run_check(True, True)

    async def test_check_mapping_done_return_success_and_message(self):
        await self.__run_check(True, False)

    async def test_check_no_mapping_found_success_and_message(self):
        await self.__run_check(False, True)
        await self.__run_check(False, False)

    async def test_fix_no_selector_plugin_data_should_quick_return_success(self):
        # Arrange
        material_shader = ValueMapping()

        with patch.object(ValueMapping, "on_progress") as progress_mock:
            # Act
            success, message, data = await material_shader._fix(Mock(), Mock(), [])

        # Assert
        self.assertTrue(success)
        self.assertEqual("Fix:\n- SKIP: No selected prims", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

    async def test_fix_mapping_match_return_success_and_message(self):
        await self.__run_fix(True, True)

    async def test_fix_mapping_done_return_success_and_message(self):
        await self.__run_fix(True, False)

    async def test_fix_no_mapping_found_return_success_and_message(self):
        await self.__run_fix(False, True)
        await self.__run_fix(False, False)

    async def __run_check(self, has_mappable_attr: bool, match_predicate: bool):
        # Arrange
        emissive_intensity = ValueMapping()

        stage = Usd.Stage.CreateInMemory()

        attr_name = "inputs:emissive_intensity"
        material_path = "/World/Looks/TestMaterial"
        shader_path = f"{material_path}/Shader"

        mapping = AttributeMapping.construct()
        mapping.operator = Operator.eq
        mapping.input_value = 10
        mapping.output_value = 1

        schema_data_mock = ValueMapping.Data.construct()
        schema_data_mock.attributes = {attr_name: [mapping]}

        if has_mappable_attr:
            stage.DefinePrim(material_path, "Material")
            shader_prim = stage.DefinePrim(shader_path, "Shader")

            shader = UsdShade.Shader.Get(stage, shader_prim.GetPath())
            intensity_input = shader.CreateInput("emissive_intensity", Sdf.ValueTypeNames.Float)
            intensity_input.Set(10 if match_predicate else 0)
        else:
            shader_prim = stage.DefinePrim(shader_path, "Xform")

        with patch.object(ValueMapping, "on_progress") as progress_mock:
            # Act
            success, message, data = await emissive_intensity._check(schema_data_mock, "", [shader_prim])

        # Assert
        if not has_mappable_attr:
            progress_message = f"SKIP: The prim ({shader_prim.GetPath()}) does not have mappable attributes"
        elif not match_predicate:
            progress_message = (
                f"SKIP: The prim ({shader_prim.GetPath()}) has the attribute '{attr_name}' "
                f"but does not match a mapping predicate"
            )
        else:
            progress_message = (
                f"FAIL: The prim ({shader_prim.GetPath()}) has the attribute '{attr_name}' that must to be mapped"
            )

        expected_success = not has_mappable_attr or not match_predicate
        expected_message = f"Check:\n- {progress_message}\n"

        self.assertEqual(expected_success, success)
        self.assertEqual(expected_message, message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, progress_message, expected_success), progress_mock.call_args_list[1])

    async def __run_fix(self, has_mappable_attr: bool, match_predicate: bool):
        # Arrange
        emissive_intensity = ValueMapping()

        stage = Usd.Stage.CreateInMemory()

        attr_name = "inputs:emissive_intensity"
        material_path = "/World/Looks/TestMaterial"
        shader_path = f"{material_path}/Shader"

        mapping = AttributeMapping.construct()
        mapping.operator = Operator.eq
        mapping.input_value = 10
        mapping.output_value = 1

        schema_data_mock = ValueMapping.Data.construct()
        schema_data_mock.attributes = {attr_name: [mapping]}

        if has_mappable_attr:
            stage.DefinePrim(material_path, "Material")
            shader_prim = stage.DefinePrim(shader_path, "Shader")

            shader = UsdShade.Shader.Get(stage, shader_prim.GetPath())
            intensity_input = shader.CreateInput("emissive_intensity", Sdf.ValueTypeNames.Float)
            intensity_input.Set(10 if match_predicate else 0)
        else:
            shader_prim = stage.DefinePrim(shader_path, "Xform")

        with (
            patch.object(ValueMapping, "on_progress") as progress_mock,
            patch.object(omni.kit.commands, "execute") as execute_mock,
        ):
            # Act
            success, message, data = await emissive_intensity._fix(schema_data_mock, "", [shader_prim])

        # Assert
        if not has_mappable_attr:
            progress_message = f"SKIP: The prim ({shader_prim.GetPath()}) does not have mappable attributes"
        elif not match_predicate:
            progress_message = (
                f"SKIP: The prim ({shader_prim.GetPath()}) has the attribute '{attr_name}' "
                f"but does not match a mapping predicate"
            )
        else:
            progress_message = f"SUCCESS: The attribute '{attr_name}' for the prim ({shader_prim.GetPath()}) was mapped"

        expected_message = f"Fix:\n- {progress_message}\n"

        self.assertEqual(True, success)
        self.assertEqual(expected_message, message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, progress_message, True), progress_mock.call_args_list[1])

        should_change = has_mappable_attr and match_predicate

        self.assertEqual(1 if should_change else 0, execute_mock.call_count)
        if should_change:
            self.assertEqual(
                call(
                    "ChangeProperty",
                    prop_path=Sdf.Path(f"{shader_path}.{attr_name}"),
                    value=float(mapping.output_value),
                    prev=None,
                    usd_context_name="",
                ),
                execute_mock.call_args,
            )

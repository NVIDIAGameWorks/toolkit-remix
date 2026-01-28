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
import sys
from collections import OrderedDict
from unittest.mock import Mock, call, patch

import carb
import omni.kit.test
from omni.flux.utils.material_converter import MaterialConverterCore, OmniPBRToAperturePBRConverterBuilder
from omni.flux.utils.material_converter.utils import (
    MaterialConverterUtils,
    SupportedShaderInputs,
    SupportedShaderOutputs,
)
from omni.flux.validator.plugin.check.usd.material.material_shaders import (
    MaterialShaders,
    disable_orphan_parameter_cleanup,
)
from pxr import Sdf, Usd, UsdShade


class TestDisableOrphanParameterCleanup(omni.kit.test.AsyncTestCase):
    async def test_enter_should_set_parameter_to_true_exit_should_set_back_to_false(self):
        # Arrange
        setting_path = "/exts/omni.usd/mdl/ignoreOrphanParametersCleanup"

        # Act
        before_value = carb.settings.get_settings().get(setting_path)
        with disable_orphan_parameter_cleanup():
            enter_value = carb.settings.get_settings().get(setting_path)
        exit_value = carb.settings.get_settings().get(setting_path)

        # Assert
        self.assertFalse(before_value)
        self.assertFalse(exit_value)
        self.assertTrue(enter_value)


class TestMaterialShaders(omni.kit.test.AsyncTestCase):
    async def test_data_at_least_one_none_should_raise_value_error(self):
        # Arrange
        shader_subidentifiers = OrderedDict()

        # Act
        with self.assertRaises(ValueError) as cm:
            MaterialShaders.Data.at_least_one(shader_subidentifiers)

        # Assert
        self.assertEqual("There should at least be 1 item in shader_subidentifiers", str(cm.exception))

    async def test_data_at_least_one_one_should_return_value(self):
        # Arrange
        shader_subidentifiers = OrderedDict([(Mock(), "")])

        # Act
        val = MaterialShaders.Data.at_least_one(shader_subidentifiers)

        # Assert
        self.assertDictEqual(shader_subidentifiers, val)

    async def test_data_at_least_one_many_should_return_value(self):
        # Arrange
        shader_subidentifiers = OrderedDict([(Mock(), ""), (Mock(), ""), (Mock(), "")])

        # Act
        val = MaterialShaders.Data.at_least_one(shader_subidentifiers)

        # Assert
        self.assertDictEqual(shader_subidentifiers, val)

    async def test_data_valid_subidentifier_not_in_library_should_raise_value_error(self):
        # Arrange
        invalid_subidentifier = "invalid"

        sub_identifier_0 = "Subidentifier_0"
        shader_url_0 = Mock()
        shader_url_0.stem = sub_identifier_0
        sub_identifier_1 = "Subidentifier_1"
        shader_url_1 = Mock()
        shader_url_1.stem = sub_identifier_1

        with patch.object(MaterialConverterUtils, "get_material_library_shader_urls") as get_shader_urls_mock:
            get_shader_urls_mock.return_value = [shader_url_0, shader_url_1]

            with self.assertRaises(ValueError) as cm:
                # Act
                MaterialShaders.Data.valid_subidentifier(OrderedDict([(invalid_subidentifier, "")]))

        # Assert
        self.assertEqual(
            f"The subidentifier ({invalid_subidentifier}) does not exist in the material library. "
            f"If using non-default shaders, add your shader path to the following setting "
            f"'{MaterialConverterUtils.MATERIAL_LIBRARY_SETTING_PATH}'. Currently available shaders are: "
            f"{sub_identifier_0}, {sub_identifier_1}",
            str(cm.exception),
        )

    async def test_data_valid_subidentifier_in_library_should_return_value(self):
        # Arrange
        sub_identifier_0 = "Subidentifier_0"
        shader_url_0 = Mock()
        shader_url_0.stem = sub_identifier_0
        sub_identifier_1 = "Subidentifier_1"
        shader_url_1 = Mock()
        shader_url_1.stem = sub_identifier_1

        with patch.object(MaterialConverterUtils, "get_material_library_shader_urls") as get_shader_urls_mock:
            get_shader_urls_mock.return_value = [shader_url_0, shader_url_1]

            # Act
            val = MaterialShaders.Data.valid_subidentifier(OrderedDict([(sub_identifier_1, "")]))

        # Assert
        self.assertEqual(OrderedDict([(sub_identifier_1, "")]), val)

    async def test_data_supported_shader_output_not_supported_should_raise_value_error(self):
        # Arrange
        invalid_subidentifier = "invalid"

        with self.assertRaises(ValueError) as cm:
            # Act
            MaterialShaders.Data.supported_shader_output(
                OrderedDict([(invalid_subidentifier, ""), (SupportedShaderOutputs.APERTURE_PBR_OPACITY.value, ".*")])
            )

        # Assert
        self.assertEqual(
            f"The shader ({invalid_subidentifier}) is not currently a supported output shader. Supported shaders are: "
            f"{', '.join([s.value for s in SupportedShaderOutputs])}",
            str(cm.exception),
        )

    async def test_data_supported_shader_output_supported_should_return_value(self):
        # Arrange
        for supported_shader in SupportedShaderOutputs:
            # Act
            val = MaterialShaders.Data.supported_shader_output(OrderedDict([(supported_shader.value, ".*")]))

            # Assert
            self.assertDictEqual(OrderedDict([(supported_shader.value, ".*")]), val)

    async def test_check_no_selector_data_should_skip_check(self):
        # Arrange
        material_shader = MaterialShaders()

        with patch.object(MaterialShaders, "on_progress") as progress_mock:
            # Act
            success, message, data = await material_shader._check(Mock(), Mock(), [])  # noqa PLW0212

        # Assert
        self.assertTrue(success)
        self.assertEqual("Check:\n- SKIPPED: No selected prims", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

    async def test_check_invalid_prim_should_add_to_invalid_paths_and_return_failure_and_message(self):
        await self.__run_check(False, True)
        await self.__run_check(False, False)

    async def test_check_valid_prim_invalid_on_other_layer_should_remove_from_invalid_paths_and_return_failure_and_message(
        self,
    ):
        await self.__run_check(True, False)

    async def test_check_valid_prim_valid_on_all_layers_should_return_success_and_message(self):
        await self.__run_check(True, True)

    async def test_fix_no_selector_plugin_data_should_quick_return_success(self):
        # Arrange
        material_shader = MaterialShaders()

        with patch.object(MaterialShaders, "on_progress") as progress_mock:
            # Act
            success, message, data = await material_shader._fix(Mock(), Mock(), [])  # noqa PLW0212

        # Assert
        self.assertTrue(success)
        self.assertEqual("Fix:\n", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

    async def test_fix_prim_is_valid_should_skip_return_success_and_message(self):
        await self.__run_fix(True, True, True)
        await self.__run_fix(True, True, False)
        await self.__run_fix(True, False, True)
        await self.__run_fix(True, False, False)

    async def test_fix_input_subidentifier_is_not_supported_should_return_failure_and_message(self):
        await self.__run_fix(False, False, True)
        await self.__run_fix(False, False, False)

    async def test_fix_input_subidentifier_is_not_supported_ignore_not_convertable_shaders(self):
        await self.__run_fix(True, False, True, ignore_not_convertable_shaders=True)
        await self.__run_fix(True, False, False, ignore_not_convertable_shaders=True)

    async def test_fix_convert_material_failed_should_return_failure_and_message(self):
        await self.__run_fix(False, True, False)

    async def test_fix_convert_material_succeeded_should_return_success_and_message(self):
        await self.__run_fix(False, True, True)

    async def test_get_material_shader_subidentifier(self):
        await self.__run_get_material_shader_subidentifier()

    async def test_validate_material_shaders_subidentifier_is_not_valid_should_return_false(self):
        await self.__run_validate_material_shaders(False)

    async def test_validate_material_shaders_subidentifier_is_valid_should_return_true(self):
        await self.__run_validate_material_shaders(True)

    async def test_convert_material_not_supported_input_should_return_false_and_error_message(self):
        await self.__run_convert_material(False, True, True)
        await self.__run_convert_material(False, True, False)
        await self.__run_convert_material(False, False, True)
        await self.__run_convert_material(False, False, False)

    async def test_convert_material_not_supported_output_should_return_false_and_error_message(self):
        await self.__run_convert_material(True, False, True)
        await self.__run_convert_material(True, False, False)

    async def test_convert_material_supported_conversion_failed_should_return_false_and_error_message(self):
        await self.__run_convert_material(True, True, False)

    async def test_convert_material_supported_conversion_succeeded_should_return_true_and_details(self):
        await self.__run_convert_material(True, True, True)

    async def __run_check(self, is_valid: bool, is_valid_other_layer: bool):
        # Arrange
        shader_subidentifiers_mock = OrderedDict([(Mock(), ""), (Mock(), "")])
        schema_data_mock = Mock()
        schema_data_mock.shader_subidentifiers = shader_subidentifiers_mock

        prim_path_mock = Mock()
        prim_mock = Mock()
        prim_mock.GetPath.return_value = prim_path_mock

        root_identifier_mock = Mock(name="root_identifier")
        context_plugin_data_mock = Mock()
        context_plugin_data_mock.GetRootLayer.return_value.identifier = root_identifier_mock
        context_plugin_data_mock.GetPrimAtPath.return_value = prim_mock

        usd_context_mock = Mock()
        usd_context_mock.get_stage.return_value = context_plugin_data_mock

        selector_prim_path_mock = Mock()
        selector_prim_mock = Mock()
        selector_prim_mock.GetPath.return_value = selector_prim_path_mock

        selector_plugin_data_mock = [selector_prim_mock]

        subidenfifier_mock = Mock()

        material_shader = MaterialShaders()
        alternate_identifier_mock = Mock(name="alternate_identifier")
        if not is_valid_other_layer:
            material_shader._layers_invalid_paths = {  # noqa PLW0212
                alternate_identifier_mock: {prim_path_mock: subidenfifier_mock}
            }
        else:
            material_shader._layers_invalid_paths = {  # noqa PLW0212
                root_identifier_mock: {prim_path_mock: subidenfifier_mock}
            }

        with (
            patch.object(MaterialShaders, "on_progress") as progress_mock,
            patch.object(MaterialShaders, "_validate_material_shaders") as validate_mock,
            patch.object(MaterialShaders, "_get_material_shader_subidentifier") as get_subidentifer_mock,
            patch("omni.flux.validator.plugin.check.usd.material.material_shaders.usd.get_context") as omni_usd_mockup,
        ):
            if sys.version_info.minor > 7:
                validate_mock.return_value = is_valid
                omni_usd_mockup.return_value = usd_context_mock
            else:
                validate_future = asyncio.Future()
                validate_future.set_result(is_valid)
                validate_mock.return_value = validate_future

                omni_usd_future = asyncio.Future()
                omni_usd_future.set_result(usd_context_mock)
                omni_usd_mockup.return_value = omni_usd_future

            if sys.version_info.minor > 7:
                get_subidentifer_mock.return_value = subidenfifier_mock
            else:
                subidentifiers_future = asyncio.Future()
                subidentifiers_future.set_result(subidenfifier_mock)
                get_subidentifer_mock.return_value = subidentifiers_future

            # Act
            success, message, data = await material_shader._check(  # noqa PLW0212
                schema_data_mock, Mock(), selector_plugin_data_mock
            )

        # Assert
        expected_invalid_dict = {root_identifier_mock: {prim_path_mock: subidenfifier_mock}}
        if not is_valid_other_layer:
            expected_invalid_dict[alternate_identifier_mock] = {}

        self.assertDictEqual(expected_invalid_dict, material_shader._layers_invalid_paths)  # noqa PLW0212

        expected_progress_message = f"{'OK' if is_valid and is_valid_other_layer else 'INVALID'}: {prim_path_mock}"
        expected_message = f"Check:\n- {expected_progress_message}\n"

        self.assertEqual(is_valid and is_valid_other_layer, success)
        self.assertEqual(expected_message, message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(
            call(1, expected_progress_message, is_valid and is_valid_other_layer), progress_mock.call_args_list[1]
        )

        self.assertEqual(1, context_plugin_data_mock.GetPrimAtPath.call_count)
        self.assertEqual(call(selector_prim_path_mock), context_plugin_data_mock.GetPrimAtPath.call_args)

        self.assertEqual(1, validate_mock.call_count)
        self.assertEqual(call(shader_subidentifiers_mock, prim_mock), validate_mock.call_args)

        self.assertEqual(1, get_subidentifer_mock.call_count)
        self.assertEqual(call(prim_mock), get_subidentifer_mock.call_args)

    async def __run_fix(
        self,
        is_valid: bool,
        is_valid_input_subid: bool,
        conversion_success: bool,
        ignore_not_convertable_shaders: bool = False,
    ):
        # Arrange
        context_name_mock = Mock()
        valid_subid = Mock()
        shader_subidentifiers_mock = OrderedDict([(valid_subid, ".*"), (Mock(), "")])
        schema_data_mock = Mock()
        schema_data_mock.context_name = context_name_mock
        schema_data_mock.shader_subidentifiers = shader_subidentifiers_mock
        schema_data_mock.ignore_not_convertable_shaders = ignore_not_convertable_shaders

        root_identifier_mock = Mock(name="root_identifier")
        context_plugin_data_mock = Mock()
        context_plugin_data_mock.GetRootLayer.return_value.identifier = root_identifier_mock

        usd_context_mock = Mock()
        usd_context_mock.get_stage.return_value = context_plugin_data_mock

        selector_prim_path_mock = Mock()
        selector_prim_mock = Mock()
        selector_prim_mock.GetPath.return_value = selector_prim_path_mock
        selector_prim_mock.GetName.return_value = "root_identifier"
        selector_plugin_data_mock = [selector_prim_mock]

        conversion_message_mock = Mock()

        valid_subidentifier = SupportedShaderInputs.OMNI_PBR.value
        invalid_subidentifier = Mock(name="invalid_subidentifier")

        material_shader = MaterialShaders()
        material_shader._layers_invalid_paths = {  # noqa PLW0212
            Mock() if is_valid else root_identifier_mock: {
                selector_prim_path_mock: valid_subidentifier if is_valid_input_subid else invalid_subidentifier
            }
        }

        with (
            patch.object(MaterialShaders, "on_progress") as progress_mock,
            patch.object(MaterialShaders, "_convert_material") as convert_mock,
            patch(
                "omni.flux.validator.plugin.check.usd.material.material_shaders.disable_orphan_parameter_cleanup"
            ) as disable_cleanup_mock,
            patch("omni.flux.validator.plugin.check.usd.material.material_shaders.usd.get_context") as omni_usd_mockup,
            patch(
                "omni.flux.validator.plugin.check.usd.material.material_shaders.usd.get_shader_from_material"
            ) as omni_usd_get_shader,
        ):
            v1 = (conversion_success, conversion_message_mock, True)
            if sys.version_info.minor > 7:
                convert_mock.return_value = v1
                omni_usd_mockup.return_value = usd_context_mock
                omni_usd_get_shader.return_value = None
            else:
                convert_future = asyncio.Future()
                convert_future.set_result(v1)
                convert_mock.return_value = convert_future

                omni_usd_future = asyncio.Future()
                omni_usd_future.set_result(usd_context_mock)
                omni_usd_mockup.return_value = omni_usd_future

                omni_usd_get_shader_future = asyncio.Future()
                omni_usd_get_shader_future.set_result(None)
                omni_usd_get_shader.return_value = omni_usd_get_shader_future

            # Act
            success, message, data = await material_shader._fix(  # noqa PLW0212
                schema_data_mock, context_name_mock, selector_plugin_data_mock
            )

        # Assert
        if is_valid:
            expected_progress_message = f"SKIPPED: {selector_prim_path_mock}"
        elif not is_valid_input_subid:
            expected_progress_message = (
                f"{'WARNING' if ignore_not_convertable_shaders else 'ERROR'}: Unsupported input material "
                f"'{invalid_subidentifier}'. Supported input material shaders are currently: "
                f"{','.join([str(s.value) for s in SupportedShaderInputs])} on layer {root_identifier_mock}"
                f"{'. Skipped' if ignore_not_convertable_shaders else ''}"
            )
        else:
            expected_progress_message = (
                f"{'FIXED' if conversion_success else 'ERROR'}: {selector_prim_path_mock} - {conversion_message_mock}"
            )

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(
            call(1, expected_progress_message, is_valid or (is_valid_input_subid and conversion_success)),
            progress_mock.call_args_list[1],
        )

        self.assertEqual(is_valid or (is_valid_input_subid and conversion_success), success)
        self.assertEqual(f"Fix:\n- {expected_progress_message}\n", message)
        self.assertIsNone(data)

        self.assertEqual(1, disable_cleanup_mock.call_count)

        self.assertEqual(1 if not is_valid and is_valid_input_subid else 0, convert_mock.call_count)
        if not is_valid and is_valid_input_subid:
            self.assertEqual(
                call(context_name_mock, valid_subid, valid_subidentifier, selector_prim_mock),
                convert_mock.call_args,
            )

    async def __run_get_material_shader_subidentifier(self):
        test_runs = (
            {
                "name": "Expected input",
                "source_mdl": "OmniPBR.mdl",
                "source_id": "OmniPBR.mdl",
                "expected_value": "OmniPBR",
            },
            {
                "name": "Maya plugin expected input should not crash",
                "source_mdl": "OmniPBR.mdl",
                "source_id": "OmniPBR(float foo, int bar)",
                "expected_value": "OmniPBR",
            },
            {
                "name": "Garbage input should not crash",
                "source_mdl": "Test.mdl",
                "source_id": "{1}{ }{334}2}f{}{23{!!!@#4556# $@5$%#%^@as~%)_-(*)+^#",
                "expected_value": None,
            },
            {"name": "Empty input should not crash", "source_mdl": "", "source_id": "", "expected_value": None},
        )

        for run in test_runs:
            with self.subTest(name=run["name"]):
                # Arrange (create usd stage, and material etc... based on testing params)
                material_shader = MaterialShaders()

                stage = Usd.Stage.CreateInMemory()
                mtl_path = omni.usd.get_stage_next_free_path(stage, "/World/Looks/TestMaterial", False)
                mat_prim = stage.DefinePrim(mtl_path, "Material")
                material_prim = UsdShade.Material.Get(stage, mat_prim.GetPath())
                shader_mtl_path = stage.DefinePrim(f"{mtl_path}/Shader", "Shader")
                shader_prim = UsdShade.Shader.Get(stage, shader_mtl_path.GetPath())
                shader_out = shader_prim.CreateOutput("out", Sdf.ValueTypeNames.Token)
                material_prim.CreateSurfaceOutput("mdl").ConnectToSource(shader_out)
                shader_out.SetRenderType("material")
                shader_prim.GetImplementationSourceAttr().Set(UsdShade.Tokens.sourceAsset)
                shader_prim.SetSourceAsset(Sdf.AssetPath(run["source_mdl"]), "mdl")
                shader_prim.SetSourceAssetSubIdentifier(run["source_id"], "mdl")

                # Act (perform the function we want to test)
                val = await material_shader._get_material_shader_subidentifier(mat_prim)  # noqa PLW0212
                stage.Unload()

                # Assert (check we get the correct value returned from function)
                self.assertEqual(run["expected_value"], val)

    async def __run_validate_material_shaders(self, is_valid: bool):
        # Arrange
        material_shader = MaterialShaders()

        prim_mock = Mock()

        invalid_subidentifier = Mock()
        valid_subidentifier = Mock()
        shader_subidentifiers_mock = OrderedDict([(Mock(), "testing"), (valid_subidentifier, ".*"), (Mock(), "")])

        with patch.object(MaterialShaders, "_get_material_shader_subidentifier") as get_subidentifier_mock:
            v1 = valid_subidentifier if is_valid else invalid_subidentifier
            if sys.version_info.minor > 7:
                get_subidentifier_mock.return_value = v1
            else:
                subidentifiers_future = asyncio.Future()
                subidentifiers_future.set_result(v1)
                get_subidentifier_mock.return_value = subidentifiers_future

            # Act
            val = await material_shader._validate_material_shaders(  # noqa PLW0212
                shader_subidentifiers_mock, prim_mock
            )

        # Assert
        self.assertEqual(is_valid, val)

        self.assertEqual(1, get_subidentifier_mock.call_count)
        self.assertEqual(call(prim_mock), get_subidentifier_mock.call_args)

    async def __run_convert_material(self, valid_input: bool, valid_output: bool, conversion_success: bool):
        # Arrange
        material_shader = MaterialShaders()

        input_subidentifier = SupportedShaderInputs.OMNI_PBR.value if valid_input else "invalid_input"
        output_subidentifier = SupportedShaderOutputs.APERTURE_PBR_OPACITY.value if valid_output else "invalid_output"

        context_name_mock = Mock()
        prim_mock = Mock()
        converter_mock = Mock()

        message_mock = Mock()

        with (
            patch.object(OmniPBRToAperturePBRConverterBuilder, "build") as build_converter_mock,
            patch.object(MaterialConverterCore, "convert") as convert_mock,
        ):
            build_converter_mock.return_value = converter_mock
            v1 = (conversion_success, message_mock, True)
            if sys.version_info.minor > 7:
                convert_mock.return_value = v1
            else:
                conversion_future = asyncio.Future()
                conversion_future.set_result(v1)
                convert_mock.return_value = conversion_future

            # Act
            success, message, _was_converted = await material_shader._convert_material(  # noqa PLW0212
                context_name_mock, output_subidentifier, input_subidentifier, prim_mock
            )

        # Assert
        self.assertEqual(valid_input and valid_output and conversion_success, success)
        self.assertEqual(message_mock if valid_input and valid_output else "No supported converter found", message)

        self.assertEqual(1 if valid_input and valid_output else 0, build_converter_mock.call_count)
        self.assertEqual(1 if valid_input and valid_output else 0, convert_mock.call_count)

        if valid_input and valid_output:
            self.assertEqual(call(prim_mock, output_subidentifier), build_converter_mock.call_args)
            self.assertEqual(call(context_name_mock, converter_mock), convert_mock.call_args)

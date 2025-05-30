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
import shutil
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, PropertyMock, call, patch

import omni.client
import omni.kit.test
import omni.usd
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_importer.widget.texture_import_list.utils import (
    create_prims_and_link_assets as _create_prims_and_link_assets,
)
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.plugin.context.usd_stage.texture_importer import TextureImporter
from pxr import Sdf


class MockValidationInfo:
    """Mock for pydantic's ValidationInfo."""

    def __init__(self, data):
        self.data = data


class MockListEntry:
    def __init__(self, path: str, flags=omni.client.ItemFlags.READABLE_FILE):
        self.relative_path = path
        self.flags = flags


class TestTextureImporterUnit(omni.kit.test.AsyncTestCase):
    async def test_data_at_least_one_with_none_should_raise_value_error(self):
        # Arrange
        input_files = []

        # Act
        with self.assertRaises(ValueError) as cm:
            TextureImporter.Data.at_least_one(input_files, MockValidationInfo({}))

        # Assert
        self.assertEqual("There should at least be 1 item in input_files", str(cm.exception))

    async def test_data_at_least_one_with_items_should_return_value(self):
        # Arrange
        input_files = [Mock(), Mock(), Mock()]

        # Act
        val = TextureImporter.Data.at_least_one(input_files, MockValidationInfo({}))

        # Assert
        self.assertListEqual(input_files, val)

    async def test_data_at_least_one_with_none_but_allowed_should_return_value(self):
        # Arrange
        input_files = []

        # Act
        val = TextureImporter.Data.at_least_one(input_files, MockValidationInfo({"allow_empty_input_files_list": True}))

        # Assert
        self.assertListEqual(input_files, val)

    async def test_data_is_readable_does_not_exist_should_raise_value_error(self):
        # Arrange
        file_url = Mock(spec=OmniUrl)
        texture_type = Mock(spec=TextureTypes)
        input_files = [(file_url, texture_type)]

        with patch.object(OmniUrl, "exists", new_callable=PropertyMock) as exists_mock:
            exists_mock.return_value = False

            with self.assertRaises(ValueError) as cm:
                # Act
                TextureImporter.Data.is_valid(input_files)

        # Assert
        self.assertEqual(f"The input file {file_url} does not exist", str(cm.exception))

    async def test_data_is_readable_valid_should_return_value(self):
        # Arrange
        file_url = Mock(spec=OmniUrl)
        texture_type = Mock(spec=TextureTypes)
        input_files = [(file_url, texture_type)]

        with patch.object(OmniUrl, "exists", new_callable=PropertyMock) as exists_mock:
            exists_mock.return_value = True

            # Act
            val = TextureImporter.Data.is_valid(input_files)

        # Assert
        self.assertEqual(input_files, val)

    async def test_data_can_have_children_not_okay_should_raise_value_error(self):
        # Arrange
        input_file = Mock()

        with self.assertRaises(ValueError) as cm, patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (omni.client.Result.ERROR_NOT_FOUND, MockListEntry("./Test.png"))

            # Act
            TextureImporter.Data.can_have_children(
                input_file, MockValidationInfo({"create_output_directory_if_missing": False})
            )

        # Assert
        self.assertEqual(f"The output directory is not valid: {input_file}", str(cm.exception))

    async def test_data_can_have_children_cannot_have_children_should_raise_value_error(self):
        # Arrange
        input_file = Mock()

        with self.assertRaises(ValueError) as cm, patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (omni.client.Result.OK, MockListEntry("./Test.png", flags=0))

            # Act
            TextureImporter.Data.can_have_children(
                input_file, MockValidationInfo({"create_output_directory_if_missing": False})
            )

        # Assert
        self.assertEqual(f"The output directory cannot have children: {input_file}", str(cm.exception))

    async def test_data_can_have_children_valid_should_return_value(self):
        await self.__run_data_can_have_children(" .  ")
        await self.__run_data_can_have_children("    ")
        await self.__run_data_can_have_children("C:/Test")

    async def test_output_dir_unequal_input_dirs_invalid_should_raise_value_error(self):
        # Arrange
        input_type = TextureTypes.NORMAL_OGL.name
        input_files = [(OmniUrl("./TestDir/Test0.png"), input_type), (OmniUrl("./TestDir/Test1.png"), input_type)]
        output_folder = OmniUrl("./TestDir")

        with self.assertRaises(ValueError) as cm:
            # Act
            TextureImporter.Data.output_dir_unequal_input_dirs(
                output_folder, MockValidationInfo({"input_files": input_files})
            )

        # Assert
        self.assertEqual(
            f'Output directory "{output_folder}" cannot be the same as any input file directory.',
            str(cm.exception),
        )

    async def test_output_dir_unequal_input_dirs_valid_subdir_should_return_value(self):
        # Arrange
        input_type = TextureTypes.NORMAL_OGL.name
        input_files = [(OmniUrl("./TestDir/Test0.png"), input_type), (OmniUrl("./TestDir/Test1.png"), input_type)]
        output_folder = OmniUrl("./TestDir/SubDir")

        # Act
        val = TextureImporter.Data.output_dir_unequal_input_dirs(
            output_folder, MockValidationInfo({"input_files": input_files})
        )

        # Assert
        self.assertEqual(output_folder, val)

    async def test_check_no_input_files_should_return_invalid(self):
        await self.__run_check(False, False, "ERROR: No input file paths were given.")
        await self.__run_check(False, True, "ERROR: No input file paths were given.")

    async def test_check_no_output_directory_should_return_invalid(self):
        await self.__run_check(True, False, "ERROR: An output directory must be set.")

    async def test_check_valid_should_return_valid(self):
        await self.__run_check(True, True, "The selected files are valid.")

    async def test_setup_no_context_should_early_return_invalid(self):
        await self.__run_setup(False)

    async def test_setup_valid_should_run_callback_and_return_valid_final_data(self):
        await self.__run_setup(True)

    async def test_setup_valid_with_push_input_data_only(self):
        await self.__run_setup(
            True, data_flows=[{"name": "InOutData", "push_input_data": True, "push_output_data": False}]
        )

    async def test_setup_valid_with_push_output_data_only(self):
        await self.__run_setup(
            True, data_flows=[{"name": "InOutData", "push_input_data": False, "push_output_data": True}]
        )

    async def test_setup_valid_with_push_input_data_and_push_output_data(self):
        await self.__run_setup(
            True, data_flows=[{"name": "InOutData", "push_input_data": True, "push_output_data": True}]
        )

    async def test_setup_not_valid_with_push_input_data_and_push_output_data(self):
        await self.__run_setup(
            True, data_flows=[{"name": "InOutData", "push_input_data": True, "push_output_data": True}]
        )

    async def test_create_prims_and_link_assets_normal_should_set_normal_and_flip_tangent_v_attributes(self):
        await self.__run_create_prims_and_link_assets(TextureTypes.NORMAL_OGL)
        await self.__run_create_prims_and_link_assets(TextureTypes.NORMAL_DX)
        await self.__run_create_prims_and_link_assets(TextureTypes.NORMAL_OTH)

    async def test_create_prims_and_link_assets_other_attribute_should_set_attribute(self):
        await self.__run_create_prims_and_link_assets(TextureTypes.DIFFUSE)
        await self.__run_create_prims_and_link_assets(TextureTypes.EMISSIVE)
        await self.__run_create_prims_and_link_assets(TextureTypes.METALLIC)
        await self.__run_create_prims_and_link_assets(TextureTypes.ROUGHNESS)
        await self.__run_create_prims_and_link_assets(TextureTypes.OTHER)

    async def test_exit_should_return_success(self):
        # Arrange
        schema_data = Mock()
        texture_importer = TextureImporter()

        # Act
        success, message = await texture_importer._on_exit(schema_data, None)  # noqa PLW0212

        # Assert
        self.assertTrue(success)
        self.assertEqual("Exit ok", message)

    async def __run_data_can_have_children(self, value: str):
        # Arrange
        with patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (
                omni.client.Result.OK,
                MockListEntry("./Test.png", flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
            )

            # Act
            val = TextureImporter.Data.can_have_children(
                value, MockValidationInfo({"create_output_directory_if_missing": False})
            )

        # Assert
        self.assertEqual(value, val)

    async def __run_check(self, has_input_files: bool, has_output_directory: bool, expected_message: str):
        # Arrange
        schema_data = Mock()
        schema_data.input_files = [Mock()] if has_input_files else []
        schema_data.output_directory = "C:/Test" if has_output_directory else "  .  "
        schema_data.error_on_texture_types = []

        texture_importer = TextureImporter()

        # Act
        is_valid, message = await texture_importer._check(schema_data, None)  # noqa PLW0212

        # Assert
        self.assertEqual(has_input_files and has_output_directory, is_valid)
        self.assertEqual(expected_message, message)

    async def __run_setup(self, valid_context: bool, data_flows: Optional[List[Dict[Any, Any]]] = None):
        # Arrange
        texture_importer = TextureImporter()

        run_callback_future = asyncio.Future()
        run_callback_future.set_result(None)
        run_callback_mock = Mock()
        run_callback_mock.return_value = run_callback_future

        input_texture_path = "C:/Test/Input/test_0.png"
        input_texture_type = TextureTypes.NORMAL_OGL.name

        context_name = "context_name"
        schema_mock = Mock()
        schema_mock.context_name = context_name
        schema_mock.create_context_if_not_exist = False
        schema_mock.input_files = [(input_texture_path, input_texture_type)]
        schema_mock.output_directory = "C:/Test/Output"
        schema_mock.data_flows = [_InOutDataFlow(**data_fl) for data_fl in data_flows] if data_flows else []

        imported_texture_path = "C:/Test/Output/test_0.png"
        expected_imported_files = [(imported_texture_path, TextureTypes[input_texture_type])]

        stage_mock = Mock()
        context_mock = Mock()
        context_mock.get_stage.return_value = stage_mock
        new_stage_mock = context_mock.new_stage_async

        create_prims_future = asyncio.Future()
        create_prims_future.set_result(None)

        new_stage_future = asyncio.Future()
        new_stage_future.set_result(None)
        new_stage_mock.return_value = new_stage_future

        with (
            patch.object(omni.client, "normalize_url") as normalize_mock,
            patch.object(shutil, "copyfile") as copy_mock,
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch(
                "omni.flux.validator.plugin.context.usd_stage.texture_importer._create_prims_and_link_assets"
            ) as create_prims_mock,
        ):
            normalize_mock.side_effect = lambda v: v
            get_context_mock.return_value = context_mock if valid_context else None
            create_prims_mock.return_value = create_prims_future

            # Act
            is_valid, message, value = await texture_importer._setup(  # noqa PLW0212
                schema_mock, run_callback_mock, None
            )

        # Assert
        expected_message = (
            "Textures were imported successfully" if valid_context else f"The context '{context_name}' doesn't exist!"
        )

        self.assertEqual(valid_context, is_valid)
        self.assertEqual(expected_message, message)
        self.assertEqual(expected_imported_files if valid_context else None, value)

        self.assertEqual(2, normalize_mock.call_count)
        self.assertEqual(call(input_texture_path), normalize_mock.call_args_list[0])
        self.assertEqual(call(imported_texture_path), normalize_mock.call_args_list[1])

        self.assertEqual(1, copy_mock.call_count)
        self.assertEqual(call(input_texture_path, imported_texture_path), copy_mock.call_args)

        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name), get_context_mock.call_args)

        self.assertEqual(1 if valid_context else 0, new_stage_mock.call_count)
        self.assertEqual(1 if valid_context else 0, create_prims_mock.call_count)
        self.assertEqual(1 if valid_context else 0, run_callback_mock.call_count)
        if valid_context:
            self.assertEqual(call(context_name, expected_imported_files), create_prims_mock.call_args)
            self.assertEqual(call(context_name), run_callback_mock.call_args)

        # check data flow
        data_flow_result = [
            data_flow_r.model_dump(serialize_as_any=True) for data_flow_r in schema_mock.data_flows or []
        ]

        data_flow_expected_result = []
        if data_flows:
            for data_flow, _data_flow_result in zip(data_flows, data_flow_result):
                if data_flow.get("push_input_data"):
                    data_flow["input_data"] = (
                        [str(input_texture_path)] if valid_context else [str(input_texture_path[0])]
                    )
                if data_flow.get("push_output_data"):
                    data_flow["output_data"] = (
                        [str(imported_texture_path)] if valid_context else [str(imported_texture_path[0])]
                    )
                data = _data_flow_result.copy()
                data.update(data_flow)
                data_flow_expected_result.append(data)

        self.assertEqual(
            data_flow_result,
            data_flow_expected_result,
        )

    async def __run_create_prims_and_link_assets(self, texture_type: TextureTypes):
        # Arrange
        stage_mock = Mock()

        context_name_mock = Mock()

        imported_file_name = f"{texture_type.name}_test"
        imported_file_path = OmniUrl(f"C:/Test/{imported_file_name}.png")
        imported_file_prim_path = f"/TextureImporter/Looks/{imported_file_name}"
        imported_files = [(imported_file_path, texture_type)]

        material_shader_mock = Mock()
        append_property_mock = material_shader_mock.GetPath.return_value.AppendProperty

        with (
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(omni.usd, "get_stage_next_free_path") as get_free_path_mock,
            patch.object(omni.kit.commands, "execute") as command_mock,
            patch.object(omni.usd, "get_shader_from_material") as get_shader_mock,
        ):
            get_context_mock.return_value.get_stage.return_value = stage_mock
            get_free_path_mock.return_value = imported_file_prim_path
            get_shader_mock.return_value = material_shader_mock

            # Act
            await _create_prims_and_link_assets(context_name_mock, imported_files)  # noqa PLW0212

        # Assert
        self.assertEqual(
            3 if texture_type in [TextureTypes.NORMAL_OGL, TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OTH] else 2,
            command_mock.call_count,
        )
        self.assertEqual(
            call(
                "CreateMdlMaterialPrim",
                mtl_url="OmniPBR.mdl",
                mtl_name="OmniPBR",
                mtl_path=imported_file_prim_path,
                stage=stage_mock,
                context_name=context_name_mock,
            ),
            command_mock.call_args_list[0],
        )

        self.assertEqual(
            call(
                "ChangePropertyCommand",
                prop_path=str(append_property_mock.return_value),
                value=Sdf.AssetPath(str(imported_file_path)),
                prev=None,
                type_to_create_if_not_exist=Sdf.ValueTypeNames.Asset,
                usd_context_name=context_name_mock,
            ),
            command_mock.call_args_list[1],
        )

        if command_mock.call_count == 3:
            encoding = -1
            match texture_type.name:
                case TextureTypes.NORMAL_OTH.name:
                    encoding = 0  # _NormalMapEncodings.OCTAHEDRAL
                case TextureTypes.NORMAL_OGL.name:
                    encoding = 1  # _NormalMapEncodings.TANGENT_SPACE_OGL
                case TextureTypes.NORMAL_DX.name:
                    encoding = 2  # _NormalMapEncodings.TANGENT_SPACE_DX
            # do we have valid normals
            if encoding != -1:
                self.assertEqual(2, append_property_mock.call_count)
                self.assertEqual(call("inputs:encoding"), append_property_mock.call_args_list[1])
                self.assertEqual(
                    call(
                        "ChangePropertyCommand",
                        prop_path=str(append_property_mock.return_value),
                        value=encoding,
                        prev=None,
                        type_to_create_if_not_exist=Sdf.ValueTypeNames.Int,
                        usd_context_name=context_name_mock,
                    ),
                    command_mock.call_args_list[2],
                )

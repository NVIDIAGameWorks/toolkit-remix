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
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, call, patch

import omni.client
import omni.kit
import omni.kit.test
import omni.usd
from omni.flux.asset_importer.core import AssetImporterModel, ImporterCore
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.validator.plugin.context.usd_stage.asset_importer import AssetImporter
from pxr import Sdf


class MockValidationInfo:
    """Mock for pydantic's ValidationInfo."""

    def __init__(self, data):
        self.data = data


class MockListEntry:
    def __init__(self, path: str, flags=omni.client.ItemFlags.READABLE_FILE):
        self.relative_path = path
        self.flags = flags


class TestAssetImporterUnit(omni.kit.test.AsyncTestCase):

    # Before running each test
    async def setUp(self):
        self.maxDiff = None
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.stage = None

    async def test_data_at_least_one_with_none_should_raise_value_error(self):
        # Arrange
        input_files = []

        # Act
        with self.assertRaises(ValueError) as cm:
            AssetImporter.Data.at_least_one(input_files, MockValidationInfo({}))

        # Assert
        self.assertEqual("There should at least be 1 item in input_files", str(cm.exception))

    async def test_data_at_least_one_with_items_should_return_value(self):
        # Arrange
        input_files = [Mock(), Mock(), Mock()]

        # Act
        val = AssetImporter.Data.at_least_one(input_files, MockValidationInfo({}))

        # Assert
        self.assertListEqual(input_files, val)

    async def test_data_at_least_one_with_none_but_allowed_should_return_value(self):
        # Arrange
        input_files = []

        # Act
        val = AssetImporter.Data.at_least_one(input_files, MockValidationInfo({"allow_empty_input_files_list": True}))

        # Assert
        self.assertListEqual(input_files, val)

    async def test_data_is_readable_not_okay_should_raise_value_error(self):
        # Arrange
        input_file = [Mock()]

        with self.assertRaises(ValueError) as cm, patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (omni.client.Result.ERROR_NOT_FOUND, MockListEntry("./Test.usd"))

            # Act
            AssetImporter.Data.is_readable(input_file)

        # Assert
        self.assertEqual(f"The input file is not valid: {input_file[0]}", str(cm.exception))

    async def test_data_is_readable_not_readable_should_raise_value_error(self):
        # Arrange
        input_file = [Mock()]

        with self.assertRaises(ValueError) as cm, patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (omni.client.Result.OK, MockListEntry("./Test.usd", flags=0))

            # Act
            AssetImporter.Data.is_readable(input_file)

        # Assert
        self.assertEqual(f"The input file is not readable: {input_file[0]}", str(cm.exception))

    async def test_data_is_readable_valid_should_return_value(self):
        # Arrange
        input_file = [Mock()]

        with patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (omni.client.Result.OK, MockListEntry("./Test.usd"))

            # Act
            val = AssetImporter.Data.is_readable(input_file)

        # Assert
        self.assertEqual(input_file, val)

    async def test_data_can_have_children_not_okay_should_raise_value_error(self):
        # Arrange
        input_file = Mock()

        with self.assertRaises(ValueError) as cm, patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (omni.client.Result.ERROR_NOT_FOUND, MockListEntry("./Test.usd"))

            # Act
            AssetImporter.Data.can_have_children(
                input_file, MockValidationInfo({"create_output_directory_if_missing": False})
            )

        # Assert
        self.assertEqual(f"The output directory is not valid: {input_file}", str(cm.exception))

    async def test_data_can_have_children_cannot_have_children_should_raise_value_error(self):
        # Arrange
        input_file = Mock()

        with self.assertRaises(ValueError) as cm, patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (omni.client.Result.OK, MockListEntry("./Test.usd", flags=0))

            # Act
            AssetImporter.Data.can_have_children(
                input_file, MockValidationInfo({"create_output_directory_if_missing": False})
            )

        # Assert
        self.assertEqual(f"The output directory cannot have children: {input_file}", str(cm.exception))

    async def test_data_can_have_children_valid_should_return_value(self):
        # Arrange
        input_file = Mock()

        with patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (
                omni.client.Result.OK,
                MockListEntry("./Test.usd", flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
            )

            # Act
            val = AssetImporter.Data.can_have_children(
                input_file, MockValidationInfo({"create_output_directory_if_missing": False})
            )

        # Assert
        self.assertEqual(input_file, val)

    async def test_output_dir_unequal_input_dirs_invalid_should_raise_value_error(self):
        # Arrange
        input_files = [OmniUrl("./TestDir/Test0.fbx"), OmniUrl("./TestDir/Test1.fbx")]
        output_folder = OmniUrl("./TestDir")

        with self.assertRaises(ValueError) as cm:
            # Act
            AssetImporter.Data.output_dir_unequal_input_dirs(
                output_folder, MockValidationInfo({"input_files": input_files})
            )

        # Assert
        self.assertEqual(
            f'Output directory "{output_folder}" cannot be the same as any input file directory.', str(cm.exception)
        )

    async def test_output_dir_unequal_input_dirs_valid_subdir_should_return_value(self):
        # Arrange
        input_files = [OmniUrl("./TestDir/Test0.fbx"), OmniUrl("./TestDir/Test1.fbx")]
        output_folder = OmniUrl("./TestDir/SubDir")

        # Act
        val = AssetImporter.Data.output_dir_unequal_input_dirs(
            output_folder, MockValidationInfo({"input_files": input_files})
        )

        # Assert
        self.assertEqual(output_folder, val)

    async def test_check_value_error_raised_should_return_invalid(self):
        await self.__run_check(False)

    async def test_check_valid_should_return_valid(self):
        await self.__run_check(True)

    async def test_setup_no_context_should_early_return_invalid(self):
        await self.__run_setup(False, True, "The context 'None' doesn't exist!")

    async def test_setup_open_stage_error_should_early_return_invalid(self):
        await self.__run_setup(True, False, "Test Open Stage Error")

    async def test_setup_valid_with_extension_should_run_callback_and_return_valid_final_data(self):
        await self.__run_setup(True, True, "Files were imported successfully", output_usd_extension="usd")

    async def test_setup_valid_no_extension_should_run_callback_and_return_valid_final_data(self):
        await self.__run_setup(True, True, "Files were imported successfully")

    async def test_setup_valid_with_push_input_data_only(self):
        await self.__run_setup(
            True,
            True,
            "Files were imported successfully",
            data_flows=[{"name": "InOutData", "push_input_data": True, "push_output_data": False}],
        )

    async def test_setup_valid_with_push_output_data_only(self):
        await self.__run_setup(
            True,
            True,
            "Files were imported successfully",
            data_flows=[{"name": "InOutData", "push_input_data": False, "push_output_data": True}],
        )

    async def test_setup_valid_with_push_input_data_and_push_output_data(self):
        await self.__run_setup(
            True,
            True,
            "Files were imported successfully",
            data_flows=[{"name": "InOutData", "push_input_data": True, "push_output_data": True}],
        )

    async def test_setup_open_stage_error_with_push_input_data_and_push_output_data(self):
        await self.__run_setup(
            True,
            False,
            "Test Open Stage Error",
            data_flows=[{"name": "InOutData", "push_input_data": True, "push_output_data": True}],
        )

    async def test_setup_open_stage_error_with_push_input_data_only(self):
        await self.__run_setup(
            True,
            False,
            "Test Open Stage Error",
            data_flows=[{"name": "InOutData", "push_input_data": True, "push_output_data": False}],
        )

    async def test_setup_context_error_with_push_input_data_and_push_output_data(self):
        await self.__run_setup(
            False,
            True,
            "The context 'None' doesn't exist!",
            data_flows=[{"name": "InOutData", "push_input_data": True, "push_output_data": True}],
        )

    async def test_exit_should_return_success(self):
        # Arrange
        input_file_path = OmniUrl("Test")
        output_folder_path = OmniUrl("OutputDir")

        with patch.object(omni.client, "stat") as stat_mock:
            stat_mock.side_effect = [
                (omni.client.Result.OK, MockListEntry(str(input_file_path))),
                (
                    omni.client.Result.OK,
                    MockListEntry(str(output_folder_path), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                ),
            ]

            asset_importer = AssetImporter()
            schema_data = asset_importer.Data(
                **{
                    "context_name": "",
                    "input_files": [input_file_path],
                    "output_directory": output_folder_path,
                }
            )
            parent_schema = Mock()
            parent_schema.data = schema_data
            asset_importer.set_parent_schema(parent_schema)

        # Act
        success, message = await asset_importer._on_exit(schema_data, None)  # noqa PLW0212

        # Assert
        self.assertTrue(success)
        self.assertEqual("Exit ok", message)

    async def test_exit_should_close_or_not_stage(self):
        for close_stage_on_exit in [True, False]:
            with self.subTest(name=f"Should close the stage {close_stage_on_exit}"):
                # Arrange
                input_file_path = OmniUrl("Test")
                output_folder_path = OmniUrl("OutputDir")

                with patch.object(omni.client, "stat") as stat_mock:
                    stat_mock.side_effect = [
                        (omni.client.Result.OK, MockListEntry(str(input_file_path))),
                        (
                            omni.client.Result.OK,
                            MockListEntry(str(output_folder_path), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                        ),
                    ]

                    asset_importer = AssetImporter()
                    schema_data = asset_importer.Data(
                        **{
                            "context_name": "",
                            "input_files": [input_file_path],
                            "output_directory": output_folder_path,
                            "close_stage_on_exit": close_stage_on_exit,
                        }
                    )
                    parent_schema = Mock()
                    parent_schema.data = schema_data
                    asset_importer.set_parent_schema(parent_schema)

                get_stage_mock = Mock()
                get_stage_mock.GetRootLayer = Mock()

                close_stage_mock = AsyncMock()

                context_mock = Mock()
                context_mock.get_stage = get_stage_mock
                context_mock.close_stage_async = close_stage_mock

                # Act
                with patch.object(omni.usd, "get_context") as get_context_mock, patch.object(Sdf, "_TestTakeOwnership"):
                    get_context_mock.return_value = context_mock
                    success, message = await asset_importer._on_exit(schema_data, None)  # noqa PLW0212

                    # Assert
                    self.assertEqual(close_stage_mock.called, close_stage_on_exit)

    async def __run_check(self, success: bool):
        # Arrange
        input_file_path_0 = OmniUrl("./Test0.fbx")
        input_file_path_1 = OmniUrl("./Test1.fbx")
        input_file_path_2 = OmniUrl("./Test2.fbx")
        input_files = [input_file_path_0, input_file_path_1, input_file_path_2]

        output_folder_path = OmniUrl("./TestOutput")

        with (
            patch.object(omni.client, "stat") as stat_mock,
            patch.object(AssetImporterModel, "__init__") as asset_importer_model_mock,
        ):
            stat_mock.side_effect = [
                (omni.client.Result.OK, MockListEntry(str(input_file_path_0))),
                (omni.client.Result.OK, MockListEntry(str(input_file_path_1))),
                (omni.client.Result.OK, MockListEntry(str(input_file_path_2))),
                (
                    omni.client.Result.OK,
                    MockListEntry(str(output_folder_path), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                ),
            ]

            asset_importer_model_mock.side_effect = [None, None if success else ValueError("Error"), None]

            asset_importer = AssetImporter()
            schema_data = asset_importer.Data(
                **{
                    "context_name": "",
                    "input_files": input_files,
                    "output_directory": output_folder_path,
                    "ignore_unbound_bones": True,
                }
            )
            parent_schema = Mock()
            parent_schema.data = schema_data
            asset_importer.set_parent_schema(parent_schema)

            # Act
            is_valid, message = await asset_importer._check(schema_data, None)  # noqa PLW0212

        # Assert
        self.assertEqual(success, is_valid)
        self.assertEqual("The selected files are valid." if success else "ERROR:\n- Error\n", message)

        for i, call_args in enumerate(asset_importer_model_mock.call_args_list):
            self.assertEqual(
                call(
                    data=[
                        {
                            "input_path": str(input_files[i]),
                            "output_path": str(output_folder_path),
                            "output_usd_extension": None,
                            "ignore_materials": False,
                            "ignore_animations": False,
                            "ignore_camera": False,
                            "ignore_light": False,
                            "single_mesh": False,
                            "smooth_normals": True,
                            "export_preview_surface": False,
                            "support_point_instancer": False,
                            "embed_mdl_in_usd": True,
                            "use_meter_as_world_unit": False,
                            "create_world_as_default_root_prim": True,
                            "embed_textures": True,
                            "convert_fbx_to_y_up": False,
                            "convert_fbx_to_z_up": False,
                            "convert_stage_up_y": False,
                            "convert_stage_up_z": False,
                            "keep_all_materials": False,
                            "merge_all_meshes": False,
                            "use_double_precision_to_usd_transform_op": False,
                            "ignore_pivots": False,
                            "disabling_instancing": False,
                            "export_hidden_props": False,
                            "baking_scales": False,
                            "ignore_flip_rotations": False,
                            "ignore_unbound_bones": True,
                            "bake_material": False,
                            "export_separate_gltf": False,
                            "export_mdl_gltf_extension": False,
                        }
                    ]
                ),
                call_args,
            )

    async def __run_setup(
        self,
        valid_context: bool,
        valid_stage: bool,
        expected_message: str,
        output_usd_extension: str = None,
        data_flows: Optional[List[Dict[Any, Any]]] = None,
    ):
        # Arrange
        input_file_path_0 = Path("./Test0.fbx")
        input_file_path_1 = Path("./Test1.fbx")
        input_file_path_2 = Path("./Test2.fbx")
        input_files = [input_file_path_0, input_file_path_1, input_file_path_2]

        output_folder_path = Path("./TestOutput")

        callback_mock = Mock()
        callback_future = asyncio.Future()
        callback_future.set_result(None)
        callback_mock.return_value = callback_future

        open_stage_future = asyncio.Future()
        open_stage_future.set_result((Mock(), None) if valid_stage else (None, expected_message))

        stage_mock = Mock()

        context_mock = Mock()
        context_mock.open_stage_async.return_value = open_stage_future
        context_mock.get_stage.return_value = stage_mock

        with (
            patch.object(omni.client, "stat") as stat_mock,
            patch.object(ImporterCore, "import_batch") as import_mock,
            patch.object(omni.usd, "get_context") as get_context_mock,
        ):
            stat_mock.side_effect = [
                (omni.client.Result.OK, MockListEntry(str(input_file_path_0))),
                (omni.client.Result.OK, MockListEntry(str(input_file_path_1))),
                (omni.client.Result.OK, MockListEntry(str(input_file_path_2))),
                (
                    omni.client.Result.OK,
                    MockListEntry(str(output_folder_path), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                ),
            ]

            import_future = asyncio.Future()
            import_future.set_result(None)
            import_mock.return_value = import_future

            get_context_mock.return_value = context_mock if valid_context else None

            asset_importer = AssetImporter()
            schema_data = asset_importer.Data(
                **{
                    "context_name": "",
                    "input_files": input_files,
                    "output_directory": output_folder_path,
                    "output_usd_extension": output_usd_extension,
                    "data_flows": data_flows,
                }
            )
            parent_schema = Mock()
            parent_schema.data = schema_data
            asset_importer.set_parent_schema(parent_schema)

            # Act
            is_valid, message, value = await asset_importer._setup(schema_data, callback_mock, None)  # noqa PLW0212

        # Assert
        self.assertEqual(valid_context and valid_stage, is_valid)
        self.assertEqual(expected_message, message)

        expected_files = [
            OmniUrl(
                (output_folder_path / f).with_suffix(f".{output_usd_extension}" if output_usd_extension else ".usd")
            )
            for f in input_files
        ]
        self.assertEqual(expected_files if valid_context and valid_stage else None, value)

        data_flow_result = [
            data_flow_r.model_dump(serialize_as_any=True) for data_flow_r in schema_data.data_flows or []
        ]

        data_flow_expected_result = []
        if data_flows:
            for data_flow, _data_flow_result in zip(data_flows, data_flow_result):
                if data_flow.get("push_input_data"):
                    data_flow["input_data"] = (
                        [str(input_file) for input_file in input_files]
                        if valid_context and valid_stage
                        else [str(input_files[0])]
                    )
                if data_flow.get("push_output_data"):
                    data_flow["output_data"] = (
                        [str(expected_file) for expected_file in expected_files]
                        if valid_context and valid_stage
                        else [str(expected_files[0])]
                    )
                data = _data_flow_result.copy()
                data.update(data_flow)
                data_flow_expected_result.append(data)

        self.assertEqual(
            data_flow_result,
            data_flow_expected_result,
        )

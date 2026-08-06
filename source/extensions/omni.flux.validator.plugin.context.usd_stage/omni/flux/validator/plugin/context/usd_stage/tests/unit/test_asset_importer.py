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

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import AsyncMock, Mock, call, patch

import omni.client
import omni.kit
import omni.kit.test
import omni.usd
from omni.flux.asset_importer.core import AssetImporterModel, ImporterCore
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.validator.plugin.context.usd_stage.asset_importer import AssetImporter
from pxr import Sdf, Usd, UsdShade


class MockValidationInfo:
    """Mock for pydantic's ValidationInfo."""

    def __init__(self, data):
        self.data = data


class MockListEntry:
    def __init__(self, path: str, flags=omni.client.ItemFlags.READABLE_FILE):
        self.relative_path = path
        self.flags = flags


def _stat_side_effect(results: list[tuple[omni.client.Result, MockListEntry]]):
    remaining_results = list(results)

    def _stat(path: str, *_args, **_kwargs):
        if remaining_results:
            return remaining_results.pop(0)
        return omni.client.Result.OK, MockListEntry(str(path))

    return _stat


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

    async def test_data_invalid_normal_map_convention_should_raise_value_error(self):
        # Arrange
        input_file = OmniUrl("./Test.fbx")

        with patch.object(omni.client, "stat") as stat_mock, self.assertRaises(ValueError):
            stat_mock.return_value = (omni.client.Result.OK, MockListEntry(str(input_file)))

            # Act
            AssetImporter.Data(
                context_name="",
                input_files=[input_file],
                normal_map_convention="INVALID",
                output_directory=OmniUrl("./Output"),
            )

    async def test_data_normal_map_convention_when_omitted_should_preserve_imported_value(self):
        # Arrange
        input_file = OmniUrl("./Test.fbx")

        with patch.object(omni.client, "stat") as stat_mock:
            stat_mock.return_value = (omni.client.Result.OK, MockListEntry(str(input_file)))

            # Act
            data = AssetImporter.Data(
                context_name="",
                input_files=[input_file],
                output_directory=OmniUrl("./Output"),
            )

        # Assert
        self.assertIsNone(data.normal_map_convention)
        self.assertIsNone(AssetImporter._get_normal_map_convention(data))

    async def test_data_normal_map_convention_with_supported_type_should_return_selected_type(self):
        for convention in (TextureTypes.NORMAL_OGL, TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OTH):
            with self.subTest(title=f"normal_map_convention={convention.name}"):
                # Arrange
                input_file = OmniUrl("./Test.fbx")

                with patch.object(omni.client, "stat") as stat_mock:
                    stat_mock.return_value = (omni.client.Result.OK, MockListEntry(str(input_file)))

                    # Act
                    data = AssetImporter.Data(
                        context_name="",
                        input_files=[input_file],
                        normal_map_convention=convention,
                        output_directory=OmniUrl("./Output"),
                    )

                # Assert
                self.assertEqual(convention.name, data.normal_map_convention)
                self.assertEqual(convention, AssetImporter._get_normal_map_convention(data))

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

    async def test_setup_normal_map_convention_should_apply_batch_convention_and_save_each_asset(self):
        await self.__run_setup(
            True,
            True,
            "Files were imported successfully",
            normal_map_convention=TextureTypes.NORMAL_DX,
            authored_count=1,
        )

    async def test_setup_without_normal_map_convention_should_preserve_imported_values(self):
        await self.__run_setup(
            True,
            True,
            "Files were imported successfully",
        )

    async def test_setup_normal_map_convention_save_multi_value_result_should_not_crash(self):
        await self.__run_setup(
            True,
            True,
            "Files were imported successfully",
            normal_map_convention=TextureTypes.NORMAL_OGL,
            authored_count=1,
            save_stage_extra_data=(["Test.usd"],),
        )

    async def test_mass_ui_should_render_model_selector_in_context_footer(self):
        # Arrange
        asset_importer = AssetImporter()
        schema_data = Mock()

        # Act
        with (
            patch.object(asset_importer, "_build_ui", new_callable=AsyncMock) as build_ui_mock,
            patch.object(asset_importer, "_build_normal_map_convention_ui") as build_selector_mock,
        ):
            await asset_importer._mass_build_ui(schema_data)
            footer_was_built = await asset_importer.mass_build_footer_ui(schema_data)

        # Assert
        build_ui_mock.assert_awaited_once_with(
            schema_data,
            force_build_ui=True,
            show_normal_map_convention=False,
        )
        build_selector_mock.assert_called_once_with(
            schema_data,
            label_width=asset_importer.DEFAULT_UI_WIDTH_PIXEL,
        )
        self.assertTrue(footer_was_built)

    async def test_setup_normal_map_convention_save_failure_should_stop_before_callback(self):
        await self.__run_setup(
            True,
            True,
            "Unable to save the normal map convention: Test Save Error",
            normal_map_convention=TextureTypes.NORMAL_OGL,
            authored_count=1,
            save_stage_success=False,
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
            stat_mock.side_effect = _stat_side_effect(
                [
                    (omni.client.Result.OK, MockListEntry(str(input_file_path))),
                    (
                        omni.client.Result.OK,
                        MockListEntry(str(output_folder_path), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                    ),
                ]
            )

            asset_importer = AssetImporter()
            schema_data = asset_importer.Data(
                context_name="", input_files=[input_file_path], output_directory=output_folder_path
            )
            parent_schema = Mock()
            parent_schema.data = schema_data
            asset_importer.set_parent_schema(parent_schema)

        # Act
        success, message = await asset_importer._on_exit(schema_data, None)

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
                    stat_mock.side_effect = _stat_side_effect(
                        [
                            (omni.client.Result.OK, MockListEntry(str(input_file_path))),
                            (
                                omni.client.Result.OK,
                                MockListEntry(str(output_folder_path), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                            ),
                        ]
                    )

                    asset_importer = AssetImporter()
                    schema_data = asset_importer.Data(
                        context_name="",
                        input_files=[input_file_path],
                        output_directory=output_folder_path,
                        close_stage_on_exit=close_stage_on_exit,
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
                    _success, _message = await asset_importer._on_exit(schema_data, None)

                    # Assert
                    self.assertEqual(close_stage_mock.called, close_stage_on_exit)

    async def test_apply_normal_map_convention_with_supported_type_should_author_expected_encoding(self):
        cases = (
            (TextureTypes.NORMAL_OGL, 1),
            (TextureTypes.NORMAL_DX, 2),
            (TextureTypes.NORMAL_OTH, 0),
        )
        for convention, expected_encoding in cases:
            with self.subTest(title=f"normal_map_convention={convention.name}"):
                # Arrange
                normal_shader = UsdShade.Shader.Define(self.stage, "/NormalShader")
                normal_shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset).Set(
                    Sdf.AssetPath("normal.png")
                )
                glass_normal_shader = UsdShade.Shader.Define(self.stage, "/GlassNormalShader")
                glass_normal_shader.CreateInput("normal_map_texture", Sdf.ValueTypeNames.Asset).Set(
                    Sdf.AssetPath("glass_normal.png")
                )
                unrelated_shader = UsdShade.Shader.Define(self.stage, "/UnrelatedShader")

                # Act
                authored_count = AssetImporter._apply_normal_map_convention(self.stage, convention)

                # Assert
                self.assertEqual(2, authored_count)
                self.assertEqual(expected_encoding, normal_shader.GetInput("encoding").Get())
                self.assertEqual(expected_encoding, glass_normal_shader.GetInput("encoding").Get())
                self.assertFalse(unrelated_shader.GetInput("encoding"))

    async def test_apply_normal_map_convention_should_persist_after_save_and_reopen(self):
        for convention, expected_encoding in (
            (TextureTypes.NORMAL_OGL, 1),
            (TextureTypes.NORMAL_DX, 2),
            (TextureTypes.NORMAL_OTH, 0),
        ):
            with self.subTest(title=f"normal_map_convention={convention.name}"), TemporaryDirectory() as temp_dir:
                # Arrange
                stage_path = Path(temp_dir) / f"{convention.name}.usda"
                stage = Usd.Stage.CreateNew(str(stage_path))
                normal_shader = UsdShade.Shader.Define(stage, "/NormalShader")
                normal_shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset).Set(
                    Sdf.AssetPath("normal.png")
                )

                # Act
                AssetImporter._apply_normal_map_convention(stage, convention)
                stage.GetRootLayer().Save()
                reopened_stage = Usd.Stage.Open(str(stage_path))

                # Assert
                reopened_shader = UsdShade.Shader(reopened_stage.GetPrimAtPath("/NormalShader"))
                self.assertEqual(expected_encoding, reopened_shader.GetInput("encoding").Get())

    async def test_apply_normal_map_convention_should_target_root_and_restore_edit_target(self):
        # Arrange
        normal_shader = UsdShade.Shader.Define(self.stage, "/NormalShader")
        normal_shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("normal.png"))
        session_layer = self.stage.GetSessionLayer()
        self.stage.SetEditTarget(session_layer)

        # Act
        authored_count = AssetImporter._apply_normal_map_convention(self.stage, TextureTypes.NORMAL_DX)

        # Assert
        encoding_path = normal_shader.GetPrim().GetPath().AppendProperty("inputs:encoding")
        self.assertEqual(1, authored_count)
        self.assertEqual(2, normal_shader.GetInput("encoding").Get())
        self.assertEqual(session_layer, self.stage.GetEditTarget().GetLayer())
        self.assertIsNotNone(self.stage.GetRootLayer().GetAttributeAtPath(encoding_path))
        self.assertIsNone(session_layer.GetAttributeAtPath(encoding_path))

    async def test_apply_normal_map_convention_should_skip_empty_and_override_dependency_normal_maps(self):
        # Arrange
        empty_shader = UsdShade.Shader.Define(self.stage, "/EmptyNormalShader")
        empty_shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath())

        dependency_layer = Sdf.Layer.CreateAnonymous("normal_dependency.usda")
        dependency_stage = Usd.Stage.Open(dependency_layer)
        dependency_shader = UsdShade.Shader.Define(dependency_stage, "/DependencyNormalShader")
        dependency_shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("normal.png"))
        self.stage.GetRootLayer().subLayerPaths.append(dependency_layer.identifier)

        # Act
        authored_count = AssetImporter._apply_normal_map_convention(self.stage, TextureTypes.NORMAL_OGL)

        # Assert
        encoding_path = dependency_shader.GetPrim().GetPath().AppendProperty("inputs:encoding")
        composed_dependency_shader = UsdShade.Shader(self.stage.GetPrimAtPath("/DependencyNormalShader"))
        self.assertEqual(1, authored_count)
        self.assertFalse(empty_shader.GetInput("encoding"))
        self.assertEqual(1, composed_dependency_shader.GetInput("encoding").Get())
        self.assertIsNotNone(self.stage.GetRootLayer().GetAttributeAtPath(encoding_path))
        self.assertIsNone(dependency_layer.GetAttributeAtPath(encoding_path))

    async def test_apply_normal_map_convention_without_stage_should_return_zero(self):
        # Arrange
        stage = None

        # Act
        authored_count = AssetImporter._apply_normal_map_convention(stage, TextureTypes.NORMAL_OGL)

        # Assert
        self.assertEqual(0, authored_count)

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
            stat_mock.side_effect = _stat_side_effect(
                [
                    (omni.client.Result.OK, MockListEntry(str(input_file_path_0))),
                    (omni.client.Result.OK, MockListEntry(str(input_file_path_1))),
                    (omni.client.Result.OK, MockListEntry(str(input_file_path_2))),
                    (
                        omni.client.Result.OK,
                        MockListEntry(str(output_folder_path), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                    ),
                ]
            )

            asset_importer_model_mock.side_effect = [None, None if success else ValueError("Error"), None]

            asset_importer = AssetImporter()
            schema_data = asset_importer.Data(
                context_name="", input_files=input_files, output_directory=output_folder_path, ignore_unbound_bones=True
            )
            parent_schema = Mock()
            parent_schema.data = schema_data
            asset_importer.set_parent_schema(parent_schema)

            # Act
            is_valid, message = await asset_importer._check(schema_data, None)

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
        data_flows: list[dict[Any, Any]] | None = None,
        normal_map_convention: TextureTypes | None = None,
        authored_count: int = 0,
        save_stage_success: bool = True,
        save_stage_extra_data: tuple[Any, ...] = (),
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
        save_stage_future = asyncio.Future()
        save_stage_future.set_result(
            (
                save_stage_success,
                None if save_stage_success else "Test Save Error",
                *save_stage_extra_data,
            )
        )
        context_mock.save_stage_async.return_value = save_stage_future

        with (
            patch.object(omni.client, "stat") as stat_mock,
            patch.object(ImporterCore, "import_batch") as import_mock,
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(
                AssetImporter,
                "_apply_normal_map_convention",
                return_value=authored_count,
            ) as apply_convention_mock,
        ):
            stat_mock.side_effect = _stat_side_effect(
                [
                    (omni.client.Result.OK, MockListEntry(str(input_file_path_0))),
                    (omni.client.Result.OK, MockListEntry(str(input_file_path_1))),
                    (omni.client.Result.OK, MockListEntry(str(input_file_path_2))),
                    (
                        omni.client.Result.OK,
                        MockListEntry(str(output_folder_path), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                    ),
                ]
            )

            import_future = asyncio.Future()
            import_future.set_result(None)
            import_mock.return_value = import_future

            get_context_mock.return_value = context_mock if valid_context else None

            asset_importer = AssetImporter()
            schema_data = asset_importer.Data(
                context_name="",
                input_files=input_files,
                output_directory=output_folder_path,
                output_usd_extension=output_usd_extension,
                data_flows=data_flows,
                normal_map_convention=normal_map_convention,
            )
            parent_schema = Mock()
            parent_schema.data = schema_data
            asset_importer.set_parent_schema(parent_schema)

            # Act
            is_valid, message, value = await asset_importer._setup(schema_data, callback_mock, None)

        # Assert
        expected_success = (
            valid_context
            and valid_stage
            and (normal_map_convention is None or save_stage_success or authored_count == 0)
        )
        self.assertEqual(expected_success, is_valid)
        self.assertEqual(expected_message, message)

        expected_files = [
            OmniUrl(
                (output_folder_path / f).with_suffix(f".{output_usd_extension}" if output_usd_extension else ".usd")
            )
            for f in input_files
        ]
        self.assertEqual(expected_files if expected_success else None, value)
        self.assertEqual(len(input_files) if expected_success else 0, callback_mock.call_count)

        expected_apply_count = 0
        if valid_context and valid_stage and normal_map_convention is not None:
            expected_apply_count = 1 if authored_count and not save_stage_success else len(input_files)
        self.assertEqual(
            [call(stage_mock, normal_map_convention)] * expected_apply_count,
            apply_convention_mock.call_args_list,
        )

        expected_save_count = 0
        if valid_context and valid_stage and normal_map_convention is not None and authored_count:
            expected_save_count = len(input_files) if save_stage_success else 1
        self.assertEqual(expected_save_count, context_mock.save_stage_async.call_count)

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

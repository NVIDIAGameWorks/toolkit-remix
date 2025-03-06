# noqa PLC0302
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
from pathlib import Path
from unittest.mock import Mock, PropertyMock, call, patch

import carb
import omni.kit.commands
import omni.kit.test
from lightspeed.layer_manager.core import (
    LSS_LAYER_MOD_DEPENDENCIES,
    LSS_LAYER_MOD_NAME,
    LSS_LAYER_MOD_NOTES,
    LSS_LAYER_MOD_VERSION,
)
from lightspeed.trex.packaging.core import PackagingCore
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.material_converter.utils import MaterialConverterUtils
from omni.kit.usd.collect.omni_client_wrapper import OmniClientWrapper
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf, UsdUtils


class TestPackagingCoreUnit(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.maxDiff = None

    async def test_package_unexpected_exception_should_be_caught_and_trigger_packaging_completed_event(self):
        # Arrange
        packaging_core = PackagingCore()

        with (
            patch("lightspeed.trex.packaging.core.packaging._ModPackagingSchema") as model_mock,
            patch.object(PackagingCore, "_initialize_usd_stage") as init_usd_mock,
            patch.object(PackagingCore, "_packaging_completed") as completed_mock,
        ):
            exception = RuntimeError("Test Exception")
            model_mock.side_effect = exception

            # Act
            await packaging_core.package_async_with_exceptions({})

        # Assert
        self.assertEqual(0, init_usd_mock.call_count)
        self.assertEqual(1, completed_mock.call_count)
        self.assertEqual(call([str(exception)], []), completed_mock.call_args)

    async def test_package_no_root_layer_should_warn_and_quick_return(self):
        # Arrange
        packaging_core = PackagingCore()

        with (
            patch("lightspeed.trex.packaging.core.packaging._ModPackagingSchema") as model_mock,
            patch.object(PackagingCore, "_initialize_usd_stage") as init_usd_mock,
            patch.object(carb, "log_warn") as warn_mock,
        ):
            model_mock.return_value.mod_layer_paths = [Mock()]
            model_mock.return_value.selected_layer_paths = [Mock()]

            # Act
            await packaging_core.package_async_with_exceptions({})

        # Assert
        self.assertEqual(0, init_usd_mock.call_count)
        self.assertEqual(1, warn_mock.call_count)
        self.assertEqual(call("The root-level mod layer was not selected. Nothing to package."), warn_mock.call_args)

    async def test_package_no_stage_should_raise_runtime_error(self):
        # Arrange
        packaging_core = PackagingCore()

        root_mod_mock = Mock()
        context_name_mock = Mock()

        with (
            patch("lightspeed.trex.packaging.core.packaging._ModPackagingSchema") as model_mock,
            patch.object(PackagingCore, "_initialize_usd_stage") as init_usd_mock,
            patch.object(PackagingCore, "_packaging_completed") as completed_mock,
        ):
            model_mock.return_value.mod_layer_paths = [root_mod_mock]
            model_mock.return_value.selected_layer_paths = [root_mod_mock]
            model_mock.return_value.context_name = context_name_mock

            if sys.version_info.minor > 7:
                init_usd_mock.return_value = None
            else:
                none_future = asyncio.Future()
                none_future.set_result(None)
                init_usd_mock.return_value = none_future

            # Act
            await packaging_core.package_async_with_exceptions({})

        # Assert
        self.assertEqual(1, init_usd_mock.call_count)
        self.assertEqual(call(context_name_mock, str(root_mod_mock)), init_usd_mock.call_args)

        self.assertEqual(1, completed_mock.call_count)
        self.assertEqual(call(["No stage is available in the current context."], []), completed_mock.call_args)

    async def test_package_no_root_mod_layer_should_raise_runtime_error(self):
        # Arrange
        packaging_core = PackagingCore()

        root_mod_mock = Mock()

        with (
            patch("lightspeed.trex.packaging.core.packaging._ModPackagingSchema") as model_mock,
            patch.object(PackagingCore, "_initialize_usd_stage") as init_usd_mock,
            patch.object(PackagingCore, "_packaging_completed") as completed_mock,
            patch.object(Sdf.Layer, "FindOrOpen") as find_open_mock,
        ):
            model_mock.return_value.mod_layer_paths = [root_mod_mock]
            model_mock.return_value.selected_layer_paths = [root_mod_mock]

            if sys.version_info.minor > 7:
                init_usd_mock.return_value = Mock()
            else:
                stage_future = asyncio.Future()
                stage_future.set_result(Mock())
                init_usd_mock.return_value = stage_future

            find_open_mock.return_value = None

            # Act
            await packaging_core.package_async_with_exceptions({})

        # Assert
        self.assertEqual(1, find_open_mock.call_count)
        self.assertEqual(call(str(root_mod_mock)), find_open_mock.call_args)

        self.assertEqual(1, completed_mock.call_count)
        self.assertEqual(
            call([f"Unable to open the root mod layer at path: {root_mod_mock}"], []), completed_mock.call_args
        )

    async def test_package_no_exported_mod_layer_should_add_error(self):
        # Arrange
        packaging_core = PackagingCore()

        root_mod_mock = Mock(name="root_mod")
        temp_root_mod_mock = Mock(name="temp_root_mod")

        mod_layer_mock = Mock()
        mod_layer_mock.customLayerData = {}

        with (
            patch("lightspeed.trex.packaging.core.packaging._ModPackagingSchema") as model_mock,
            patch.object(PackagingCore, "_initialize_usd_stage") as init_usd_mock,
            patch.object(PackagingCore, "_filter_sublayers") as filter_mock,
            patch.object(PackagingCore, "_get_redirected_dependencies") as redirect_mock,
            patch.object(PackagingCore, "_make_temp_layer") as make_temp_mock,
            patch.object(PackagingCore, "_collect") as collect_mock,
            patch.object(PackagingCore, "_update_layer_metadata") as update_metadata_mock,
            patch.object(PackagingCore, "_packaging_completed") as completed_mock,
            patch.object(Sdf.Layer, "FindOrOpen") as find_open_mock,
        ):
            model_mock.return_value.mod_layer_paths = [root_mod_mock]
            model_mock.return_value.selected_layer_paths = [root_mod_mock]

            if sys.version_info.minor > 7:
                init_usd_mock.return_value = Mock()
                make_temp_mock.return_value = temp_root_mod_mock
                filter_mock.return_value = []
                collect_mock.return_value = ([], [])
            else:
                stage_future = asyncio.Future()
                stage_future.set_result(Mock())
                init_usd_mock.return_value = stage_future

                make_temp_future = asyncio.Future()
                make_temp_future.set_result(temp_root_mod_mock)
                make_temp_mock.return_value = make_temp_future

                filter_future = asyncio.Future()
                filter_future.set_result([])
                filter_mock.return_value = filter_future

                collect_future = asyncio.Future()
                collect_future.set_result([])
                collect_mock.return_value = collect_future

            update_metadata_mock.return_value = []
            redirect_mock.return_value = ([], [])

            find_open_mock.side_effect = [mod_layer_mock, temp_root_mod_mock, None]

            # Act
            await packaging_core.package_async_with_exceptions({})

        # Assert
        self.assertEqual(1, completed_mock.call_count)
        self.assertEqual(call(["Unable to find the exported mod file."], []), completed_mock.call_args)

    async def test_package_should_filter_redirect_and_collect_then_trigger_packaging_complete_event(self):
        # Arrange
        packaging_core = PackagingCore()

        root_mod_mock = Mock()
        context_name_mock = Mock()
        output_directory_mock = Mock()

        temp_layers_mock = [Mock()]

        mod_layer_mock = Mock(name="mod_layer")
        mod_layer_mock.customLayerData = {}

        temp_mod_layer_mock = Mock(name="temp_mod_layer")

        exported_mod_layer_mock = Mock(name="exported_mod_layer")
        exported_mod_layer_mock.customLayerData = {}

        dependencies_mock = [Mock()]
        redirected_mock = [Mock()]

        with (
            patch("lightspeed.trex.packaging.core.packaging._ModPackagingSchema") as model_mock,
            patch.object(PackagingCore, "_initialize_usd_stage") as init_usd_mock,
            patch.object(PackagingCore, "_filter_sublayers") as filter_mock,
            patch.object(PackagingCore, "_get_redirected_dependencies") as redirect_mock,
            patch.object(PackagingCore, "_collect") as collect_mock,
            patch.object(PackagingCore, "_packaging_completed") as completed_mock,
            patch.object(PackagingCore, "_update_layer_metadata") as update_metadata_mock,
            patch.object(Sdf.Layer, "FindOrOpen") as find_open_mock,
            patch.object(Sdf.Layer, "OpenAsAnonymous"),
        ):
            model_mock.return_value.mod_layer_paths = [root_mod_mock]
            model_mock.return_value.selected_layer_paths = [root_mod_mock]
            model_mock.return_value.context_name = context_name_mock
            model_mock.return_value.output_directory = output_directory_mock
            model_mock.return_value.ignored_errors = []

            if sys.version_info.minor > 7:
                init_usd_mock.return_value = Mock()
                filter_mock.return_value = temp_layers_mock
                collect_mock.return_value = ([], [])
            else:
                stage_future = asyncio.Future()
                stage_future.set_result(Mock())
                init_usd_mock.return_value = stage_future

                filter_future = asyncio.Future()
                filter_future.set_result(temp_layers_mock)
                filter_mock.return_value = filter_future

                collect_future = asyncio.Future()
                collect_future.set_result([])
                collect_mock.return_value = collect_future

            redirect_mock.return_value = (dependencies_mock, redirected_mock)

            find_open_mock.side_effect = [mod_layer_mock, temp_mod_layer_mock, exported_mod_layer_mock]

            # Act
            await packaging_core.package_async_with_exceptions({})

        # Assert
        self.assertEqual(1, completed_mock.call_count)
        self.assertEqual(call([], []), completed_mock.call_args)

        self.assertEqual(1, init_usd_mock.call_count)
        self.assertEqual(1, filter_mock.call_count)
        self.assertEqual(1, redirect_mock.call_count)
        self.assertEqual(1, collect_mock.call_count)
        self.assertEqual(2, update_metadata_mock.call_count)

        self.assertEqual(call(context_name_mock, str(root_mod_mock)), init_usd_mock.call_args)
        self.assertEqual(
            call(context_name_mock, None, temp_mod_layer_mock, [OmniUrl(root_mod_mock).path.lower()]),
            filter_mock.call_args,
        )
        self.assertEqual(call(temp_mod_layer_mock, []), redirect_mock.call_args)
        self.assertEqual(
            call(
                init_usd_mock.return_value,
                temp_mod_layer_mock,
                temp_layers_mock,
                output_directory_mock,
                redirected_mock,
                [],
            ),
            collect_mock.call_args,
        )
        self.assertEqual(
            call(model_mock(), exported_mod_layer_mock, dependencies_mock, True), update_metadata_mock.call_args_list[0]
        )
        self.assertEqual(
            call(model_mock(), mod_layer_mock, dependencies_mock, False), update_metadata_mock.call_args_list[1]
        )

    async def test_cancel_should_set_cancel_token(self):
        # Arrange
        packaging_core = PackagingCore()
        packaging_core._cancel_token = False  # noqa PLW0212

        # Act
        packaging_core.cancel()

        # Assert
        self.assertTrue(packaging_core._cancel_token)  # noqa PLW0212

    async def test_current_count_should_return_current_count(self):
        # Arrange
        expected_val = 12345

        packaging_core = PackagingCore()
        packaging_core._current_count = expected_val  # noqa PLW0212

        # Act
        val = packaging_core.current_count

        # Assert
        self.assertEqual(expected_val, val)

    async def test_current_count_setter_should_set_current_count_max_total_value_and_trigger_packaging_progress_event(
        self,
    ):
        # Arrange
        packaging_core = PackagingCore()
        packaging_core._current_count = 0  # noqa PLW0212
        packaging_core._total_count = 1  # noqa PLW0212

        with patch.object(PackagingCore, "_packaging_progress") as progress_mock:
            # Act
            packaging_core.current_count = 12345

        # Assert
        self.assertEqual(1, packaging_core._current_count)  # noqa PLW0212

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(), progress_mock.call_args)

    async def test_total_count_should_return_total_count(self):
        # Arrange
        expected_val = 12345

        packaging_core = PackagingCore()
        packaging_core._total_count = expected_val  # noqa PLW0212

        # Act
        val = packaging_core.total_count

        # Assert
        self.assertEqual(expected_val, val)

    async def test_total_count_setter_should_set_total_count_and_trigger_packaging_progress_event(self):
        # Arrange
        expected_val = 12345

        packaging_core = PackagingCore()
        packaging_core._current_count = 1  # noqa PLW0212
        packaging_core._total_count = 0  # noqa PLW0212

        with patch.object(PackagingCore, "_packaging_progress") as progress_mock:
            # Act
            packaging_core.total_count = expected_val

        # Assert
        self.assertEqual(expected_val, packaging_core._total_count)  # noqa PLW0212

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(), progress_mock.call_args)

    async def test_status_should_return_status(self):
        # Arrange
        expected_val = "Doing something"

        packaging_core = PackagingCore()
        packaging_core._status = expected_val  # noqa PLW0212

        # Act
        val = packaging_core.status

        # Assert
        self.assertEqual(expected_val, val)

    async def test_initialize_usd_stage_no_context_should_create_context_and_return_stage(self):
        await self.__run_initialize_usd(False)

    async def test_initialize_usd_stage_existing_context_should_return_stage(self):
        await self.__run_initialize_usd(True)

    async def test_filter_sublayers_cancel_token_was_set_should_quick_return(self):
        # Arrange
        packaging_core = PackagingCore()
        packaging_core._cancel_token = True  # noqa PLW0212

        selected_layer_mock = Mock()

        # Act
        await packaging_core._filter_sublayers(Mock(), Mock(), Mock(), [selected_layer_mock])  # noqa PLW0212

        # Assert
        self.assertEqual(0, selected_layer_mock.identifier.call_count)

    async def test_filter_sublayers_should_recursively_remove_non_selected_sublayers_and_return_remaining_layers(self):
        # Arrange
        packaging_core = PackagingCore()

        layer_0_mock = Mock(name="layer_0")
        layer_1_mock = Mock(name="layer_1")
        layer_2_mock = Mock(name="layer_2")
        layer_3_mock = Mock(name="layer_3")
        layer_4_mock = Mock(name="layer_4")

        layer_0_identifier_mock = "layer_0_identifier"
        layer_1_identifier_mock = "layer_1_identifier"
        layer_2_identifier_mock = "layer_2_identifier"
        layer_3_identifier_mock = "layer_3_identifier"
        layer_4_identifier_mock = "layer_4_identifier"

        layer_0_mock.identifier = layer_0_identifier_mock
        layer_1_mock.identifier = layer_1_identifier_mock
        layer_2_mock.identifier = layer_2_identifier_mock
        layer_3_mock.identifier = layer_3_identifier_mock
        layer_4_mock.identifier = layer_4_identifier_mock

        layer_0_mock.subLayerPaths = [layer_1_identifier_mock, layer_2_identifier_mock]
        layer_1_mock.subLayerPaths = [layer_3_identifier_mock]
        layer_2_mock.subLayerPaths = []
        layer_3_mock.subLayerPaths = [layer_4_identifier_mock]
        layer_4_mock.subLayerPaths = []

        position_mock = 1

        context_name_mock = Mock()
        selected_layer_paths_mocks = [layer_0_identifier_mock, layer_1_identifier_mock, layer_3_identifier_mock]

        layer_1_temp_identifier = Mock()
        layer_1_temp_mock = Mock()
        layer_1_temp_mock.identifier = layer_1_temp_identifier

        layer_2_temp_identifier = Mock()
        layer_2_temp_mock = Mock()
        layer_2_temp_mock.identifier = layer_2_temp_identifier

        layer_3_temp_identifier = Mock()
        layer_3_temp_mock = Mock()
        layer_3_temp_mock.identifier = layer_3_temp_identifier

        layer_4_temp_identifier = Mock()
        layer_4_temp_mock = Mock()
        layer_4_temp_mock.identifier = layer_4_temp_identifier

        with (
            patch.object(PackagingCore, "_make_temp_layer") as make_temp_mock,
            patch.object(PackagingCore, "_get_original_path") as get_original_mock,
            patch.object(LayerUtils, "get_sublayer_position_in_parent") as get_position_mock,
            patch.object(omni.kit.commands, "execute") as execute_mock,
            patch.object(Sdf.Layer, "FindOrOpen") as find_open_mock,
        ):
            get_position_mock.return_value = position_mock

            if sys.version_info.minor > 7:
                make_temp_mock.side_effect = [
                    layer_1_temp_mock,
                    layer_2_temp_mock,
                    layer_3_temp_mock,
                    layer_4_temp_mock,
                ]
            else:
                layer_1_temp_future = asyncio.Future()
                layer_1_temp_future.set_result(layer_1_temp_mock)

                layer_2_temp_future = asyncio.Future()
                layer_2_temp_future.set_result(layer_2_temp_mock)

                layer_3_temp_future = asyncio.Future()
                layer_3_temp_future.set_result(layer_3_temp_mock)

                layer_4_temp_future = asyncio.Future()
                layer_4_temp_future.set_result(layer_4_temp_mock)

                make_temp_mock.side_effect = [
                    layer_1_temp_future,
                    layer_3_temp_future,
                    layer_4_temp_future,
                    layer_2_temp_future,
                ]
            get_original_mock.side_effect = [
                layer_0_identifier_mock,
                layer_1_identifier_mock,
                layer_3_identifier_mock,
                layer_4_identifier_mock,
                layer_2_identifier_mock,
            ]
            find_open_mock.side_effect = [layer_1_mock, layer_3_mock, layer_4_mock, layer_2_mock]

            # Act
            await packaging_core._filter_sublayers(  # noqa PLW0212
                context_name_mock, None, layer_0_mock, selected_layer_paths_mocks
            )

        # Assert
        self.assertEqual(2, get_position_mock.call_count)
        self.assertEqual(2, execute_mock.call_count)
        self.assertEqual(4, find_open_mock.call_count)

        self.assertListEqual(
            [
                call(layer_3_identifier_mock, layer_4_identifier_mock),
                call(layer_0_identifier_mock, layer_2_identifier_mock),
            ],
            get_position_mock.call_args_list,
        )
        self.assertListEqual(
            [
                call(
                    "RemoveSublayerCommand",
                    layer_identifier=layer_3_identifier_mock,
                    sublayer_position=position_mock,
                    usd_context=context_name_mock,
                ),
                call(
                    "RemoveSublayerCommand",
                    layer_identifier=layer_0_identifier_mock,
                    sublayer_position=position_mock,
                    usd_context=context_name_mock,
                ),
            ],
            execute_mock.call_args_list,
        )
        self.assertListEqual(
            [
                call(layer_1_temp_mock),
                call(layer_2_temp_mock),
                call(layer_3_temp_mock),
                call(layer_4_temp_mock),
            ],
            find_open_mock.call_args_list,
        )

    async def test_get_redirected_dependencies_cancel_token_was_set_should_quick_return(self):
        await self.__run_get_redirected_dependencies(True)

    async def test_get_redirected_dependencies_should_return_mod_dependencies_and_known_redirected_dependencies(self):
        await self.__run_get_redirected_dependencies(False)

    async def test_collect_cancel_token_was_set_should_quick_return_errors(self):
        await self.__run_collect(True, True)
        await self.__run_collect(True, False)

    async def test_collect_unresolved_paths_should_quick_return_errors(self):
        await self.__run_collect(False, True)

    async def test_collect_should_modify_asset_paths_create_output_directory_and_export_layers_and_copy_dependencies(
        self,
    ):
        await self.__run_collect(False, False)

    async def test_update_layer_metadata_update_dependencies_should_update_metadata(self):
        await self.__run_update_layer_metadata(True, False)

    async def test_update_layer_metadata_no_update_dependencies_should_update_metadata_without_dependencies(self):
        await self.__run_update_layer_metadata(False, False)

    async def test_update_layer_metadata_invalid_dependency_should_return_errors(self):
        await self.__run_update_layer_metadata(False, True)
        await self.__run_update_layer_metadata(True, True)

    async def test_update_layer_metadata_cancel_token_set_should_quick_return(self):
        # Arrange
        packaging_core = PackagingCore()
        packaging_core._cancel_token = True  # noqa PLW0212

        model = Mock()
        layer = Mock()
        dependencies = {Mock(), Mock()}

        with patch.object(Sdf.Layer, "OpenAsAnonymous") as open_anonymous_mock:
            # Act
            packaging_core._update_layer_metadata(model, layer, dependencies, True)  # noqa PLW0212

        # Assert
        self.assertEqual(0, open_anonymous_mock.call_count)

    async def test_redirect_to_existing_project_should_replace_deps_with_relative_path(self):
        # Arrange
        packaging_core = PackagingCore()

        path_0 = "./deps/mods/Mod0/mod.usd"
        path_1 = "./assets/wall.usd"

        expected_0 = "./../../mods/Mod0/mod.usd"
        expected_1 = path_1

        # Act
        val_0 = packaging_core._redirect_to_existing_project(Mock(), path_0)  # noqa PLW0212
        val_1 = packaging_core._redirect_to_existing_project(Mock(), path_1)  # noqa PLW0212

        # Assert
        self.assertEqual(expected_0, val_0)
        self.assertEqual(expected_1, val_1)

    async def test_redirect_inside_package_directory_absolute_path_should_change_to_subusds_relative_path_and_mark_dependencies_for_collection(  # noqa E501
        self,
    ):
        await self.__run_redirect_inside_package_directory(True, False)

    async def test_redirect_inside_package_directory_outside_output_path_should_move_to_subusds_and_mark_dependencies_for_collection(  # noqa E501
        self,
    ):
        await self.__run_redirect_inside_package_directory(False, True)

    async def test_redirect_inside_package_directory_valid_should_return_original_value_and_mark_dependencies_for_collection(  # noqa E501
        self,
    ):
        await self.__run_redirect_inside_package_directory(False, False)

    async def test_modify_asset_paths_does_not_exist_should_return_original_path(self):
        await self.__run_modify_asset_paths(False, True, False)
        await self.__run_modify_asset_paths(False, False, False)

    async def test_modify_asset_paths_not_in_dependency_updates_should_return_original_path(self):
        await self.__run_modify_asset_paths(True, False, False)

    async def test_modify_asset_paths_in_dependency_updates_relative_path_should_return_modified_path(self):
        await self.__run_modify_asset_paths(True, True, False)

    async def test_modify_asset_paths_in_dependency_updates_absolute_path_should_return_modified_path(self):
        await self.__run_modify_asset_paths(True, True, True)

    async def test_simplify_relative_path_starting_with_relative_should_return_original(self):
        # Arrange
        packaging_core = PackagingCore()
        input_val = "../../../../test/path"

        # Act
        val = packaging_core._simplify_relative_path(input_val)  # noqa PLW0212

        # Assert
        self.assertEqual(input_val, val)

    async def test_simplify_relative_path_many_relatives_grouped_should_only_remove_available_parts(self):
        # Arrange
        packaging_core = PackagingCore()

        input_val_0 = "C:/parent/parent2/./parent3/../../test/path"
        output_val_0 = "C:/parent/test/path"

        input_val_1 = "C:/parent/parent2/parent3/../../../../../../test/path"
        output_val_1 = "C:/../../../test/path"

        input_val_2 = "./././././single_dir"
        output_val_2 = "./single_dir"

        # Act
        val_0 = packaging_core._simplify_relative_path(input_val_0)  # noqa PLW0212
        val_1 = packaging_core._simplify_relative_path(input_val_1)  # noqa PLW0212
        val_2 = packaging_core._simplify_relative_path(input_val_2)  # noqa PLW0212

        # Assert
        self.assertEqual(output_val_0, val_0)
        self.assertEqual(output_val_1, val_1)
        self.assertEqual(output_val_2, val_2)

    async def test_simplify_relative_path_no_relatives_should_return_original(self):
        # Arrange
        packaging_core = PackagingCore()
        input_val = "C:/test/path"

        # Act
        val = packaging_core._simplify_relative_path(input_val)  # noqa PLW0212

        # Assert
        self.assertEqual(input_val, val)

    async def test_packaging_new_stage_should_set_stat_and_total_count_and_reset_current_count(self):
        # Arrange
        packaging_core = PackagingCore()
        status = "Status Test"
        total_count = 12345

        packaging_core._status = "Before"  # noqa PLW0212
        packaging_core._current_count = 999  # noqa PLW0212
        packaging_core._total_count = 999  # noqa PLW0212

        # Act
        packaging_core._packaging_new_stage(status, total_count)  # noqa PLW0212

        # Assert
        self.assertEqual(status, packaging_core._status)  # noqa PLW0212
        self.assertEqual(total_count, packaging_core._total_count)  # noqa PLW0212
        self.assertEqual(0, packaging_core._current_count)  # noqa PLW0212

    async def __run_initialize_usd(self, existing_context: bool):
        # Arrange
        packaging_core = PackagingCore()

        context_name = "TestContext"
        root_mod_layer_path_mock = Mock()

        stage_mock = Mock()

        context_mock = Mock()
        context_mock.get_stage.return_value = stage_mock

        create_context_mock = Mock()
        create_context_stage_mock = Mock()
        create_context_mock.get_stage.return_value = create_context_stage_mock

        with (
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(omni.usd, "create_context") as create_mock,
        ):
            get_context_mock.side_effect = [context_mock] if existing_context else [None, context_mock]
            create_mock.return_value = create_context_mock

            # Act
            val = await packaging_core._initialize_usd_stage(context_name, root_mod_layer_path_mock)  # noqa PLW0212

        # Assert
        self.assertEqual(stage_mock if existing_context else create_context_stage_mock, val)

        self.assertEqual(1, get_context_mock.call_count)
        self.assertEqual(call(context_name), get_context_mock.call_args)

        if existing_context:
            self.assertEqual(0, create_mock.call_count)
            self.assertEqual(1, context_mock.get_stage.call_count)
            self.assertEqual(1, context_mock.open_stage.call_count)
            self.assertEqual(0, create_context_mock.get_stage.call_count)
            self.assertEqual(0, create_context_mock.open_stage.call_count)

            self.assertEqual(call(root_mod_layer_path_mock), context_mock.open_stage.call_args)

        else:
            self.assertEqual(1, create_mock.call_count)
            self.assertEqual(0, context_mock.get_stage.call_count)
            self.assertEqual(0, context_mock.open_stage.call_count)
            self.assertEqual(1, create_context_mock.get_stage.call_count)
            self.assertEqual(1, create_context_mock.open_stage.call_count)

            self.assertEqual(call(context_name), create_mock.call_args)
            self.assertEqual(call(root_mod_layer_path_mock), create_context_mock.open_stage.call_args)

    async def __run_redirect_inside_package_directory(self, is_absolute: bool, is_outside: bool):
        # Arrange
        packaging_core = PackagingCore()
        packaging_core._collected_dependencies = {}  # noqa PLW0212

        dependency_path_mock = Mock()
        layer_path_mock = "S:/projects/Project/mod.usda"
        relative_path = "./assets/cube.usda"
        if is_absolute:
            relative_path = "C:/assets/sphere.usda"
        elif is_outside:
            relative_path = "../../../outside/pyramid.usda"

        layer_mock = Mock()
        layer_mock.identifier = layer_path_mock

        # Act
        val = packaging_core._redirect_inside_package_directory(  # noqa PLW0212
            dependency_path_mock, "S:/output_directory", layer_mock, relative_path
        )

        # Assert
        expected_val = f"./{OmniUrl(relative_path).path}"
        if is_absolute:
            expected_val = "./SubUSDs/sphere.usda"
        elif is_outside:
            expected_val = "./SubUSDs/outside/pyramid.usda"

        self.assertEqual(expected_val, val)
        self.assertDictEqual(
            {dependency_path_mock: OmniUrl(expected_val).path}, packaging_core._collected_dependencies  # noqa PLW0212
        )

    async def __run_modify_asset_paths(self, dependency_exists: bool, dependency_update: bool, is_absolute: bool):
        # Arrange
        packaging_core = PackagingCore()
        packaging_core._current_count = 0  # noqa PLW0212
        packaging_core._total_count = 9999  # noqa PLW0212

        layer_mock = Mock()
        layer_mock.identifier = "C:/Test/layer.usda"
        absolute_path = "C:/Test/assets/test.usd"
        relative_path = absolute_path if is_absolute else "./assets/test.usd"
        modified_path = "C:/modified_path"

        with patch.object(OmniUrl, "exists", new_callable=PropertyMock) as exists_mock:
            exists_mock.return_value = dependency_exists

            # Act
            val = packaging_core._modify_asset_paths(  # noqa PLW0212
                layer_mock,
                {absolute_path if dependency_update else "C:/absolute_path": lambda *_: modified_path},
                relative_path,
            )

        # Assert
        self.assertEqual(modified_path if dependency_exists and dependency_update else relative_path, val)

    async def __run_get_redirected_dependencies(self, should_cancel: bool):
        # Arrange
        packaging_core = PackagingCore()
        if should_cancel:
            packaging_core._cancel_token = True  # noqa PLW0212

        root_layer_path_mock = Mock()
        root_layer_mock = Mock()
        root_layer_mock.identifier = root_layer_path_mock

        external_mod = "C:/game/rtx-remix/mods/ExternalMod_1/mod.usda"
        external_layer = "D:/projects/Project_0/deps/mods/ExternalMod_1/mod.usda"
        external_asset = "C:/game/rtx-remix/mods/ExternalMod_1/assets/mesh_1.usd"

        layer_0_mock = Mock()
        layer_0_mock.identifier = "D:/projects/Project_0/sublayer.usda"
        layer_1_mock = Mock()
        layer_1_mock.identifier = external_layer

        layer_mocks = [layer_0_mock, layer_1_mock]
        asset_mocks = ["D:/projects/Project_0/assets/mesh_0.usd", external_asset]
        external_mod_paths = [Path("C:/game/rtx-remix/mods/ExternalMod_0/mod.usda"), Path(external_mod)]

        with patch.object(UsdUtils, "ComputeAllDependencies") as compute_dependencies_mock:
            compute_dependencies_mock.return_value = layer_mocks, asset_mocks, []

            # Act
            mod_dependencies, redirected_dependencies = packaging_core._get_redirected_dependencies(  # noqa PLW0212
                root_layer_mock, external_mod_paths
            )

        # Assert
        self.assertSetEqual(set() if should_cancel else {external_mod}, mod_dependencies)
        self.assertSetEqual(set() if should_cancel else {external_layer, external_asset}, redirected_dependencies)

    async def __run_collect(self, should_cancel: bool, has_unresolved_assets: bool):
        packaging_core = PackagingCore()
        if should_cancel:
            packaging_core._cancel_token = True  # noqa PLW0212

        layer_0_path_mock = "C:/projects/Project/mod.usda"
        layer_1_path_mock = "C:/projects/Project/sublayer.usda"

        layer_0_temp_path_mock = "C:/projects/Project/mod_temp.usda"
        layer_1_temp_path_mock = "C:/projects/Project/sublayer_temp.usda"

        layer_0_mock = Mock()
        layer_1_mock = Mock()

        layer_0_temp_mock = Mock()
        layer_1_temp_mock = Mock()

        layer_0_mock.identifier = layer_0_path_mock
        layer_1_mock.identifier = layer_1_path_mock

        layer_0_temp_mock.identifier = layer_0_temp_path_mock
        layer_1_temp_mock.identifier = layer_1_temp_path_mock

        asset_0_mock = "C:/projects/Project/assets/cube.fbx"  # Collected asset
        asset_1_mock = "C:/projects/Project/deps/mods/OtherProject/assets/sphere.dds"  # Redirected asset
        asset_2_mock = "C:/projects/Project/assets/mdl/AperturePBR_Opacity.mdl"  # Skipped shader

        asset_0_output_mock = "./assets/cube.usda"

        unresolved_dependency_mock = Mock()

        temp_layers_mock = [layer_0_temp_mock, layer_1_temp_mock]
        layers_mock = [layer_0_mock, layer_1_mock]
        assets_mock = [asset_0_mock, asset_1_mock]
        unresolved_mock = [unresolved_dependency_mock] if has_unresolved_assets else []

        root_layer_mock = Mock()
        existing_temps_mock = [layer_0_temp_path_mock]
        output_directory_mock = "S:/mods/ProjectMod"
        redirected_dependencies_mock = {asset_1_mock}

        with (
            patch.object(PackagingCore, "_get_original_path") as get_original_mock,
            patch.object(PackagingCore, "_make_temp_layer") as make_temp_mock,
            patch.object(PackagingCore, "_get_unresolved_assets_prim_paths") as get_unresolved_mock,
            patch.object(Sdf.Layer, "FindOrOpen") as find_open_mock,
            patch.object(UsdUtils, "ComputeAllDependencies") as compute_dependencies_mock,
            patch.object(UsdUtils, "ModifyAssetPaths") as modify_assets_mock,
            patch.object(MaterialConverterUtils, "get_material_library_shader_urls") as get_shaders_mock,
            patch.object(OmniClientWrapper, "create_folder") as create_folder_mock,
            patch.object(OmniClientWrapper, "delete") as delete_folder_mock,
            patch.object(OmniClientWrapper, "copy") as copy_mock,
            patch.object(OmniUrl, "exists", new_callable=PropertyMock) as exists_mock,
        ):
            compute_dependencies_mock.return_value = (layers_mock, assets_mock, unresolved_mock)
            get_shaders_mock.return_value = [OmniUrl(asset_2_mock)]

            modify_assets_mock.side_effect = lambda *_: packaging_core._collected_dependencies.update(  # noqa PLW0212
                {
                    asset_0_mock: asset_0_output_mock,
                }
            )
            get_original_mock.side_effect = [
                layer_0_path_mock,
                layer_0_path_mock,
                layer_1_path_mock,
                None,
                None,
                layer_0_path_mock,
                layer_1_path_mock,
                layer_0_path_mock,
                layer_1_path_mock,
                None,
            ]

            find_open_mock.side_effect = [layer_0_temp_mock, layer_1_temp_mock]
            exists_mock.side_effect = [True, False, True, True, False]

            stage_mock = Mock()
            stage_mock.TraverseAll.return_value = []

            unresolved_deps = {("layer", "prim", "asset")} if has_unresolved_assets else set()

            if sys.version_info.minor > 7:
                make_temp_mock.side_effect = layer_1_temp_path_mock
                get_unresolved_mock.return_value = unresolved_deps
                delete_folder_mock.return_value = None
                create_folder_mock.return_value = None
                copy_mock.return_value = None
            else:
                make_temp_future = asyncio.Future()
                make_temp_future.set_result(layer_1_temp_path_mock)
                make_temp_mock.side_effect = [make_temp_future]

                set_future = asyncio.Future()
                set_future.set_result(unresolved_deps)
                get_unresolved_mock.return_value = set_future

                none_future = asyncio.Future()
                none_future.set_result(None)
                delete_folder_mock.return_value = none_future
                create_folder_mock.return_value = none_future
                copy_mock.return_value = none_future

            # Act
            errors, unresolved_assets = await packaging_core._collect(  # noqa PLW0212
                stage_mock,
                root_layer_mock,
                existing_temps_mock,
                output_directory_mock,
                redirected_dependencies_mock,
                [],
            )

        # Assert
        self.assertListEqual(list(unresolved_deps) if not should_cancel else [], unresolved_assets)

        self.assertEqual(0 if should_cancel else 1, compute_dependencies_mock.call_count)
        if not should_cancel:
            self.assertEqual(call(root_layer_mock.identifier), compute_dependencies_mock.call_args)

        if should_cancel or has_unresolved_assets:
            self.assertEqual(0, get_shaders_mock.call_count)
            self.assertEqual(0, modify_assets_mock.call_count)
            self.assertEqual(0, delete_folder_mock.call_count)
            self.assertEqual(0, create_folder_mock.call_count)
            self.assertEqual(0, copy_mock.call_count)
            for layer_mock in temp_layers_mock:
                self.assertEqual(0, layer_mock.Export.call_count)
        else:
            self.assertEqual(1, get_shaders_mock.call_count)
            self.assertEqual(len(layers_mock), modify_assets_mock.call_count)
            self.assertEqual(1, delete_folder_mock.call_count)
            self.assertEqual(2, create_folder_mock.call_count)
            self.assertEqual(1, copy_mock.call_count)
            for layer_mock in temp_layers_mock:
                self.assertEqual(1, layer_mock.Export.call_count)

            self.assertEqual(call(output_directory_mock), delete_folder_mock.call_args)
            self.assertEqual(
                [call("S:/mods/ProjectMod"), call("S:/mods/ProjectMod/assets")], create_folder_mock.call_args_list
            )
            self.assertEqual(
                call(asset_0_mock, str(OmniUrl(output_directory_mock) / asset_0_output_mock)), copy_mock.call_args
            )
            for index, layer_mock in enumerate(temp_layers_mock):
                # Only compare the first arg since the partial function is built on the fly
                self.assertEqual(layer_mock, modify_assets_mock.call_args_list[index][0][0])
                self.assertEqual(
                    call(str(OmniUrl(output_directory_mock) / OmniUrl(layers_mock[index].identifier).name)),
                    layer_mock.Export.call_args,
                )

    async def __run_update_layer_metadata(self, update_dependencies: bool, invalid_dependencies: bool):
        # Arrange
        packaging_core = PackagingCore()

        mod_name_mock = Mock()
        mod_version_mock = Mock()
        mod_details_mock = Mock()
        model_mock = Mock()
        model_mock.mod_name = mod_name_mock
        model_mock.mod_version = mod_version_mock
        model_mock.mod_details = mod_details_mock

        dependency_mock = Mock()
        dependencies_mock = {dependency_mock}

        layer_mock = Mock()
        layer_mock.customLayerData = {}

        dependency_name_mock = Mock()
        dependency_version_mock = Mock()
        dependency_layer_mock = Mock()
        dependency_layer_mock.customLayerData = (
            {}
            if invalid_dependencies
            else {LSS_LAYER_MOD_NAME: dependency_name_mock, LSS_LAYER_MOD_VERSION: dependency_version_mock}
        )

        with patch.object(Sdf.Layer, "OpenAsAnonymous") as open_anonymous_mock:
            open_anonymous_mock.return_value = dependency_layer_mock

            # Act
            errors = packaging_core._update_layer_metadata(  # noqa PLW0212
                model_mock, layer_mock, dependencies_mock, update_dependencies
            )

        # Assert
        expected_data = {
            LSS_LAYER_MOD_NAME: mod_name_mock,
            LSS_LAYER_MOD_VERSION: mod_version_mock,
            LSS_LAYER_MOD_NOTES: mod_details_mock,
        }
        if update_dependencies:
            if invalid_dependencies:
                expected_data.update({LSS_LAYER_MOD_DEPENDENCIES: {}})
            else:
                expected_data.update({LSS_LAYER_MOD_DEPENDENCIES: {dependency_name_mock: dependency_version_mock}})

        self.assertDictEqual(expected_data, layer_mock.customLayerData)
        self.assertListEqual(
            (
                [f'Invalid mod dependency was found: "{dependency_mock}". Dependencies must to be packaged mods.']
                if update_dependencies and invalid_dependencies
                else []
            ),
            errors,
        )

        self.assertEqual(1, layer_mock.Reload.call_count)
        self.assertEqual(1, layer_mock.Save.call_count)

        self.assertEqual(1 if update_dependencies else 0, open_anonymous_mock.call_count)

        if update_dependencies:
            self.assertEqual(call(dependency_mock, metadataOnly=True), open_anonymous_mock.call_args)

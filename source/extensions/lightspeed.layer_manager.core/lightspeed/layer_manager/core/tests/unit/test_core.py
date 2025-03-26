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

import contextlib
import pathlib
import re
from types import NoneType
from typing import Union
from unittest.mock import Mock, call, patch

import omni.usd
from lightspeed.common.constants import REMIX_CAPTURE_FOLDER, REMIX_FOLDER
from lightspeed.layer_manager.core import LayerManagerCore, LayerType, LayerTypeKeys
from lightspeed.layer_manager.core.data_models import LayerManagerValidators
from lightspeed.layer_manager.core.layers.autoupscale import AutoUpscaleLayer
from lightspeed.layer_manager.core.layers.capture import CaptureLayer
from lightspeed.layer_manager.core.layers.capture_baker import CaptureBakerLayer
from lightspeed.layer_manager.core.layers.replacement import ReplacementLayer
from lightspeed.layer_manager.core.layers.workfile import WorkfileLayer
from omni.flux.layer_tree.usd.core import LayerCustomData
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path, open_stage
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf, Usd


class TestLayerManagerCore(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()

        self.layer_manager = LayerManagerCore()

    # After running each test
    async def tearDown(self):
        if self.context.can_close_stage():
            await self.context.close_stage_async()

        self.layer_manager = None
        self.context = None

    async def test_get_edit_target_should_return_edit_target(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            # Make sure the mod layer is the edit target
            mod_layer = Sdf.Layer.FindOrOpen((OmniUrl(project_url.parent_url) / "mod.usda").path)
            edit_target = Usd.EditTarget(mod_layer)
            self.context.get_stage().SetEditTarget(edit_target)

            # Act
            edit_target_layer = self.layer_manager.get_edit_target()

            # Assert
            self.assertIsNotNone(edit_target_layer)
            self.assertFalse(edit_target_layer.expired)
            self.assertEqual(edit_target_layer.identifier, mod_layer.identifier)

    async def test_set_edit_target_with_identifier_should_set_edit_target(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            stage = self.context.get_stage()

            # Make sure the project layer is the edit target
            project_layer = Sdf.Layer.FindOrOpen(project_url.path)
            edit_target = Usd.EditTarget(project_layer)
            stage.SetEditTarget(edit_target)

            mod_identifier = (OmniUrl(project_url.parent_url) / "mod.usda").path

            # Act
            self.layer_manager.set_edit_target_with_identifier(mod_identifier)

            # Assert
            edit_target_layer = stage.GetEditTarget().GetLayer()

            self.assertIsNotNone(edit_target_layer)
            self.assertFalse(edit_target_layer.expired)
            self.assertEqual(edit_target_layer.identifier, mod_identifier)

    async def test_move_layer_with_identifier_no_parent_layer_should_raise_value_error(self):
        # Arrange
        parent_identifier = r"C:\parent.test"

        # Act
        with self.assertRaises(ValueError) as cm:
            self.layer_manager.move_layer_with_identifier(
                r"C:\test.test", parent_identifier, new_parent_layer_identifier=r"C:\new_parent.test", layer_index=-1
            )

        # Assert
        self.assertEqual(str(cm.exception), f'Can\'t find the parent layer with identifier "{parent_identifier}".')

    async def test_move_layer_with_identifier_should_move_sublayer(self):
        # Arrange
        for change_parent in [True, False]:
            with self.subTest(name=f"change_parent_{change_parent}"):
                async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
                    mod_identifier = (OmniUrl(project_url.parent_url) / "mod.usda").path
                    sublayer_identifier = (OmniUrl(project_url.parent_url) / "sublayer.usda").path
                    sublayer_child_01_identifier = (OmniUrl(project_url.parent_url) / "sublayer_child_01.usda").path

                    mod_layer = Sdf.Layer.FindOrOpen(mod_identifier)
                    sublayer_layer = Sdf.Layer.FindOrOpen(sublayer_identifier)

                    # Act
                    if change_parent:
                        self.layer_manager.move_layer_with_identifier(
                            sublayer_child_01_identifier,
                            sublayer_identifier,
                            new_parent_layer_identifier=mod_identifier,
                        )
                    else:
                        self.layer_manager.move_layer_with_identifier(
                            sublayer_child_01_identifier, sublayer_identifier, layer_index=-1
                        )

                    # Assert
                    if change_parent:
                        self.assertListEqual(
                            [str(layer) for layer in mod_layer.subLayerPaths],
                            ["./sublayer_child_01.usda", "./sublayer.usda", "./mod_capture_baker.usda"],
                        )
                        self.assertListEqual(
                            [str(layer) for layer in sublayer_layer.subLayerPaths], ["./sublayer_child_02.usda"]
                        )
                    else:
                        self.assertListEqual(
                            [str(layer) for layer in mod_layer.subLayerPaths],
                            ["./sublayer.usda", "./mod_capture_baker.usda"],
                        )
                        self.assertListEqual(
                            [str(layer) for layer in sublayer_layer.subLayerPaths],
                            ["./sublayer_child_02.usda", "./sublayer_child_01.usda"],
                        )

    async def test_remove_layer_with_identifier_should_remove_sublayer(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            mod_identifier = (OmniUrl(project_url.parent_url) / "mod.usda").path
            sublayer_identifier = (OmniUrl(project_url.parent_url) / "sublayer.usda").path

            mod_layer = Sdf.Layer.FindOrOpen(mod_identifier)

            # Act
            self.layer_manager.remove_layer_with_identifier(sublayer_identifier, mod_identifier)

            # Assert
            self.assertListEqual([str(layer) for layer in mod_layer.subLayerPaths], ["./mod_capture_baker.usda"])

    async def test_mute_layer_with_identifier_should_mute_layer(self):
        # Arrange
        for mute_layer in [True, False]:
            with self.subTest(name=f"mute_layer_{mute_layer}"):
                async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
                    stage = self.context.get_stage()

                    sublayer_identifier = (OmniUrl(project_url.parent_url) / "sublayer.usda").path

                    # Make sure the layer is not muted if muting or muted if unmuting
                    if mute_layer:
                        stage.UnmuteLayer(sublayer_identifier)
                    else:
                        stage.MuteLayer(sublayer_identifier)

                    # Act
                    self.layer_manager.mute_layer_with_identifier(sublayer_identifier, mute_layer)

                    # Assert
                    self.assertEqual(stage.IsLayerMuted(sublayer_identifier), mute_layer)

    async def test_lock_layer_with_identifier_should_lock_layer(self):
        # Arrange
        for lock_layer in [True, False]:
            with self.subTest(name=f"lock_layer_{lock_layer}"):
                async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
                    # Make sure the layer is not locked if locking or locked if unlocking
                    project_layer = Sdf.Layer.FindOrOpen(project_url.path)
                    project_layer.customLayerData["omni_layer"]["locked"]["./sublayer.usda"] = not lock_layer

                    # Act
                    self.layer_manager.lock_layer_with_identifier(
                        (OmniUrl(project_url.parent_url) / "sublayer.usda").path, lock_layer
                    )

                    # Assert
                    self.assertEqual(
                        project_layer.customLayerData["omni_layer"]["locked"]["./sublayer.usda"], lock_layer
                    )

    async def test_save_layer_with_identifier_no_layer_should_raise_value_error(self):
        # Arrange
        for force_save in [True, False]:
            with self.subTest(name=f"force_save_{force_save}"):
                layer_identifier = r"C:\test.test"

                # Act
                with self.assertRaises(ValueError) as cm:
                    self.layer_manager.save_layer_with_identifier(layer_identifier, force=force_save)

                # Assert
                self.assertEqual(str(cm.exception), f'Can\'t find the layer with identifier "{layer_identifier}".')

    async def test_save_layer_with_identifier_should_save_layer(self):
        # Arrange
        for force_save in [True, False]:
            with self.subTest(name=f"force_save_{force_save}"):
                async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
                    with patch.object(Sdf.Layer, "FindOrOpen") as find_mock:
                        layer_mock = Mock()
                        find_mock.return_value = layer_mock

                        # Act
                        self.layer_manager.save_layer_with_identifier(project_url.path, force=force_save)

                        # Assert
                        self.assertEqual(1, find_mock.call_count)
                        self.assertEqual(call(project_url.path), find_mock.call_args)

                        self.assertEqual(1, layer_mock.Save.call_count)
                        self.assertEqual(call(force=force_save), layer_mock.Save.call_args)

    async def test_set_custom_layer_type_data_with_identifier_no_layer_should_raise_value_error(self):
        # Arrange
        layer_identifier = r"C:\test.test"

        # Act
        with self.assertRaises(ValueError) as cm:
            self.layer_manager.set_custom_layer_type_data_with_identifier(layer_identifier, LayerType.capture_baker)

        # Assert
        self.assertEqual(str(cm.exception), f'Can\'t find the layer with identifier "{layer_identifier}".')

    async def test_set_custom_layer_type_data_with_identifier_should_set_and_return_layer_type_custom_data(self):
        # Arrange
        expected_custom_data = {
            LayerType.autoupscale: {
                LayerTypeKeys.layer_type.value: LayerType.autoupscale.value,
            },
            LayerType.capture: {
                LayerTypeKeys.layer_type.value: LayerType.capture.value,
            },
            LayerType.capture_baker: {
                LayerTypeKeys.layer_type.value: LayerType.capture_baker.value,
                LayerCustomData.ROOT.value: {
                    LayerCustomData.EXCLUDE_ADD_CHILD.value: True,
                    LayerCustomData.EXCLUDE_EDIT_TARGET.value: True,
                    LayerCustomData.EXCLUDE_LOCK.value: True,
                    LayerCustomData.EXCLUDE_MOVE.value: True,
                    LayerCustomData.EXCLUDE_MUTE.value: True,
                    LayerCustomData.EXCLUDE_REMOVE.value: True,
                },
            },
            LayerType.replacement: {
                LayerTypeKeys.layer_type.value: LayerType.replacement.value,
            },
            LayerType.workfile: {
                LayerTypeKeys.layer_type.value: LayerType.workfile.value,
            },
        }

        for layer_type, layer_custom_data in expected_custom_data.items():
            with self.subTest(name=f"layer_type_{layer_type.value}"):
                async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
                    with patch.object(Sdf.Layer, "Save") as save_mock:
                        # Act
                        custom_layer_data = self.layer_manager.set_custom_layer_type_data_with_identifier(
                            project_url.path, layer_type
                        )

                        # Assert
                        for key, value in layer_custom_data.items():
                            self.assertEqual(custom_layer_data.get(key), value)
                        self.assertEqual(1, save_mock.call_count)

    async def test_get_layer_instance_should_return_layer_type_definition_instance(self):
        expected_instances = {
            LayerType.autoupscale: AutoUpscaleLayer,
            LayerType.capture: CaptureLayer,
            LayerType.capture_baker: CaptureBakerLayer,
            LayerType.replacement: ReplacementLayer,
            LayerType.workfile: WorkfileLayer,
            "Invalid": NoneType,
        }

        # Arrange
        for layer_type, layer_instance_type in expected_instances.items():
            with self.subTest(name=f"layer_type_{'invalid' if isinstance(layer_type, str) else layer_type.value}"):
                # Act
                layer_instance = self.layer_manager.get_layer_instance(layer_type)

                # Assert
                self.assertEqual(type(layer_instance), layer_instance_type)

    async def test_create_layer_fail_create_file_should_raise_value_error(self):
        layer_types = list(LayerType)
        layer_types.append("none")

        # Test Matrix to test all argument combinations
        for should_raise in [True, False]:  # noqa PLR1702
            for create_or_insert in [True, False]:
                for replace_existing in [True, False]:
                    for transfer_root_content in [True, False]:
                        for set_edit_target in [True, False]:
                            for set_parent in [True, False]:
                                for layer_type in layer_types:
                                    with self.subTest(
                                        name=f"raise_{should_raise}_"
                                        f"create_{create_or_insert}_"
                                        f"replace_{replace_existing}_"
                                        f"transfer_{transfer_root_content}_"
                                        f"edit_{set_edit_target}_"
                                        f"parent_{set_parent}_"
                                        f"layer_{layer_type if isinstance(layer_type, str) else layer_type.value}"
                                    ):
                                        await self.__run_create_layer(
                                            should_raise,
                                            create_or_insert,
                                            replace_existing,
                                            transfer_root_content,
                                            set_edit_target,
                                            set_parent,
                                            layer_type,
                                        )

    async def test_broken_layers_stack_should_return_correct_value(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            base_path = OmniUrl(project_url.parent_url)
            test_items = [
                (base_path / "full_project.usda", False),
                (base_path / "mod.usda", False),
                (base_path / "mod_capture_baker.usda", False),
                (base_path / "sublayer_child_01.usda", False),
                (base_path / "wrong_layer.usda", True),
            ]

            # Setup
            root_layer = self.context.get_stage().GetRootLayer()
            copy_layers = root_layer.subLayerPaths.copy()
            copy_layers.append("./wrong_layer.usda")
            root_layer.subLayerPaths = copy_layers

            for layer_path, is_in_stack in test_items:
                with self.subTest(name=f"layer_identifier_{layer_path.stem}_value_{is_in_stack}"):
                    # Act
                    value = self.layer_manager.broken_layers_stack()

                    # Assert
                    self.assertEqual(value, [(root_layer, "./wrong_layer.usda")])
                    self.assertEqual(pathlib.Path(value[0][1]).name == layer_path.name, is_in_stack)

    async def test_remove_broken_layer(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__):
            # Setup
            root_layer = self.context.get_stage().GetRootLayer()
            copy_layers = root_layer.subLayerPaths.copy()
            copy_layers.append("./wrong_layer.usda")
            root_layer.subLayerPaths = copy_layers

            # Assert 1
            self.assertEqual(
                [str(sublayer) for sublayer in root_layer.subLayerPaths],
                ["./mod.usda", "./capture.usda", "./wrong_layer.usda"],
            )

            # Act
            self.layer_manager.remove_broken_layer(root_layer.identifier, "./wrong_layer.usda")

            # Assert 2
            self.assertEqual([str(sublayer) for sublayer in root_layer.subLayerPaths], ["./mod.usda", "./capture.usda"])

    async def test_layer_type_in_stack_should_return_correct_value(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            base_path = OmniUrl(project_url.parent_url)
            test_items = [
                (base_path / "full_project.usda", LayerType.workfile, True),
                (base_path / "full_project.usda", LayerType.replacement, False),
                (base_path / "mod.usda", LayerType.workfile, True),
                (base_path / "mod.usda", LayerType.replacement, True),
                (base_path / "mod.usda", LayerType.capture, False),
                (base_path / "mod_capture_baker.usda", LayerType.workfile, True),
                (base_path / "mod_capture_baker.usda", LayerType.replacement, True),
                (base_path / "mod_capture_baker.usda", LayerType.capture_baker, True),
                (base_path / "mod_capture_baker.usda", LayerType.capture, False),
                (base_path / "sublayer_child_01.usda", LayerType.workfile, True),
                (base_path / "sublayer_child_01.usda", LayerType.replacement, True),
                (base_path / "sublayer_child_01.usda", LayerType.capture_baker, False),
                (base_path / "sublayer_child_01.usda", LayerType.capture, False),
                (base_path / "not_in_stack.usda", LayerType.workfile, False),
            ]

            for layer_path, layer_type, is_in_stack in test_items:
                with self.subTest(
                    name=f"layer_identifier_{layer_path.stem}_type_{layer_type.value}_value_{is_in_stack}"
                ):
                    # Act
                    value = self.layer_manager.layer_type_in_stack(layer_path.path, layer_type)

                    # Assert
                    self.assertEqual(value, is_in_stack)

    async def test_create_new_anonymous_layer_should_create_layer(self):
        # Arrange
        pass

        # Act
        layer = self.layer_manager.create_new_anonymous_layer()

        # Assert
        self.assertIsNotNone(layer)
        self.assertTrue(layer.anonymous)

    async def test_save_layer_should_save_layer_with_type(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__):
            root_layer = self.context.get_stage().GetRootLayer()
            Sdf.CreatePrimInLayer(root_layer, "RootNode/TestPrim")

            # Act
            self.layer_manager.save_layer(LayerType.workfile, show_checkpoint_error=False)

            # Assert
            self.assertFalse(root_layer.dirty)

    async def test_save_layer_as_no_layer_should_return_false(self):
        # Arrange
        root_layer = self.context.get_stage().GetRootLayer()
        Sdf.CreatePrimInLayer(root_layer, "RootNode/TestPrim")

        # Act
        value = self.layer_manager.save_layer_as(LayerType.workfile, "C:/test.test", show_checkpoint_error=False)

        # Assert
        self.assertFalse(value)

    async def test_save_layer_as_fail_export_should_return_false(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            output_path = OmniUrl(project_url.parent_url) / "test.usda"

            with patch.object(Sdf.Layer, "Export") as export_mock:
                export_mock.return_value = False

                # Act
                value = self.layer_manager.save_layer_as(
                    LayerType.workfile, output_path.path, show_checkpoint_error=False
                )

            # Assert
            self.assertFalse(value)
            self.assertTrue(output_path.exists)

    async def test_save_layer_as_should_export_layer_with_type_and_return_true(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            output_path = OmniUrl(project_url.parent_url) / "test.usda"

            # Act
            value = self.layer_manager.save_layer_as(LayerType.workfile, output_path.path, show_checkpoint_error=False)

            # Assert
            self.assertTrue(value)
            self.assertTrue(output_path.exists)

    async def test_get_layers_should_return_layers_of_type(self):
        # Arrange
        for layer_type in list(LayerType):
            for max_results in [-1, 0, 1, 20]:
                for find_muted in [True, False]:
                    with self.subTest(name=f"layer_type_{layer_type}_max_results_{max_results}_find_muted{find_muted}"):
                        with patch.object(LayerManagerValidators, "get_layers_of_type") as mock:
                            mock_value = Mock()
                            mock.return_value = mock_value

                            # Act
                            val = self.layer_manager.get_layers(
                                layer_type, max_results=max_results, find_muted_layers=find_muted
                            )

                        # Assert
                        self.assertEqual(val, mock_value)
                        self.assertEqual(1, mock.call_count)
                        self.assertEqual(
                            call(layer_type, max_results=max_results, context_name="", find_muted_layers=find_muted),
                            mock.call_args,
                        )

    async def test_get_layer_should_return_layer_of_type(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            stage = self.context.get_stage()
            capture_identifier = (OmniUrl(project_url.parent_url) / "capture.usda").path

            stage.MuteLayer(capture_identifier)

            for find_muted_layers in [True, False]:
                with self.subTest(name=f"muted_{find_muted_layers}"):
                    # Act
                    value = self.layer_manager.get_layer(LayerType.capture, find_muted_layers=find_muted_layers)

                    # Assert
                    if find_muted_layers:
                        self.assertEqual(value.identifier, capture_identifier)
                    else:
                        self.assertIsNone(value)

    async def test_get_custom_data_should_return_layer_custom_data(self):
        # Arrange
        test_data = {
            get_test_data_path(__name__, "usd/full_project/full_project.usda"): {
                "lightspeed_layer_type": "workfile",
                "omni_layer": {
                    "authoring_layer": "./mod.usda",
                    "locked": {
                        "./capture.usda": True,
                        "./sublayer_child_02.usda": True,
                    },
                    "muteness": {
                        "./mod_capture_baker.usda": True,
                        "./sublayer_child_01.usda": True,
                    },
                },
            },
            get_test_data_path(__name__, "usd/full_project/capture.usda"): {
                "lightspeed_exe_name": "hl2.exe",
                "lightspeed_game_icon": "hl2.exe_icon.bmp",
                "lightspeed_game_name": "Portal with RTX - Direct3D 9",
                "lightspeed_geometry_hash_rules": "positions,indices,geometrydescriptor",
                "lightspeed_layer_type": "capture",
                "omni_layer": {"authoring_layer": "./capture.usda", "locked": {}, "muteness": {}},
            },
            get_test_data_path(__name__, "usd/full_project/mod_capture_baker.usda"): {
                "flux_layer_widget_exclusions": {
                    "exclude_add_child": True,
                    "exclude_edit_target": True,
                    "exclude_lock": True,
                    "exclude_move": True,
                    "exclude_mute": True,
                    "exclude_remove": True,
                },
                "lightspeed_layer_type": "capture_baker",
            },
        }

        for layer_path, expected_data in test_data.items():
            with self.subTest(name=f"layer_{OmniUrl(layer_path).stem}"):
                layer = Sdf.Layer.FindOrOpen(layer_path)

                # Act
                data = LayerManagerCore.get_custom_data(layer)

                # Assert
                self.assertDictEqual(data, expected_data)

    async def test_set_custom_data_layer_type_should_set_layer_type_and_return_dict(self):
        # Arrange
        layer_path = get_test_data_path(__name__, "usd/import_layer/import_layer.usda")
        layer = Sdf.Layer.FindOrOpen(layer_path)

        # Act
        data = LayerManagerCore.set_custom_data_layer_type(layer, LayerType.capture_baker)

        # Assert
        self.assertDictEqual(data, {"lightspeed_layer_type": "capture_baker"})

    async def test_get_custom_data_layer_type_should_return_layer_type_instance_custom_data(self):
        # Arrange
        layer_path = get_test_data_path(__name__, "usd/full_project/mod_capture_baker.usda")
        layer = Sdf.Layer.FindOrOpen(layer_path)

        # Act
        data = LayerManagerCore.get_custom_data_layer_type(layer)

        # Assert
        self.assertEqual(data, "capture_baker")

    async def test_set_edit_target_layer_should_set_layer_as_edit_target(self):
        # Arrange
        for force_identifier in [True, False]:
            for find_layer_type in [True, False]:
                with self.subTest(name=f"force_identifier_{force_identifier}_find_layer_type_{find_layer_type}"):
                    test_project_url = (
                        "usd/full_project/full_project.usda"
                        if find_layer_type
                        else "usd/import_layer/import_layer.usda"
                    )
                    async with open_test_project(test_project_url, __name__) as project_url:
                        force_layer_identifier = (
                            (OmniUrl(project_url.parent_url) / "sublayer.usda").path if force_identifier else None
                        )

                        # Act
                        self.layer_manager.set_edit_target_layer(
                            LayerType.replacement, force_layer_identifier=force_layer_identifier
                        )

                        # Assert
                        actual_edit_target = self.context.get_stage().GetEditTarget().GetLayer().identifier
                        expected_edit_target = project_url.path
                        if find_layer_type:
                            expected_edit_target = (
                                OmniUrl(force_layer_identifier).path
                                if force_identifier
                                else (OmniUrl(project_url.parent_url) / "sublayer_child_02.usda").path
                            )

                        self.assertEqual(actual_edit_target, expected_edit_target)

    async def test_lock_layer_should_lock_all_layers_of_type(self):
        # Arrange
        for expected_value in [True, False]:
            for find_layer_type in [True, False]:
                with self.subTest(name=f"expected_value_{expected_value}_find_layer_type_{find_layer_type}"):
                    test_project_url = (
                        "usd/full_project/full_project.usda"
                        if find_layer_type
                        else "usd/import_layer/import_layer.usda"
                    )
                    async with open_test_project(test_project_url, __name__) as project_url:
                        if find_layer_type:
                            layer_identifier = (OmniUrl(project_url.parent_url) / "mod.usda").path
                            LayerUtils.set_layer_lock_status(
                                self.context.get_stage().GetRootLayer(), layer_identifier, not expected_value
                            )

                        # Act
                        self.layer_manager.lock_layer(LayerType.replacement, value=expected_value)

                        # Assert
                        if find_layer_type:
                            self.assertEqual(omni.usd.is_layer_locked(self.context, layer_identifier), expected_value)
                        else:
                            self.assertEqual(omni.usd.is_layer_locked(self.context, project_url), False)

    async def test_mute_layer_should_mute_all_layers_of_type(self):
        # Arrange
        for expected_value in [True, False]:
            for find_layer_type in [True, False]:
                with self.subTest(name=f"expected_value_{expected_value}_find_layer_type_{find_layer_type}"):
                    test_project_url = (
                        "usd/full_project/full_project.usda"
                        if find_layer_type
                        else "usd/import_layer/import_layer.usda"
                    )
                    async with open_test_project(test_project_url, __name__) as project_url:
                        if find_layer_type:
                            layer_identifier = (OmniUrl(project_url.parent_url) / "mod.usda").path
                            if expected_value:
                                self.context.get_stage().UnmuteLayer(layer_identifier)
                            else:
                                self.context.get_stage().MuteLayer(layer_identifier)

                        # Act
                        self.layer_manager.mute_layer(LayerType.replacement, value=expected_value)

                        # Assert
                        if find_layer_type:
                            self.assertEqual(self.context.get_stage().IsLayerMuted(layer_identifier), expected_value)
                        else:
                            self.assertEqual(self.context.get_stage().IsLayerMuted(project_url.path), False)

    async def test_remove_layer_should_remove_all_layers_of_type(self):
        # Arrange
        for find_layer_type in [True, False]:
            with self.subTest(name=f"find_layer_type_{find_layer_type}"):
                test_project_url = (
                    "usd/full_project/full_project.usda" if find_layer_type else "usd/import_layer/import_layer.usda"
                )
                async with open_test_project(test_project_url, __name__) as project_url:
                    # Act
                    self.layer_manager.remove_layer(LayerType.replacement)

                    # Assert
                    layer = Sdf.Layer.FindOrOpen(project_url.path)
                    self.assertEqual(len(layer.subLayerPaths), 1 if find_layer_type else 0)

    async def test_get_game_name_from_path_should_return_game_name(self):
        # Arrange
        for has_metadata in [True, False]:
            for find_layer in [True, False]:
                with self.subTest(name=f"has_metadata_{has_metadata}_find_layer_{find_layer}"):
                    layer_path = "usd/non_existent/no_project.usda"
                    if find_layer:
                        layer_path = (
                            "usd/full_project/capture.usda" if has_metadata else "usd/full_project/sublayer.usda"
                        )

                    # Act
                    value = self.layer_manager.get_game_name_from_path(get_test_data_path(__name__, layer_path))

                    # Assert
                    self.assertEqual(
                        value, "Portal with RTX - Direct3D 9" if has_metadata and find_layer else "Unknown game"
                    )

    async def test_game_current_game_capture_folder_capture_should_return_game_name_and_capture_directory(self):
        # Arrange
        for has_capture in [True, False]:
            for in_rtx_remix in [True, False]:
                with self.subTest(name=f"has_capture_{has_capture}_in_rtx_remix_{in_rtx_remix}"):
                    test_project_url = (
                        "usd/full_project/full_project.usda" if has_capture else "usd/import_layer/import_layer.usda"
                    )
                    async with open_test_project(test_project_url, __name__) as project_url:
                        capture_url = None
                        if in_rtx_remix:
                            # Create a rtx-remix/captures directory and copy the temp project there.
                            capture_url = (
                                OmniUrl(OmniUrl(project_url.parent_url).parent_url)
                                / REMIX_FOLDER
                                / REMIX_CAPTURE_FOLDER
                            )
                            await omni.client.copy_async(project_url.parent_url, capture_url.path)
                            await open_stage((capture_url / project_url.name).path)

                        # Act
                        name_value, dir_value = self.layer_manager.game_current_game_capture_folder(show_error=False)

                        # Assert
                        self.assertEqual(
                            name_value, "Portal with RTX - Direct3D 9" if has_capture and in_rtx_remix else None
                        )
                        self.assertEqual(
                            OmniUrl(dir_value).path if dir_value else dir_value,
                            capture_url.path if has_capture and in_rtx_remix else None,
                        )

    async def test_get_layer_hashes_no_comp_arcs_should_return_hashes_and_prim_paths(self):
        # Arrange
        test_cases = {
            "usd/full_project/capture.usda": {
                "6CA2F12444DEBE09": Sdf.Path("/RootNode/meshes/mesh_6CA2F12444DEBE09"),
                "9907D0B07D040077": Sdf.Path("/RootNode/lights/light_9907D0B07D040077"),
                "8D1946B4993CE5A3": Sdf.Path("/RootNode/Looks/mat_8D1946B4993CE5A3"),
            },
            "usd/full_project/sublayer.usda": {"9907D0B07D040077": Sdf.Path("/RootNode/lights/light_9907D0B07D040077")},
            "usd/full_project/sublayer_child_01.usda": {
                "8D1946B4993CE5A3": Sdf.Path("/RootNode/Looks/mat_8D1946B4993CE5A3")
            },
            "usd/full_project/sublayer_child_02.usda": {},
            "usd/full_project/mod.usda": {},
        }

        for layer_path, expected_hashes in test_cases.items():
            with self.subTest(name=f"layer_{layer_path}"):
                layer = Sdf.Layer.FindOrOpen(get_test_data_path(__name__, layer_path))

                # Act
                value = self.layer_manager.get_layer_hashes_no_comp_arcs(layer)

                # Assert
                self.assertDictEqual(value, expected_hashes)

    async def __run_create_layer(
        self,
        should_raise: bool,
        create_or_insert: bool,
        replace_existing: bool,
        transfer_root_content: bool,
        set_edit_target: bool,
        set_parent: bool,
        layer_type: Union[str, LayerType],
    ):
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            # Arrange
            if create_or_insert:
                relative_layer_path = "./create_layer.usda"
            else:
                # If inserting an existing layer, copy the import layer to the temp project directory
                import_layer = OmniUrl(get_test_data_path(__name__, "usd/import_layer/import_layer.usda"))
                await omni.client.copy_async(
                    import_layer.parent_url, (OmniUrl(OmniUrl(project_url.parent_url).parent_url) / "import_layer").path
                )
                relative_layer_path = "../import_layer/import_layer.usda"

            # The absolute created or imported layer
            layer_path = (OmniUrl(project_url.parent_url) / relative_layer_path).path

            if set_parent:
                parent_layer_identifier = (OmniUrl(project_url.parent_url) / "mod.usda").path
            else:
                parent_layer_identifier = None

            # Make sure the "none" value is converted to None
            set_layer_type = isinstance(layer_type, LayerType)
            if not set_layer_type:
                layer_type = None

            with (
                patch.object(LayerManagerCore, "layer_type_in_stack") as layer_type_in_stack_mock,
                patch.object(LayerManagerCore, "set_edit_target_with_identifier") as set_edit_target_mock,
                patch.object(LayerManagerCore, "set_custom_layer_type_data_with_identifier") as set_custom_data_mock,
            ):
                if should_raise:
                    set_custom_data_mock.side_effect = ValueError()

                # Will only raise if the `get_custom_data_layer_type` function raises and is called
                metadata_will_fail = should_raise and set_layer_type

                # Will only raise if replacing a layer of the same type as a parent layer
                create_will_fail = False
                if replace_existing:
                    if set_parent:
                        create_will_fail = layer_type in [LayerType.workfile, LayerType.replacement]
                    else:
                        create_will_fail = layer_type in [LayerType.workfile]

                layer_type_in_stack_mock.return_value = create_will_fail

                # Act
                with (
                    self.assertRaises(ValueError)
                    if metadata_will_fail or create_will_fail
                    else contextlib.nullcontext()
                ) as cm:
                    self.layer_manager.create_layer(
                        layer_path,
                        layer_type=layer_type,
                        set_edit_target=set_edit_target,
                        parent_layer_identifier=parent_layer_identifier,
                        replace_existing=replace_existing,
                        create_or_insert=create_or_insert,
                        transfer_root_content=transfer_root_content,
                    )

            # Assert
            if set_parent:
                # If the parent was given we should look at the parent's sublayers. Parent = mod.usda
                expected_layer = Sdf.Layer.FindOrOpen(parent_layer_identifier)
                expected_sublayers = ["./sublayer.usda", "./mod_capture_baker.usda"]
            else:
                # If not parent was given we should look at the stage root layer's sublayers.
                expected_layer = self.context.get_stage().GetRootLayer()
                expected_sublayers = ["./mod.usda", "./capture.usda"]

            # If replacing existing layers of type, adjust the expected sublayers
            if replace_existing:
                if set_parent:
                    match layer_type:
                        case LayerType.capture_baker:
                            expected_sublayers = ["./sublayer.usda"]
                else:
                    match layer_type:
                        case LayerType.replacement:
                            expected_sublayers = ["./capture.usda"]
                        case LayerType.capture:
                            expected_sublayers = ["./mod.usda"]

            # If creating a layer was supposed to raise a value error, make sure it was the correct error
            if create_will_fail:
                self.assertEqual(str(cm.exception), "Can't replace a layer of the same type as the parent layer.")
            # If creating a layer was supposed to create a layer, make sure it was created correctly
            else:
                expected_sublayers = [relative_layer_path] + expected_sublayers
                self.assertListEqual([str(sublayer) for sublayer in expected_layer.subLayerPaths], expected_sublayers)

                # If setting metadata was supposed to raise a value error, make sure it was the correct error
                if metadata_will_fail:
                    self.assertEqual(
                        str(cm.exception),
                        f"Unable to update the created layer's metadata. "
                        f'Can\'t find the layer with identifier "{layer_path}".',
                    )

            # Replace any "parent/../dir" with "dir" and any "dir/./" with "dir/"
            resolved_path = re.sub(r"(/[^/]+/\.\./)|(\./)|(//+)", "/", layer_path)

            self.assertEqual(1 if set_edit_target and not create_will_fail else 0, set_edit_target_mock.call_count)
            if set_edit_target and not create_will_fail:
                self.assertEqual(call(resolved_path), set_edit_target_mock.call_args)

            self.assertEqual(1 if set_layer_type and not create_will_fail else 0, set_custom_data_mock.call_count)
            if set_layer_type and not create_will_fail:
                self.assertEqual(call(resolved_path, layer_type), set_custom_data_mock.call_args)

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

from contextlib import nullcontext

import omni.usd
from lightspeed.layer_manager.core import LayerType, LayerTypeKeys
from lightspeed.layer_manager.core.data_models import LayerManagerValidators
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path, wait_stage_loading
from pxr import Sdf


class TestLayerManagerValidators(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if self.context.can_close_stage():
            await self.context.close_stage_async()
        self.context = None

    async def test_layer_is_in_project_returns_expected_value_or_raises(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:

            def get_temp_layer(layer_name: str) -> str:
                return (OmniUrl(OmniUrl(project_url).parent_url) / layer_name).path

            test_cases = {
                get_temp_layer("capture.usda"): (True, None),
                get_temp_layer("sublayer_child_02.usda"): (True, None),
                get_temp_layer("invalid.usda"): (False, "The layer does not exist"),
                get_test_data_path(__name__, "usd/import_layer/import_layer.usda"): (
                    False,
                    "The layer is not present in the loaded project's layer stack",
                ),
            }

            for layer_identifier, expected_results in test_cases.items():
                is_valid, expected_message = expected_results
                with self.subTest(title=f"layer_identifier_{OmniUrl(layer_identifier).stem}_is_valid_{is_valid}"):
                    # Act
                    with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
                        value = LayerManagerValidators.layer_is_in_project(layer_identifier, "")

                    # Assert
                    if is_valid:
                        self.assertEqual(value, layer_identifier)
                    else:
                        self.assertEqual(str(cm.exception), f"{expected_message}: {layer_identifier}")

    async def test_is_valid_index_returns_expected_value_or_raises(self):
        # Arrange
        test_cases = {-1000: False, -2: False, -1: True, 0: True, 1000: True}

        for input_value, is_valid in test_cases.items():
            with self.subTest(title=f"value_{input_value}_is_valid_{is_valid}"):
                # Act
                with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
                    value = LayerManagerValidators.is_valid_index(input_value)

                # Assert
                if is_valid:
                    self.assertEqual(value, input_value)
                else:
                    self.assertEqual(str(cm.exception), "The index should be a positive integer or -1")

    async def test_can_create_layer_returns_expected_value_or_raises(self):
        # Arrange
        test_cases = {
            "Z:/test_01.png": (True, False, "The layer path must point to a USD file"),
            "Z:/test_02.png": (False, False, "The layer path must point to a USD file"),
            "Z:/test_03.usda": (True, True, None),
            "Z:/test_04.usda": (False, False, "The layer does not exist"),
            get_test_data_path(__name__, "usd/full_project/mod.usda"): (
                True,
                False,
                "A file already exists at the layer path",
            ),
            get_test_data_path(__name__, "usd/full_project/capture.usda"): (False, True, None),
        }

        for layer_identifier, expected_results in test_cases.items():
            create_or_insert, is_valid, expected_message = expected_results
            with self.subTest(
                title=f"layer_identifier_{OmniUrl(layer_identifier).stem}"
                f"_create_or_insert_{create_or_insert}_is_valid_{is_valid}"
            ):
                # Act
                with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
                    value = LayerManagerValidators.can_create_layer(layer_identifier, create_or_insert)

                # Assert
                if is_valid:
                    self.assertEqual(value, layer_identifier)
                else:
                    self.assertEqual(str(cm.exception), f"{expected_message}: {layer_identifier}")

    async def test_can_insert_sublayer_returns_expected_value_or_raises(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:

            def get_temp_layer(layer_name: str) -> str:
                return (OmniUrl(OmniUrl(project_url).parent_url) / layer_name).path

            test_cases = {
                None: (True, None),
                get_temp_layer("full_project.usda"): (False, "Inserting a sublayer in the given layer is not allowed"),
                get_temp_layer("capture.usda"): (False, "Inserting a sublayer in the given layer is not allowed"),
                get_temp_layer("mod_capture_baker.usda"): (
                    False,
                    "Inserting a sublayer in the given layer is not allowed",
                ),
                get_temp_layer("sublayer_child_02.usda"): (False, "The layer is locked"),
                get_temp_layer("mod.usda"): (True, None),
                get_temp_layer("sublayer_child_01.usda"): (True, None),
            }

            for layer_identifier, expected_results in test_cases.items():
                is_valid, expected_message = expected_results
                with self.subTest(title=f"layer_identifier_{OmniUrl(layer_identifier).stem}_is_valid_{is_valid}"):
                    # Act
                    with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
                        value = LayerManagerValidators.can_insert_sublayer(layer_identifier, "")

                    # Assert
                    if is_valid:
                        self.assertEqual(value, layer_identifier)
                    else:
                        self.assertEqual(str(cm.exception), f"{expected_message}: {layer_identifier}")

    async def test_can_move_sublayer_returns_expected_value_or_raises(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:

            def get_temp_layer(layer_name: str) -> str:
                return (OmniUrl(OmniUrl(project_url).parent_url) / layer_name).path

            test_cases = {
                get_temp_layer("full_project.usda"): (False, "Moving the sublayer is not allowed"),
                get_temp_layer("capture.usda"): (False, "Moving the sublayer is not allowed"),
                get_temp_layer("mod.usda"): (False, "Moving the sublayer is not allowed"),
                get_temp_layer("mod_capture_baker.usda"): (False, "Moving the sublayer is not allowed"),
                get_temp_layer("sublayer_child_02.usda"): (False, "The layer is locked"),
                get_temp_layer("sublayer.usda"): (True, None),
                get_temp_layer("sublayer_child_01.usda"): (True, None),
            }

            for layer_identifier, expected_results in test_cases.items():
                is_valid, expected_message = expected_results
                with self.subTest(title=f"layer_identifier_{OmniUrl(layer_identifier).stem}_is_valid_{is_valid}"):
                    # Act
                    with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
                        value = LayerManagerValidators.can_move_sublayer(layer_identifier, "")

                    # Assert
                    if is_valid:
                        self.assertEqual(value, layer_identifier)
                    else:
                        self.assertEqual(str(cm.exception), f"{expected_message}: {layer_identifier}")

    async def test_can_delete_layer_returns_expected_value_or_raises(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:

            def get_temp_layer(layer_name: str) -> str:
                return (OmniUrl(OmniUrl(project_url).parent_url) / layer_name).path

            test_cases = {
                get_temp_layer("full_project.usda"): (False, "Deleting the sublayer is not allowed"),
                get_temp_layer("capture.usda"): (False, "Deleting the sublayer is not allowed"),
                get_temp_layer("mod.usda"): (False, "Deleting the sublayer is not allowed"),
                get_temp_layer("mod_capture_baker.usda"): (False, "Deleting the sublayer is not allowed"),
                get_temp_layer("sublayer.usda"): (True, None),
                get_temp_layer("sublayer_child_01.usda"): (True, None),
            }

            for layer_identifier, expected_results in test_cases.items():
                is_valid, expected_message = expected_results
                with self.subTest(title=f"layer_identifier_{OmniUrl(layer_identifier).stem}_is_valid_{is_valid}"):
                    # Act
                    with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
                        value = LayerManagerValidators.can_delete_layer(layer_identifier, "")

                    # Assert
                    if is_valid:
                        self.assertEqual(value, layer_identifier)
                    else:
                        self.assertEqual(str(cm.exception), f"{expected_message}: {layer_identifier}")

    async def test_can_mute_layer_returns_expected_value_or_raises(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:

            def get_temp_layer(layer_name: str) -> str:
                return (OmniUrl(OmniUrl(project_url).parent_url) / layer_name).path

            test_cases = {
                get_temp_layer("full_project.usda"): (False, "Muting/Unmuting the sublayer is not allowed"),
                get_temp_layer("capture.usda"): (False, "Muting/Unmuting the sublayer is not allowed"),
                get_temp_layer("mod_capture_baker.usda"): (False, "Muting/Unmuting the sublayer is not allowed"),
                get_temp_layer("mod.usda"): (True, None),
                get_temp_layer("sublayer.usda"): (True, None),
                get_temp_layer("sublayer_child_01.usda"): (True, None),
            }

            for layer_identifier, expected_results in test_cases.items():
                is_valid, expected_message = expected_results
                with self.subTest(title=f"layer_identifier_{OmniUrl(layer_identifier).stem}_is_valid_{is_valid}"):
                    # Act
                    with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
                        value = LayerManagerValidators.can_mute_layer(layer_identifier, "")

                    # Assert
                    if is_valid:
                        self.assertEqual(value, layer_identifier)
                    else:
                        self.assertEqual(str(cm.exception), f"{expected_message}: {layer_identifier}")

    async def test_can_lock_layer_returns_expected_value_or_raises(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:

            def get_temp_layer(layer_name: str) -> str:
                return (OmniUrl(OmniUrl(project_url).parent_url) / layer_name).path

            test_cases = {
                get_temp_layer("full_project.usda"): (False, "Locking/Unlocking the sublayer is not allowed"),
                get_temp_layer("capture.usda"): (False, "Locking/Unlocking the sublayer is not allowed"),
                get_temp_layer("mod.usda"): (False, "Locking/Unlocking the sublayer is not allowed"),
                get_temp_layer("mod_capture_baker.usda"): (False, "Locking/Unlocking the sublayer is not allowed"),
                get_temp_layer("sublayer.usda"): (True, None),
                get_temp_layer("sublayer_child_01.usda"): (True, None),
            }

            for layer_identifier, expected_results in test_cases.items():
                is_valid, expected_message = expected_results
                with self.subTest(title=f"layer_identifier_{OmniUrl(layer_identifier).stem}_is_valid_{is_valid}"):
                    # Act
                    with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
                        value = LayerManagerValidators.can_lock_layer(layer_identifier, "")

                    # Assert
                    if is_valid:
                        self.assertEqual(value, layer_identifier)
                    else:
                        self.assertEqual(str(cm.exception), f"{expected_message}: {layer_identifier}")

    async def test_can_set_edit_target_layer_returns_expected_value_or_raises(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:

            def get_temp_layer(layer_name: str) -> str:
                return (OmniUrl(OmniUrl(project_url).parent_url) / layer_name).path

            test_cases = {
                get_temp_layer("full_project.usda"): (False, "Setting the sublayer as edit target is not allowed"),
                get_temp_layer("capture.usda"): (False, "Setting the sublayer as edit target is not allowed"),
                get_temp_layer("mod_capture_baker.usda"): (False, "Setting the sublayer as edit target is not allowed"),
                get_temp_layer("mod.usda"): (True, None),
                get_temp_layer("sublayer.usda"): (True, None),
                get_temp_layer("sublayer_child_01.usda"): (True, None),
            }

            for layer_identifier, expected_results in test_cases.items():
                is_valid, expected_message = expected_results
                with self.subTest(title=f"layer_identifier_{OmniUrl(layer_identifier).stem}_is_valid_{is_valid}"):
                    # Act
                    with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
                        value = LayerManagerValidators.can_set_edit_target_layer(layer_identifier, "")

                    # Assert
                    if is_valid:
                        self.assertEqual(value, layer_identifier)
                    else:
                        self.assertEqual(str(cm.exception), f"{expected_message}: {layer_identifier}")

    async def test_get_layers_of_type_returns_expected_value(self):
        # Arrange
        async with open_test_project("usd/full_project/full_project.usda", __name__) as project_url:
            # Add more capture layers
            stage = self.context.get_stage()
            layer_stack = stage.GetLayerStack(includeSessionLayers=False)
            base_path = OmniUrl(project_url.parent_url)
            custom_data = {LayerTypeKeys.layer_type.value: LayerType.capture.value}

            # Create the layers
            root_capture = Sdf.Layer.CreateAnonymous(tag="root_capture")
            sublayer_capture = Sdf.Layer.CreateAnonymous(tag="sublayer_capture")
            child_capture = Sdf.Layer.CreateAnonymous(tag="child_capture")

            # Make sure all the layers are capture layers
            root_capture.customLayerData = custom_data
            sublayer_capture.customLayerData = custom_data
            child_capture.customLayerData = custom_data

            def find_layer(layer_name: str) -> Sdf.Layer:
                return [layer for layer in layer_stack if OmniUrl(layer.identifier).name == layer_name][0]

            # Insert the layers
            find_layer("full_project.usda").subLayerPaths.insert(0, root_capture.identifier)
            find_layer("sublayer.usda").subLayerPaths.insert(0, sublayer_capture.identifier)
            find_layer("capture.usda").subLayerPaths.insert(0, child_capture.identifier)

            # Mute some layers for testing
            stage.MuteLayer(root_capture.identifier)
            stage.MuteLayer(child_capture.identifier)

            for limit_selection in [True, False]:
                with self.subTest(name=f"limit_{limit_selection}"):
                    # Act
                    value = LayerManagerValidators.get_layers_of_type(
                        LayerType.capture, max_results=1 if limit_selection else -1
                    )

                    # Assert
                    if limit_selection:
                        expected_layers = [root_capture.identifier]
                    else:
                        expected_layers = [
                            root_capture.identifier,
                            sublayer_capture.identifier,
                            (base_path / "capture.usda").path,
                            child_capture.identifier,
                        ]

                    actual_layers = [v.identifier for v in value]
                    self.assertListEqual(actual_layers, expected_layers)

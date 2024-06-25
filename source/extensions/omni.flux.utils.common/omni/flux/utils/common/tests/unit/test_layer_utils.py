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

import tempfile
import weakref
from pathlib import Path
from unittest.mock import Mock, call, patch

import omni.kit.test
import omni.usd
from omni.flux.utils.common import layer_utils
from omni.kit import commands
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf, Usd


class TestLayerUtils(omni.kit.test.AsyncTestCase):

    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()

    async def test_create_layer_existing_should_clear(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        with (
            patch.object(Sdf.Layer, "FindOrOpen") as find_mock,
            patch.object(Sdf.Layer, "Clear") as clear_mock,
            patch.object(Sdf.Layer, "CreateNew") as create_mock,
        ):
            find_mock.return_value = layer0

            # Act
            result = layer_utils.create_layer(layer0.identifier)

            # Assert
            self.assertEqual(1, clear_mock.call_count)
            self.assertEqual(layer0, result)
            self.assertFalse(create_mock.called)

    async def test_create_layer_new_should_create(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        with (
            patch.object(Sdf.Layer, "FindOrOpen") as find_mock,
            patch.object(Sdf.Layer, "Clear") as clear_mock,
            patch.object(Sdf.Layer, "CreateNew") as create_mock,
        ):
            find_mock.return_value = None
            create_mock.return_value = layer0

            # Act
            result = layer_utils.create_layer(layer0.identifier)

            # Assert
            self.assertEqual(1, create_mock.call_count)
            self.assertEqual(layer0, result)
            self.assertFalse(clear_mock.called)

    async def test_save_layer_as_no_layer_ref_quick_return(self):
        # Arrange
        mock_ref = Mock()
        mock_ref.return_value = None

        save_done_mock = Mock()

        with patch("omni.flux.utils.common.layer_utils.create_layer") as mock:
            # Act
            layer_utils.save_layer_as("", True, mock_ref, mock_ref, save_done_mock, str(self.temp_dir))  # noqa

            # Assert
            self.assertFalse(mock.called)

    async def test_save_layer_as_should_transfer_content_resolve_and_save(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)

        root_ref = weakref.ref(root)
        layer0_ref = weakref.ref(layer0)

        save_done_mock = Mock()

        with (
            patch("omni.flux.utils.common.layer_utils.create_layer") as create_mock,
            patch.object(Sdf.Layer, "TransferContent") as transfer_mock,
            patch.object(LayerUtils, "resolve_paths") as resolve_mock,
            patch.object(LayerUtils, "create_checkpoint") as checkpoint_mock,
            patch.object(Sdf.Layer, "Save") as save_mock,
            patch.object(Usd.Stage, "GetEditTarget") as edit_target_mock,
        ):
            create_mock.return_value = layer1

            # Act
            layer_utils.save_layer_as("", False, layer0_ref, root_ref, save_done_mock, str(layer1_path))  # noqa

            # Assert
            self.assertEqual(1, create_mock.call_count)
            self.assertEqual(1, transfer_mock.call_count)
            self.assertEqual(1, resolve_mock.call_count)
            self.assertEqual(1, checkpoint_mock.call_count)
            self.assertEqual(1, save_mock.call_count)
            self.assertEqual(1, save_done_mock.call_count)

            self.assertFalse(edit_target_mock.called)

            transfer_args, _ = transfer_mock.call_args
            self.assertEqual((layer0,), transfer_args)

            resolve_args, _ = resolve_mock.call_args
            self.assertEqual((layer0, layer1), resolve_args)

            checkpoint_args, _ = checkpoint_mock.call_args
            self.assertEqual((layer1.identifier, ""), checkpoint_args)

            save_done_args, _ = save_done_mock.call_args
            self.assertEqual((True, "", [layer1.identifier]), save_done_args)

    async def test_save_layer_as_replace_no_parent_should_open_stage(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        root = self.stage.GetRootLayer()

        root_ref = weakref.ref(root)

        save_done_mock = Mock()

        with (
            patch("omni.flux.utils.common.layer_utils.create_layer") as create_mock,
            patch.object(omni.usd, "get_context") as context_mock,
            patch("omni.flux.utils.common.layer_utils.validate_edit_target") as validate_mock,
        ):
            open_mock = context_mock.return_value.open_stage
            create_mock.return_value = layer0

            # Act
            layer_utils.save_layer_as("", True, root_ref, None, save_done_mock, str(layer0_path))  # noqa

        # Assert
        self.assertEqual(1, context_mock.call_count)
        self.assertEqual(1, open_mock.call_count)
        self.assertEqual(1, validate_mock.call_count)
        self.assertEqual(1, save_done_mock.call_count)

        self.assertEqual(call(""), context_mock.call_args)
        self.assertEqual(call(layer0.realPath), open_mock.call_args)
        self.assertEqual(call(""), validate_mock.call_args)
        self.assertEqual(call(True, "", [layer0.identifier]), save_done_mock.call_args)

    async def test_save_layer_as_replace_with_parent_should_replace_sublayer(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)

        root_ref = weakref.ref(root)
        layer0_ref = weakref.ref(layer0)

        save_done_mock = Mock()

        with (
            patch("omni.flux.utils.common.layer_utils.create_layer") as create_mock,
            patch.object(LayerUtils, "get_sublayer_position_in_parent") as sublayer_mock,
            patch.object(commands, "execute") as command_mock,
            patch("omni.flux.utils.common.layer_utils.validate_edit_target") as validate_mock,
        ):
            sublayer_position = 2

            create_mock.return_value = layer1
            sublayer_mock.return_value = sublayer_position

            # Act
            layer_utils.save_layer_as("", True, layer0_ref, root_ref, save_done_mock, str(layer1_path))  # noqa

            # Assert
            self.assertEqual(1, sublayer_mock.call_count)
            self.assertEqual(1, command_mock.call_count)
            self.assertEqual(1, validate_mock.call_count)
            self.assertEqual(1, save_done_mock.call_count)

            sublayer_args, _ = sublayer_mock.call_args
            self.assertEqual((root.identifier, layer0.identifier), sublayer_args)

            command_args, command_kwargs = command_mock.call_args
            self.assertEqual(("ReplaceSublayer",), command_args)
            self.assertEqual(
                {
                    "layer_identifier": root.identifier,
                    "sublayer_position": sublayer_position,
                    "new_layer_path": layer1.realPath,
                    "usd_context": "",
                },
                command_kwargs,
            )

            validate_args, _ = validate_mock.call_args
            self.assertEqual(("",), validate_args)

            save_done_args, _ = save_done_mock.call_args
            self.assertEqual((True, "", [layer1.identifier]), save_done_args)

    async def test_validate_edit_target_should_set_if_invalid(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        root = self.stage.GetRootLayer()

        with (
            patch.object(LayerUtils, "get_edit_target") as get_edit_target_mock,
            patch.object(Usd.Stage, "GetEditTarget") as stage_get_edit_target_mock,
            patch.object(LayerUtils, "set_edit_target") as set_edit_target_mock,
        ):
            get_edit_target_mock.return_value = layer0.identifier

            # Act
            layer_utils.validate_edit_target("")

            # Assert
            self.assertEqual(1, stage_get_edit_target_mock.call_count)
            self.assertEqual(1, get_edit_target_mock.call_count)
            self.assertEqual(1, set_edit_target_mock.call_count)

            set_edit_target_args, _ = set_edit_target_mock.call_args
            self.assertEqual((self.stage, root.identifier), set_edit_target_args)

    async def test_validate_edit_target_return_if_valid(self):
        # Arrange
        root = self.stage.GetRootLayer()

        with (
            patch.object(LayerUtils, "get_edit_target") as get_edit_target_mock,
            patch.object(Usd.EditTarget, "GetLayer") as get_layer_mock,
            patch.object(Usd.Stage, "GetLayerStack") as get_layer_stack_mock,
            patch.object(LayerUtils, "set_edit_target") as set_edit_target_mock,
        ):
            get_edit_target_mock.return_value = root.identifier
            get_layer_mock.return_value = root.identifier
            get_layer_stack_mock.return_value = [root.identifier]

            # Act
            layer_utils.validate_edit_target("")

            # Assert
            self.assertEqual(1, get_edit_target_mock.call_count)
            self.assertEqual(1, get_layer_mock.call_count)
            self.assertEqual(1, get_layer_stack_mock.call_count)

            self.assertFalse(set_edit_target_mock.called)

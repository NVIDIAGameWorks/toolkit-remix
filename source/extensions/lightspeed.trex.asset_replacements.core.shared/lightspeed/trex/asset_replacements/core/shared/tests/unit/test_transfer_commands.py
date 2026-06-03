"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from unittest.mock import patch

import omni.kit.test
from lightspeed.trex.asset_replacements.core.shared.commands import (
    TransferPrimDefinitionSpecToLayerCommand,
    TransferPropertySpecToLayerCommand,
    TransferReferenceSpecToLayerCommand,
)
from pxr import Sdf


class TestAssetReplacementsTransferCommands(omni.kit.test.AsyncTestCase):
    async def test_property_transfer_command_do_should_forward_to_core(self):
        # Arrange
        layer_undos = [object()]
        with patch("lightspeed.trex.asset_replacements.core.shared.commands.Setup") as setup_mock:
            core_mock = setup_mock.return_value
            core_mock.transfer_property_spec_to_layer.return_value = layer_undos
            command = TransferPropertySpecToLayerCommand(
                "/World/TestPrim.visibility",
                ["source.usda"],
                "target.usda",
                "test_context",
            )

            # Act
            result = command.do()

        # Assert
        self.assertTrue(result)
        self.assertEqual(command._layer_undos, layer_undos)
        setup_mock.assert_called_once_with("test_context")
        core_mock.transfer_property_spec_to_layer.assert_called_once_with(
            "/World/TestPrim.visibility",
            ["source.usda"],
            "target.usda",
        )

    async def test_property_transfer_command_returns_false_when_core_rejects_transfer(self):
        # Arrange
        with patch("lightspeed.trex.asset_replacements.core.shared.commands.Setup") as setup_mock:
            core_mock = setup_mock.return_value
            core_mock.transfer_property_spec_to_layer.return_value = None
            command = TransferPropertySpecToLayerCommand(
                "/World/TestPrim.visibility",
                ["source.usda"],
                "target.usda",
            )

            # Act
            result = command.do()

        # Assert
        self.assertFalse(result)
        core_mock.transfer_property_spec_to_layer.assert_called_once_with(
            "/World/TestPrim.visibility",
            ["source.usda"],
            "target.usda",
        )
        core_mock.undo_spec_transfer.assert_not_called()

    async def test_property_transfer_command_undo_should_forward_stored_undos_to_core(self):
        # Arrange
        layer_undos = [object()]
        with patch("lightspeed.trex.asset_replacements.core.shared.commands.Setup") as setup_mock:
            core_mock = setup_mock.return_value
            command = TransferPropertySpecToLayerCommand(
                "/World/TestPrim.visibility",
                ["source.usda"],
                "target.usda",
                "test_context",
            )
            command._layer_undos = layer_undos

            # Act
            command.undo()

        # Assert
        setup_mock.assert_called_once_with("test_context")
        core_mock.undo_spec_transfer.assert_called_once_with(layer_undos)

    async def test_prim_definition_transfer_command_do_should_forward_to_core(self):
        # Arrange
        layer_undos = [object()]
        with patch("lightspeed.trex.asset_replacements.core.shared.commands.Setup") as setup_mock:
            core_mock = setup_mock.return_value
            core_mock.transfer_prim_definition_spec_to_layer.return_value = layer_undos
            command = TransferPrimDefinitionSpecToLayerCommand(
                "/World/StageLight",
                ["source.usda"],
                "target.usda",
                "test_context",
            )

            # Act
            result = command.do()

        # Assert
        self.assertTrue(result)
        self.assertEqual(command._layer_undos, layer_undos)
        setup_mock.assert_called_once_with("test_context")
        core_mock.transfer_prim_definition_spec_to_layer.assert_called_once_with(
            "/World/StageLight",
            ["source.usda"],
            "target.usda",
        )

    async def test_reference_transfer_command_do_should_forward_to_core(self):
        # Arrange
        layer_undos = [object()]
        reference = Sdf.Reference("asset.usda", Sdf.Path("/World/SourceMesh"))
        with patch("lightspeed.trex.asset_replacements.core.shared.commands.Setup") as setup_mock:
            core_mock = setup_mock.return_value
            core_mock.transfer_reference_spec_to_layer.return_value = layer_undos
            command = TransferReferenceSpecToLayerCommand(
                "/World/ReferencedMesh",
                reference,
                ["source.usda"],
                "target.usda",
                "test_context",
            )

            # Act
            result = command.do()

        # Assert
        self.assertTrue(result)
        self.assertEqual(command._layer_undos, layer_undos)
        setup_mock.assert_called_once_with("test_context")
        core_mock.transfer_reference_spec_to_layer.assert_called_once_with(
            "/World/ReferencedMesh",
            reference,
            ["source.usda"],
            "target.usda",
        )

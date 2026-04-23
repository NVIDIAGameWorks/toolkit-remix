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

from contextlib import nullcontext
from unittest.mock import DEFAULT, MagicMock, patch

import omni.kit.test
from lightspeed.trex.control.stagecraft.commands import SwitchCaptureCommand


class TestCommands(omni.kit.test.AsyncTestCase):
    def _patch_capture_switch_dependencies(self):
        return patch.multiple(
            "lightspeed.trex.control.stagecraft.commands",
            _CaptureCoreSetup=DEFAULT,
        )

    def _make_settings(self, lighting_values):
        settings = MagicMock()
        if isinstance(lighting_values, list):
            settings.get.side_effect = lighting_values
        else:
            settings.get.return_value = lighting_values
        return settings

    async def test_do_applies_requested_capture_and_restores_non_stage_lighting(self):
        # Arrange
        settings = self._make_settings("camera")
        usd_context = MagicMock()
        usd_context.get_stage.return_value = None
        with (
            self._patch_capture_switch_dependencies() as patched,
            patch(
                "lightspeed.trex.control.stagecraft.commands.omni.client.normalize_url",
                side_effect=lambda path: path,
            ),
            patch("lightspeed.trex.control.stagecraft.commands.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.trex.control.stagecraft.commands.omni.usd.get_context", return_value=usd_context),
            patch("lightspeed.trex.control.stagecraft.commands.omni.kit.undo.disabled", return_value=nullcontext()),
            patch("lightspeed.trex.control.stagecraft.commands.omni.kit.commands.execute") as mock_execute,
        ):
            capture_setup = patched["_CaptureCoreSetup"].return_value
            capture_setup.get_layer.return_value = MagicMock(identifier="/captures/capture_a.usda")
            command = SwitchCaptureCommand(
                new_capture_path="/captures/capture_b.usda",
                context_name="stagecraft",
            )

            # Act
            result = command.do()

        # Assert
        self.assertEqual("/captures/capture_b.usda", result)
        patched["_CaptureCoreSetup"].assert_called_once_with("stagecraft")
        capture_setup.import_capture_layer.assert_called_once_with("/captures/capture_b.usda", do_undo=False)
        mock_execute.assert_called_once_with(
            "SetLightingMenuModeCommand",
            lighting_mode="camera",
            usd_context_name="stagecraft",
        )

    async def test_undo_restores_previous_capture_without_reapplying_stage_lighting(self):
        # Arrange
        settings = self._make_settings("stage")
        usd_context = MagicMock()
        usd_context.get_stage.return_value = None
        with (
            self._patch_capture_switch_dependencies() as patched,
            patch(
                "lightspeed.trex.control.stagecraft.commands.omni.client.normalize_url",
                side_effect=lambda path: path,
            ),
            patch("lightspeed.trex.control.stagecraft.commands.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.trex.control.stagecraft.commands.omni.usd.get_context", return_value=usd_context),
            patch("lightspeed.trex.control.stagecraft.commands.omni.kit.commands.execute") as mock_execute,
        ):
            capture_setup = patched["_CaptureCoreSetup"].return_value
            capture_setup.get_layer.return_value = MagicMock(identifier="/captures/capture_a.usda")
            command = SwitchCaptureCommand(
                new_capture_path="/captures/capture_b.usda",
                context_name="stagecraft",
            )

            # Act
            result = command.undo()

        # Assert
        self.assertEqual("/captures/capture_a.usda", result)
        patched["_CaptureCoreSetup"].assert_called_once_with("stagecraft")
        capture_setup.import_capture_layer.assert_called_once_with("/captures/capture_a.usda", do_undo=False)
        mock_execute.assert_not_called()

    async def test_redo_reapplies_requested_capture_and_restores_non_stage_lighting(self):
        # Arrange
        settings = self._make_settings("off")
        usd_context = MagicMock()
        usd_context.get_stage.return_value = None
        with (
            self._patch_capture_switch_dependencies() as patched,
            patch(
                "lightspeed.trex.control.stagecraft.commands.omni.client.normalize_url",
                side_effect=lambda path: path,
            ),
            patch("lightspeed.trex.control.stagecraft.commands.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.trex.control.stagecraft.commands.omni.usd.get_context", return_value=usd_context),
            patch("lightspeed.trex.control.stagecraft.commands.omni.kit.undo.disabled", return_value=nullcontext()),
            patch("lightspeed.trex.control.stagecraft.commands.omni.kit.commands.execute") as mock_execute,
        ):
            capture_setup = patched["_CaptureCoreSetup"].return_value
            capture_setup.get_layer.return_value = MagicMock(identifier="/captures/capture_a.usda")
            command = SwitchCaptureCommand(
                new_capture_path="/captures/capture_b.usda",
                context_name="stagecraft",
            )

            # Act
            result = command.redo()

        # Assert
        self.assertEqual("/captures/capture_b.usda", result)
        patched["_CaptureCoreSetup"].assert_called_once_with("stagecraft")
        capture_setup.import_capture_layer.assert_called_once_with("/captures/capture_b.usda", do_undo=False)
        mock_execute.assert_called_once_with(
            "SetLightingMenuModeCommand",
            lighting_mode="off",
            usd_context_name="stagecraft",
        )

    async def test_do_undo_and_redo_preserve_non_stage_lighting_active_at_each_step(self):
        # Arrange
        settings = self._make_settings(["camera", "stage", "off"])
        usd_context = MagicMock()
        usd_context.get_stage.return_value = None
        with (
            self._patch_capture_switch_dependencies() as patched,
            patch(
                "lightspeed.trex.control.stagecraft.commands.omni.client.normalize_url",
                side_effect=lambda path: path,
            ),
            patch("lightspeed.trex.control.stagecraft.commands.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.trex.control.stagecraft.commands.omni.usd.get_context", return_value=usd_context),
            patch("lightspeed.trex.control.stagecraft.commands.omni.kit.undo.disabled", return_value=nullcontext()),
            patch("lightspeed.trex.control.stagecraft.commands.omni.kit.commands.execute") as mock_execute,
        ):
            capture_setup = patched["_CaptureCoreSetup"].return_value
            capture_setup.get_layer.return_value = MagicMock(identifier="/captures/capture_a.usda")
            command = SwitchCaptureCommand(
                new_capture_path="/captures/capture_b.usda",
                context_name="stagecraft",
            )

            # Act
            do_result = command.do()
            undo_result = command.undo()
            redo_result = command.redo()

        # Assert
        self.assertEqual("/captures/capture_b.usda", do_result)
        self.assertEqual("/captures/capture_a.usda", undo_result)
        self.assertEqual("/captures/capture_b.usda", redo_result)
        self.assertEqual(
            [
                (("/captures/capture_b.usda",), {"do_undo": False}),
                (("/captures/capture_a.usda",), {"do_undo": False}),
                (("/captures/capture_b.usda",), {"do_undo": False}),
            ],
            [(call.args, call.kwargs) for call in capture_setup.import_capture_layer.call_args_list],
        )
        self.assertEqual(
            [
                (
                    ("SetLightingMenuModeCommand",),
                    {"lighting_mode": "camera", "usd_context_name": "stagecraft"},
                ),
                (
                    ("SetLightingMenuModeCommand",),
                    {"lighting_mode": "off", "usd_context_name": "stagecraft"},
                ),
            ],
            [(call.args, call.kwargs) for call in mock_execute.call_args_list],
        )

    async def test_do_returns_none_when_target_matches_current(self):
        # Arrange
        with (
            patch(
                "lightspeed.trex.control.stagecraft.commands.omni.client.normalize_url",
                side_effect=lambda path: path,
            ),
            self._patch_capture_switch_dependencies() as patched,
            patch("lightspeed.trex.control.stagecraft.commands.omni.kit.commands.execute") as mock_execute,
        ):
            capture_setup = patched["_CaptureCoreSetup"].return_value
            capture_setup.get_layer.return_value = MagicMock(identifier="/captures/capture_a.usda")
            command = SwitchCaptureCommand(
                new_capture_path="/captures/capture_a.usda",
                context_name="stagecraft",
            )

            # Act
            result = command.do()

        # Assert
        self.assertIsNone(result)
        capture_setup.import_capture_layer.assert_not_called()
        mock_execute.assert_not_called()

    async def test_undo_returns_none_when_target_matches_current(self):
        # Arrange
        with (
            patch(
                "lightspeed.trex.control.stagecraft.commands.omni.client.normalize_url",
                side_effect=lambda path: path,
            ),
            self._patch_capture_switch_dependencies() as patched,
            patch("lightspeed.trex.control.stagecraft.commands.omni.kit.commands.execute") as mock_execute,
        ):
            capture_setup = patched["_CaptureCoreSetup"].return_value
            capture_setup.get_layer.return_value = MagicMock(identifier="/captures/capture_a.usda")
            command = SwitchCaptureCommand(
                new_capture_path="/captures/capture_a.usda",
                context_name="stagecraft",
            )

            # Act
            result = command.undo()

        # Assert
        self.assertIsNone(result)
        capture_setup.import_capture_layer.assert_not_called()
        mock_execute.assert_not_called()

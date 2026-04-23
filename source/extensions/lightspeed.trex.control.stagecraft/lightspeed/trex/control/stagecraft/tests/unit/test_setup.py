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

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import omni.kit.test
import omni.usd
from lightspeed.layer_manager.core import LayerType as _LayerType
import lightspeed.trex.control.stagecraft.setup as _setup_module
from lightspeed.trex.control.stagecraft.setup import Setup


class TestSetup(omni.kit.test.AsyncTestCase):
    async def test_on_undo_shows_dialog_when_next_undo_is_capture_swap(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._stage_core_setup = MagicMock()
        setup._capture_swap_undo_dialog_open = False

        history = {
            1: SimpleNamespace(name="SwitchCaptureCommand"),
        }

        # Act
        with (
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.undo.can_undo", return_value=True),
            patch(
                "lightspeed.trex.control.stagecraft.setup.omni.kit.undo.get_undo_stack", return_value=history.values()
            ),
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog") as mock_dialog,
        ):
            setup._on_undo()

        # Assert
        setup._stage_core_setup.undo.assert_not_called()
        dialog_kwargs = mock_dialog.call_args.kwargs
        self.assertEqual(
            "Undoing this action will change the loaded capture.\n\nDo you want to load the previous capture?",
            dialog_kwargs["message"],
        )
        self.assertEqual("Undo Capture Change", dialog_kwargs["title"])
        self.assertEqual("Load Capture", dialog_kwargs["ok_label"])
        self.assertEqual("Cancel", dialog_kwargs["cancel_label"])
        self.assertTrue(setup._capture_swap_undo_dialog_open)

    async def test_on_undo_runs_stage_undo_when_capture_swap_is_not_next(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._stage_core_setup = MagicMock()
        setup._capture_swap_undo_dialog_open = False

        history = {1: SimpleNamespace(name="TransformPrimCommand")}

        # Act
        with (
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.undo.can_undo", return_value=True),
            patch(
                "lightspeed.trex.control.stagecraft.setup.omni.kit.undo.get_undo_stack", return_value=history.values()
            ),
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog") as mock_dialog,
        ):
            setup._on_undo()

        # Assert
        setup._stage_core_setup.undo.assert_called_once_with()
        mock_dialog.assert_not_called()
        self.assertFalse(setup._capture_swap_undo_dialog_open)

    async def test_dialog_ok_handler_runs_stage_undo(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._stage_core_setup = MagicMock()
        setup._capture_swap_undo_dialog_open = False

        with patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog") as mock_dialog:
            setup._show_capture_swap_undo_dialog()

        ok_handler = mock_dialog.call_args.kwargs["ok_handler"]
        ok_handler()

        setup._stage_core_setup.undo.assert_called_once_with()
        self.assertFalse(setup._capture_swap_undo_dialog_open)

    async def test_dialog_cancel_handler_keeps_stage_unchanged(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._stage_core_setup = MagicMock()
        setup._capture_swap_undo_dialog_open = False

        with patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog") as mock_dialog:
            setup._show_capture_swap_undo_dialog()

        cancel_handler = mock_dialog.call_args.kwargs["cancel_handler"]
        cancel_handler()

        setup._stage_core_setup.undo.assert_not_called()
        self.assertFalse(setup._capture_swap_undo_dialog_open)

    async def test_capture_swap_with_existing_capture_executes_single_command(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = ""
        setup._capture_core_setup = MagicMock()
        setup._replacement_core_setup = MagicMock()
        setup._update_modding_button_state = MagicMock()
        setup._capture_core_setup.get_layer.return_value = SimpleNamespace(identifier="/captures/capture_a.usda")

        with (
            patch(
                "lightspeed.trex.control.stagecraft.setup.omni.client.normalize_url",
                return_value="/captures/capture_b.usda",
            ),
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.commands.execute") as mock_execute,
        ):
            # Act
            setup._on_import_layer(_LayerType.capture, "/captures/capture_b.usda")

        # Assert
        mock_execute.assert_called_once_with(
            "SwitchCaptureCommand",
            new_capture_path="/captures/capture_b.usda",
            context_name=setup._context_name,
        )
        setup._capture_core_setup.import_capture_layer.assert_not_called()
        setup._update_modding_button_state.assert_called_once_with()

    async def test_capture_swap_same_capture_short_circuits(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = ""
        setup._capture_core_setup = MagicMock()
        setup._replacement_core_setup = MagicMock()
        setup._update_modding_button_state = MagicMock()
        setup._capture_core_setup.get_layer.return_value = SimpleNamespace(identifier="/captures/capture_a.usda")

        with (
            patch(
                "lightspeed.trex.control.stagecraft.setup.omni.client.normalize_url",
                return_value="/captures/capture_a.usda",
            ),
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.commands.execute") as mock_execute,
        ):
            # Act
            setup._on_import_layer(_LayerType.capture, "/captures/capture_a.usda")

        # Assert
        mock_execute.assert_not_called()
        setup._capture_core_setup.import_capture_layer.assert_not_called()
        setup._update_modding_button_state.assert_called_once_with()

    async def test_capture_import_without_existing_capture_bypasses_command_and_undo(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._capture_core_setup = MagicMock()
        setup._replacement_core_setup = MagicMock()
        setup._update_modding_button_state = MagicMock()
        setup._capture_core_setup.get_layer.return_value = None

        with patch("lightspeed.trex.control.stagecraft.setup.omni.kit.commands.execute") as mock_execute:
            # Act
            setup._on_import_layer(_LayerType.capture, "/captures/capture_a.usda")

        # Assert
        mock_execute.assert_not_called()
        setup._capture_core_setup.import_capture_layer.assert_called_once_with(
            "/captures/capture_a.usda", do_undo=False
        )
        setup._update_modding_button_state.assert_called_once_with()

    async def test_replacement_import_keeps_existing_behavior(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._capture_core_setup = MagicMock()
        setup._replacement_core_setup = MagicMock()
        setup._update_modding_button_state = MagicMock()

        with patch("lightspeed.trex.control.stagecraft.setup.omni.kit.commands.execute") as mock_execute:
            # Act
            setup._on_import_layer(_LayerType.replacement, "/mods/mod.usda", existing_file=True)

        # Assert
        mock_execute.assert_not_called()
        setup._replacement_core_setup.import_replacement_layer.assert_called_once_with(
            "/mods/mod.usda", use_existing_layer=True
        )
        setup._update_modding_button_state.assert_called_once_with()

    async def test_stage_open_event_checks_capture_and_clears_lighting_undo_suppression(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        setup._update_modding_button_state = MagicMock()
        setup._check_capture_on_open = MagicMock()
        next_update_async = AsyncMock()
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = True

        # Act
        with patch("lightspeed.trex.control.stagecraft.setup.omni.kit.app.get_app") as mock_get_app:
            mock_get_app.return_value.next_update_async = next_update_async
            await setup._update_modding_button_state_deferred(int(omni.usd.StageEventType.OPENED))

        # Assert
        next_update_async.assert_awaited_once()
        setup._update_modding_button_state.assert_called_once_with()
        setup._check_capture_on_open.assert_called_once_with()
        self.assertFalse(Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO)

    async def test_non_open_stage_event_does_not_check_capture(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        setup._update_modding_button_state = MagicMock()
        setup._check_capture_on_open = MagicMock()
        next_update_async = AsyncMock()
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = True

        # Act
        with patch("lightspeed.trex.control.stagecraft.setup.omni.kit.app.get_app") as mock_get_app:
            mock_get_app.return_value.next_update_async = next_update_async
            await setup._update_modding_button_state_deferred(int(omni.usd.StageEventType.CLOSING))

        # Assert
        next_update_async.assert_awaited_once()
        setup._update_modding_button_state.assert_called_once_with()
        setup._check_capture_on_open.assert_not_called()
        self.assertTrue(Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO)

    async def test_open_stage_loads_workspace_and_suppresses_stage_open_lighting_undo(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = False

        # Act
        with (
            patch(
                "lightspeed.trex.control.stagecraft.setup._ProjectWizardSchema.is_project_file_valid", return_value=True
            ),
            patch(
                "lightspeed.trex.control.stagecraft.setup._ProjectWizardSchema.are_project_symlinks_valid",
                return_value=True,
            ),
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.window.file.open_stage") as mock_open_stage,
            patch("lightspeed.trex.control.stagecraft.setup.load_layout") as mock_load_layout,
            patch("lightspeed.trex.control.stagecraft.setup._get_quicklayout_config", return_value="layout"),
        ):
            setup._Setup__open_stage_and_load_layout("C:/project/mod.usda")

        # Assert
        mock_open_stage.assert_called_once_with("C:/project/mod.usda")
        mock_load_layout.assert_called_once_with("layout")
        self.assertTrue(Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO)

    async def test_destroy_restores_stage_open_lighting_patch(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        original_on_stage_open = object()
        original_disable_lighting_undo = Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = True

        # Act
        with (
            patch.object(Setup, "_LIGHTING_STAGE_OPEN_ORIGINAL", original_on_stage_open),
            patch(
                "lightspeed.trex.control.stagecraft.setup._ViewportLightingMenuContainer._MenuContainer__on_stage_open",
                new=MagicMock(),
            ),
            patch("lightspeed.trex.control.stagecraft.setup._reset_default_attrs") as mock_reset_default_attrs,
        ):
            setup.destroy()

            # Assert
            self.assertIs(
                original_on_stage_open,
                _setup_module._ViewportLightingMenuContainer._MenuContainer__on_stage_open,
            )
            self.assertIsNone(Setup._LIGHTING_STAGE_OPEN_ORIGINAL)
            self.assertFalse(Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO)
            mock_reset_default_attrs.assert_called_once_with(setup)

        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = original_disable_lighting_undo

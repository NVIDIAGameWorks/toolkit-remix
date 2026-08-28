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

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import omni.kit.test
import omni.usd
from lightspeed.layer_manager.core import LayerType as _LayerType
import lightspeed.trex.control.stagecraft.setup as _setup_module
from lightspeed.trex.control.stagecraft.setup import Setup


class TestSetup(omni.kit.test.AsyncTestCase):
    """Test StageCraft setup behavior and resource ownership."""

    async def test_register_sidebar_items_keeps_ingestion_enabled_without_project(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context = MagicMock()
        setup._context.get_stage.return_value = None
        modding_subscription = MagicMock()
        ingestion_subscription = MagicMock()

        # Act
        with patch.object(
            _setup_module.sidebar,
            "register_items",
            side_effect=[modding_subscription, ingestion_subscription],
        ) as mock_register_items:
            setup.register_sidebar_items()

        # Assert
        self.assertEqual(2, mock_register_items.call_count)
        self.assertEqual("Modding", mock_register_items.call_args_list[0].args[0][0].name)
        self.assertEqual("Ingestion", mock_register_items.call_args_list[1].args[0][0].name)
        modding_subscription.set_enabled.assert_called_once_with(False)
        ingestion_subscription.set_enabled.assert_not_called()

    async def test_pending_ingestion_activation_ignores_another_click(self):
        """Ignore another IngestCraft activation while one task is pending."""
        # Arrange
        setup = Setup.__new__(Setup)
        activation_task = MagicMock()
        activation_task.done.return_value = False
        setup._ingest_activation_task = activation_task

        with patch.object(_setup_module, "ensure_future", return_value=activation_task) as mock_ensure_future:
            # Act
            setup._Setup__open_ingest_layout(0, 0, 0, 0)

        # Assert
        mock_ensure_future.assert_not_called()
        self.assertIs(activation_task, setup._ingest_activation_task)

    async def test_ingestion_activation_owns_task(self):
        """Retain a newly scheduled IngestCraft activation task."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._ingest_activation_task = None
        setup._deferred_tasks = set()
        activation_task = MagicMock()

        with (
            patch.object(setup, "_open_ingest_layout_async", new=MagicMock(return_value="activation-work")),
            patch.object(_setup_module, "ensure_future", return_value=activation_task),
        ):
            # Act
            setup._Setup__open_ingest_layout(0, 0, 0, 0)

        # Assert
        self.assertIs(activation_task, setup._ingest_activation_task)
        self.assertIn(activation_task, setup._deferred_tasks)

    async def test_ingest_activation_failure_shows_visible_feedback_and_releases_task(self):
        """Show activation failure feedback and release the completed task."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._ingest_activation_task = MagicMock()

        with (
            patch.object(_setup_module, "ensure_ingestcraft_loaded", new=AsyncMock(return_value=False)),
            patch.object(_setup_module, "_TrexMessageDialog") as mock_dialog,
        ):
            # Act
            await setup._open_ingest_layout_async()

        # Assert
        mock_dialog.assert_called_once()
        self.assertEqual("Unable to Open IngestCraft", mock_dialog.call_args.kwargs["title"])
        self.assertIsNone(setup._ingest_activation_task)

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

    async def test_stage_event_owns_deferred_update_task(self):
        """Retain the deferred update scheduled for a StageCraft stage event."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._deferred_tasks = set()
        deferred_task = MagicMock()

        with (
            patch.object(setup, "_update_modding_button_state_deferred", new=MagicMock(return_value="deferred-work")),
            patch.object(_setup_module.asyncio, "ensure_future", return_value=deferred_task),
        ):
            # Act
            setup._on_stage_event(SimpleNamespace(type=int(omni.usd.StageEventType.OPENED)))

        # Assert
        self.assertIn(deferred_task, setup._deferred_tasks)

    async def test_completed_deferred_task_releases_ownership(self):
        """Release a StageCraft task after it completes."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._deferred_tasks = set()
        deferred_task = MagicMock()
        setup._Setup__own_deferred_task(deferred_task)
        completion_callback = deferred_task.add_done_callback.call_args.args[0]

        # Act
        completion_callback(deferred_task)

        # Assert
        self.assertNotIn(deferred_task, setup._deferred_tasks)

    async def test_open_workfile_validates_once_before_prompting(self):
        """Validate a project once before handing its open callback to the unsaved-work prompt."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        setup.prompt_if_unsaved_project = MagicMock(return_value=False)

        with (
            patch.object(_setup_module._ProjectWizardSchema, "is_project_file_valid", return_value=True) as mock_schema,
            patch.object(_setup_module._ProjectWizardSchema, "is_deps_directory_valid", return_value=True) as mock_deps,
            patch.object(
                _setup_module._ProjectWizardSchema, "are_project_symlinks_valid", return_value=True
            ) as mock_symlinks,
        ):
            # Act
            result = setup._on_open_workfile("C:/project/mod.usda")

        # Assert
        self.assertFalse(result)
        mock_schema.assert_called_once()
        mock_deps.assert_called_once()
        mock_symlinks.assert_called_once()
        setup.prompt_if_unsaved_project.assert_called_once()

    async def test_open_workfile_false_validation_result_shows_project_wizard_without_prompting(self):
        """Open the project wizard when project-file validation returns false."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._Setup__show_project_open_wizard = MagicMock()
        setup.prompt_if_unsaved_project = MagicMock(return_value=True)

        with (
            patch.object(_setup_module._ProjectWizardSchema, "is_project_file_valid", return_value=False),
            patch.object(_setup_module._ProjectWizardSchema, "is_deps_directory_valid") as mock_deps,
            patch.object(_setup_module._ProjectWizardSchema, "are_project_symlinks_valid") as mock_symlinks,
        ):
            # Act
            result = setup._on_open_workfile("C:/project/invalid.remix")

        # Assert
        self.assertFalse(result)
        setup._Setup__show_project_open_wizard.assert_called_once_with(Path("C:/project/invalid.remix"))
        mock_deps.assert_not_called()
        mock_symlinks.assert_not_called()
        setup.prompt_if_unsaved_project.assert_not_called()

    async def test_open_workfile_other_validation_error_shows_feedback_without_prompting(self):
        """Contain ordinary project validation failures and show user feedback."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup.prompt_if_unsaved_project = MagicMock()

        with (
            patch.object(
                _setup_module._ProjectWizardSchema,
                "is_project_file_valid",
                side_effect=ValueError("The project file is not writable"),
            ),
            patch.object(_setup_module._ProjectWizardSchema, "is_deps_directory_valid") as mock_deps,
            patch.object(_setup_module._ProjectWizardSchema, "are_project_symlinks_valid") as mock_symlinks,
            patch.object(_setup_module, "_TrexMessageDialog") as mock_dialog,
        ):
            # Act
            result = setup._on_open_workfile("C:/project/invalid.usda")

        # Assert
        self.assertFalse(result)
        mock_dialog.assert_called_once_with(
            message="The project file is not writable",
            title="Invalid Selected Project",
            disable_cancel_button=True,
        )
        mock_deps.assert_not_called()
        mock_symlinks.assert_not_called()
        setup.prompt_if_unsaved_project.assert_not_called()

    async def test_open_workfile_missing_metadata_shows_guidance_without_prompting(self):
        """Show repair guidance only for the missing project metadata error."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup.prompt_if_unsaved_project = MagicMock()

        with (
            patch.object(
                _setup_module._ProjectWizardSchema,
                "is_project_file_valid",
                side_effect=_setup_module._ProjectFileMetadataError("not a valid Remix project file"),
            ),
            patch.object(_setup_module, "_TrexMessageDialog") as mock_dialog,
        ):
            # Act
            result = setup._on_open_workfile("C:/project/legacy.usda")

        # Assert
        self.assertFalse(result)
        setup.prompt_if_unsaved_project.assert_not_called()
        mock_dialog.assert_called_once()
        dialog_kwargs = mock_dialog.call_args.kwargs
        self.assertIn("Project Wizard", dialog_kwargs["message"])
        self.assertEqual("Missing Project Metadata Detected", dialog_kwargs["title"])
        self.assertTrue(dialog_kwargs["disable_cancel_button"])

    async def test_open_workfile_invalid_dependencies_shows_rebuild_dialog_without_prompting(self):
        """Offer dependency rebuilding before prompting to open an invalid project."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup.prompt_if_unsaved_project = MagicMock()

        with (
            patch.object(_setup_module._ProjectWizardSchema, "is_project_file_valid", return_value=True),
            patch.object(_setup_module._ProjectWizardSchema, "is_deps_directory_valid", return_value=False),
            patch.object(_setup_module, "_should_confirm_link_path_replacement", return_value=True),
            patch.object(_setup_module, "_show_invalid_deps_rebuild_dialog") as mock_dialog,
        ):
            # Act
            result = setup._on_open_workfile("C:/project/mod.usda")

        # Assert
        self.assertFalse(result)
        setup.prompt_if_unsaved_project.assert_not_called()
        mock_dialog.assert_called_once()
        self.assertEqual(Path("C:/project/deps"), mock_dialog.call_args.args[0])

    async def test_open_workfile_invalid_symlinks_shows_project_wizard_without_prompting(self):
        """Open the repair wizard before prompting when project symlinks are invalid."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._Setup__show_project_open_wizard = MagicMock()
        setup.prompt_if_unsaved_project = MagicMock()

        with (
            patch.object(_setup_module._ProjectWizardSchema, "is_project_file_valid", return_value=True),
            patch.object(_setup_module._ProjectWizardSchema, "is_deps_directory_valid", return_value=True),
            patch.object(_setup_module._ProjectWizardSchema, "are_project_symlinks_valid", return_value=False),
        ):
            # Act
            result = setup._on_open_workfile("C:/project/invalid.usda")

        # Assert
        self.assertFalse(result)
        setup._Setup__show_project_open_wizard.assert_called_once_with(Path("C:/project/invalid.usda"))
        setup.prompt_if_unsaved_project.assert_not_called()

    async def test_project_open_wizard_owns_completion_subscription(self):
        """Retain the project-wizard completion subscription while the wizard is open."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        setup._sub_wizard_completed = None
        wizard = MagicMock()
        wizard_subscription = MagicMock()
        wizard.subscribe_wizard_completed.return_value = wizard_subscription

        with patch.object(_setup_module, "_get_wizard_instance", return_value=wizard):
            # Act
            setup._Setup__show_project_open_wizard(Path("C:/project/mod.usda"))

        # Assert
        wizard.set_payload.assert_called_once()
        wizard.subscribe_wizard_completed.assert_called_once()
        wizard.show_project_wizard.assert_called_once_with(reset_page=True)
        self.assertIs(wizard_subscription, setup._sub_wizard_completed)

    async def test_project_open_wizard_completion_loads_workspace_and_releases_subscription(self):
        """Load the workspace and release the subscription when the project wizard completes."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._sub_wizard_completed = MagicMock()
        setup._deferred_tasks = set()

        with (
            patch.object(_setup_module, "load_layout") as mock_load_layout,
            patch.object(_setup_module, "_get_quicklayout_config", return_value="layout"),
        ):
            # Act
            setup._Setup__on_project_open_wizard_completed()

        # Assert
        mock_load_layout.assert_called_once_with("layout")
        self.assertIsNone(setup._sub_wizard_completed)

    async def test_capture_repair_completion_without_capture_releases_subscription(self):
        """Release the capture-repair subscription when the wizard returns no capture."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._sub_wizard_completed = MagicMock()

        # Act
        setup._on_capture_repair_completed({})

        # Assert
        self.assertIsNone(setup._sub_wizard_completed)

    async def test_open_stage_loads_workspace_and_suppresses_stage_open_lighting_undo(self):
        """Load the workspace while suppressing lighting undo during stage open."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        setup._deferred_tasks = set()
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = False

        # Act
        with (
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.window.file.open_stage") as mock_open_stage,
            patch("lightspeed.trex.control.stagecraft.setup.load_layout") as mock_load_layout,
            patch("lightspeed.trex.control.stagecraft.setup._get_quicklayout_config", return_value="layout"),
        ):
            setup._Setup__open_stage_and_load_layout(Path("C:/project/mod.usda"))

        # Assert
        mock_open_stage.assert_called_once_with(str(Path("C:/project/mod.usda")))
        mock_load_layout.assert_called_once_with("layout")
        self.assertTrue(Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO)

    async def test_new_workfile_owns_close_and_layout_tasks(self):
        """Retain the stage-close and Home layout tasks for a new workfile."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context = MagicMock()
        setup._context.close_stage_async = MagicMock(return_value="close-work")
        setup._deferred_tasks = set()
        close_task = MagicMock()
        layout_task = MagicMock()

        with (
            patch.object(_setup_module, "ensure_future", return_value=close_task),
            patch.object(_setup_module, "load_layout", return_value=layout_task),
            patch.object(_setup_module, "_get_quicklayout_config", return_value="layout"),
        ):
            # Act
            setup._Setup__create_stage_and_save_previous_identifier()

        # Assert
        self.assertEqual({close_task, layout_task}, setup._deferred_tasks)

    async def test_installed_closure_survives_uninstall_resetting_class_attr(self):
        # Regression: omni.kit.viewport.menubar.lighting subscribes to the
        # stage-open event and holds a strong reference to whatever closure was
        # bound to ``_MenuContainer__on_stage_open`` AT SUBSCRIPTION TIME. If
        # ``__uninstall_stage_open_lighting_undo_patch`` later runs (or the
        # extension is hot-reloaded) the class attribute
        # ``_LIGHTING_STAGE_OPEN_ORIGINAL`` is reset to ``None``. An in-flight
        # event firing after that reset would dereference None and raise
        # ``TypeError: 'NoneType' object is not callable``, which has been
        # observed to cascade into a GPU crash during HL2 stage open. The fix
        # is to capture the original as a closure-local — pin that contract.
        original_disable_lighting_undo = Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO
        original_class_attr = Setup._LIGHTING_STAGE_OPEN_ORIGINAL
        original_on_stage_open = MagicMock(name="original_on_stage_open", return_value="sentinel")
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = False
        Setup._LIGHTING_STAGE_OPEN_ORIGINAL = None
        try:
            with patch(
                "lightspeed.trex.control.stagecraft.setup._ViewportLightingMenuContainer._MenuContainer__on_stage_open",
                new=original_on_stage_open,
            ):
                # Install captures the original, replaces the attribute with a closure.
                Setup._Setup__install_stage_open_lighting_undo_patch()
                installed_closure = _setup_module._ViewportLightingMenuContainer._MenuContainer__on_stage_open
                self.assertIsNot(installed_closure, original_on_stage_open)

                # Uninstall restores the original AND sets the class attr to None.
                Setup._Setup__uninstall_stage_open_lighting_undo_patch()
                self.assertIsNone(Setup._LIGHTING_STAGE_OPEN_ORIGINAL)

                # The closure is what a late event subscription would still hold.
                # Calling it after uninstall must NOT crash — it should call the
                # local-captured original, not deref the (now-None) class attr.
                result = installed_closure(
                    MagicMock(name="menu_container"),
                    MagicMock(name="menu_context"),
                    "stagecraft",
                    MagicMock(name="usd_context"),
                    MagicMock(name="prev_mode"),
                )
                self.assertEqual(
                    result, "sentinel", "post-uninstall closure call must delegate to the captured original"
                )
                original_on_stage_open.assert_called_once()
        finally:
            Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = original_disable_lighting_undo
            Setup._LIGHTING_STAGE_OPEN_ORIGINAL = original_class_attr

    async def test_destroy_restores_stage_open_lighting_patch(self):
        """Restore the captured lighting callback when StageCraft is destroyed."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        setup._ingest_activation_task = None
        setup._deferred_tasks = set()
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

    async def test_destroy_releases_sidebar_subscriptions(self):
        """Release StageCraft sidebar subscriptions and deferred tasks during teardown."""
        # Arrange
        setup = Setup.__new__(Setup)
        setup._Setup__sub_sidebar_items = MagicMock()
        setup._Setup__sub_ingestion_sidebar_item = MagicMock()
        ingest_activation_task = MagicMock()
        deferred_task = MagicMock()
        setup._ingest_activation_task = ingest_activation_task
        setup._deferred_tasks = {ingest_activation_task, deferred_task}

        # Act
        with (
            patch.object(setup, "_Setup__set_stage_open_lighting_undo_disabled"),
            patch.object(setup, "_Setup__uninstall_light_rig_reference_validation_patch"),
            patch.object(setup, "_Setup__uninstall_stage_open_lighting_undo_patch"),
            patch("lightspeed.trex.control.stagecraft.setup._reset_default_attrs"),
        ):
            setup.destroy()

        # Assert
        ingest_activation_task.cancel.assert_called_once_with()
        deferred_task.cancel.assert_called_once_with()
        self.assertIsNone(setup._ingest_activation_task)
        self.assertEqual(set(), setup._deferred_tasks)
        self.assertIsNone(setup._Setup__sub_sidebar_items)
        self.assertIsNone(setup._Setup__sub_ingestion_sidebar_item)

    async def test_destroy_releases_load_workfile_subscription(self):
        """Release the load-workfile subscription during StageCraft teardown."""
        # Arrange
        load_workfile_subscription = MagicMock()
        event_manager = MagicMock()
        event_manager.subscribe_global_custom_event.side_effect = [MagicMock(), load_workfile_subscription]
        context = MagicMock()
        contexts = MagicMock()
        contexts.get_usd_context.return_value = context
        settings = MagicMock()
        settings.get.return_value = ""

        with (
            patch.object(_setup_module, "_trex_contexts_instance", return_value=contexts),
            patch.object(_setup_module, "_LayerManagerCore"),
            patch.object(_setup_module, "_get_menu_workfile_instance"),
            patch.object(_setup_module, "_StageCoreSetup"),
            patch.object(_setup_module, "_CaptureCoreSetup"),
            patch.object(_setup_module, "_ReplacementCoreSetup"),
            patch.object(_setup_module, "_get_event_manager_instance", return_value=event_manager),
            patch.object(_setup_module, "_get_global_hotkey_manager"),
            patch.object(_setup_module.carb.settings, "get_settings", return_value=settings),
            patch.object(Setup, "_Setup__install_light_rig_reference_validation_patch"),
            patch.object(Setup, "_Setup__install_stage_open_lighting_undo_patch"),
            patch.object(Setup, "_Setup__set_stage_open_lighting_undo_disabled"),
            patch.object(Setup, "_Setup__uninstall_light_rig_reference_validation_patch"),
            patch.object(Setup, "_Setup__uninstall_stage_open_lighting_undo_patch"),
        ):
            setup = Setup()

            # Act
            setup.destroy()

        # Assert
        load_workfile_subscription.destroy.assert_called_once_with()
        self.assertIsNone(setup._sub_load_workfile)

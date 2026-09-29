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

__all__ = ["TestProjectWizardFeedback"]

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from omni.kit.test import AsyncTestCase

from ... import setup_ui

_OPENING_PROJECT_TITLE = "Opening Project"


class _ProgressPopup:
    """Record progress popup state without creating live UI."""

    instances = []
    created = None

    def __init__(self, title, status_text=""):
        """Create a progress-popup recorder."""
        self.title = title
        self.status_text = status_text
        self.progress = 0
        self.cancel_enabled = True
        self.cancel_fn = None
        self.visible = False
        self.destroyed = False
        self.destroyed_event = asyncio.Event()
        self.instances.append(self)
        self.created.put_nowait(self)

    def set_cancel_fn(self, callback):
        """Store the cancellation callback."""
        self.cancel_fn = callback

    def set_cancel_enabled(self, enabled):
        """Store whether cancellation is enabled."""
        self.cancel_enabled = enabled

    def set_progress(self, progress):
        """Store the displayed progress."""
        self.progress = progress

    def set_status_text(self, status_text):
        """Store the displayed status text."""
        self.status_text = status_text

    def show(self):
        """Mark the popup visible."""
        self.visible = True

    def hide(self):
        """Mark the popup hidden."""
        self.visible = False

    def is_visible(self):
        """Return whether the popup is visible."""
        return self.visible

    def destroy(self):
        """Mark the popup destroyed and notify waiters."""
        self.destroyed = True
        self.visible = False
        self.destroyed_event.set()


class _ErrorPopup:
    """Record error popup details without creating live UI."""

    shown = []
    shown_event = None

    def __init__(self, title, message, details=None, window_size=None):
        """Create an error-popup recorder."""
        self.details = details

    def show(self):
        """Record the shown error details and notify waiters."""
        self.shown.append(self.details)
        self.shown_event.set()


class _MessageDialog:
    """Record awaitable message dialog choices without creating live UI."""

    instances = []
    created = None

    def __init__(self, **kwargs):
        """Create a message-dialog recorder."""
        self.ok_handler = kwargs.get("ok_handler")
        self.middle_handler = kwargs.get("middle_handler")
        self.middle_2_handler = kwargs.get("middle_2_handler")
        self.cancel_handler = kwargs.get("cancel_handler")
        self.on_window_closed_fn = kwargs.get("on_window_closed_fn")
        self.instances.append(self)
        self.created.put_nowait(self)

    @classmethod
    async def prompt_async(cls, **_kwargs):
        """Wait for and return the recorded dialog choice."""
        result = asyncio.get_running_loop().create_future()

        def resolve(value):
            if not result.done():
                result.set_result(value)

        cls(
            ok_handler=lambda: resolve(setup_ui._MessageDialogResult.OK),
            middle_handler=lambda: resolve(setup_ui._MessageDialogResult.MIDDLE),
            middle_2_handler=lambda: resolve(setup_ui._MessageDialogResult.MIDDLE_2),
            cancel_handler=lambda: resolve(setup_ui._MessageDialogResult.CANCEL),
            on_window_closed_fn=lambda: resolve(setup_ui._MessageDialogResult.CANCEL),
        )
        return await result

    def close(self):
        """Invoke the dialog's close callback."""
        if self.on_window_closed_fn:
            self.on_window_closed_fn()


class _WizardWindow:
    """Record wizard restoration without creating live UI."""

    def __init__(self):
        """Create a wizard-window recorder."""
        self.show_count = 0
        self.shown = asyncio.Event()

    def show_wizard(self, reset_page=False):
        """Record that the wizard was restored and notify waiters."""
        self.show_count += 1
        self.shown.set()


class _App:
    """Provide the application update boundary used by prompt creation."""

    def __init__(self):
        """Create a controllable application update boundary."""
        self.next_update_started = asyncio.Queue()
        self.next_update_allowed = asyncio.Event()
        self.next_update_allowed.set()

    async def next_update_async(self):
        """Yield at the application update boundary."""
        self.next_update_started.put_nowait(None)
        await self.next_update_allowed.wait()


class _WizardCore:
    """Provide deterministic probe and setup boundaries for the wizard."""

    def __init__(self):
        """Create controllable probe and setup boundaries."""
        self.probe_started = asyncio.Event()
        self.probe_finished = asyncio.Event()
        self.setup_started = asyncio.Event()
        self.setup_finished = asyncio.Event()
        self.setup_finished.set()
        self.probe_models = []
        self.setup_payloads = []
        self.progress_callback = None
        self.probe_progress_callback = None
        self.setup_result = (True, None)
        self.setup_exception = None
        self.probe_cancelled = True
        self.probe_package_files = []
        self.needs_symlink = False

    def subscribe_run_progress(self, callback):
        """Store the project setup progress callback."""
        self.progress_callback = callback
        return SimpleNamespace()

    async def probe_rtxio_project(self, model, on_progress=None):
        """Wait for and return the configured RTX IO probe result."""
        self.probe_models.append(model)
        self.probe_progress_callback = on_progress
        self.probe_started.set()
        if on_progress:
            on_progress(0, 1, "Checking package files")
        await self.probe_finished.wait()
        return SimpleNamespace(
            package_files=self.probe_package_files, broken_references=[], was_cancelled=self.probe_cancelled
        )

    def cancel_rtxio(self):
        """Release the pending RTX IO probe."""
        self.probe_finished.set()

    def need_project_directory_symlink(self, _model):
        """Return whether the configured setup needs a project symlink."""
        return self.needs_symlink

    def need_deps_directory_symlink(self, _model):
        """Return whether the configured setup needs a dependencies symlink."""
        return False

    async def setup_project_async(self, payload):
        """Wait for and return the configured project setup result."""
        self.setup_payloads.append(payload)
        if self.progress_callback:
            self.progress_callback(30)
        self.setup_started.set()
        await self.setup_finished.wait()
        if self.setup_exception:
            raise self.setup_exception
        return self.setup_result

    def destroy(self):
        """Release the pending RTX IO probe during fixture cleanup."""
        self.probe_finished.set()


class TestProjectWizardFeedback(AsyncTestCase):
    """Verify project-open feedback and recovery behavior."""

    async def setUp(self):
        """Create isolated Project Wizard feedback doubles."""
        self.core = _WizardCore()
        self.app = _App()
        self.patches = [
            patch.object(setup_ui, "_ProjectWizardCore", return_value=self.core),
            patch.object(setup_ui, "_ProgressPopup", _ProgressPopup),
            patch.object(setup_ui, "_ErrorPopup", _ErrorPopup),
            patch.object(setup_ui, "_TrexMessageDialog", _MessageDialog),
            patch.object(setup_ui, "_ProjectWizardSchema", SimpleNamespace),
            patch.object(setup_ui.omni.kit.app, "get_app", return_value=self.app),
            patch.object(
                setup_ui.carb.settings,
                "get_settings",
                return_value=SimpleNamespace(get=lambda _setting_name: False),
            ),
        ]
        _ErrorPopup.shown.clear()
        _ErrorPopup.shown_event = asyncio.Event()
        _ProgressPopup.instances.clear()
        _ProgressPopup.created = asyncio.Queue()
        _MessageDialog.instances.clear()
        _MessageDialog.created = asyncio.Queue()
        for active_patch in self.patches:
            active_patch.start()
        self.wizard = setup_ui.OpenProjectWizardWindow()
        self.wizard.show_capture_picker = True
        self.wizard._wizard_window = _WizardWindow()
        self.completion_subscription = None

    async def tearDown(self):
        """Destroy the wizard and wait for its scheduled tasks to stop."""
        tasks = tuple(self.wizard._project_open_tasks or ())
        self.completion_subscription = None
        self.wizard.destroy()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for active_patch in reversed(self.patches):
            active_patch.stop()

    async def test_accept_wizard_completion_copies_payload_before_async_processing(self):
        """Preserve the accepted payload when the caller mutates its original data."""
        # Arrange
        payload = {"existing_project": True, "project_file": "first.usda", "existing_mods": ["first_mod.usda"]}

        # Act
        self.wizard._accept_wizard_completion(payload)
        payload["project_file"] = "changed.usda"
        payload["existing_mods"].append("changed_mod.usda")
        await self.core.probe_started.wait()

        # Assert
        self.assertEqual("first.usda", self.core.probe_models[0].project_file)
        self.assertEqual(["first_mod.usda"], self.core.probe_models[0].existing_mods)

    async def test_accept_wizard_completion_while_running_rejects_duplicate(self):
        """Reject a repeated completion while the first request is running."""
        # Arrange
        first_payload = {"existing_project": True, "project_file": "first.usda"}

        # Act
        self.wizard._accept_wizard_completion(first_payload)
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "second.usda"})

        # Assert
        self.assertTrue(self.wizard._project_open_in_progress)
        self.assertEqual(1, len(self.wizard._project_open_tasks))

    async def test_accept_capture_completion_defers_feedback_until_next_update(self):
        """Create capture feedback only after the wizard completion callback has returned."""
        # Arrange
        self.app.next_update_allowed.clear()

        # Act
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
        await self.app.next_update_started.get()
        open_in_progress_before_update = self.wizard._project_open_in_progress
        popup_before_update = self.wizard._progress_popup
        instances_before_update = list(_ProgressPopup.instances)
        self.app.next_update_allowed.set()
        await self.core.probe_started.wait()

        # Assert
        self.assertTrue(open_in_progress_before_update)
        self.assertIsNone(popup_before_update)
        self.assertEqual([], instances_before_update)
        self.assertEqual(1, len(_ProgressPopup.instances))
        self.assertTrue(self.wizard._progress_popup.visible)
        self.assertEqual(_OPENING_PROJECT_TITLE, self.wizard._progress_popup.title)

    async def test_cancel_probe_restores_wizard_and_clears_feedback(self):
        """Restore the wizard after cancelling the package probe."""
        # Arrange
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
        await self.core.probe_started.wait()

        # Act
        self.wizard._progress_popup.cancel_fn()
        await self.wizard._wizard_window.shown.wait()

        # Assert
        self.assertEqual(1, self.wizard._wizard_window.show_count)
        self.assertIsNone(self.wizard._progress_popup)
        self.assertFalse(self.wizard._project_open_in_progress)

    async def test_probe_progress_after_cancel_does_not_reshow_capture_feedback(self):
        """Keep capture feedback hidden while probe cancellation finishes."""
        # Arrange
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
        await self.core.probe_started.wait()
        progress_popup = self.wizard._progress_popup

        # Act
        progress_popup.hide()
        progress_popup.cancel_fn()
        self.core.probe_progress_callback(1, 2, "Finishing current package")

        # Assert
        self.assertFalse(progress_popup.visible)

    async def test_destroy_before_deferred_feedback_does_not_create_ui(self):
        """Cancel capture opening before the deferred popup can be created."""
        # Arrange
        self.app.next_update_allowed.clear()
        wizard_window = self.wizard._wizard_window
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
        await self.app.next_update_started.get()
        tasks = tuple(self.wizard._project_open_tasks)

        # Act
        self.wizard.destroy()
        self.app.next_update_allowed.set()
        await asyncio.gather(*tasks, return_exceptions=True)

        # Assert
        self.assertEqual([], _ProgressPopup.instances)
        self.assertEqual([], _ErrorPopup.shown)
        self.assertEqual(0, wizard_window.show_count)
        self.assertIsNone(self.wizard._progress_popup)

    async def test_destroy_before_normal_open_task_runs_does_not_start_probe(self):
        """Cancel normal opening before its scheduled package probe can start."""
        # Arrange
        self.wizard.show_capture_picker = False
        wizard_window = self.wizard._wizard_window
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
        tasks = tuple(self.wizard._project_open_tasks)

        # Act
        self.wizard.destroy()
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert
        self.assertTrue(tasks[0].cancelled())
        self.assertIsInstance(results[0], asyncio.CancelledError)
        self.assertEqual([], self.core.probe_models)
        self.assertEqual([], _ErrorPopup.shown)
        self.assertEqual(0, wizard_window.show_count)

    async def test_wizard_completion_after_destroy_does_not_start_probe(self):
        """Ignore a stale project-open completion after wizard teardown."""
        # Arrange
        payload = {"existing_project": True, "project_file": "project.usda"}
        self.wizard.destroy()

        # Act
        await self.wizard._on_wizard_completed(payload)

        # Assert
        self.assertEqual([], self.core.probe_models)
        self.assertEqual([], _ProgressPopup.instances)

    async def test_destroy_during_probe_does_not_restore_wizard(self):
        """Cancel pending work without recreating UI during shutdown."""
        # Arrange
        wizard_window = self.wizard._wizard_window
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
        await self.core.probe_started.wait()
        tasks = tuple(self.wizard._project_open_tasks)

        # Act
        self.wizard.destroy()
        await asyncio.gather(*tasks, return_exceptions=True)

        # Assert
        self.assertEqual(0, wizard_window.show_count)
        self.assertIsNone(self.wizard._wizard_window)

    async def test_project_setup_success_transitions_to_scene_opening_and_clears_feedback(self):
        """Keep modal feedback through setup and release it after the scene-open handoff."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        opened_projects = []
        payload = {"existing_project": True, "project_file": "project.usda"}

        # Act
        with (
            patch.object(self.wizard, "_is_stage_already_open", return_value=False),
            patch.object(setup_ui.omni.kit.window.file, "open_stage", side_effect=opened_projects.append),
        ):
            self.wizard._accept_wizard_completion(payload)
            progress_popup = await _ProgressPopup.created.get()
            await progress_popup.destroyed_event.wait()

        # Assert
        self.assertEqual(["project.usda"], opened_projects)
        self.assertEqual("Opening project...", progress_popup.status_text)
        self.assertEqual(1, progress_popup.progress)
        self.assertFalse(progress_popup.cancel_enabled)
        self.assertTrue(progress_popup.destroyed)
        self.assertIsNone(self.wizard._progress_popup)

    async def test_normal_open_completes_without_continuous_opening_popup(self):
        """Preserve normal project opening without the capture preparation popup."""
        # Arrange
        self.wizard.show_capture_picker = False
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        completed = asyncio.Event()
        self.completion_subscription = self.wizard.subscribe_wizard_completed(lambda _payload: completed.set())
        opened_projects = []

        # Act
        with (
            patch.object(self.wizard, "_is_stage_already_open", return_value=False),
            patch.object(setup_ui.omni.kit.window.file, "open_stage", side_effect=opened_projects.append),
        ):
            self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "open.usda"})
            await completed.wait()

        # Assert
        self.assertEqual(["open.usda"], opened_projects)
        self.assertNotIn(_OPENING_PROJECT_TITLE, [popup.title for popup in _ProgressPopup.instances])

    async def test_normal_open_package_and_elevation_prompts_complete_without_opening_popup(self):
        """Preserve normal Open prompts without creating capture feedback."""
        # Arrange
        self.wizard.show_capture_picker = False
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.probe_package_files = [Path("package.pkg")]
        self.core.needs_symlink = True
        completed = asyncio.Event()
        self.completion_subscription = self.wizard.subscribe_wizard_completed(lambda _payload: completed.set())

        # Act
        with patch.object(self.wizard, "_is_stage_already_open", return_value=True):
            self.wizard._accept_wizard_completion({"existing_project": True, "project_file": Path("open.usda")})
            package_dialog = await _MessageDialog.created.get()
            package_dialog.ok_handler()
            elevation_dialog = await _MessageDialog.created.get()
            elevation_dialog.ok_handler()
            await completed.wait()

        # Assert
        self.assertEqual(2, len(_MessageDialog.instances))
        self.assertEqual(1, len(self.core.setup_payloads))
        self.assertNotIn(_OPENING_PROJECT_TITLE, [popup.title for popup in _ProgressPopup.instances])

    async def test_edit_project_completes_without_continuous_opening_popup(self):
        """Preserve project editing without the capture preparation popup."""
        # Arrange
        self.wizard.destroy()
        self.wizard = setup_ui.CreateProjectWizardWindow()
        self.wizard._wizard_window = _WizardWindow()
        self.wizard.set_payload({"project_file": Path("edit.usda")})
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        completed = asyncio.Event()
        self.completion_subscription = self.wizard.subscribe_wizard_completed(lambda _payload: completed.set())
        opened_projects = []
        payload = {"existing_project": True, "project_file": "edit.usda", "existing_mods": ["mod.usda"]}

        # Act
        with (
            patch.object(self.wizard, "_is_stage_already_open", return_value=False),
            patch.object(setup_ui.omni.kit.window.file, "open_stage", side_effect=opened_projects.append),
        ):
            self.wizard._accept_wizard_completion(payload)
            await completed.wait()

        # Assert
        self.assertEqual(["edit.usda"], opened_projects)
        self.assertEqual(["mod.usda"], self.core.setup_payloads[0]["existing_mods"])
        self.assertNotIn(_OPENING_PROJECT_TITLE, [popup.title for popup in _ProgressPopup.instances])

    async def test_project_setup_while_loading_keeps_feedback_visible_and_disables_cancellation(self):
        """Keep modal loading feedback visible while project preparation is running."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.setup_finished.clear()
        self.core.setup_exception = asyncio.CancelledError()

        # Act
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
        await self.core.setup_started.wait()

        # Assert
        self.assertTrue(self.wizard._project_open_in_progress)
        self.assertTrue(self.wizard._progress_popup.visible)
        self.assertEqual("Loading project data...", self.wizard._progress_popup.status_text)
        self.assertEqual(0.3, self.wizard._progress_popup.progress)
        self.assertFalse(self.wizard._progress_popup.cancel_enabled)

    async def test_project_setup_error_restores_wizard_and_shows_error(self):
        """Restore the wizard and retain error details when project setup fails."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.setup_result = (False, "setup failed")

        # Act
        with patch.object(setup_ui.carb, "log_error"):
            self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
            await _ErrorPopup.shown_event.wait()

        # Assert
        self.assertEqual(1, self.wizard._wizard_window.show_count)
        self.assertEqual(["setup failed"], _ErrorPopup.shown)
        self.assertIsNone(self.wizard._progress_popup)

    async def test_project_setup_exception_restores_wizard_shows_error_and_logs_failure(self):
        """Recover the wizard and log diagnostic details when project preparation raises."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.setup_exception = RuntimeError("stage load failed")

        # Act
        with patch.object(setup_ui.carb, "log_error") as log_error:
            self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
            await _ErrorPopup.shown_event.wait()

        # Assert
        self.assertEqual(1, self.wizard._wizard_window.show_count)
        self.assertEqual(["stage load failed"], _ErrorPopup.shown)
        self.assertIsNone(self.wizard._progress_popup)
        log_error.assert_called_once_with("Project Wizard open request failed: stage load failed")

    async def test_elevation_prompt_ok_runs_setup_without_opening_another_prompt(self):
        """Run setup directly after acknowledging the elevation prompt."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.needs_symlink = True

        # Act
        with patch.object(self.wizard, "_is_stage_already_open", return_value=True):
            self.wizard._accept_wizard_completion({"existing_project": True, "project_file": "project.usda"})
            dialog = await _MessageDialog.created.get()
            progress_popup = self.wizard._progress_popup
            dialog.ok_handler()
            await progress_popup.destroyed_event.wait()

        # Assert
        self.assertEqual(1, len(_MessageDialog.instances))
        self.assertEqual(1, len(self.core.setup_payloads))

    async def test_package_then_elevation_prompts_ok_runs_setup_once(self):
        """Resolve each sequential prompt independently before running setup."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.probe_package_files = [Path("package.pkg")]
        self.core.needs_symlink = True

        # Act
        with patch.object(self.wizard, "_is_stage_already_open", return_value=True):
            self.wizard._accept_wizard_completion({"existing_project": True, "project_file": Path("project.usda")})
            package_dialog = await _MessageDialog.created.get()
            progress_popup = self.wizard._progress_popup
            package_dialog.ok_handler()
            elevation_dialog = await _MessageDialog.created.get()
            elevation_dialog.ok_handler()
            await progress_popup.destroyed_event.wait()

        # Assert
        self.assertEqual(2, len(_MessageDialog.instances))
        self.assertEqual(1, len(self.core.setup_payloads))

    async def test_elevation_prompt_close_restores_wizard_and_clears_request(self):
        """Restore the wizard when the elevation prompt is closed."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.needs_symlink = True

        # Act
        await self._close_prompt_and_wait_for_recovery({"existing_project": True, "project_file": "project.usda"})

        # Assert
        self.assertEqual(1, self.wizard._wizard_window.show_count)
        self.assertFalse(self.wizard._project_open_in_progress)
        self.assertIsNone(self.wizard._progress_popup)

    async def test_package_prompt_cancel_then_close_restores_wizard_once(self):
        """Treat package prompt cancellation and its close callback as one recovery."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.probe_package_files = [Path("package.pkg")]

        # Act
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": Path("project.usda")})
        dialog = await _MessageDialog.created.get()
        dialog.cancel_handler()
        dialog.close()
        await self.wizard._wizard_window.shown.wait()

        # Assert
        self.assertEqual(1, self.wizard._wizard_window.show_count)
        self.assertFalse(self.wizard._project_open_in_progress)
        self.assertIsNone(self.wizard._progress_popup)

    async def test_package_prompt_close_restores_wizard_and_clears_request(self):
        """Restore the wizard when the package prompt is closed."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.probe_package_files = [Path("package.pkg")]

        # Act
        await self._close_prompt_and_wait_for_recovery({"existing_project": True, "project_file": Path("project.usda")})

        # Assert
        self.assertEqual(1, self.wizard._wizard_window.show_count)
        self.assertFalse(self.wizard._project_open_in_progress)
        self.assertIsNone(self.wizard._progress_popup)

    async def test_package_prompt_confirmation_after_destroy_does_not_restart_project_open(self):
        """Ignore a retained package prompt callback after wizard destruction."""
        # Arrange
        self.core.probe_cancelled = False
        self.core.probe_finished.set()
        self.core.probe_package_files = [Path("package.pkg")]
        self.wizard._accept_wizard_completion({"existing_project": True, "project_file": Path("project.usda")})
        dialog = await _MessageDialog.created.get()
        self.wizard.destroy()

        # Act
        dialog.ok_handler()

        # Assert
        self.assertIsNone(self.wizard._project_open_tasks)
        self.assertIsNone(self.wizard._progress_popup)

    async def _close_prompt_and_wait_for_recovery(self, payload):
        """Close the next project-open prompt and wait for wizard recovery."""
        self.wizard._accept_wizard_completion(payload)
        dialog = await _MessageDialog.created.get()
        dialog.close()
        await self.wizard._wizard_window.shown.wait()

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

import abc
import asyncio
from copy import deepcopy
from enum import Enum
from pathlib import Path

import carb.settings
import omni.kit.app
import omni.kit.window.file
from lightspeed.trex.project_wizard.core import SETTING_JUNCTION_NAME as _SETTING_JUNCTION_NAME
from lightspeed.trex.project_wizard.core import PROJECT_LOADING_PROGRESS_START as _PROJECT_LOADING_PROGRESS_START
from lightspeed.trex.project_wizard.core import ProjectWizardCore as _ProjectWizardCore
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.project_wizard.core import ProjectWizardSchema as _ProjectWizardSchema
from lightspeed.trex.project_wizard.open_project_page.widget import WizardOpenProjectPage as _WizardOpenProjectPage
from lightspeed.trex.project_wizard.setup_page.widget import SetupPage as _SetupPage
from lightspeed.trex.project_wizard.start_page.widget import WizardStartPage as _WizardStartPage
from lightspeed.trex.utils.widget import MessageDialogResult as _MessageDialogResult
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni import ui, usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.dialog import ErrorPopup as _ErrorPopup
from omni.flux.utils.dialog import ProgressPopup as _ProgressPopup
from omni.flux.wizard.widget import WizardModel as _WizardModel
from omni.flux.wizard.widget import WizardPage as _WizardPage
from omni.flux.wizard.window import WizardWindow as _WizardWindow

_PREPARING_PROJECT_STATUS = "Preparing project..."


class WizardTypes(Enum):
    CREATE = "Create"
    OPEN = "Open"


class ProjectWizardBase(abc.ABC):
    def __init__(self, context_name: str = "", width: int = 650, height: int = 400):
        """Initialize the wizard and its project-open lifecycle state."""
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._wizard_core = _ProjectWizardCore()
        self._project_open_in_progress = False
        self._progress_popup = None
        self._run_progress_sub = None
        self._project_open_tasks = set()
        self._width = width
        self._height = height

        self.__on_wizard_completed = _Event(copy=True)

    @property
    @abc.abstractmethod
    def _default_attrs(self) -> dict[str, None]:
        """Return legacy wizard attributes managed by the reset helper."""
        return {
            "_context_name": None,
            "_wizard_core": None,
            "_wizard_window": None,
            "_wizard_completed_sub": None,
            "_payload": None,
        }

    @property
    @abc.abstractmethod
    def _start_page(self) -> _WizardPage:
        pass

    @property
    def context_name(self) -> str:
        return self._context_name

    @property
    def _show_opening_feedback(self) -> bool:
        """Return whether this wizard needs continuous project-opening feedback."""
        return False

    async def _on_wizard_completed(self, payload: dict):
        """Probe packages and prepare the accepted project for opening."""
        if self._wizard_core is None:
            return

        async def _run_setup_project(
            extract_rtxio_packages: bool = False, extract_rtxio_overwrite_existing: bool = False
        ):
            """Prepare the accepted project and complete its scene-open handoff."""
            setup_payload = dict(payload)
            setup_payload[_ProjectWizardKeys.EXTRACT_RTXIO_PACKAGES.value] = extract_rtxio_packages
            setup_payload[_ProjectWizardKeys.EXTRACT_RTXIO_OVERWRITE_EXISTING.value] = extract_rtxio_overwrite_existing
            carb.log_info(
                f"Project Wizard is preparing project: {setup_payload[_ProjectWizardKeys.PROJECT_FILE.value]}"
            )
            if self._progress_popup is not None:
                self._progress_popup.set_cancel_enabled(False)
                self._progress_popup.set_status_text(_PREPARING_PROJECT_STATUS)
                self._progress_popup.set_progress(0)
                self._run_progress_sub = self._wizard_core.subscribe_run_progress(self._on_setup_progress)
            success, error = await self._wizard_core.setup_project_async(setup_payload)
            self._on_setup_completed(setup_payload, success, error)

        async def _setup_project(extract_rtxio_packages: bool = False, extract_rtxio_overwrite_existing: bool = False):
            """Request elevation when needed before preparing the project."""
            if (
                any(
                    [
                        self._wizard_core.need_project_directory_symlink(model),
                        self._wizard_core.need_deps_directory_symlink(model),
                    ]
                )
                and not force_junction
            ):
                await omni.kit.app.get_app().next_update_async()

                if self._progress_popup is not None:
                    self._progress_popup.hide()
                result = await _TrexMessageDialog.prompt_async(
                    title="Elevated Privileges Required",
                    message=(
                        'You will be prompted with a "User Account Control" window.\n\n'
                        "RTX Remix requires elevated privileges to symlink your project in your game install directory.\n\n"
                        "Without elevated privileges the project creation will fail."
                    ),
                    cancel_label=None,
                )
                if result != _MessageDialogResult.OK:
                    self._cancel_project_open(model.project_file)
                    return
                _show_setup_feedback()
            await _run_setup_project(extract_rtxio_packages, extract_rtxio_overwrite_existing)

        def _show_setup_feedback():
            """Restore non-cancellable project preparation feedback after a prompt."""
            if self._progress_popup is not None:
                self._progress_popup.show()
                self._progress_popup.set_cancel_enabled(False)

        settings = carb.settings.get_settings()
        force_junction = settings.get(_SETTING_JUNCTION_NAME)  # junction doesn't need admin right

        model = _ProjectWizardSchema(**payload)
        probe_popup = self._progress_popup or _ProgressPopup(title="Checking RTX IO Packages")
        owns_probe_popup = probe_popup is not self._progress_popup
        if owns_probe_popup:
            probe_popup.set_cancel_fn(self._wizard_core.cancel_rtxio)

        def _on_probe_progress(current: int, total: int, status: str):
            """Update feedback for the RTX IO package probe."""
            if owns_probe_popup and not probe_popup.is_visible():
                probe_popup.show()
            status_text = status
            if total > 0:
                status_text = f"{status}\n{current} / {total}"
            if probe_popup.status_text != status_text:
                probe_popup.set_status_text(status_text)
            probe_popup.set_progress(current / total if total > 0 else 0)

        carb.log_info(f"Project Wizard is checking RTX IO packages: {model.project_file}")
        try:
            probe_result = await self._wizard_core.probe_rtxio_project(model, on_progress=_on_probe_progress)
        finally:
            if owns_probe_popup:
                if probe_popup.is_visible():
                    probe_popup.hide()
                probe_popup.destroy()

        if probe_result.was_cancelled:
            carb.log_warn(f"Project Wizard open request was cancelled: {model.project_file}")
            self._finish_project_open(restore_wizard=True)
            return

        carb.log_info(f"Project Wizard finished checking RTX IO packages: {model.project_file}")

        rtxio_package_files = probe_result.package_files
        if rtxio_package_files:
            probe_directory = model.project_file.parent if model.existing_project else model.mod_file.parent
            broken_references = probe_result.broken_references
            location_hint = (
                "The selected project's directory will be modified."
                if model.existing_project
                else "Extraction will happen only in the copied project directory, not the source mod."
            )

            await omni.kit.app.get_app().next_update_async()
            if self._progress_popup is not None:
                self._progress_popup.hide()
            if broken_references:
                title = "RTX IO Extraction Required"
                message = (
                    f"Found {len(rtxio_package_files)} RTX IO package file(s) in:\n{probe_directory}\n\n"
                    f"The stage also contains {len(broken_references)} broken asset reference(s), so extraction "
                    "is required before continuing.\n\n"
                    "Extract & Skip: unpack the RTX IO packages and leave any existing destination files unchanged.\n"
                    "Extract & Overwrite: unpack the RTX IO packages and replace matching files in the destination "
                    "project directory.\n"
                    "Cancel: stop here without opening the project.\n\n"
                    f"{location_hint}"
                )
                continue_label = None
            else:
                title = "RTX IO Packages Detected"
                message = (
                    f"Found {len(rtxio_package_files)} RTX IO package file(s) in:\n{probe_directory}\n\n"
                    "Choose how the project should handle them before continuing.\n\n"
                    "Extract & Skip: unpack the RTX IO packages and leave any existing destination files unchanged.\n"
                    "Extract & Overwrite: unpack the RTX IO packages and replace matching files in the destination "
                    "project directory.\n"
                    "Continue: open the project without extracting the RTX IO packages.\n"
                    "Cancel: stop here without opening the project.\n\n"
                    f"{location_hint}"
                )
                continue_label = "Continue"

            result = await _TrexMessageDialog.prompt_async(
                title=title,
                message=message,
                ok_label="Extract & Skip",
                middle_label="Extract & Overwrite",
                middle_2_label=continue_label,
            )
            if result == _MessageDialogResult.OK:
                extract_rtxio_packages, extract_rtxio_overwrite_existing = True, False
            elif result == _MessageDialogResult.MIDDLE:
                extract_rtxio_packages, extract_rtxio_overwrite_existing = True, True
            elif result == _MessageDialogResult.MIDDLE_2:
                extract_rtxio_packages, extract_rtxio_overwrite_existing = False, False
            else:
                self._cancel_project_open(model.project_file)
                return

            _show_setup_feedback()
            await _setup_project(extract_rtxio_packages, extract_rtxio_overwrite_existing)
            return

        await _setup_project(False)

    async def _run_wizard_completion(self, payload: dict):
        """Create capture feedback after event dispatch, then process the request."""
        if self._show_opening_feedback:
            await omni.kit.app.get_app().next_update_async()
            if not self._project_open_in_progress:
                return
            self._progress_popup = _ProgressPopup(title="Opening Project", status_text="Checking RTX IO packages...")
            self._progress_popup.set_cancel_fn(self._wizard_core.cancel_rtxio)
            self._progress_popup.show()
        await self._on_wizard_completed(payload)

    def _accept_wizard_completion(self, payload: dict):
        """Accept one wizard completion and defer asynchronous processing."""
        if self._project_open_in_progress:
            carb.log_warn("Project Wizard ignored a duplicate open request while another request is running")
            return

        payload = deepcopy(payload)
        self._project_open_in_progress = True
        carb.log_info(f"Project Wizard accepted open request: {payload.get(_ProjectWizardKeys.PROJECT_FILE.value, '')}")
        self._schedule_project_open(self._run_wizard_completion(payload))

    def _schedule_project_open(self, coroutine):
        """Schedule project opening with shared failure recovery."""
        task = asyncio.ensure_future(coroutine)
        self._project_open_tasks.add(task)
        task.add_done_callback(self._on_project_open_task_done)

    def _on_project_open_task_done(self, task):
        """Restore the wizard when an asynchronous project-open step fails."""
        if self._project_open_tasks is not None:
            self._project_open_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is None or not self._project_open_in_progress:
            return
        carb.log_error(f"Project Wizard open request failed: {error}")
        self._show_setup_error(str(error))

    def _on_setup_progress(self, progress: float):
        """Update project preparation feedback from core progress."""
        if self._progress_popup is None:
            return
        self._progress_popup.set_progress(progress / 100)
        self._progress_popup.set_status_text(
            "Loading project data..." if progress >= _PROJECT_LOADING_PROGRESS_START else _PREPARING_PROJECT_STATUS
        )

    def _cancel_project_open(self, project_file):
        """Restore the wizard after a package-choice cancellation."""
        if not self._project_open_in_progress:
            return
        carb.log_warn(f"Project Wizard open request was cancelled: {project_file}")
        self._finish_project_open(restore_wizard=True)

    def _finish_project_open(self, restore_wizard: bool = False):
        """Release progress feedback and optionally restore the wizard."""
        self._run_progress_sub = None
        if self._progress_popup is not None:
            self._progress_popup.hide()
            self._progress_popup.destroy()
            self._progress_popup = None
        self._project_open_in_progress = False
        if restore_wizard:
            self.show_project_wizard()

    def _show_setup_error(self, error: str | None):
        """Restore the wizard and show the existing project setup error dialog."""
        self._finish_project_open(restore_wizard=True)
        _ErrorPopup(
            "Wizard Error Occurred",
            "An error occurred while setting up the project.",
            details=error,
            window_size=(400, 250),
        ).show()

    def _on_setup_completed(self, payload: dict, success: bool, error: str | None):
        """Finish project preparation and hand the accepted project to scene opening."""
        if not success:
            carb.log_error(
                f"Project Wizard failed to prepare '{payload.get(_ProjectWizardKeys.PROJECT_FILE.value, '')}': {error}"
            )
            self._show_setup_error(error)
            return

        project_file = payload.get(_ProjectWizardKeys.PROJECT_FILE.value, "")
        if self._progress_popup is not None:
            self._progress_popup.set_progress(1)
            self._progress_popup.set_status_text("Opening project...")
        carb.log_info(f"Project Wizard is handing off scene opening: {project_file}")
        if not self._is_stage_already_open(project_file):
            omni.kit.window.file.open_stage(str(project_file))

        self.__on_wizard_completed(payload)
        self._finish_project_open()

    @staticmethod
    def _is_stage_already_open(project_file) -> bool:
        """Return True when the default USD context already has this project loaded."""
        stage = usd.get_context().get_stage()
        if not stage:
            return False
        root_layer = stage.GetRootLayer()
        if not root_layer or root_layer.anonymous:
            return False
        return Path(root_layer.realPath).resolve() == Path(str(project_file)).resolve()

    def create_wizard_window(self):
        """Create the modal wizard and subscribe its completion lifecycle."""
        self._wizard_window = _WizardWindow(
            _WizardModel(self._start_page),
            title="RTX Remix Project Wizard",
            width=self._width,
            height=self._height,
            flags=ui.WINDOW_FLAGS_MODAL
            | ui.WINDOW_FLAGS_NO_DOCKING
            | ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE
            | ui.WINDOW_FLAGS_NO_MOVE
            | ui.WINDOW_FLAGS_NO_RESIZE,
        )
        self._wizard_completed_sub = self._wizard_window.widget.subscribe_wizard_completed(
            self._accept_wizard_completion
        )

    def show_project_wizard(self, reset_page: bool = False):
        if not self._wizard_window:
            self.create_wizard_window()
        self._wizard_window.show_wizard(reset_page=reset_page)

    def hide_project_wizard(self):
        if not self._wizard_window:
            return
        self._wizard_window.hide_wizard()

    def subscribe_wizard_completed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the wizard is completed.
        """
        return _EventSubscription(self.__on_wizard_completed, function)

    def set_payload(self, payload: dict):
        self._payload = payload

    def destroy(self):
        """Cancel project opening and release all wizard-owned resources."""
        project_open_tasks = self._project_open_tasks
        for task in project_open_tasks or ():
            task.cancel()
        if project_open_tasks is not None:
            project_open_tasks.clear()
        self._project_open_tasks = None
        self._finish_project_open()
        wizard_core = self._wizard_core
        if wizard_core is not None:
            wizard_core.destroy()
        _reset_default_attrs(self)


class CreateProjectWizardWindow(ProjectWizardBase):
    def __init__(self, context_name: str = "", width: int = 650, height: int = 400):
        super().__init__(context_name=context_name, width=width, height=height)

        self._start_page_instance = None

    @property
    def _default_attrs(self) -> dict[str, None]:
        default_attrs = super()._default_attrs
        default_attrs.update(
            {
                "_start_page_instance": None,
                "_file_picker_opened_sub": None,
                "_file_picker_closed_sub": None,
            }
        )
        return default_attrs

    @property
    def _start_page(self) -> _WizardPage:
        if self._start_page_instance is not None:
            return self._start_page_instance

        # TODO Feature OM-45888 - File Picker will appear behind the wizard modal (so hide and re-show wizard window)
        self._start_page_instance = _WizardStartPage(context_name=self._context_name)
        self._file_picker_opened_sub = self._start_page_instance.subscribe_file_picker_opened(self.hide_project_wizard)
        self._file_picker_closed_sub = self._start_page_instance.subscribe_file_picker_closed(self.show_project_wizard)

        return self._start_page_instance


class OpenProjectWizardWindow(ProjectWizardBase):
    def __init__(self, context_name: str = "", width: int = 650, height: int = 400):
        super().__init__(context_name=context_name, width=width, height=height)

        self._start_page_instance = None
        self._show_capture_picker = False

    @property
    def _default_attrs(self) -> dict[str, None]:
        default_attrs = super()._default_attrs
        default_attrs.update(
            {
                "_start_page_instance": None,
                "_show_capture_picker": None,
                "_file_picker_opened_sub": None,
                "_file_picker_closed_sub": None,
            }
        )
        return default_attrs

    @property
    def show_capture_picker(self) -> bool:
        return self._show_capture_picker

    @show_capture_picker.setter
    def show_capture_picker(self, value: bool) -> None:
        self._show_capture_picker = value
        if isinstance(self._start_page_instance, _SetupPage):
            self._start_page_instance.show_capture_picker = value

    @property
    def _show_opening_feedback(self) -> bool:
        """Return whether Open with Capture needs continuous opening feedback."""
        return self._show_capture_picker

    @property
    def _start_page(self) -> _WizardPage:
        if self._start_page_instance is not None:
            return self._start_page_instance

        # TODO Feature OM-45888 - File Picker will appear behind the wizard modal (so hide and re-show wizard window)
        # If we have a payload, we are opening an existing project and want to start on the setup page
        if self._payload and self._payload.get(_ProjectWizardKeys.PROJECT_FILE.value, None):
            self._start_page_instance = _SetupPage(context_name=self._context_name, previous_page=None)
            self._start_page_instance.open_or_create = True
            self._start_page_instance.show_capture_picker = self._show_capture_picker
            self._start_page_instance.payload = self._payload
        else:
            self._start_page_instance = _WizardOpenProjectPage(context_name=self._context_name)
        self._file_picker_opened_sub = self._start_page_instance.subscribe_file_picker_opened(self.hide_project_wizard)
        self._file_picker_closed_sub = self._start_page_instance.subscribe_file_picker_closed(self.show_project_wizard)

        return self._start_page_instance


WIZARD_MAP = {
    WizardTypes.CREATE: CreateProjectWizardWindow,
    WizardTypes.OPEN: OpenProjectWizardWindow,
}

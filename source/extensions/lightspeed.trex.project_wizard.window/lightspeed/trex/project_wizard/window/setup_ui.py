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
from enum import Enum
from functools import partial
from typing import Dict, Optional

import carb.settings
import omni.kit.app
import omni.kit.window.file
from lightspeed.error_popup.window import ErrorPopup as _ErrorPopup
from lightspeed.trex.project_wizard.core import SETTING_JUNCTION_NAME as _SETTING_JUNCTION_NAME
from lightspeed.trex.project_wizard.core import ProjectWizardCore as _ProjectWizardCore
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.project_wizard.open_project_page.widget import WizardOpenProjectPage as _WizardOpenProjectPage
from lightspeed.trex.project_wizard.setup_page.widget import SetupPage as _SetupPage
from lightspeed.trex.project_wizard.start_page.widget import WizardStartPage as _WizardStartPage
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni import ui, usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.wizard.widget import WizardModel as _WizardModel
from omni.flux.wizard.widget import WizardPage as _WizardPage
from omni.flux.wizard.window import WizardWindow as _WizardWindow


class WizardTypes(Enum):
    CREATE = "Create"
    OPEN = "Open"


class ProjectWizardBase(abc.ABC):
    def __init__(self, context_name: str = "", width: int = 650, height: int = 400):
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._wizard_core = _ProjectWizardCore()
        self._wizard_window = None
        self._width = width
        self._height = height

        self._wizard_completed_sub = None

        self.__on_wizard_completed = _Event()

    @property
    @abc.abstractmethod
    def _default_attrs(self) -> dict[str, None]:
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

    @usd.handle_exception
    async def _on_wizard_completed(self, payload: Dict):
        @usd.handle_exception
        async def _setup_project():
            success, error = await self._wizard_core.setup_project_async(payload)
            self._on_setup_completed(payload, success, error)

        settings = carb.settings.get_settings()
        force_junction = settings.get(_SETTING_JUNCTION_NAME)  # junction doesn't need admin right

        if (
            any(
                [
                    self._wizard_core.need_project_directory_symlink(schema=payload),
                    self._wizard_core.need_deps_directory_symlink(schema=payload),
                ]
            )
            and not force_junction
        ):
            await omni.kit.app.get_app().next_update_async()

            _TrexMessageDialog(
                title="Elevated Privileges Required",
                message=(
                    'You will be prompted with a "User Account Control" window.\n\n'
                    "RTX Remix requires elevated privileges to symlink your project in your game install directory.\n\n"
                    "Without elevated privileges the project creation will fail."
                ),
                disable_cancel_button=True,
                ok_handler=partial(asyncio.ensure_future, _setup_project()),
            )
        else:
            await _setup_project()

    def _on_setup_completed(self, payload: Dict, success: bool, error: Optional[str]):
        if not success:
            _ErrorPopup(
                "Wizard Error Occurred",
                "An error occurred while setting up the project.",
                details=error,
                window_size=(400, 250),
            ).show()
            return

        omni.kit.window.file.open_stage(str(payload.get(_ProjectWizardKeys.PROJECT_FILE.value, "")))

        self.__on_wizard_completed()

    def create_wizard_window(self):
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
            lambda payload: asyncio.ensure_future(self._on_wizard_completed(payload))
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
        # If we have a payload, we are opening an existing project and want to start on the setup page
        if self._payload and self._payload.get(_ProjectWizardKeys.PROJECT_FILE.value, None):
            self._start_page_instance = _SetupPage(context_name=self._context_name, previous_page=None)
            self._start_page_instance.open_or_create = True
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

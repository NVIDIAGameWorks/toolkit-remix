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

from pathlib import Path
from typing import Callable

from lightspeed.common import constants as _constants
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.project_wizard.core import ProjectWizardSchema as _ProjectWizardSchema
from lightspeed.trex.project_wizard.setup_page.widget import SetupPage as _SetupPage
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker
from omni.flux.wizard.widget import WizardPage as _WizardPage


class WizardOpenProjectPage(_WizardPage):
    def __init__(self, context_name: str = ""):
        self._setup_page = _SetupPage(context_name=context_name, previous_page=self)

        super().__init__(previous_page=None, next_page=self._setup_page, hide_navigation=True)

        default_attr = self._default_attr
        default_attr.update(
            {
                "_validation_error": None,
                "_sub_file_picker_opened": None,
                "_sub_file_picker_closed": None,
            }
        )

        self._validation_error = "The selected path is invalid: An unknown error occurred."

        self._sub_file_picker_opened = self._setup_page.subscribe_file_picker_opened(self._on_file_picker_opened)
        self._sub_file_picker_closed = self._setup_page.subscribe_file_picker_closed(self._on_file_picker_closed)

        self.__on_file_picker_opened = _Event()
        self.__on_file_picker_closed = _Event()

    def create_ui(self):
        self._setup_page.open_or_create = True

        self._on_file_picker_opened()
        _open_file_picker(
            "Open an RTX Remix project",
            self._on_file_selected,
            lambda *_: None,
            apply_button_label="Open",
            file_extension_options=_constants.SAVE_USD_FILE_EXTENSIONS_OPTIONS,
            select_directory=False,
            validate_selection=self._validate_path,
            validation_failed_callback=self._show_validation_failed_dialog,
        )

    def _on_file_selected(self, project_path):
        self.payload = {_ProjectWizardKeys.PROJECT_FILE.value: Path(project_path)}
        # Only update the payload if we're completing the wizard process
        if self.next_page is None:
            self.payload = {_ProjectWizardKeys.EXISTING_PROJECT.value: True}
        self._on_file_picker_closed()

        self._setup_page.open_or_create = True
        self._setup_page.project_path = project_path
        self.request_next()

    def _validate_path(self, dirname, filename):
        is_valid = True
        project_path = Path(dirname) / filename

        try:
            _ProjectWizardSchema.is_project_file_valid(project_path, {_ProjectWizardKeys.EXISTING_PROJECT.value: True})
        except ValueError as e:
            self._validation_error = str(e)
            is_valid = False

        if is_valid:
            self._setup_page.next_page = None
            self.next_page = (
                None if _ProjectWizardSchema.are_project_symlinks_valid(Path(project_path)) else self._setup_page
            )

        return is_valid

    def _show_validation_failed_dialog(self, *_):
        _TrexMessageDialog(self._validation_error, disable_cancel_button=True)

    def _on_file_picker_opened(self):
        """
        Trigger the __on_file_picker_opened event
        """
        self.__on_file_picker_opened()

    def subscribe_file_picker_opened(self, function: Callable[[], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the file picker is opened.
        """
        return _EventSubscription(self.__on_file_picker_opened, function)

    def _on_file_picker_closed(self):
        """
        Trigger the __on_file_picker_closed event
        """
        self.__on_file_picker_closed()

    def subscribe_file_picker_closed(self, function: Callable[[], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the file picker is closed.
        """
        return _EventSubscription(self.__on_file_picker_closed, function)

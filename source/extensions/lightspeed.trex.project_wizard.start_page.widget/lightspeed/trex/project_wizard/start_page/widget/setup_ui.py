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
from functools import partial
from pathlib import Path

from lightspeed.common import constants as _constants
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.project_wizard.core import ProjectWizardSchema as _ProjectWizardSchema
from lightspeed.trex.project_wizard.existing_mods_page.widget import ExistingModsPage as _ExistingModsPage
from lightspeed.trex.project_wizard.setup_page.widget import SetupPage as _SetupPage
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni import ui
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker
from omni.flux.wizard.widget import WizardPage as _WizardPage

from .items import StartOption


class WizardStartPage(_WizardPage):
    DEFAULT_PRIMARY_DESCRIPTION = "Select one of the options below to get started."
    DEFAULT_SECONDARY_DESCRIPTION = "Hovering an option will give you a detailed description of the intended use-case."
    BUTTON_SIZE = 144

    def __init__(self, context_name: str = ""):
        self._setup_page = _SetupPage(context_name=context_name, previous_page=self)
        self._existing_mods_page = _ExistingModsPage(previous_page=self._setup_page)

        super().__init__(previous_page=None, next_page=self._setup_page, hide_navigation=True)

        default_attr = self._default_attr
        default_attr.update(
            {
                "_setup_page": None,
                "_existing_mods_page": None,
                "_primary_description": None,
                "_detailed_description": None,
                "_example_description": None,
                "_option_icons": None,
                "_option_labels": None,
            }
        )

        self._primary_description = None
        self._detailed_description = None
        self._example_description = None
        self._option_icons = {}
        self._option_labels = {}

        # Option: (StyleName, Callback)
        self._options = {
            StartOption.OPEN: ("ModOpen", self._open_project),
            StartOption.CREATE: ("ModCreate", self._create_mod),
            StartOption.EDIT: ("ModEdit", self._edit_mod),
            StartOption.REMASTER: ("ModRemaster", self._remaster_mod),
        }

    def _on_mouse_hover(self, option: StartOption, value: bool):
        # Update Icon Colors
        style_name, _ = self._options[option]
        if value:
            style_name = style_name + "Hovered"
        self._option_icons[option].name = style_name

        # Update Button Text Color
        self._option_labels[option].name = "WizardTitleActive" if value else "WizardTitle"

        # Update Description Texts
        self._primary_description.text = option.value[1] if value else self.DEFAULT_PRIMARY_DESCRIPTION
        self._detailed_description.text = option.value[2] if value else self.DEFAULT_SECONDARY_DESCRIPTION
        self._example_description.text = f"Example: {option.value[3]}" if value else ""

    def _open_project(self, _x, _y, button, _m):
        if button != 0:
            return
        self._setup_page.open_or_create = True

        validation_error = "The selected path is invalid: An unknown error occurred."

        def on_file_selected(project_path):
            self.payload = {_ProjectWizardKeys.PROJECT_FILE.value: Path(project_path)}
            # Only update the payload if we're completing the wizard process
            if self.next_page is None:
                self.payload = {_ProjectWizardKeys.EXISTING_PROJECT.value: True}
            self._setup_page.open_or_create = True
            self._setup_page.project_path = project_path
            self.request_next()

        def validate_path(dirname, filename):
            is_valid = True
            project_path = Path(dirname) / filename

            nonlocal validation_error

            try:
                _ProjectWizardSchema.is_project_file_valid(
                    project_path, {_ProjectWizardKeys.EXISTING_PROJECT.value: True}
                )
            except ValueError as e:
                validation_error = str(e)
                is_valid = False

            if is_valid:
                self._setup_page.next_page = None
                self.next_page = (
                    None if _ProjectWizardSchema.are_project_symlinks_valid(Path(project_path)) else self._setup_page
                )

            return is_valid

        def show_validation_failed_dialog(*_):
            _TrexMessageDialog(
                validation_error,
                disable_cancel_button=True,
            )

        # TODO Feature OM-45888 - File Picker will appear behind the modal
        _open_file_picker(
            "Open an RTX Remix project",
            on_file_selected,
            lambda *_: None,
            apply_button_label="Open",
            file_extension_options=_constants.SAVE_USD_FILE_EXTENSIONS_OPTIONS,
            select_directory=False,
            validate_selection=validate_path,
            validation_failed_callback=show_validation_failed_dialog,
        )

    def _create_mod(self, _x, _y, button, _m):
        if button != 0:
            return
        self._setup_page.open_or_create = False
        self._setup_page.next_page = None
        self.request_next()

    def _edit_mod(self, _x, _y, button, _m):
        if button != 0:
            return
        self._setup_page.open_or_create = False
        self._existing_mods_page.set_mod_file = True
        self._setup_page.next_page = self._existing_mods_page
        self.request_next()

    def _remaster_mod(self, _x, _y, button, _m):
        if button != 0:
            return
        self._setup_page.open_or_create = False
        self._existing_mods_page.set_mod_file = False
        self._setup_page.next_page = self._existing_mods_page
        self.request_next()

    def create_ui(self):
        with ui.VStack():
            ui.Spacer(width=0)

            with ui.HStack():
                ui.Spacer(width=ui.Pixel(24), height=0)
                with ui.VStack():
                    self._primary_description = ui.Label(
                        self.DEFAULT_PRIMARY_DESCRIPTION, name="WizardDescription", alignment=ui.Alignment.CENTER
                    )
                    ui.Spacer(height=ui.Pixel(8), width=0)
                    self._detailed_description = ui.Label(
                        self.DEFAULT_SECONDARY_DESCRIPTION, alignment=ui.Alignment.CENTER
                    )
                    ui.Spacer(height=ui.Pixel(4), width=0)
                    self._example_description = ui.Label("", alignment=ui.Alignment.CENTER)

            ui.Spacer(height=ui.Pixel(24), width=0)

            with ui.HStack():
                ui.Spacer(height=0)
                for option, value in self._options.items():
                    icon, callback = value
                    with ui.ZStack(width=0):
                        ui.Rectangle(name="WizardPageButton")
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(8), height=0)
                            with ui.VStack(
                                identifier="OptionButton",
                                mouse_released_fn=callback,
                                mouse_hovered_fn=partial(self._on_mouse_hover, option),
                            ):
                                ui.Spacer(height=ui.Pixel(8), width=0)
                                self._option_icons[option] = ui.Image(
                                    "", name=icon, width=self.BUTTON_SIZE, height=self.BUTTON_SIZE
                                )
                                self._option_labels[option] = ui.Label(
                                    option.value[0], name="WizardTitle", alignment=ui.Alignment.CENTER
                                )
                                ui.Spacer(height=ui.Pixel(24), width=0)
                            ui.Spacer(width=ui.Pixel(8), height=0)
                ui.Spacer(height=0)

            ui.Spacer(width=0)

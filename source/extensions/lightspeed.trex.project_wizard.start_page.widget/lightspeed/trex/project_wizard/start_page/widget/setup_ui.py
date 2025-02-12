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
from typing import Callable

from lightspeed.trex.project_wizard.existing_mods_page.widget import ExistingModsPage as _ExistingModsPage
from lightspeed.trex.project_wizard.setup_page.widget import SetupPage as _SetupPage
from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
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
                "_sub_file_picker_opened": None,
                "_sub_file_picker_closed": None,
            }
        )

        self._primary_description = None
        self._detailed_description = None
        self._example_description = None
        self._option_icons = {}
        self._option_labels = {}

        self._sub_file_picker_opened = self._setup_page.subscribe_file_picker_opened(self._on_file_picker_opened)
        self._sub_file_picker_closed = self._setup_page.subscribe_file_picker_closed(self._on_file_picker_closed)

        self.__on_file_picker_opened = _Event()
        self.__on_file_picker_closed = _Event()

        # Option: (StyleName, Callback)
        self._options = {
            StartOption.CREATE: ("ModCreate", self._create_mod),
            StartOption.EDIT: ("ModEdit", self._edit_mod),
            # StartOption.REMASTER: ("ModRemaster", self._remaster_mod),  # Disabled until the runtime implements
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

            with ui.VStack():
                self._primary_description = ui.Label(
                    self.DEFAULT_PRIMARY_DESCRIPTION, name="WizardDescription", alignment=ui.Alignment.CENTER
                )
                ui.Spacer(height=ui.Pixel(8), width=0)
                self._detailed_description = ui.Label(self.DEFAULT_SECONDARY_DESCRIPTION, alignment=ui.Alignment.CENTER)
                ui.Spacer(height=ui.Pixel(2), width=0)
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

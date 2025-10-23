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

from typing import TYPE_CHECKING

from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.wizard.widget import WizardWidget

if TYPE_CHECKING:
    from omni.flux.wizard.widget import WizardModel


class WizardWindow:
    def __init__(
        self,
        model: "WizardModel",
        title: str = "",
        width: int = 600,
        height: int = 400,
        flags: int = ui.WINDOW_FLAGS_NONE,
    ):
        self._default_attr = {
            "_model": None,
            "_title": None,
            "_width": None,
            "_height": None,
            "_flags": None,
            "_window": None,
            "_wizard_completed_sub": None,
            "_wizard_cancelled_sub": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._model = model
        self._title = title
        self._width = width
        self._height = height
        self._flags = flags

        self._window = None
        self._widget = None

        self._wizard_completed_sub = None
        self._wizard_cancelled_sub = None

        self.__create_ui()

    @property
    def widget(self) -> WizardWidget:
        """
        Get the widget rendered in the window frame.
        """
        return self._widget

    def show_wizard(self, reset_page: bool = True):
        """
        Make the Wizard Window visible. This will automatically refresh the content of the wizard

        Args:
            reset_page: If the wizard should reset to the root page or not
        """
        if self._window:
            if reset_page:
                self._model.reset_active_item()
            self._widget.queue_refresh()
            self._window.visible = True

    def hide_wizard(self, *_):
        """
        Hide the Wizard Window.
        """
        if self._window:
            self._window.visible = False

    def __create_ui(self):
        self._window = ui.Window(
            self._title,
            visible=False,
            width=self._width,
            height=self._height,
            flags=self._flags
            or (
                ui.WINDOW_FLAGS_MODAL
                | ui.WINDOW_FLAGS_NO_DOCKING
                | ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_SCROLLBAR
                | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
            ),
        )
        with self._window.frame:
            self._widget = WizardWidget(self._model)

        self._wizard_completed_sub = self._widget.subscribe_wizard_completed(self.hide_wizard)
        self._wizard_cancelled_sub = self._widget.subscribe_wizard_cancelled(self.hide_wizard)

    def destroy(self):
        _reset_default_attrs(self)

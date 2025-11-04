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

from typing import Tuple

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class CustomErrorModel(ui.AbstractValueModel):
    def __init__(self, value: str = None):
        self._value = value
        super().__init__()

    def set_value(self, value):
        """Reimplemented set"""
        if value != self._value:
            # Tell the widget that the model is changed
            self._value = value
            self._value_changed()

    def get_value_as_string(self):
        return self._value


class ErrorPopup:
    """Creates a modal window with a status label and a progress bar inside.
    Args:
        title (str): Title of this window.
        message (str): Error message to display in a label.
        details (str): Error details to display in a string field.
        yes_no (bool): Show a Yes/No
    """

    BUTTON_WIDTH = 64

    def __init__(
        self, title, message, details: str = None, yes_no: bool = False, window_size: Tuple[int, int] = (400, 300)
    ):
        self.__default_attr = {
            "_title": None,
            "_message": None,
            "_details": None,
            "_popup": None,
            "_buttons": None,
            "_message_label": None,
            "_details_label": None,
            "_okay_button": None,
            "_yes_button": None,
            "_no_button": None,
        }
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self._title = title
        self._message = message
        self._details = details
        self._yes_no = yes_no
        self._window_size = window_size
        self._popup = None
        self._buttons = []

        self.__build_ui()

        self.__on_yes_clicked = _Event()
        self.__on_no_clicked = _Event()

    def _yes_clicked(self):
        """Call the event object that has the list of functions"""
        self.__on_yes_clicked()

    def subscribe_yes_clicked(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_yes_clicked, func)

    def _no_clicked(self):
        """Call the event object that has the list of functions"""
        self.__on_no_clicked()

    def subscribe_no_clicked(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_no_clicked, func)

    def __enter__(self):
        self._popup.visible = True
        return self

    def __exit__(self, type_, value, trace):
        self._popup.visible = False

    def show(self):
        self._popup.visible = True

    def hide(self):
        self._popup.visible = False

    def is_visible(self):
        return self._popup.visible

    def __build_ui(self):
        self._popup = ui.Window(
            self._title,
            visible=False,
            width=self._window_size[0],
            height=self._window_size[1],
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_CLOSE
                | ui.WINDOW_FLAGS_MODAL
            ),
        )

        with self._popup.frame:
            with ui.VStack():
                ui.Spacer(width=0, height=ui.Pixel(8))
                with ui.HStack(height=24):
                    ui.Spacer(width=ui.Pixel(8), height=0)
                    self._message_label = ui.Label(self._message, word_wrap=True, alignment=ui.Alignment.CENTER)
                    ui.Spacer(width=ui.Pixel(8), height=0)
                if self._details:
                    ui.Spacer(width=0, height=ui.Pixel(8))
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8), height=0)
                        with ui.ScrollingFrame(height=ui.Percent(100)):
                            self._details_label = ui.StringField(
                                CustomErrorModel(self._details), multiline=True, read_only=True
                            )
                        ui.Spacer(width=ui.Pixel(8), height=0)
                else:
                    ui.Spacer(width=0)
                ui.Spacer(width=0, height=ui.Pixel(8))
                with ui.HStack(height=24):
                    ui.Spacer(height=0)
                    if self._yes_no:

                        def yes_clicked():
                            self.hide()
                            self._yes_clicked()

                        def no_clicked():
                            self.hide()
                            self._no_clicked()

                        self._yes_button = ui.Button("Yes", width=ui.Pixel(self.BUTTON_WIDTH))
                        self._yes_button.set_clicked_fn(yes_clicked)
                        self._no_button = ui.Button("No", width=ui.Pixel(self.BUTTON_WIDTH))
                        self._no_button.set_clicked_fn(no_clicked)
                    else:
                        self._okay_button = ui.Button("Okay", width=ui.Pixel(self.BUTTON_WIDTH))
                        self._okay_button.set_clicked_fn(self.hide)
                        self._buttons.append(self._okay_button)
                    ui.Spacer(height=0)
                ui.Spacer(width=0, height=ui.Pixel(8))

    def destroy(self):
        for button in self._buttons:
            button.set_clicked_fn(None)

        _reset_default_attrs(self)

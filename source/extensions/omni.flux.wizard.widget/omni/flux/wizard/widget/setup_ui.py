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

import asyncio
from functools import partial
from typing import TYPE_CHECKING

from omni import kit, ui, usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if TYPE_CHECKING:
    from .model import WizardModel


class WizardWidget:
    NAVIGATION_BUTTON_WIDTH = 96
    WIZARD_PADDING = 8

    def __init__(
        self,
        model: "WizardModel",
    ):
        """
        A flexible wizard widget where users sequentially go through pages.

        Args:
            model: The WizardModel responsible for managing the pages and navigation
        """

        self._default_attr = {
            "_model": None,
            "_frame": None,
            "_refresh_task": None,
            "_on_blocked_changed_sub": None,
            "_on_active_item_changed_sub": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._model = model
        self._frame = ui.ZStack()

        self._refresh_task = None
        self._on_blocked_changed_sub = None
        self._on_active_item_changed_sub = self._model.subscribe_on_active_item_changed(self.queue_refresh)

        self.__on_wizard_cancelled = _Event()

        self.__create_ui()

    def queue_refresh(self):
        """
        Queue up an asynchronous refresh of the widget
        """
        if self._refresh_task:
            self._refresh_task.cancel()
        self._refresh_task = asyncio.ensure_future(self._refresh_deferred())

    def __create_ui(self):
        active_item = self._model.get_active_item()
        self._on_blocked_changed_sub = active_item.subscribe_on_blocked_changed(
            partial(self._refresh_navigation, active_item)
        )

        self._frame.clear()
        with self._frame:
            ui.Rectangle(name="WizardBackground")
            with ui.HStack():
                ui.Spacer(width=ui.Pixel(self.WIZARD_PADDING), height=0)
                with ui.VStack():
                    ui.Spacer(width=0, height=ui.Pixel(self.WIZARD_PADDING))
                    active_item.create_ui()
                    ui.Spacer(width=0)
                    self._navigation_holder = ui.HStack()
                    ui.Spacer(width=0, height=ui.Pixel(self.WIZARD_PADDING))
                ui.Spacer(width=ui.Pixel(self.WIZARD_PADDING), height=0)

            self._refresh_navigation(active_item)

    def _refresh_navigation(self, active_item):
        if not self._navigation_holder or not active_item:
            return

        self._navigation_holder.clear()
        self._navigation_holder.height = ui.Pixel(0) if active_item.hide_navigation else ui.Pixel(32)

        if active_item.hide_navigation:
            return

        with self._navigation_holder:
            ui.Button(
                "Cancel",
                identifier="CancelButton",
                width=ui.Pixel(self.NAVIGATION_BUTTON_WIDTH),
                clicked_fn=self._on_wizard_cancelled,
            )
            ui.Spacer(height=0)
            if active_item.previous_page:
                ui.Button(
                    active_item.previous_text,
                    identifier="PreviousButton",
                    width=ui.Pixel(self.NAVIGATION_BUTTON_WIDTH),
                    clicked_fn=self._model.go_previous,
                )
            ui.Spacer(width=ui.Pixel(8), height=0)
            ui.Button(
                active_item.next_text if active_item.next_page else active_item.done_text,
                identifier="NextButton",
                width=ui.Pixel(self.NAVIGATION_BUTTON_WIDTH),
                clicked_fn=self._model.go_next,
                enabled=not active_item.blocked,
            )
        ui.Spacer(width=0, height=ui.Pixel(self.WIZARD_PADDING))

    @usd.handle_exception
    async def _refresh_deferred(self):
        await kit.app.get_app().next_update_async()
        self.__create_ui()

    def subscribe_wizard_completed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the wizard is completed.
        """
        return self._model.subscribe_on_items_completed(function)

    def _on_wizard_cancelled(self):
        self.__on_wizard_cancelled()

    def subscribe_wizard_cancelled(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the wizard is completed.
        """
        return _EventSubscription(self.__on_wizard_cancelled, function)

    def destroy(self):
        if self._refresh_task:
            self._refresh_task.cancel()

        _reset_default_attrs(self)

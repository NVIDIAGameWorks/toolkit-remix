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
import functools
from typing import Any, Callable, List

import omni.ui as ui
import omni.usd
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget
from omni.flux.info_icon.widget import SelectableToolTipWidget as _SelectableToolTipWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.validator.factory import BaseValidatorRunMode as _BaseValidatorRunMode
from omni.ui import color as cl

from .model import HEADER_DICT  # noqa PLE0402
from .model import BaseItem as _BaseItem
from .model import CheckerItem as _CheckerItem
from .model import ContextItem as _ContextItem
from .model import ResultorItem as _ResultorItem
from .model import SelectorItem as _SelectorItem
from .model import UIItem as _UIItem


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the tree"""

    __DEFAULT_IMAGE_ICON_SIZE = 24

    def __init__(self):
        super().__init__()
        self._default_attrs = {
            "_sub_check_check": None,
            "_sub_check_fix": None,
            "_sub_select_select": None,
            "_sub_resultor_result": None,
            "_sub_context_check": None,
            "_sub_context_set": None,
            "_info_icon": None,
            "_tooltip_window": None,
            "_context_menu_widgets": None,
            "_progress_message_widget": None,
        }
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)
        self._context_menu_widgets = {}
        self._sub_check_check = {}
        self._sub_check_fix = {}
        self._sub_select_select = {}
        self._sub_context_check = {}
        self._sub_context_set = {}
        self._sub_resultor_result = {}
        self._info_icon = {}
        self._progress_message_widget = {}
        self._tooltip_window = None

        self.__on_run_menu_clicked = _Event()

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        if column_id == 0:
            with ui.HStack(width=16 * (level + 1), height=self.__DEFAULT_IMAGE_ICON_SIZE):
                if model.can_item_have_children(item):
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(16 * level))
                        # Draw the +/- icon
                        style_type_name_override = "TreeView.Item.Minus" if expanded else "TreeView.Item.Plus"
                        with ui.VStack(
                            width=ui.Pixel(16),
                        ):
                            ui.Spacer(width=0)
                            ui.Image(
                                "",
                                width=10,
                                height=10,
                                style_type_name_override=style_type_name_override,
                                identifier="expand_plugin",
                            )
                            ui.Spacer(width=0)
                else:
                    ui.Spacer()

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        asyncio.ensure_future(self.__deferred_build_widget(model, item, column_id, level, expanded, ui.Frame()))

    @omni.usd.handle_exception
    async def __deferred_build_widget(self, model, item, column_id, level, expanded, root_frame):
        """Create a widget per item"""
        with root_frame:
            if column_id == 0:
                if isinstance(item, _UIItem):
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(8))
                        await item.plugin.instance.build_ui(item.plugin.data)
                        ui.Spacer(height=ui.Pixel(8))
                elif isinstance(item, (_CheckerItem, _SelectorItem, _ResultorItem, _ContextItem)):

                    if isinstance(item, _CheckerItem):
                        message = item.plugin.data.last_check_message or "No message"
                        message += "\n"
                        message += (
                            item.plugin.data.last_fix_message
                            if item.plugin.data.last_fix_message is not None
                            else "No message"
                        )
                    elif isinstance(item, _SelectorItem):
                        message = item.plugin.data.last_select_message or "No message"
                    elif isinstance(item, _ContextItem):
                        message = item.plugin.data.last_check_message or "No message"
                        message += "\n"
                        message += (
                            item.plugin.data.last_set_message
                            if item.plugin.data.last_set_message is not None
                            else "No message"
                        )
                    elif isinstance(item, _ResultorItem):
                        message = item.plugin.data.last_resultor_message or "No message"

                    vstack = ui.VStack(mouse_released_fn=functools.partial(self._show_context_menu, item))
                    self._progress_message_widget[id(item)] = _SelectableToolTipWidget(
                        vstack, message, follow_mouse_pointer=True
                    )
                    with vstack:
                        ui.Spacer(width=0, height=ui.Pixel(1))
                        with ui.HStack():
                            with ui.ZStack():
                                setattr(
                                    cl,
                                    item.progress_color_attr,
                                    getattr(cl, item.progress_color_attr) or cl(0.0, 0, 0, 1.0),
                                )
                                ui.ProgressBar(
                                    item.progress_model,
                                    style={"border_radius": 5, "color": getattr(cl, item.progress_color_attr)},
                                )
                                with ui.HStack():
                                    ui.Spacer(width=ui.Pixel(8))
                                    ui.Label(
                                        item.title,
                                        width=ui.Percent(20),
                                        name="PropertiesWidgetLabel",
                                        identifier="plugin_title",
                                        tooltip=item.plugin.instance.name,
                                    )
                                    ui.Spacer()
                            ui.Spacer(width=ui.Pixel(4))
                            with ui.VStack(height=0, width=0):
                                ui.Spacer(height=2)
                                self._info_icon[id(item)] = _InfoIconWidget(item.plugin.instance.tooltip)
                        ui.Spacer(width=0, height=ui.Pixel(1))

                    if isinstance(item, _CheckerItem):
                        fn_message = functools.partial(
                            self.on_plugin_done,
                            self._progress_message_widget[id(item)].set_message,
                            item.plugin.data,
                            ["last_check_message", "last_fix_message"],
                        )
                        self._sub_check_check[id(item)] = item.plugin.instance.subscribe_check(fn_message)
                        self._sub_check_fix[id(item)] = item.plugin.instance.subscribe_fix(fn_message)
                    elif isinstance(item, _SelectorItem):
                        self._sub_select_select[id(item)] = item.plugin.instance.subscribe_select(
                            functools.partial(
                                self.on_plugin_done,
                                self._progress_message_widget[id(item)].set_message,
                                item.plugin.data,
                                ["last_select_message"],
                            )
                        )
                    elif isinstance(item, _ContextItem):
                        fn_message = functools.partial(
                            self.on_plugin_done,
                            self._progress_message_widget[id(item)].set_message,
                            item.plugin.data,
                            ["last_check_message", "last_set_message"],
                        )
                        self._sub_context_check[id(item)] = item.plugin.instance.subscribe_check(fn_message)
                        self._sub_context_set[id(item)] = item.plugin.instance.subscribe_set(fn_message)
                    elif isinstance(item, _ResultorItem):
                        self._sub_resultor_result[id(item)] = item.plugin.instance.subscribe_result(
                            functools.partial(
                                self.on_plugin_done,
                                self._progress_message_widget[id(item)].set_message,
                                item.plugin.data,
                                ["last_resultor_message"],
                            )
                        )
                else:
                    ui.Label(item.title, name="PropertiesWidgetLabel")

    def _show_context_menu(self, item, x, y, button, *_):
        if button != 1:
            return
        self._context_menu_widgets[id(item)] = ui.Menu(
            "Validator menu", direction=ui.Direction.LEFT_TO_RIGHT, identifier="right_click_menu"
        )
        with self._context_menu_widgets[id(item)]:
            ui.MenuItem(
                "Re-run all",
                triggered_fn=functools.partial(self._on_run_menu_clicked, item, _BaseValidatorRunMode.BASE_ALL),
                identifier="run_all_menu",
            )
            ui.MenuItem(
                "Re-run context + selected item(s)",
                triggered_fn=functools.partial(
                    self._on_run_menu_clicked, item, _BaseValidatorRunMode.BASE_ONLY_SELECTED
                ),
                identifier="run_selected_menu",
            )
            ui.MenuItem(
                "Re-run context + from selected item(s) to last item",
                triggered_fn=functools.partial(self._on_run_menu_clicked, item, _BaseValidatorRunMode.BASE_SELF_TO_END),
                identifier="run_selected_to_end_menu",
            )
        self._context_menu_widgets[id(item)].show_at(x, y)

    def _on_run_menu_clicked(self, item: _BaseItem, run_mode: _BaseValidatorRunMode):
        self.__on_run_menu_clicked(item, run_mode)

    def subscribe_on_run_selected_clicked(self, function: Callable[[_BaseItem, _BaseValidatorRunMode], Any]):
        """
        Subscribe to the *on_item_expanded* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_run_menu_clicked, function)

    def on_plugin_done(
        self, message_set_fn: Callable[[str], Any], data, attr_messages: List[str], _result: bool, _message: str, *_args
    ):
        """
        When a plugin finished his process, we can set the message into a string field

        Args:
            message_set_fn: the callback that will set the message
            data: data of the plugin
            attr_messages: attributes to get the message from
            _result: the bool result of the plugin
            _message: the message of the plugin that we want to show
            *_args: anything from the plugin
        """
        message = ""
        for attr_message in attr_messages:
            message += getattr(data, attr_message, "Failed to get the message") or "No message"
            message += "\n"
        message_set_fn(message)

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        _reset_default_attrs(self)

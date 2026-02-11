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

from __future__ import annotations

import asyncio
import threading
from functools import partial
from typing import Any

import carb.settings
import carb.tokens
import omni.ui as ui
import omni.usd
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget
from omni.flux.info_icon.widget import SelectableToolTipWidget as _SelectableToolTipWidget
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.background_pattern import create_widget_with_pattern as _create_widget_with_pattern
from omni.flux.utils.widget.color import hex_to_color as _hex_to_color
from omni.flux.validator.factory import BaseValidatorRunMode as _BaseValidatorRunMode
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.ui import color as cl

from .tree.delegate import Delegate as _Delegate
from .tree.model import BaseItem as _BaseItem
from .tree.model import CheckerItem as _CheckerItem
from .tree.model import CustomProgressValueModel as _CustomProgressValueModel
from .tree.model import Model as _Model
from .tree.model import ResultorItem as _ResultorItem

SCHEMA_PATH_SETTING = "/exts/omni.flux.validator.manager.widget/schema"


class ValidatorManagerWidget:
    DEFAULT_BLINKING_OVERLAY_COLOR = [0.8, 0.4, 0.0, 0.6]

    _main_loop = asyncio.get_event_loop()

    def __init__(
        self, core: _ManagerCore = None, use_global_style: bool = False, style: dict[str, dict[str, Any]] = None
    ):
        """
        Create a validator widget

        Args:
            core: the manager core to use that contains the schema
            use_global_style: use the global style or the local one
            style: UI style to use
        """

        self._default_attr = {
            "_manager_core": None,
            "_info_icon": None,
            "_tooltip_window": None,
            "_style": None,
            "_check_model": None,
            "_check_tree_view": None,
            "_check_delegate": None,
            "_resultor_tree_view": None,
            "_resultor_model": None,
            "_resultor_delegate": None,
            "_sub_context_progress": None,
            "_context_progress_message_widget": None,
            "_context_delegate": None,
            "_sub_context_fix": None,
            "_sub_run_progress": None,
            "_progress_widget": None,
            "_sub_run_finished": None,
            "_sub_run_stopped": None,
            "_sub_run_started": None,
            "_sub_run_paused": None,
            "_resume_button_frame": None,
            "_sub_on_check_run_selected_clicked": None,
            "_sub_on_resultor_run_selected_clicked": None,
            "_context_progress_color_attr": None,
            "_context_progress_model": None,
            "_sub_context_check": None,
            "_sub_context_set": None,
        }

        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        default_schema = carb.settings.get_settings().get(SCHEMA_PATH_SETTING)
        if not core and not default_schema:
            raise ValueError(f"Please set a default schema using the setting '{SCHEMA_PATH_SETTING}'")
        if default_schema:
            schema_path = carb.tokens.get_tokens_interface().resolve(default_schema)
            data = _path_utils.read_json_file(schema_path)
        self._manager_core = core if core else _ManagerCore(data)
        self.__stop_warning_loop = False
        if not use_global_style:
            from .style import style as _local_style  # noqa: PLC0415  # or doc will not build

            self._style = style or _local_style
        else:
            self._style = ui.Style.get_instance().default
        self.__loop = self._main_loop
        self._check_delegate = _Delegate()
        self._check_model = _Model()
        self._check_model.set_items([_CheckerItem(plugin) for plugin in self._manager_core.model.check_plugins])
        self._resultor_delegate = _Delegate()
        self._resultor_model = _Model()
        self._resultor_model.set_items(
            [_ResultorItem(plugin) for plugin in self._manager_core.model.resultor_plugins or []]
        )
        self._context_delegate = _Delegate()
        self.__root_frame = ui.Frame(style=self._style)
        self.__create_ui()

    def _on_run_progress(self, progress):
        self._progress_widget.model.set_value(progress / 100)

    def _on_run_finished(self, result, message: str | None = None):
        cl.validation_progress_color = cl.validation_result_ok if result else cl.validation_result_failed

    def _on_run_started(self):
        cl.validation_progress_color = cl.validation_result_ok

    def _on_run_paused(self, result):
        self._resume_button_frame.visible = result

    def _on_run_stopped(self):
        cl.validation_progress_color = cl.validation_result_failed

    def __create_ui(self):
        if threading.current_thread() is threading.main_thread():
            asyncio.ensure_future(self.__deferred_create_ui())
        else:
            asyncio.run_coroutine_threadsafe(self.__deferred_create_ui(), self.__loop)

    def refresh(self):
        self.__root_frame.clear()
        self.__create_ui()

    @omni.usd.handle_exception
    async def __deferred_create_ui(self):
        with self.__root_frame:
            with ui.VStack(spacing=ui.Pixel(8)):
                if not self._manager_core.model.context_plugin.data.hide_context_ui:
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.ZStack(height=0):
                        ui.Rectangle(name="BackgroundWithBorder")
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            with ui.HStack():
                                ui.Spacer(width=ui.Pixel(8))

                                with ui.VStack(spacing=ui.Pixel(8)):
                                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                                        ui.Label(
                                            "Context plugin", name="PropertiesPaneSectionTitle", width=ui.Percent(40)
                                        )
                                        with ui.HStack():
                                            ui.Spacer(width=ui.Pixel(4))
                                            display_name = self._manager_core.model.context_plugin.instance.display_name
                                            if display_name is None:
                                                display_name = self._manager_core.model.context_plugin.instance.name
                                            ui.Label(display_name)
                                            ui.Spacer()
                                            with ui.VStack(height=0, width=0):
                                                ui.Spacer(height=2)
                                                self._info_icon = _InfoIconWidget(
                                                    self._manager_core.model.context_plugin.instance.tooltip
                                                )

                                    with ui.Frame():
                                        with ui.VStack():
                                            await self._manager_core.model.context_plugin.instance.build_ui(
                                                self._manager_core.model.context_plugin.data
                                            )
                                            ui.Spacer(height=ui.Pixel(8))

                                            with ui.HStack():
                                                ui.Spacer(height=0, width=ui.Pixel(24))
                                                ui.Label(
                                                    "Progression",
                                                    width=ui.Pixel(105 - 8),
                                                    name="PropertiesWidgetLabel",
                                                    alignment=ui.Alignment.RIGHT,
                                                )
                                                ui.Spacer(height=0, width=ui.Pixel(8))
                                                self._context_progress_color_attr = f"progress_color_{id(self._manager_core.model.context_plugin.instance)}"
                                                setattr(
                                                    cl,
                                                    self._context_progress_color_attr,
                                                    getattr(cl, self._context_progress_color_attr)
                                                    or cl(0.0, 0, 0, 1.0),
                                                )
                                                (
                                                    value,
                                                    message,
                                                    result,
                                                ) = self._manager_core.model.context_plugin.instance.get_progress()
                                                self._context_progress_model = _CustomProgressValueModel(
                                                    value, message, result
                                                )
                                                progress_bar = ui.ProgressBar(
                                                    self._context_progress_model,
                                                    style={
                                                        "border_radius": 5,
                                                        "color": getattr(cl, self._context_progress_color_attr),
                                                    },
                                                )
                                                ui.Spacer(height=0, width=ui.Pixel(24))
                                                self._sub_context_progress = (
                                                    self._manager_core.model.context_plugin.instance.subscribe_progress(
                                                        self.__context_set_progress
                                                    )
                                                )
                                                message = (
                                                    self._manager_core.model.context_plugin.data.last_check_message
                                                    or "No message"
                                                )
                                                message += "\n"
                                                message += (
                                                    self._manager_core.model.context_plugin.data.last_set_message
                                                    if self._manager_core.model.context_plugin.data.last_set_message
                                                    is not None
                                                    else "No message"
                                                )
                                                self._context_progress_message_widget = _SelectableToolTipWidget(
                                                    progress_bar, message, follow_mouse_pointer=True
                                                )
                                                fn_message = partial(
                                                    self._context_delegate.on_plugin_done,
                                                    self._context_progress_message_widget.set_message,
                                                    self._manager_core.model.context_plugin.data,
                                                    ["last_check_message", "last_set_message"],
                                                )
                                                self._sub_context_check = (
                                                    self._manager_core.model.context_plugin.instance.subscribe_check(
                                                        fn_message
                                                    )
                                                )
                                                self._sub_context_set = (
                                                    self._manager_core.model.context_plugin.instance.subscribe_set(
                                                        fn_message
                                                    )
                                                )

                                ui.Spacer(width=ui.Pixel(8))
                            ui.Spacer(height=ui.Pixel(8))
                    ui.Spacer(height=ui.Pixel(8))

                with ui.ZStack():
                    ui.Rectangle(name="BackgroundWithBorder")
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(8))
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(8))

                            with ui.VStack(spacing=ui.Pixel(8)):
                                ui.Label(
                                    "Check plugin(s)", name="PropertiesPaneSectionTitle", width=ui.Percent(40), height=0
                                )

                                with ui.ScrollingFrame(
                                    name="PropertiesPaneSection",
                                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                ):
                                    self._check_tree_view = ui.TreeView(
                                        self._check_model,
                                        delegate=self._check_delegate,
                                        root_visible=False,
                                        header_visible=False,
                                        identifier="validator_check_plugins",
                                    )
                            ui.Spacer(width=ui.Pixel(8))
                        ui.Spacer(height=ui.Pixel(8))
                ui.Spacer(height=ui.Pixel(8))

                with ui.ZStack(height=ui.Percent(20)):
                    ui.Rectangle(name="BackgroundWithBorder")
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(8))
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(8))

                            with ui.VStack(spacing=ui.Pixel(8)):
                                ui.Label(
                                    "Resultor plugin(s)",
                                    name="PropertiesPaneSectionTitle",
                                    width=ui.Percent(40),
                                    height=0,
                                )

                                with ui.ScrollingFrame(
                                    name="PropertiesPaneSection",
                                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                ):
                                    self._resultor_tree_view = ui.TreeView(
                                        self._resultor_model,
                                        delegate=self._resultor_delegate,
                                        root_visible=False,
                                        header_visible=False,
                                        # column_widths=[ui.Percent(40), ui.Percent(60)]
                                    )
                            ui.Spacer(width=ui.Pixel(8))
                        ui.Spacer(height=ui.Pixel(8))
                ui.Spacer(height=ui.Pixel(8))

                self._resume_button_frame = ui.Frame(visible=False, height=0, identifier="resume_validation")
                with self._resume_button_frame:
                    with ui.ZStack():
                        _create_widget_with_pattern(
                            self.__create_resume_button,
                            "BackgroundButton",
                            height=ui.Pixel(30),
                            background_margin=(2, 2),
                        )
                        with ui.Frame(separate_window=True):
                            with ui.ZStack():
                                if not ui.ColorStore.find("blinking_overlay_rectangle"):
                                    cl.blinking_overlay_rectangle = cl(*self.DEFAULT_BLINKING_OVERLAY_COLOR)
                                ui.Rectangle(
                                    name="BlinkingOverlayRectangle",
                                    style={"background_color": cl.blinking_overlay_rectangle},
                                )
                                ui.Label("Resume", alignment=ui.Alignment.CENTER)

                with ui.HStack(height=0, spacing=ui.Pixel(4)):
                    _create_widget_with_pattern(
                        self.__create_run_button,
                        "BackgroundButton",
                        height=ui.Pixel(30),
                        background_margin=(2, 2),
                    )

                    _create_widget_with_pattern(
                        self.__create_stop_button,
                        "BackgroundButton",
                        height=ui.Pixel(30),
                        background_margin=(2, 2),
                    )

        if self._manager_core.is_run_started():
            self._on_run_started()
        self._on_run_progress(self._manager_core.get_progress())
        self._on_run_paused(self._manager_core.is_paused())
        if self._manager_core.is_stopped():
            self._on_run_stopped()
        run_finished = self._manager_core.is_run_finished()
        if run_finished is not None:
            self._on_run_finished(run_finished)

        self._sub_run_progress = self._manager_core.subscribe_run_progress(self._on_run_progress)
        self._sub_run_finished = self._manager_core.subscribe_run_finished(self._on_run_finished)
        self._sub_run_started = self._manager_core.subscribe_run_started(self._on_run_started)
        self._sub_run_paused = self._manager_core.subscribe_run_paused(self._on_run_paused)
        self._sub_run_stopped = self._manager_core.subscribe_run_stopped(self._on_run_stopped)

        self._sub_on_check_run_selected_clicked = self._check_delegate.subscribe_on_run_selected_clicked(
            partial(self.__on_run_selected_clicked, self._check_tree_view)
        )
        self._sub_on_resultor_run_selected_clicked = self._resultor_delegate.subscribe_on_run_selected_clicked(
            partial(self.__on_run_selected_clicked, self._resultor_tree_view)
        )

        asyncio.ensure_future(self.__deferred_loop_warning())

    def __context_set_progress(self, progress: float, message: str, result: bool):
        self._context_progress_model.set_value(progress, message, result)
        self.__context_progress_changed()

    def __context_progress_changed(self):
        progress_value = self._context_progress_model.get_value_as_float()
        red = (1 - progress_value) * 0.6
        green = progress_value * 0.6
        result = self._context_progress_model.get_value_as_bool()
        if not result:
            red = 0.6
            green = 0.0
        setattr(cl, self._context_progress_color_attr, cl(red, green, 0, 1.0))

    @omni.usd.handle_exception
    async def __deferred_loop_warning(self):
        current_value = ui.ColorStore.find("blinking_overlay_rectangle")
        if not current_value:
            return
        speed = 1
        alpha = _hex_to_color(current_value)[-1] / 255
        default_value = list(self.DEFAULT_BLINKING_OVERLAY_COLOR)
        while True:
            if self.__stop_warning_loop:
                break
            await asyncio.sleep(speed)
            alpha = 0 if alpha == self.DEFAULT_BLINKING_OVERLAY_COLOR[-1] else self.DEFAULT_BLINKING_OVERLAY_COLOR[-1]
            default_value[-1] = alpha
            cl.blinking_overlay_rectangle = cl(*default_value)

    def __create_resume_button(self):
        ui.Button(" ", clicked_fn=self._resume_check_and_fix, identifier="resume_validation")

    def __create_run_button(self):
        with ui.ZStack():
            cl.validation_progress_color = cl.validation_result_default
            self._progress_widget = ui.ProgressBar(
                style={"border_radius": 5, "color": cl.validation_progress_color, "background_color": 0x0},
                identifier="run_validation",
            )
            ui.Button("Run", clicked_fn=self._run_check_and_fix, identifier="run_validation")

    def __create_stop_button(self):
        ui.Button("Stop", clicked_fn=self._stop_check_and_fix, identifier="stop_validation")

    def _resume_check_and_fix(self):
        self._manager_core.resume()

    def _run_check_and_fix(self):
        self._manager_core.run()

    def _stop_check_and_fix(self):
        self._manager_core.stop()

    def __on_run_selected_clicked(self, tree_view: ui.TreeView, item: _BaseItem, run_mode: _BaseValidatorRunMode):
        self._manager_core.run(
            run_mode=run_mode, instance_plugins=[_item.plugin.instance for _item in tree_view.selection]
        )

    def destroy(self):
        self.__stop_warning_loop = True
        self.__root_frame.clear()
        self.__root_frame = None
        _reset_default_attrs(self)

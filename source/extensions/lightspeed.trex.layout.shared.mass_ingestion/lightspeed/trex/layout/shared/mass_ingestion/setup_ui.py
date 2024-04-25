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
import functools
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

import omni.ui as ui
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.layout.shared.base import SetupUI as _BaseLayout
from lightspeed.trex.stage_view.shared.widget import SetupUI as _StageViewWidget
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.tabbed.widget import SetupUI as _TabbedFrame
from omni.flux.validator.mass.queue.widget import Actions as _MassQueueTreeActions
from omni.flux.validator.mass.widget import ValidatorMassWidget as _ValidatorMassWidget

if TYPE_CHECKING:
    from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
    from omni.flux.validator.mass.core import Item as _MassCoreItem


class Pages(Enum):
    WORKSPACE_PAGE = "WorkspacePage"


class SetupUI(_BaseLayout):
    WIDTH_TAB_LABEL_PROPERTY = 40

    _VALIDATION_TAB_NAME = "Validation"
    _STAGE_VIEW_TAB_NAME = "Stage View"

    def __init__(self, ext_id, schema_paths: List[str], context: TrexContexts = ""):
        super().__init__(ext_id)

        self._schema_paths = schema_paths
        self._trex_context = context
        self._context_name = context.value
        self._context = trex_contexts_instance().get_usd_context(context)

        self._sub_mass_cores_started = []
        self._sub_mass_cores_finished = []

        self._mass_cores_are_running = {}

        self.__last_show_viewport_item = None

    @property
    def default_attr(self):
        default_attr = super().default_attr
        default_attr.update(
            {
                "_context_name": None,
                "_context": None,
                "_sub_mass_cores_started": None,
                "_sub_mass_cores_finished": None,
                "_mass_cores_are_running": None,
                "_frame_workspace": None,
                "_mass_ingest_widget": None,
                "_sub_mass_core_added": None,
                "_sub_mass_queue_action_pressed": None,
                "_properties_panel": None,
                "_frame_viewport": None,
                "_viewport": None,
                "_stage_view_widget": None,
            }
        )
        return default_attr

    @property
    @abc.abstractmethod
    def button_name(self) -> str:
        return ""

    @property
    def context(self) -> TrexContexts:
        return self._trex_context

    @property
    @abc.abstractmethod
    def button_priority(self) -> int:
        return 0

    def show(self, value: bool):
        if self._mass_ingest_widget:
            self._mass_ingest_widget.show(value)

    def _create_layout(self):
        self._frame_workspace = ui.Frame(name=Pages.WORKSPACE_PAGE.value, visible=True)
        with self._frame_workspace:
            with ui.HStack():
                self._mass_ingest_widget = _ValidatorMassWidget(
                    schema_paths=self._schema_paths,
                    use_global_style=True,
                )
                self._sub_mass_core_added = self._mass_ingest_widget.core.subscribe_core_added(
                    self._on_mass_ingest_core_added
                )
                self._sub_mass_queue_action_pressed = self._mass_ingest_widget.subscribe_mass_queue_action_pressed(
                    self._on_mass_queue_action_pressed
                )
                self._properties_panel = _TabbedFrame(
                    horizontal=False,
                    size_tab_label=(ui.Pixel(self.WIDTH_TAB_LABEL_PROPERTY), ui.Pixel(100)),
                    disable_tab_toggle=False,
                    hidden_by_default=True,
                )
                self._frame_viewport = ui.Frame(separate_window=False, visible=False, width=ui.Fraction(20))
                with self._frame_viewport:
                    self._viewport = _create_viewport_instance(self._context_name)

        self._properties_panel.add([self._VALIDATION_TAB_NAME, self._STAGE_VIEW_TAB_NAME])
        self._mass_ingest_widget.set_validator_widget_root_frame(
            self._properties_panel.get_frame(self._VALIDATION_TAB_NAME)
        )

        with self._properties_panel.get_frame(self._STAGE_VIEW_TAB_NAME):
            with ui.HStack():
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.ZStack():
                        ui.Rectangle(name="BackgroundWithBorder")
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            with ui.HStack():
                                ui.Spacer(width=ui.Pixel(8))
                                self._stage_view_widget = _StageViewWidget(usd_context_name=self._context_name)
                                ui.Spacer(width=ui.Pixel(8))
                            ui.Spacer(height=ui.Pixel(8))
                    ui.Spacer(height=ui.Pixel(8))
                ui.Spacer(width=ui.Pixel(8))

        self._properties_panel.selection = [self._VALIDATION_TAB_NAME]

        # by default, we don't want to show the validation/stage view panel
        self._properties_panel.force_toggle(self._properties_panel.selection[0], False)

    def _on_mass_queue_action_pressed(self, item: "_MassCoreItem", action_name: str, **kwargs):
        if action_name == "show_in_viewport":
            if self.__last_show_viewport_item == item or self.__last_show_viewport_item is None:
                value = not self._frame_viewport.visible
                self._frame_viewport.visible = value
                self._frame_viewport.width = ui.Fraction(1) if value else ui.Percent(0)
            self.__last_show_viewport_item = item
        elif action_name == _MassQueueTreeActions.SHOW_VALIDATION.value:
            self._properties_panel.selection = [self._VALIDATION_TAB_NAME]
            self._properties_panel.force_toggle(
                self._properties_panel.selection[0], kwargs.get("show_validation_checked", False)
            )

    def _on_mass_ingest_core_added(self, core: "_ManagerCore"):
        self._sub_mass_cores_started.append(
            core.subscribe_run_started(functools.partial(self._on_mass_cores_started, core))
        )
        self._sub_mass_cores_finished.append(
            core.subscribe_run_finished(functools.partial(self._on_mass_cores_finished, core))
        )

    def _on_mass_cores_started(self, core: "_ManagerCore"):
        if self._viewport:
            self._viewport.set_active(False)
        self._stage_view_widget.enable_context_event(False)
        self._mass_cores_are_running[id(core)] = True

    def _on_mass_cores_finished(self, core: "_ManagerCore", _finished: bool, message: Optional[str] = None):
        self._mass_cores_are_running[id(core)] = False
        update_viewport = not any(self._mass_cores_are_running.values())
        if update_viewport:
            if self._viewport:
                self._viewport.set_active(True)
            self._stage_view_widget.enable_context_event(True)

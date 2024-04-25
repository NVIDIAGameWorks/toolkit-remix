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
from typing import TYPE_CHECKING, List

import carb.settings
import omni.ui as ui
from lightspeed.trex.app.setup.extension import get_instance as _get_main_instance
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from omni.flux.header_navigator.widget import setup_ui as _header_navigator_ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if TYPE_CHECKING:
    from lightspeed.trex.contexts.setup import Contexts as _TrexContexts

_APP_NAME = "/app/name"
_DISABLED_LAYOUT_EXTENSION = "/app/trex/disabled_layouts"

_LAYOUT_INSTANCES: List["SetupUI"] = []


class SetupUI:

    SHARED_ZSTACK = None

    def __init__(self, ext_id):
        """Header navigator UI"""
        global _LAYOUT_INSTANCES  # noqa PLW0602

        self._button_name = None
        self._button_priority = None
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        settings = carb.settings.get_settings()
        top_header_instance_name = settings.get(_APP_NAME)
        if not top_header_instance_name:
            top_header_instance_name = "App name"
        headers_navigator = _header_navigator_ui.get_instances()
        if headers_navigator.get(top_header_instance_name):
            self._header_navigator = headers_navigator.get(top_header_instance_name)
        else:
            self._header_navigator = _header_navigator_ui.create_instance(top_header_instance_name)

        disabled_ext_ids = settings.get(_DISABLED_LAYOUT_EXTENSION)
        self.__enabled = True
        if disabled_ext_ids:
            self.__enabled = not bool(
                [disabled_ext_id for disabled_ext_id in disabled_ext_ids if ext_id.startswith(disabled_ext_id)]
            )

        self._header_navigator.register_button({self.button_name: (self._create_menu_text, self.button_priority)})
        _LAYOUT_INSTANCES.append(self)

    @property
    def default_attr(self):
        return {"_root_frame": None}

    def _create_menu_text(self) -> ui.Widget:
        image_widget = ui.Label(
            self.button_name,
            name="HeaderNavigatorMenuItem",
            alignment=ui.Alignment.LEFT,
            height=0,
            enabled=self.__enabled,
        )
        if self.__enabled:
            image_widget.set_mouse_pressed_fn(self._on_button_clicked)

        return image_widget

    @property
    @abc.abstractmethod
    def button_name(self) -> str:
        return ""

    @property
    @abc.abstractmethod
    def context(self) -> "_TrexContexts":
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def button_priority(self) -> int:
        return 0

    def _on_button_clicked(self, x, y, b, m):  # noqa PLC0103
        if b != 0:
            return
        self._show_layout(self)

    def _show_layout(self, cls: "SetupUI"):
        for frame in ui.Inspector.get_children(SetupUI.SHARED_ZSTACK):
            value = frame == cls._root_frame  # noqa PLW0212
            frame.visible = value
            frame.enabled = value
        if cls._root_frame is None:  # noqa PLW0212
            cls.create_layout()
        else:
            cls._header_navigator.select_button(cls.button_name)  # noqa PLW0212
            _trex_contexts_instance().set_current_context(cls.context)
        for layout in _LAYOUT_INSTANCES:
            layout.show(layout == cls)

    @abc.abstractmethod
    def show(self, value: bool):
        pass

    def show_layout_by_name(self, name: str):
        for layout in _LAYOUT_INSTANCES:
            if layout.button_name == name:
                self._show_layout(layout)
                return

    def create_layout(self):
        self.create_shared_layout()
        with SetupUI.SHARED_ZSTACK:  # noqa PLE1129
            self._root_frame = ui.Frame()
            with self._root_frame:
                self._create_layout()
        self._header_navigator.select_button(self.button_name)
        _trex_contexts_instance().set_current_context(self.context)

    @abc.abstractmethod
    def _create_layout(self):
        pass

    def create_shared_layout(self):
        if SetupUI.SHARED_ZSTACK is None:
            main_window = _get_main_instance()
            with main_window.frame:
                with ui.VStack():
                    self._header_navigator.create_ui()
                    self._header_navigator.refresh()
                    SetupUI.SHARED_ZSTACK = ui.ZStack()

    def destroy(self):
        global _LAYOUT_INSTANCES  # noqa PLW0602
        SetupUI.SHARED_ZSTACK = None
        self._header_navigator.unregister_button(self.button_name)
        _LAYOUT_INSTANCES.remove(self)
        _reset_default_attrs(self)

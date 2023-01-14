"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import abc

import carb.settings
import omni.ui as ui
from lightspeed.trex.app.setup.extension import get_instance as get_main_instance
from omni.flux.header_navigator.widget import setup_ui as header_navigator_ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

_APP_NAME = "/app/name"
_DISABLED_LAYOUT_EXTENSION = "/app/trex/disabled_layouts"


class SetupUI:

    SHARED_ZSTACK = None

    def __init__(self, ext_id):
        """Header navigator UI"""

        self._button_name = None
        self._button_priority = None
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        settings = carb.settings.get_settings()
        top_header_instance_name = settings.get(_APP_NAME)
        if not top_header_instance_name:
            top_header_instance_name = "App name"
        headers_navigator = header_navigator_ui.get_instances()
        if headers_navigator.get(top_header_instance_name):
            self._header_navigator = headers_navigator.get(top_header_instance_name)
        else:
            self._header_navigator = header_navigator_ui.create_instance(top_header_instance_name)

        disabled_ext_ids = settings.get(_DISABLED_LAYOUT_EXTENSION)
        self.__enabled = True
        if disabled_ext_ids:
            self.__enabled = not bool(
                [disabled_ext_id for disabled_ext_id in disabled_ext_ids if ext_id.startswith(disabled_ext_id)]
            )

        self._header_navigator.register_button({self.button_name: (self._create_menu_text, self.button_priority)})

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
    def button_priority(self) -> int:
        return 0

    def _on_button_clicked(self, x, y, b, m):  # noqa PLC0103
        if b != 0:
            return
        for frame in ui.Inspector.get_children(SetupUI.SHARED_ZSTACK):
            frame.visible = frame == self._root_frame
        if self._root_frame is None:
            self.create_layout()
        else:
            self._header_navigator.select_button(self.button_name)

    def create_layout(self):
        self.create_shared_layout()
        with SetupUI.SHARED_ZSTACK:  # noqa PLE1129
            self._root_frame = ui.Frame()
            with self._root_frame:
                self._create_layout()
        self._header_navigator.select_button(self.button_name)

    @abc.abstractmethod
    def _create_layout(self):
        pass

    def create_shared_layout(self):
        if SetupUI.SHARED_ZSTACK is None:
            main_window = get_main_instance()
            with main_window.frame:
                with ui.VStack():
                    self._header_navigator.create_ui()
                    self._header_navigator.refresh()
                    SetupUI.SHARED_ZSTACK = ui.ZStack()

    def destroy(self):
        SetupUI.SHARED_ZSTACK = None
        self._header_navigator.unregister_button(self.button_name)
        _reset_default_attrs(self)

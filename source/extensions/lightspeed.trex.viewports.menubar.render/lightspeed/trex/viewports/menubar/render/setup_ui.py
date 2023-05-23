"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import functools

from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.viewport.menubar.render import SingleRenderMenuItem as _SingleRenderMenuItem
from omni.kit.viewport.menubar.render import get_instance as _get_menubar_extension

from .item import lss_single_render_menu_item as _lss_single_render_menu_item


class SetupUI:
    def __init__(self):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__on_render_menu_option_clicked = _Event()
        self.__extension = None

        self.__create_ui()

    def _render_menu_option_clicked(self, engine_name: str, render_mode: str):
        """Call the event object that has the list of functions"""
        self.__on_render_menu_option_clicked(engine_name, render_mode)

    def subscribe_render_menu_option_clicked(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_render_menu_option_clicked, function)

    def __create_ui(self):
        # TODO: waiting for OM-72923
        return
        self.__extension = _get_menubar_extension()  # noqa PLW0101
        self.__extension.register_menu_item_type(
            functools.partial(_lss_single_render_menu_item, lss_option_clicked=self._render_menu_option_clicked)
        )

    def destroy(self):
        if self.__extension:
            self.__extension.register_menu_item_type(_SingleRenderMenuItem)
        if self._default_attr:
            _reset_default_attrs(self)

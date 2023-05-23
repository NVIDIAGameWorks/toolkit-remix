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
from omni.kit.viewport.menubar.camera import SingleCameraMenuItem as _SingleCameraMenuItem
from omni.kit.viewport.menubar.camera import get_instance as _get_menubar_extension

from .item import lss_single_camera_menu_item as _lss_single_camera_menu_item


class SetupUI:
    def __init__(self):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__on_camera_menu_option_clicked = _Event()
        self.__extension = None

        self.__create_ui()

    def _camera_menu_option_clicked(self, path):
        """Call the event object that has the list of functions"""
        self.__on_camera_menu_option_clicked(path)

    def subscribe_camera_menu_option_clicked(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_camera_menu_option_clicked, function)

    def __create_ui(self):
        self.__extension = _get_menubar_extension()
        self.__extension.register_menu_item_type(
            functools.partial(_lss_single_camera_menu_item, lss_option_clicked=self._camera_menu_option_clicked)
        )

    def destroy(self):
        if self.__extension:
            self.__extension.register_menu_item_type(_SingleCameraMenuItem)
        if self._default_attr:
            _reset_default_attrs(self)

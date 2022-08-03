"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .delegate import Delegate as _Delegate


class SetupUI:
    def __init__(self):
        super().__init__()
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._delegate = _Delegate()
        self.__on_save = _Event()
        self.__on_save_as = _Event()
        self.__create_ui()

    def _save(self):
        """Call the event object that has the list of functions"""
        self.__on_save()

    def subscribe_save(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_save, function)

    def _save_as(self):
        """Call the event object that has the list of functions"""
        self.__on_save_as()

    def subscribe_save_as(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_save_as, function)

    def __create_ui(self):
        self.menu = ui.Menu(
            "Burger Menu",
            menu_compatibility=False,
            delegate=self._delegate,
            style_type_name_override="MenuBurger",
        )

        with self.menu:
            ui.MenuItem(
                "Save", style_type_name_override="MenuBurgerItem", triggered_fn=self._save, hotkey_text="Ctrl+S"
            )
            ui.MenuItem(
                "Save as",
                style_type_name_override="MenuBurgerItem",
                triggered_fn=self._save_as,
                hotkey_text="Ctrl+Shift+S",
            )
            ui.MenuItem("About", style_type_name_override="MenuBurgerItem")  # todo

    def show_at(self, x, y):
        if self.menu.shown:
            return
        self.menu.show_at(x, y)

    def destroy(self):
        _reset_default_attrs(self)

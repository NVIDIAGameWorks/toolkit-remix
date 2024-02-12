"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

from typing import Callable

import omni.kit.actions
import omni.kit.app
from omni.kit.hotkeys.core import Hotkey, KeyCombination, get_hotkey_registry


class AppHotkey:
    """
    Wrapper around :py:class:`omni.kit.hotkeys.core.Hotkey` to help manage
    registration and de-registration of app hotkeys.
    """

    def __init__(
        self, action_id: str, key: KeyCombination, action: Callable[[], None], display_name: str, description: str
    ):
        self._hotkey_registry = get_hotkey_registry()
        self._action_registry = omni.kit.actions.core.get_action_registry()
        self._manager = omni.kit.app.get_app().get_extension_manager()
        self._extension_id = omni.ext.get_extension_name(self._manager.get_extension_id_by_module(__name__))

        self.action_id = action_id
        self.key = key
        self.action = action
        self.display_name = display_name
        if not description:
            description = display_name
        self.description = description
        self.tag = self.__class__.__name__

        self._registered_hotkey = None
        self._registered_action = None
        self._kit_hotkey_ext_hook = None

        self._kit_hotkey_ext_hook = self._manager.subscribe_to_extension_enable(
            lambda _: self._register_hotkey(),
            lambda _: self._deregister_hotkey(),
            ext_name="omni.kit.hotkeys.core",
            hook_name=f"{self.__class__.__name__} hotkey {self.action_id} listener",
        )

    def _register_hotkey(self):
        self._registered_action = self._action_registry.register_action(
            self._extension_id,
            self.action_id,
            self.action,
            display_name=self.display_name,
            description=self.description,
            tag=self.tag,
        )
        hotkey = Hotkey(
            hotkey_ext_id=self._extension_id,
            key=self.key,
            action_ext_id=self._extension_id,
            action_id=self.action_id,
        )
        self._registered_hotkey = self._hotkey_registry.register_hotkey(hotkey)

    def _deregister_hotkey(self):
        if self._registered_hotkey and self._hotkey_registry:
            self._hotkey_registry.deregister_hotkey(self._registered_hotkey)
            self._registered_hotkey = None
        if self._registered_action:
            self._action_registry.deregister_action(self._registered_action)
            self._registered_action = None

    def destroy(self):
        """Cleanup and de-register hooks"""
        self._deregister_hotkey()
        self._kit_hotkey_ext_hook = None

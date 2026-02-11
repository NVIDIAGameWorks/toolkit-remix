"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

Action and hotkey registration for the Remix Logic Graph editor.

This module extends OmniGraphActions/OmniGraphHotkeys to register all actions
and hotkeys defined in MENU_ENTRIES (context_menu.py).
"""

from __future__ import annotations

__all__ = ["RemixLogicGraphActions", "RemixLogicGraphHotkeys"]

from typing import TYPE_CHECKING
from collections.abc import Callable

import omni.kit.actions.core
import omni.kit.app
import omni.kit.hotkeys.core as hotkeys
from omni.graph.window.core import OmniGraphActions, OmniGraphHotkeys
from omni.graph.window.core.hotkeys import _HOTKEYS_EXT
from pxr import Sdf

from .context_menu import MENU_ENTRIES

if TYPE_CHECKING:
    from .graph_widget import RemixLogicGraphWidget


class RemixLogicGraphActions(OmniGraphActions):
    """
    Extended OmniGraph actions registered from MENU_ENTRIES.

    All action handlers delegate to the shared handlers in context_menu.py.
    """

    def __init__(self, extension_id: str, filter_fn: Callable[[Sdf.Path, Sdf.PrimSpec], bool] | None = None):
        super().__init__(extension_id, filter_fn)

        action_registry = omni.kit.actions.core.get_action_registry()

        for entry in MENU_ENTRIES:
            # Skip separators (no action_id) and entries without handlers
            if not entry.action_id or not entry.handler:
                continue

            action_registry.register_action(
                self._extension_id,
                entry.action_id,
                self._make_handler(entry.handler),
                display_name=entry.display_name,
                description=entry.description,
                tag="OmniGraph Actions",
            )

    def _make_handler(self, handler: Callable[[RemixLogicGraphWidget], None]) -> Callable[[], None]:
        """Wrap a handler to pass the current widget."""

        def wrapped():
            if widget := self._get_widget():
                handler(widget)

        return wrapped


class RemixLogicGraphHotkeys(OmniGraphHotkeys):
    """
    Extended hotkey bindings registered from MENU_ENTRIES.

    Hotkeys are derived directly from MenuEntry.hotkey - no duplicate definitions.
    """

    def _register(self):
        super()._register()

        ext_manager = omni.kit.app.get_app_interface().get_extension_manager()
        if not ext_manager.is_extension_enabled(_HOTKEYS_EXT):
            return

        hotkey_registry = hotkeys.get_hotkey_registry()
        hotkey_filter = hotkeys.HotkeyFilter(windows=[self._window_name])

        for entry in MENU_ENTRIES:
            # Skip separators (no action_id) and entries without hotkeys
            if not entry.action_id or not entry.hotkey:
                continue

            hotkey_registry.register_hotkey(
                hotkey_ext_id=self._extension_id,
                key=entry.hotkey,
                action_ext_id=self._extension_id,
                action_id=entry.action_id,
                filter=hotkey_filter,
            )

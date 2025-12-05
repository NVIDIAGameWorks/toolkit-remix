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
"""

from __future__ import annotations

__all__ = ["RemixLogicGraphActions", "RemixLogicGraphHotkeys"]

from typing import Callable, Optional

import carb.input
import omni.kit.actions.core
import omni.kit.app
import omni.kit.commands
from omni.graph.window.core import OmniGraphActions, OmniGraphHotkeys
from omni.graph.window.core.hotkeys import _HOTKEYS_EXT
from omni.graph.window.core.virtual_node_helper import VirtualNodeHelper
from omni.kit.hotkeys.core import KeyCombination
from pxr import Sdf


class RemixLogicGraphActions(OmniGraphActions):
    """
    Extended OmniGraph actions that include select all, select none, and delete selection.

    Inherits from OmniGraphActions and adds the missing actions that are shown in the
    context menu but not registered as hotkey-able actions.
    """

    # Additional action names
    SELECT_ALL = "og_select_all"
    SELECT_NONE = "og_select_none"
    DELETE_SELECTION = "og_delete_selection"

    def __init__(self, extension_id: str, filter_fn: Optional[Callable[[Sdf.Path, Sdf.PrimSpec], bool]] = None):
        super().__init__(extension_id, filter_fn)

        action_registry = omni.kit.actions.core.get_action_registry()
        actions_tag = "OmniGraph Actions"

        action_registry.register_action(
            self._extension_id,
            RemixLogicGraphActions.SELECT_ALL,
            self.select_all,
            display_name="Select All",
            description="Select all nodes in the graph.",
            tag=actions_tag,
        )

        action_registry.register_action(
            self._extension_id,
            RemixLogicGraphActions.SELECT_NONE,
            self.select_none,
            display_name="Select None",
            description="Clear the node selection.",
            tag=actions_tag,
        )

        action_registry.register_action(
            self._extension_id,
            RemixLogicGraphActions.DELETE_SELECTION,
            self.delete_selection,
            display_name="Delete Selection",
            description="Delete selected nodes.",
            tag=actions_tag,
        )

    def select_all(self):
        """Select all the nodes in the graph."""
        widget = self._get_widget()
        if widget:
            model = widget.model
            current_graph = widget.current_compound
            model.selection = model[current_graph].nodes

    def select_none(self):
        """Clear the node selection."""
        widget = self._get_widget()
        if widget:
            model = widget.model
            model.selection = []

    def delete_selection(self):
        """Delete the selected nodes, excluding virtual nodes."""
        widget = self._get_widget()
        if widget:
            view = widget._graph_view  # noqa: protected-access
            selected_view_items = view.selection or []
            # Filter out virtual nodes (input/output proxy nodes) - matches context menu logic
            selected_non_graph_items = [p for p in selected_view_items if not VirtualNodeHelper.is_virtual_node(p)]
            if selected_non_graph_items:
                paths = [n.GetPath() for n in selected_non_graph_items]
                omni.kit.commands.execute("DeletePrims", paths=paths)


class RemixLogicGraphHotkeys(OmniGraphHotkeys):
    """
    Extended hotkey bindings for Remix Logic Graph editor.

    Includes the default OmniGraph hotkeys plus select all, select none, and delete selection.
    """

    _ADDITIONAL_HOTKEYS = {
        RemixLogicGraphActions.SELECT_ALL: KeyCombination(
            carb.input.KeyboardInput.A, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL
        ),
        RemixLogicGraphActions.SELECT_NONE: KeyCombination(carb.input.KeyboardInput.ESCAPE),
        RemixLogicGraphActions.DELETE_SELECTION: KeyCombination(carb.input.KeyboardInput.DEL),
    }

    def _register(self):
        # Register base hotkeys first
        super()._register()

        # Register additional hotkeys
        ext_manager = omni.kit.app.get_app_interface().get_extension_manager()
        if not ext_manager.is_extension_enabled(_HOTKEYS_EXT):
            return
        import omni.kit.hotkeys.core as hotkeys

        hotkey_registry = hotkeys.get_hotkey_registry()
        ext_actions = omni.kit.actions.core.get_action_registry().get_all_actions_for_extension(self._extension_id)
        hotkey_filter = hotkeys.HotkeyFilter(windows=[self._window_name])

        for action in ext_actions:
            key = self._ADDITIONAL_HOTKEYS.get(action.id, None)
            if not key:
                continue

            hotkey_registry.register_hotkey(
                hotkey_ext_id=self._extension_id,
                key=key,
                action_ext_id=action.extension_id,
                action_id=action.id,
                filter=hotkey_filter,
            )

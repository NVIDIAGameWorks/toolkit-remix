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

Unified context menu, actions, and hotkeys for the Remix Logic Graph editor.

This module provides a single source of truth (MENU_ENTRIES) for all menu entries,
keyboard shortcuts, and action handlers. Registration of actions, hotkeys, and
context menu items all derive from this single definition.
"""

from __future__ import annotations

__all__ = ["MENU_GROUP", "MENU_ENTRIES", "MenuEntry", "show_context_menu", "register_context_menu"]

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import carb.input
import omni.graph.core as og
import omni.graph.window.core.graph_operations as graph_operations
import omni.kit.actions.core
import omni.kit.commands
import omni.kit.context_menu
import omni.kit.undo
import omni.kit.usd.layers
import omni.ui as ui
import omni.usd
from omni.graph.core import traverse_downstream_graph, traverse_upstream_graph
from omni.graph.window.core.virtual_node_helper import VirtualNodeHelper
from omni.kit.hotkeys.core import KeyCombination
from omni.kit.menu.core import IconMenuBaseDelegate
from omni.kit.widget.graph import IsolationGraphModel
from pxr import Sdf

from .backdrop_delegate import trigger_backdrop_rename

if TYPE_CHECKING:
    from .graph_widget import RemixLogicGraphWidget


MENU_GROUP = "REMIX_LOGIC_GRAPH"


# =============================================================================
# Menu Entry Definition
# =============================================================================


@dataclass
class MenuEntry:
    """
    Single source of truth for an action, hotkey, and context menu entry.

    Args:
        action_id: Unique identifier for the action (empty string for separators)
        display_name: Text shown in the menu
        handler: Function called when action is triggered, receives widget
        description: Action description for the registry
        hotkey: Optional keyboard shortcut
        enabled_fn: If provided, grays out menu item when it returns False
        show_fn: If provided, hides menu item when it returns False
    """

    action_id: str = ""
    display_name: str = ""
    handler: Callable[[RemixLogicGraphWidget], None] | None = None
    description: str = ""
    hotkey: KeyCombination | None = None
    enabled_fn: Callable[[RemixLogicGraphWidget], bool] | None = None
    show_fn: Callable[[RemixLogicGraphWidget], bool] | None = None


# =============================================================================
# Selection Helpers
# =============================================================================
# These functions extract different subsets of the current selection from the widget.
# They are used by both condition functions (to enable/disable menu items) and
# handler functions (to operate on the selection).


def _get_selection(widget: RemixLogicGraphWidget) -> list:
    """Get all currently selected items in the graph view."""
    return widget._graph_view.selection or []  # noqa: PLW0212


def _get_og_prims(widget: RemixLogicGraphWidget) -> list:
    """Get selected items that are valid OmniGraph prims (nodes that exist in the graph)."""
    model = widget.model
    result = []
    for item in _get_selection(widget):
        # IsolationGraphModel wraps input/output nodes - unwrap to get the source prim
        if isinstance(item, (IsolationGraphModel.InputNode, IsolationGraphModel.OutputNode)):
            result.append(item.source)
        elif model.get_node_from_prim(item):
            result.append(item)
    return result


def _get_non_graph_items(widget: RemixLogicGraphWidget) -> list:
    """Get selected items excluding virtual nodes (like compound I/O nodes)."""
    return [p for p in _get_selection(widget) if not VirtualNodeHelper.is_virtual_node(p)]


def _get_node_only_prims(widget: RemixLogicGraphWidget) -> list:
    """Get selected OmniGraph prims excluding virtual nodes."""
    return [p for p in _get_og_prims(widget) if not VirtualNodeHelper.is_virtual_node(p)]


# =============================================================================
# Condition Functions (for enabled_fn / show_fn)
# =============================================================================
# These functions determine whether menu items should be enabled or visible.
# They receive the widget and return a boolean.


def _has_selection(widget: RemixLogicGraphWidget) -> bool:
    """True if anything is selected."""
    return bool(_get_selection(widget))


def _has_non_graph_selection(widget: RemixLogicGraphWidget) -> bool:
    """True if selection contains deletable items (non-virtual nodes)."""
    return bool(_get_non_graph_items(widget))


def _has_node_only_selection(widget: RemixLogicGraphWidget) -> bool:
    """True if selection contains real OmniGraph nodes (for disconnect, copy)."""
    return bool(_get_node_only_prims(widget))


def _has_og_selection(widget: RemixLogicGraphWidget) -> bool:
    """True if selection contains valid OmniGraph prims."""
    return bool(_get_og_prims(widget))


def _is_single_backdrop(widget: RemixLogicGraphWidget) -> bool:
    """True if exactly one backdrop is selected (for rename action)."""
    sel = _get_selection(widget)
    if len(sel) != 1:
        return False
    p = sel[0]
    return p and hasattr(p, "IsValid") and p.IsValid() and p.GetTypeName() == "Backdrop"


def _can_paste(widget: RemixLogicGraphWidget) -> bool:
    """True if the paste action is available in the action registry."""
    return omni.kit.actions.core.get_action_registry().get_action("omni.kit.stage.copypaste", "stage_paste") is not None


# =============================================================================
# Handler Functions
# =============================================================================


def _on_select_all(widget: RemixLogicGraphWidget):
    model = widget.model
    graph = widget.current_compound
    if model and graph:
        model.selection = model[graph].nodes


def _on_select_none(widget: RemixLogicGraphWidget):
    if model := widget.model:
        model.selection = []


def _on_select_downstream(widget: RemixLogicGraphWidget):
    if (sel := _get_og_prims(widget)) and (model := widget.model):
        model.selection = [og.Controller.prim(p) for p in traverse_downstream_graph(sel)]


def _on_select_upstream(widget: RemixLogicGraphWidget):
    if (sel := _get_og_prims(widget)) and (model := widget.model):
        model.selection = [og.Controller.prim(p) for p in traverse_upstream_graph(sel)]


def _on_select_tree(widget: RemixLogicGraphWidget):
    if (sel := _get_og_prims(widget)) and (model := widget.model):
        up = traverse_upstream_graph(sel, attribute_predicate=model.is_execution)
        down = traverse_downstream_graph(sel, attribute_predicate=model.is_execution)
        model.selection = [og.Controller.prim(p) for p in up.union(down)]


def _on_delete(widget: RemixLogicGraphWidget):
    if paths := [n.GetPath() for n in _get_non_graph_items(widget)]:
        omni.kit.commands.execute("DeletePrims", paths=paths)


def _on_duplicate(widget: RemixLogicGraphWidget):
    if paths := [n.GetPath() for n in _get_non_graph_items(widget)]:
        ctx = omni.usd.get_context()
        with omni.kit.usd.layers.active_authoring_layer_context(ctx):
            omni.kit.commands.execute("CopyPrims", paths_from=paths)


def _on_disconnect(widget: RemixLogicGraphWidget):
    model = widget.model
    if not model:
        return
    with omni.kit.undo.group():
        for node in _get_selection(widget):
            if VirtualNodeHelper.is_virtual_node(node) or not model.get_node_from_prim(node):
                continue
            for port in model[node].ports:
                if conns := model._connections.get(port):  # noqa: PLW0212
                    model.remove_connections(port, conns)
                for conn in model.get_output_connections(port):
                    model.remove_connections(conn, [port])


def _on_frame(widget: RemixLogicGraphWidget):
    view = widget._graph_view  # noqa: PLW0212
    if view and (items := _get_selection(widget)):
        view.focus_on_nodes(items)


def _on_copy(widget: RemixLogicGraphWidget):
    if action := omni.kit.actions.core.get_action_registry().get_action("omni.kit.stage.copypaste", "stage_copy"):
        action.execute()


def _on_paste(widget: RemixLogicGraphWidget):
    view = widget._graph_view  # noqa: PLW0212
    graph = widget.current_compound
    filter_fn = widget._OmniGraphWidget__filter_fn  # noqa: PLW0212

    action = omni.kit.actions.core.get_action_registry().get_action("omni.kit.stage.copypaste", "stage_paste")
    if not action or not view or not graph:
        return

    canvas_pos = None
    if (
        hasattr(widget, "_get_graph_view_hovered_position")
        and hasattr(view, "screen_to_canvas")
        and (mouse_pos := widget._get_graph_view_hovered_position())  # noqa: PLW0212
    ):
        canvas_pos = view.screen_to_canvas(*mouse_pos)

    def filter_wrapper(prim_spec: Sdf.PrimSpec):
        return filter_fn(graph.GetPath(), prim_spec) if filter_fn else True

    if "keep_inputs" in dict(action.parameters):
        action.execute(root=graph.GetPath(), keep_inputs=False, position=canvas_pos, filter_fn=filter_wrapper)
    else:
        action.execute()


def _on_layout_all(widget: RemixLogicGraphWidget):
    view = widget._graph_view  # noqa: PLW0212
    if view:
        with omni.kit.undo.group():
            view.layout_all()


def _on_create_backdrop(widget: RemixLogicGraphWidget):
    view = widget._graph_view  # noqa: PLW0212
    graph = widget.current_compound
    items = _get_selection(widget)

    if not view or not graph or not items:
        return

    header_offset = 25
    x_min = y_min = float("inf")
    x_max = y_max = float("-inf")

    for node in items:
        pos = view._model[node].position  # noqa: PLW0212
        widget_node = view._node_widgets[node]  # noqa: PLW0212
        x_min = min(x_min, pos[0] - header_offset)
        x_max = max(x_max, pos[0] + widget_node.computed_width)
        y_min = min(y_min, pos[1] - header_offset)
        y_max = max(y_max, pos[1] + widget_node.computed_height)

    with omni.kit.undo.group():
        omni.kit.commands.execute(
            "CreateUsdUIBackdropCommand",
            parent_path=Sdf.Path(graph.GetPrimPath()),
            identifier="OGBackdrop",
            position=(x_min, y_min),
            size=(x_max - x_min, y_max - y_min),
            display_color=(0.3, 0.6, 0.2),
        )


def _on_rename_backdrop(widget: RemixLogicGraphWidget):
    if (sel := _get_selection(widget)) and hasattr(sel[0], "GetPath"):
        trigger_backdrop_rename(sel[0].GetPath())


def _on_help(widget: RemixLogicGraphWidget):
    for prim in _get_og_prims(widget):
        try:
            node = og.Controller.node(prim)
            if node and hasattr(node, "get_node_type"):
                graph_operations.show_help_for_node_type(node.get_node_type())  # type: ignore[union-attr]
        except og.OmniGraphError:
            continue


# =============================================================================
# Menu Entries - Single Source of Truth
# =============================================================================
# All context menu items, keyboard shortcuts, and actions are defined here.
# Each MenuEntry defines:
#   - action_id: Used to register the action and link hotkeys
#   - display_name: Shown in the context menu
#   - handler: Called when the action is triggered
#   - hotkey: Optional keyboard shortcut (displayed in menu, registered as hotkey)
#   - enabled_fn: Grays out the menu item when False
#   - show_fn: Hides the menu item when False
#
# Empty MenuEntry() creates a separator line in the context menu.
# Separators have no action_id, so they are skipped during action/hotkey registration.

MENU_ENTRIES: list[MenuEntry] = [
    MenuEntry(
        action_id="select_all",
        display_name="Select All",
        handler=_on_select_all,
        description="Select all nodes in the graph",
        hotkey=KeyCombination(carb.input.KeyboardInput.A, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL),
    ),
    MenuEntry(
        action_id="select_none",
        display_name="Select None",
        handler=_on_select_none,
        description="Clear the node selection",
        hotkey=KeyCombination(carb.input.KeyboardInput.ESCAPE),
    ),
    MenuEntry(
        action_id="select_downstream",
        display_name="Select Downstream Nodes",
        handler=_on_select_downstream,
        description="Select all nodes downstream from selection",
        enabled_fn=_has_og_selection,
    ),
    MenuEntry(
        action_id="select_upstream",
        display_name="Select Upstream Nodes",
        handler=_on_select_upstream,
        description="Select all nodes upstream from selection",
        enabled_fn=_has_og_selection,
    ),
    MenuEntry(),  # Separator
    MenuEntry(
        action_id="delete",
        display_name="Delete Selection",
        handler=_on_delete,
        description="Delete selected nodes",
        hotkey=KeyCombination(carb.input.KeyboardInput.DEL),
        enabled_fn=_has_non_graph_selection,
    ),
    MenuEntry(
        action_id="duplicate",
        display_name="Duplicate Selection",
        handler=_on_duplicate,
        description="Duplicate selected nodes",
        hotkey=KeyCombination(carb.input.KeyboardInput.D, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL),
        enabled_fn=_has_non_graph_selection,
    ),
    MenuEntry(
        action_id="disconnect",
        display_name="Disconnect",
        handler=_on_disconnect,
        description="Disconnect all connections from selected nodes",
        enabled_fn=_has_node_only_selection,
    ),
    MenuEntry(
        action_id="frame",
        display_name="Frame",
        handler=_on_frame,
        description="Frame selected nodes in view",
        hotkey=KeyCombination(carb.input.KeyboardInput.F),
        enabled_fn=_has_selection,
    ),
    MenuEntry(),  # Separator
    MenuEntry(
        action_id="copy",
        display_name="Copy",
        handler=_on_copy,
        description="Copy selected nodes",
        hotkey=KeyCombination(carb.input.KeyboardInput.C, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL),
        enabled_fn=_has_node_only_selection,
    ),
    MenuEntry(
        action_id="paste",
        display_name="Paste",
        handler=_on_paste,
        description="Paste nodes",
        hotkey=KeyCombination(carb.input.KeyboardInput.V, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL),
        enabled_fn=_can_paste,
    ),
    MenuEntry(),  # Separator
    MenuEntry(
        action_id="layout_all",
        display_name="Layout All",
        handler=_on_layout_all,
        description="Auto-layout all nodes",
    ),
    MenuEntry(),  # Separator
    MenuEntry(
        action_id="create_backdrop",
        display_name="Create Backdrop",
        handler=_on_create_backdrop,
        description="Create a backdrop around selected nodes",
        enabled_fn=_has_selection,
    ),
    MenuEntry(
        action_id="rename_backdrop",
        display_name="Rename Backdrop",
        handler=_on_rename_backdrop,
        description="Rename the selected backdrop",
        hotkey=KeyCombination(carb.input.KeyboardInput.F2),
        show_fn=_is_single_backdrop,
    ),
    MenuEntry(),  # Separator
    MenuEntry(
        action_id="help",
        display_name="Help",
        handler=_on_help,
        description="Show documentation for the selected node",
        hotkey=KeyCombination(carb.input.KeyboardInput.F1),
        enabled_fn=_has_og_selection,
    ),
]


# =============================================================================
# Utility Functions
# =============================================================================


def hotkey_to_display_text(hotkey: KeyCombination) -> str:
    """Convert KeyCombination to display text (e.g., 'CTRL + A')."""
    parts = []
    if hotkey.modifiers & carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL:
        parts.append("CTRL")
    if hotkey.modifiers & carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT:
        parts.append("SHIFT")
    if hotkey.modifiers & carb.input.KEYBOARD_MODIFIER_FLAG_ALT:
        parts.append("ALT")

    key_names = {
        carb.input.KeyboardInput.ESCAPE: "ESC",
        carb.input.KeyboardInput.DEL: "DEL",
    }
    key_display = key_names.get(hotkey.key) or (hotkey.key.name if hotkey.key else "?")
    parts.append(key_display)
    return " + ".join(parts)


# =============================================================================
# Context Menu Display
# =============================================================================


class _HotkeyMenuDelegate(IconMenuBaseDelegate):
    """
    Custom menu delegate that renders hotkey text on the right side of menu items.

    The default delegate (DefaultMenuDelegate) doesn't render the menu_hotkey_text
    that we pass via additional_kwargs, so we override _build_item_hotkey to display it.
    """

    def __init__(self):
        super().__init__()
        self.load_settings("omni.kit.widget.context_menu")

    def _build_item_hotkey(self, item):
        # Check both standard hotkey_text and our custom menu_hotkey_text attribute
        if hotkey := (item.hotkey_text or getattr(item, "menu_hotkey_text", None)):
            ui.Spacer()
            ui.Label(
                hotkey,
                height=self.ICON_SIZE,
                width=self.HOTKEY_SPACING[1],
                alignment=ui.Alignment.RIGHT,
                name="Disabled",
            )


_menu_delegate: _HotkeyMenuDelegate | None = None


def _get_menu_delegate() -> _HotkeyMenuDelegate:
    global _menu_delegate  # noqa: PLW0603
    if _menu_delegate is None:
        _menu_delegate = _HotkeyMenuDelegate()
    return _menu_delegate


def show_context_menu(widget: RemixLogicGraphWidget, context_item: Any, pos: tuple[float, float] | None = None):
    """
    Display the context menu at the current cursor position.

    This is monkey-patched onto RemixLogicGraphWidget.show_context_menu by the extension.
    The {"widget": widget} dict is passed to all menu item callbacks (onclick_fn, enabled_fn, show_fn).
    """
    if (menu := ui.Menu.get_current()) and menu.shown:
        return

    context_menu_instance = omni.kit.context_menu.get_instance()
    if not context_menu_instance:
        return

    menu_list = omni.kit.context_menu.get_menu_dict(MENU_GROUP, "")
    omni.kit.context_menu.reorder_menu_dict(menu_list)
    context_menu_instance.show_context_menu(MENU_GROUP, {"widget": widget}, menu_list, delegate=_get_menu_delegate())


# =============================================================================
# Registration Functions
# =============================================================================


def register_context_menu(ext_id: str) -> list:
    """
    Register all context menu items from MENU_ENTRIES.

    Args:
        ext_id: The extension ID used to look up registered actions.

    Returns:
        List of subscription handles. Keep these alive to maintain the menu registration.
        Clear the list to unregister all menu items.
    """
    subs = []
    prev_name = ""

    for entry in MENU_ENTRIES:
        # Empty action_id means this is a separator
        if not entry.action_id:
            subs.append(omni.kit.context_menu.add_menu({"name": "", "appear_after": prev_name}, MENU_GROUP))
        else:
            # Capture in local vars to avoid closure issues in lambdas
            enabled_fn = entry.enabled_fn
            show_fn = entry.show_fn

            # Use onclick_action to reference the registered action by (extension_id, action_id)
            item = {
                "name": entry.display_name,
                "onclick_action": (ext_id, entry.action_id),
                "appear_after": prev_name,
            }
            if enabled_fn:
                item["enabled_fn"] = lambda o, fn=enabled_fn: fn(o["widget"])
            if show_fn:
                item["show_fn"] = lambda o, fn=show_fn: fn(o["widget"])
            if entry.hotkey:
                item["additional_kwargs"] = {"menu_hotkey_text": hotkey_to_display_text(entry.hotkey)}

            subs.append(omni.kit.context_menu.add_menu(item, MENU_GROUP))
            prev_name = entry.display_name

    return subs

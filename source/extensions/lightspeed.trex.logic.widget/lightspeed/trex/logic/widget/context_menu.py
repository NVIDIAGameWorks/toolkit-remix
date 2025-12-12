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

__all__ = ["MENU_GROUP", "LogicGraphContextMenu", "show_context_menu"]

from typing import TYPE_CHECKING, Any, Callable

import omni.graph.core as og
import omni.graph.window.core.graph_operations as graph_operations
import omni.kit.actions.core
import omni.kit.commands
import omni.kit.context_menu
import omni.kit.undo
import omni.kit.usd.layers
import omni.ui as ui
import omni.usd
from omni.graph.window.core.virtual_node_helper import VirtualNodeHelper
from omni.kit.menu.core import IconMenuBaseDelegate
from omni.kit.widget.graph import IsolationGraphModel
from pxr import Sdf

from .backdrop_delegate import trigger_backdrop_rename


class _HotkeyMenuDelegate(IconMenuBaseDelegate):
    """Custom delegate that properly renders menu_hotkey_text (DefaultMenuDelegate doesn't)."""

    def __init__(self):
        super().__init__()
        self.load_settings("omni.kit.widget.context_menu")

    def _build_item_hotkey(self, item):
        hotkey = item.hotkey_text or getattr(item, "menu_hotkey_text", None)
        if hotkey:
            ui.Spacer()  # Flexible spacer pushes hotkey to the right
            ui.Label(
                hotkey,
                height=self.ICON_SIZE,
                width=self.HOTKEY_SPACING[1],
                alignment=ui.Alignment.RIGHT,
                name="Disabled",
            )


_hotkey_delegate = None


def _get_hotkey_delegate():
    global _hotkey_delegate
    if _hotkey_delegate is None:
        _hotkey_delegate = _HotkeyMenuDelegate()
    return _hotkey_delegate


BACKDROP_PRIM_TYPE = "Backdrop"

if TYPE_CHECKING:
    from .graph_widget import RemixLogicGraphWidget

MENU_GROUP = "REMIX_LOGIC_GRAPH"


# =============================================================================
# Context Menu Display
# =============================================================================


def show_context_menu(widget: RemixLogicGraphWidget, context_item: Any, pos: tuple[float, float] | None = None):
    """
    Display the context menu using omni.kit.context_menu.

    Args:
        widget: The graph widget instance
        context_item: The item that was right-clicked (prim or None)
        pos: Optional screen position for the menu
    """
    current_menu = ui.Menu.get_current()
    if current_menu and current_menu.shown:
        return

    filter_fn = widget._OmniGraphWidget__filter_fn  # noqa: SLF001, PLW0212
    objects = _build_objects(widget, context_item, filter_fn)

    menu_list = omni.kit.context_menu.get_menu_dict(MENU_GROUP, "")
    omni.kit.context_menu.reorder_menu_dict(menu_list)
    omni.kit.context_menu.get_instance().show_context_menu(
        MENU_GROUP, objects, menu_list, delegate=_get_hotkey_delegate()
    )


def _build_objects(widget: RemixLogicGraphWidget, prim: Any, filter_fn: Callable | None) -> dict:
    """Build the objects dictionary passed to menu callbacks."""
    model = widget.model
    view = widget._graph_view  # noqa: SLF001, PLW0212
    current_graph = widget.current_compound
    fallback = [prim] if prim else []

    selected_view_items = view.selection or fallback
    selected_og_prims = [p for p in (_to_og_prim(model, i) for i in selected_view_items) if p]
    selected_non_graph_items = [p for p in selected_view_items if not VirtualNodeHelper.is_virtual_node(p)]
    selected_node_only_prims = [p for p in selected_og_prims if not VirtualNodeHelper.is_virtual_node(p)]

    return {
        "widget": widget,
        "model": model,
        "prim": prim,
        "graph_view": view,
        "current_graph": current_graph,
        "filter_fn": filter_fn,
        "selected_view_items": selected_view_items,
        "selected_og_prims": selected_og_prims,
        "selected_non_graph_items": selected_non_graph_items,
        "selected_node_only_prims": selected_node_only_prims,
    }


def _to_og_prim(model, item):
    """Convert a view item to an OmniGraph prim."""
    if isinstance(item, (IsolationGraphModel.InputNode, IsolationGraphModel.OutputNode)):
        return item.source
    if model.get_node_from_prim(item):
        return item
    return None


# =============================================================================
# Menu Item Registration
# =============================================================================


class LogicGraphContextMenu:
    """Manages registration and lifecycle of context menu items."""

    def __init__(self):
        self._subscriptions: list = []

    def register(self):
        """Register all menu items in display order."""
        self._subscriptions = [
            self._add("Select All", on_select_all, hotkey="CTRL + A"),
            self._add("Select None", on_clear_selection, hotkey="ESC", after="Select All"),
            self._add(
                "Select Downstream Nodes", on_select_downstream, enabled_fn=has_og_selection, after="Select None"
            ),
            self._add(
                "Select Upstream Nodes",
                on_select_upstream,
                enabled_fn=has_og_selection,
                after="Select Downstream Nodes",
            ),
            self._add("Select Tree", on_select_tree, enabled_fn=has_og_selection, after="Select Upstream Nodes"),
            self._separator(after="Select Tree"),
            self._add("Delete Selection", on_delete, enabled_fn=has_non_graph_selection, hotkey="DEL", after=""),
            self._add(
                "Duplicate Selection",
                on_duplicate,
                enabled_fn=has_non_graph_selection,
                hotkey="CTRL + D",
                after="Delete Selection",
            ),
            self._add("Disconnect", on_disconnect, enabled_fn=has_node_only_selection, after="Duplicate Selection"),
            self._add("Frame", on_frame, enabled_fn=has_selection, hotkey="F", after="Disconnect"),
            self._separator(after="Frame"),
            self._add("Copy", on_copy, enabled_fn=has_node_only_selection, hotkey="CTRL + C", after=""),
            self._add("Paste", on_paste, enabled_fn=can_paste, hotkey="CTRL + V", after="Copy"),
            self._separator(after="Paste"),
            self._add("Layout All", on_layout_all, after=""),
            self._separator(after="Layout All"),
            self._add("Create Backdrop", on_create_backdrop, enabled_fn=has_selection, after=""),
            self._add(
                "Rename Backdrop",
                on_rename_backdrop,
                show_fn=is_single_backdrop_selected,
                hotkey="F2",
                after="Create Backdrop",
            ),
            self._separator(after="Rename Backdrop"),
            self._add("Help", on_help, enabled_fn=has_og_selection, hotkey="F1", after=""),
        ]

    def unregister(self):
        self._subscriptions.clear()

    def _add(
        self,
        name: str,
        onclick_fn: Callable,
        *,
        enabled_fn: Callable | None = None,
        show_fn: Callable | None = None,
        hotkey: str | None = None,
        after: str | None = None,
    ):
        item: dict = {"name": name, "onclick_fn": onclick_fn}
        if enabled_fn:
            item["enabled_fn"] = enabled_fn
        if show_fn:
            item["show_fn"] = show_fn
        if hotkey:
            item["additional_kwargs"] = {"menu_hotkey_text": hotkey}
        if after is not None:
            item["appear_after"] = after
        return omni.kit.context_menu.add_menu(item, MENU_GROUP)

    def _separator(self, *, after: str | None = None):
        item = {"name": ""}
        if after is not None:
            item["appear_after"] = after
        return omni.kit.context_menu.add_menu(item, MENU_GROUP)


# =============================================================================
# Condition Functions
# =============================================================================


def has_selection(objects: dict) -> bool:
    return bool(objects.get("selected_view_items"))


def has_non_graph_selection(objects: dict) -> bool:
    return bool(objects.get("selected_non_graph_items"))


def has_node_only_selection(objects: dict) -> bool:
    return bool(objects.get("selected_node_only_prims"))


def has_og_selection(objects: dict) -> bool:
    return bool(objects.get("selected_og_prims"))


def is_single_backdrop_selected(objects: dict) -> bool:
    selected = objects.get("selected_view_items", [])
    if len(selected) != 1:
        return False
    prim = selected[0]
    return prim and hasattr(prim, "IsValid") and prim.IsValid() and prim.GetTypeName() == BACKDROP_PRIM_TYPE


def can_paste(objects: dict) -> bool:
    action = omni.kit.actions.core.get_action_registry().get_action("omni.kit.stage.copypaste", "stage_paste")
    return action is not None


# =============================================================================
# Action Handlers
# =============================================================================


def on_select_all(objects: dict):
    model = objects.get("model")
    current_graph = objects.get("current_graph")
    if model and current_graph:
        model.selection = model[current_graph].nodes


def on_clear_selection(objects: dict):
    model = objects.get("model")
    if model:
        model.selection = []


def on_select_downstream(objects: dict):
    try:
        from omni.graph.core import traverse_downstream_graph

        selected = objects.get("selected_og_prims", [])
        model = objects.get("model")
        if selected and model:
            new_selection = traverse_downstream_graph(selected)
            model.selection = [og.Controller.prim(p) for p in new_selection]
    except ImportError:
        pass


def on_select_upstream(objects: dict):
    try:
        from omni.graph.core import traverse_upstream_graph

        selected = objects.get("selected_og_prims", [])
        model = objects.get("model")
        if selected and model:
            new_selection = traverse_upstream_graph(selected)
            model.selection = [og.Controller.prim(p) for p in new_selection]
    except ImportError:
        pass


def on_select_tree(objects: dict):
    try:
        from omni.graph.core import traverse_downstream_graph, traverse_upstream_graph

        selected = objects.get("selected_og_prims", [])
        model = objects.get("model")
        if selected and model:
            upstream = traverse_upstream_graph(selected, attribute_predicate=model.is_execution)
            downstream = traverse_downstream_graph(selected, attribute_predicate=model.is_execution)
            execution_chain = upstream.union(downstream)
            model.selection = [og.Controller.prim(p) for p in execution_chain]
    except ImportError:
        pass


def on_delete(objects: dict):
    paths = [n.GetPath() for n in objects.get("selected_non_graph_items", [])]
    if paths:
        omni.kit.commands.execute("DeletePrims", paths=paths)


def on_duplicate(objects: dict):
    paths = [n.GetPath() for n in objects.get("selected_non_graph_items", [])]
    if paths:
        usd_context = omni.usd.get_context()
        with omni.kit.usd.layers.active_authoring_layer_context(usd_context):
            omni.kit.commands.execute("CopyPrims", paths_from=paths)


def on_disconnect(objects: dict):
    model = objects.get("model")
    with omni.kit.undo.group():
        for node in objects.get("selected_view_items", []):
            if VirtualNodeHelper.is_virtual_node(node) or not model.get_node_from_prim(node):
                continue
            for port in model[node].ports:
                if connections := model._connections.get(port):  # noqa: SLF001, PLW0212
                    model.remove_connections(port, connections)
                if output_connections := model.get_output_connections(port):
                    for conn in output_connections:
                        model.remove_connections(conn, [port])


def on_frame(objects: dict):
    view = objects.get("graph_view")
    items = objects.get("selected_view_items", [])
    if view and items:
        view.focus_on_nodes(items)


def on_copy(objects: dict):
    action = omni.kit.actions.core.get_action_registry().get_action("omni.kit.stage.copypaste", "stage_copy")
    if action:
        action.execute()


def on_paste(objects: dict):
    widget = objects.get("widget")
    view = objects.get("graph_view")
    current_graph = objects.get("current_graph")
    filter_fn = objects.get("filter_fn")

    action = omni.kit.actions.core.get_action_registry().get_action("omni.kit.stage.copypaste", "stage_paste")
    if not action:
        return

    canvas_pos = None
    if (
        hasattr(widget, "_get_graph_view_hovered_position")
        and hasattr(view, "screen_to_canvas")
        and (mouse_pos := widget._get_graph_view_hovered_position())  # noqa: SLF001, PLW0212
    ):
        canvas_pos = view.screen_to_canvas(*mouse_pos)

    def filter_wrapper(prim_spec: Sdf.PrimSpec):
        return filter_fn(current_graph.GetPath(), prim_spec) if filter_fn else True

    if "keep_inputs" in dict(action.parameters):
        action.execute(root=current_graph.GetPath(), keep_inputs=False, position=canvas_pos, filter_fn=filter_wrapper)
    else:
        action.execute()


def on_layout_all(objects: dict):
    view = objects.get("graph_view")
    if view:
        with omni.kit.undo.group():
            view.layout_all()


def on_create_backdrop(objects: dict):
    view = objects.get("graph_view")
    current_graph = objects.get("current_graph")
    items = objects.get("selected_view_items", [])

    if not view or not items:
        return

    header_offset = 25
    x_min, x_max = float("inf"), float("-inf")
    y_min, y_max = float("inf"), float("-inf")

    for node in items:
        pos = view._model[node].position  # noqa: SLF001, PLW0212
        widget_node = view._node_widgets[node]  # noqa: SLF001, PLW0212
        x_min = min(x_min, pos[0] - header_offset)
        x_max = max(x_max, pos[0] + widget_node.computed_width)
        y_min = min(y_min, pos[1] - header_offset)
        y_max = max(y_max, pos[1] + widget_node.computed_height)

    with omni.kit.undo.group():
        omni.kit.commands.execute(
            "CreateUsdUIBackdropCommand",
            parent_path=Sdf.Path(current_graph.GetPrimPath()),
            identifier="OGBackdrop",
            position=(x_min, y_min),
            size=(x_max - x_min, y_max - y_min),
            display_color=(0.3, 0.6, 0.2),
        )


def on_rename_backdrop(objects: dict):
    selected = objects.get("selected_view_items", [])
    if selected and hasattr(selected[0], "GetPath"):
        trigger_backdrop_rename(selected[0].GetPath())


def on_help(objects: dict):
    for prim in objects.get("selected_og_prims", []):
        try:
            node = og.Controller.node(prim)
            if node:
                graph_operations.show_help_for_node_type(node.get_node_type())
        except og.OmniGraphError:
            continue

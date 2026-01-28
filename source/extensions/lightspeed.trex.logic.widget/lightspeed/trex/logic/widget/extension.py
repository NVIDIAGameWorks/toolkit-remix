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

__all__ = ["LOGIC_GRAPH_MENU_GROUP", "RemixLogicGraphExtension", "get_instance"]

import asyncio
import webbrowser
from contextlib import suppress
from functools import lru_cache, partial

import carb.windowing
import omni.appwindow
import omni.ext
import omni.graph.core as og
import omni.graph.window.core.graph_delegate as graph_delegate
import omni.graph.window.core.graph_operations as graph_operations
import omni.kit.app
import omni.kit.notification_manager as nm
import omni.ui as ui
from lightspeed.common.constants import DXVK_REMIX_DOCUMENTATION_URL, GlobalEventNames, WindowNames
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from omni.graph.window.core import (
    OmniGraphCatalogTreeDelegate,
    OmniGraphModel,
    graph_config,
    register_stage_graph_opener,
)
from pxr import Sdf, Tf, Usd

from .actions import RemixLogicGraphActions, RemixLogicGraphHotkeys
from .backdrop_delegate import clear_edit_triggers
from .catalog_model import OmniGraphNodeQuickSearchModel
from .context_menu import MENU_GROUP as LOGIC_GRAPH_MENU_GROUP
from .context_menu import register_context_menu, show_context_menu
from .graph_widget import RemixLogicGraphWidget
from .graph_window import RemixLogicGraphWindow
from .workspace import RemixLogicGraphWorkspaceWindow

_extension_instance: RemixLogicGraphExtension | None = None
_original_show_help_for_node_type = None
_original_are_compounds_enabled = None
_original_show_context_menu = None
_original_model_name_setter = None


@lru_cache
def _get_windowing() -> carb.windowing.IWindowing:
    return carb.windowing.acquire_windowing_interface()


def _patched_model_name_setter(self, value, item):
    """
    Patched name setter that handles backdrops using MovePrim instead of RenameNodeCommand.
    Backdrops are USD prims, not OmniGraph nodes, so the original setter fails for them.
    """
    if isinstance(item, Usd.Prim) and item.GetTypeName() == "Backdrop":
        old_path = item.GetPath()
        # Sanitize the new name to be a valid USD identifier
        new_name = Tf.MakeValidIdentifier(value)
        if not new_name or new_name == old_path.name:
            return
        new_path = old_path.GetParentPath().AppendChild(new_name)
        if old_path != new_path:
            import omni.kit.commands as kit_commands  # noqa: PLW0621

            kit_commands.execute("MovePrim", path_from=old_path, path_to=new_path)
            self._item_changed(None)  # noqa: SLF001, PLW0212
        return

    # Fall back to original setter for all other cases
    if _original_model_name_setter is not None:
        _original_model_name_setter.fset(self, value, item)


def get_instance() -> RemixLogicGraphExtension:
    if _extension_instance is None:
        raise ValueError("RemixLogicGraphExtension is not initialized")
    return _extension_instance


def _remix_show_help_for_node_type(node_type: str | og.NodeType):
    """Route help requests to Remix documentation for lightspeed nodes."""
    if isinstance(node_type, str):
        node_type_name = node_type
    elif isinstance(node_type, og.NodeType):
        node_type_name = node_type.get_node_type()
    else:
        return

    if node_type_name.startswith("lightspeed."):
        if node_type_name.startswith("lightspeed.trex.logic."):
            component_name = node_type_name.split(".")[-1]
            doc_url = f"{DXVK_REMIX_DOCUMENTATION_URL}/components/{component_name}.md"
        else:
            doc_url = f"{DXVK_REMIX_DOCUMENTATION_URL}/components"
        webbrowser.open(doc_url)
    elif _original_show_help_for_node_type:
        _original_show_help_for_node_type(node_type)


class RemixLogicGraphExtension(omni.ext.IExt):
    """Extension entry point for the Remix Logic Graph window."""

    def __init__(self):
        super().__init__()
        self._actions = None
        self._hotkeys = None
        self._workspace = None
        self._quicksearch_pos = None
        self._quicksearch_sub = None
        self._stage_opener_sub = None
        self._create_graph_sub = None
        self._edit_graph_sub = None
        self._context_menu_subs = []
        self._extensions_subscription = None

    def on_startup(self, ext_id: str):
        global _extension_instance
        _extension_instance = self

        self._quicksearch_pos = (None, None)
        self._actions = RemixLogicGraphActions(ext_id, filter_fn=self._make_paste_filter())
        self._hotkeys = RemixLogicGraphHotkeys(ext_id, WindowNames.REMIX_LOGIC_GRAPH)

        self._workspace = RemixLogicGraphWorkspaceWindow()
        self._workspace.create_window()
        self._actions.set_window(self._workspace.get_window())
        ui.Workspace.set_show_window_fn(self._workspace.title, self.show_window)

        app = omni.kit.app.get_app_interface()
        ext_manager = app.get_extension_manager()
        self._extensions_subscription = [
            ext_manager.subscribe_to_extension_enable(
                partial(self._on_extensions_changed, True),
                partial(self._on_extensions_changed, False),
                ext_name="omni.kit.window.quicksearch",
                hook_name="lightspeed.trex.logic.widget listener",
            )
        ]

        self._stage_opener_sub = self._register_for_stage_open()
        self._event_manager = _get_event_manager_instance()
        self._create_graph_sub = self._event_manager.subscribe_global_custom_event(
            GlobalEventNames.LOGIC_GRAPH_CREATE_REQUEST.value,
            self.on_create_graph_under_parent_action,
        )
        self._edit_graph_sub = self._event_manager.subscribe_global_custom_event(
            GlobalEventNames.LOGIC_GRAPH_EDIT_REQUEST.value,
            self.on_load_existing_graph_action,
        )

        self._apply_monkey_patches()
        self._context_menu_subs = register_context_menu(ext_id)

    def on_shutdown(self):
        global _extension_instance
        _extension_instance = None

        ui.Workspace.set_show_window_fn(self._workspace.title, lambda *_: None)
        self._extensions_subscription = None

        if self._hotkeys:
            self._hotkeys.destroy()
            self._hotkeys = None

        if self._actions:
            self._actions.destroy()
            self._actions = None

        if self._workspace:
            self._workspace.cleanup()
            self._workspace = None

        self._quicksearch_sub = None
        self._stage_opener_sub = None
        self._quicksearch_pos = None
        self._create_graph_sub = None
        self._edit_graph_sub = None

        self._context_menu_subs.clear()
        self._restore_monkey_patches()
        clear_edit_triggers()

    def _apply_monkey_patches(self):
        global _original_show_help_for_node_type, _original_are_compounds_enabled
        global _original_show_context_menu, _original_model_name_setter

        _original_show_help_for_node_type = graph_operations.show_help_for_node_type
        graph_operations.show_help_for_node_type = _remix_show_help_for_node_type
        graph_delegate.show_help_for_node_type = _remix_show_help_for_node_type

        _original_are_compounds_enabled = graph_config.Settings.are_compounds_enabled
        graph_config.Settings.are_compounds_enabled = staticmethod(lambda *args: False)

        _original_show_context_menu = RemixLogicGraphWidget.show_context_menu
        RemixLogicGraphWidget.show_context_menu = show_context_menu

        # Patch OmniGraphModel.name setter to handle backdrop renaming.
        # OmniGraph uses a non-standard property pattern where fset receives (self, value, item).
        _original_model_name_setter = OmniGraphModel.name
        OmniGraphModel.name = property(fget=_original_model_name_setter.fget, fset=_patched_model_name_setter)

    def _restore_monkey_patches(self):
        global _original_show_help_for_node_type, _original_are_compounds_enabled
        global _original_show_context_menu, _original_model_name_setter

        if _original_show_help_for_node_type is not None:
            graph_operations.show_help_for_node_type = _original_show_help_for_node_type
            graph_delegate.show_help_for_node_type = _original_show_help_for_node_type
            _original_show_help_for_node_type = None

        if _original_are_compounds_enabled is not None:
            graph_config.Settings.are_compounds_enabled = _original_are_compounds_enabled
            _original_are_compounds_enabled = None

        if _original_show_context_menu is not None:
            RemixLogicGraphWidget.show_context_menu = _original_show_context_menu
            _original_show_context_menu = None

        if _original_model_name_setter is not None:
            OmniGraphModel.name = _original_model_name_setter
            _original_model_name_setter = None

    def show_window(self, value: bool):
        if value:
            self._workspace.create_window()
            if self._actions:
                self._actions.set_window(self._workspace.get_window())
        elif self._actions:
            self._actions.set_window(None)
        self._workspace.show_window_fn(value)

    @staticmethod
    def show_graph(prim_list: list[Usd.Prim]):
        if not _extension_instance:
            return

        inst = _extension_instance

        async def import_prims():
            if not inst._workspace.get_window():  # noqa: SLF001, PLW0212
                inst.show_window(True)
            else:
                inst._workspace.get_window().focus()  # noqa: SLF001, PLW0212
            if prim_list:
                inst._workspace.get_window()._import_prims(None, prim_list)  # noqa: SLF001, PLW0212

        asyncio.ensure_future(import_prims())

    def _on_extensions_changed(self, loaded: bool, ext_id: str):
        if loaded:
            from omni.kit.window.quicksearch import QuickSearchRegistry

            style = {
                "Graph.Node.Category": {"background_color": 0xFFADFB47},
                "Graph.Node.Icon.Background": {"background_color": 0xFF31291E},
            }
            for name, info in graph_config.CategoryStyles.STYLE_BY_CATEGORY.items():
                style.update({f"Graph.Node.Category::{name}": {"background_color": info[0]}})

            with suppress(TypeError):
                self._quicksearch_sub = QuickSearchRegistry().register_quick_search_model(
                    "Omni Graph Component nodes",
                    OmniGraphNodeQuickSearchModel,
                    OmniGraphCatalogTreeDelegate,
                    accept_fn=self._is_window_focused,
                    exclusive_fn=lambda: True,
                    priority=0,
                    flat_search=False,
                    style=style,
                )
        else:
            self._quicksearch_sub = None

    def _make_paste_filter(self):
        return self._filter_paste_nodes

    def _filter_paste_nodes(self, graph_path: Sdf.Path, prim_spec: Sdf.PrimSpec) -> bool:
        if prim_spec.typeName != "OmniGraphNode":
            return False

        graph = og.get_graph_by_path(str(graph_path))
        if graph is None:
            nm.post_notification(
                f"Pasting error: Graph {str(graph_path)} does not exist",
                status=nm.NotificationStatus.WARNING,
                duration=5,
            )
            return False

        varnames = {var.name for var in graph.get_variables()}
        if "inputs:variableName" in prim_spec.properties:
            depvar = prim_spec.properties["inputs:variableName"].default
            if depvar is not None and depvar != "" and depvar not in varnames:
                nm.post_notification(
                    f'Variable "{depvar}" does not exist in the pasted graph. Graph will not work until this is fixed',
                    status=nm.NotificationStatus.WARNING,
                    duration=5,
                )

        catalog = self._workspace.get_window().get_graph_widget()._catalog_model  # noqa: SLF001, PLW0212
        node_type = prim_spec.properties["node:type"].default
        if catalog.allow_node_type(node_type):
            return True

        nm.post_notification(
            f"Cannot paste incompatible node {prim_spec.path} (type {node_type}) into Remix Logic Graph",
            status=nm.NotificationStatus.WARNING,
            duration=5,
        )
        return False

    def _is_window_focused(self) -> bool:
        if self._workspace.get_window() and self._workspace.get_window().focused:
            windowing = _get_windowing()
            app_window = omni.appwindow.get_default_app_window()
            self._quicksearch_pos = windowing.get_cursor_position(app_window.get_window())
            OmniGraphNodeQuickSearchModel._node_created = False  # noqa: SLF001, PLW0212
            return True
        self._quicksearch_pos = (None, None)
        return False

    @staticmethod
    def add_node(mime_data: str, is_drop: bool = True):
        if not _extension_instance:
            return

        inst = _extension_instance
        if not inst._workspace.get_window():  # noqa: SLF001, PLW0212
            return

        class CustomEvent:
            def __init__(self, data):
                self.mime_data = data
                self.x = None if is_drop else inst._quicksearch_pos[0]  # noqa: SLF001
                self.y = None if is_drop else inst._quicksearch_pos[1]  # noqa: SLF001

        graph_widget = inst._workspace.get_window().get_graph_widget()  # noqa: SLF001, PLW0212
        if graph_widget:
            graph_widget.on_drop(CustomEvent(mime_data))

    @staticmethod
    def _register_for_stage_open():
        def can_open(prims: list[Usd.Prim]):
            if prims:
                graph = og.get_graph_by_path(prims[0].GetPrimPath().pathString)
                return bool(graph)
            return False

        return register_stage_graph_opener(can_open, RemixLogicGraphExtension.show_graph, 1000)

    def _get_graph_widget(self) -> RemixLogicGraphWidget | None:
        window: RemixLogicGraphWindow = self._workspace.get_window()
        return window.get_graph_widget() if window else None

    async def _show_and_get_graph_widget(self):
        self.show_window(False)
        await omni.kit.app.get_app().next_update_async()
        self.show_window(True)
        await omni.kit.app.get_app().next_update_async()
        for _ in range(10):
            if graph_widget := self._get_graph_widget():
                return graph_widget
            await omni.kit.app.get_app().next_update_async()
        return self._get_graph_widget()

    async def _on_create_graph_under_parent_action(self, parent: Usd.Prim):
        graph_widget = await self._show_and_get_graph_widget()
        graph_widget.on_create_graph_under_parent_action(parent)

    def on_create_graph_under_parent_action(self, parent: Usd.Prim):
        asyncio.ensure_future(self._on_create_graph_under_parent_action(parent))

    async def _on_load_existing_graph_action(self, graph: Usd.Prim):
        graph_widget = await self._show_and_get_graph_widget()
        graph_widget.on_load_existing_graph_action(graph)

    def on_load_existing_graph_action(self, graph: Usd.Prim):
        asyncio.ensure_future(self._on_load_existing_graph_action(graph))

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

__all__ = ["RemixLogicGraphExtension"]

import asyncio
import webbrowser
from contextlib import suppress
from functools import lru_cache, partial
from typing import List

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
from omni.graph.window.core import OmniGraphCatalogTreeDelegate, graph_config, register_stage_graph_opener
from pxr import Sdf, Usd

from .actions import RemixLogicGraphActions, RemixLogicGraphHotkeys
from .catalog_model import OmniGraphNodeQuickSearchModel
from .graph_widget import RemixLogicGraphWidget
from .graph_window import RemixLogicGraphWindow
from .workspace import RemixLogicGraphWorkspaceWindow

_extension_instance = None
_original_show_help_for_node_type = None
_original_are_compounds_enabled = None


@lru_cache
def _get_windowing() -> carb.windowing.IWindowing:
    return carb.windowing.acquire_windowing_interface()


def get_instance() -> RemixLogicGraphExtension:
    if _extension_instance is None:
        raise ValueError("RemixLogicGraphExtension is not initialized")
    return _extension_instance


def _remix_show_help_for_node_type(node_type: str | og.NodeType):
    """Custom help function that handles Remix nodes with custom documentation."""

    if isinstance(node_type, str):
        node_type_name = node_type
    elif isinstance(node_type, og.NodeType):
        node_type_name = node_type.get_node_type()
    else:
        return

    # Check if it's a Remix/lightspeed node
    if node_type_name.startswith("lightspeed."):
        # Construct docs URL based on the node type for Remix nodes
        if node_type_name.startswith("lightspeed.trex.logic."):
            component_name = node_type_name.split(".")[-1]
            doc_url = f"{DXVK_REMIX_DOCUMENTATION_URL}/components/{component_name}.md"
        else:
            doc_url = f"{DXVK_REMIX_DOCUMENTATION_URL}/components"
        webbrowser.open(doc_url)
    else:
        # Fall back to original behavior for non-Remix nodes
        if _original_show_help_for_node_type:
            _original_show_help_for_node_type(node_type)


class RemixLogicGraphExtension(omni.ext.IExt):
    """The entry point for the extension"""

    def __init__(self):
        super().__init__()
        self._actions = None
        self._hotkeys = None
        self._workspace = None
        self.__extensions_subscription = None

        # Position of cursor when Quick Search window was launched
        self._quicksearch_pos = None
        # Quick Search subscription
        self._quicksearch_sub = None
        # Stage Opener subscription
        self._stage_opener_sub = None

        self._create_graph_sub = None
        self._edit_graph_sub = None

    def on_startup(self, ext_id: str):
        global _extension_instance
        _extension_instance = self
        self._quicksearch_sub = None
        self._quicksearch_pos = (None, None)
        self._stage_opener_sub = None

        # Use extended actions and hotkeys that include select all, select none, and delete selection.
        self._actions = RemixLogicGraphActions(ext_id, filter_fn=self._make_paste_filter())
        self._hotkeys = RemixLogicGraphHotkeys(ext_id, WindowNames.REMIX_LOGIC_GRAPH)

        self._workspace = RemixLogicGraphWorkspaceWindow()
        self._workspace.create_window()
        ui.Workspace.set_show_window_fn(self._workspace.title, self.show_window)

        app = omni.kit.app.get_app_interface()
        ext_manager = app.get_extension_manager()
        self.__extensions_subscription = []

        self.__extensions_subscription.append(
            ext_manager.subscribe_to_extension_enable(
                partial(self._on_extensions_changed, True),
                partial(self._on_extensions_changed, False),
                ext_name="omni.kit.window.quicksearch",
                hook_name="lightspeed.trex.logic.widget listener",
            )
        )

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

        # Monkey patch show_help_for_node_type to handle Remix nodes
        global _original_show_help_for_node_type
        _original_show_help_for_node_type = graph_operations.show_help_for_node_type
        graph_operations.show_help_for_node_type = _remix_show_help_for_node_type
        graph_delegate.show_help_for_node_type = _remix_show_help_for_node_type

        # Monkey patch Settings.are_compounds_enabled to disable compound graphs in Lightspeed
        global _original_are_compounds_enabled
        _original_are_compounds_enabled = graph_config.Settings.are_compounds_enabled
        graph_config.Settings.are_compounds_enabled = staticmethod(lambda *args: False)

    def on_shutdown(self):
        global _extension_instance
        _extension_instance = None

        ui.Workspace.set_show_window_fn(self._workspace.title, lambda *_: None)

        self.__extensions_subscription = None

        if self._hotkeys:
            self._hotkeys.destroy()
            self._hotkeys = None

        if self._actions:
            self._actions.destroy()
            self._actions = None

        if self._workspace:
            self._workspace.cleanup()
            self._workspace = None

        # deregister quick search model
        if self._quicksearch_sub is not None:
            self._quicksearch_sub = None
        self._stage_opener_sub = None
        self._quicksearch_pos = None
        self._create_graph_sub = None
        self._edit_graph_sub = None

        # Restore original show_help_for_node_type
        global _original_show_help_for_node_type
        if _original_show_help_for_node_type is not None:
            graph_operations.show_help_for_node_type = _original_show_help_for_node_type
            graph_delegate.show_help_for_node_type = _original_show_help_for_node_type
            _original_show_help_for_node_type = None

        # Restore original are_compounds_enabled
        global _original_are_compounds_enabled
        if _original_are_compounds_enabled is not None:
            graph_config.Settings.are_compounds_enabled = _original_are_compounds_enabled
            _original_are_compounds_enabled = None

    def show_window(self, value: bool):
        """Show/hide the window"""
        if value:
            self._workspace.create_window()
            if self._actions:
                self._actions.set_window(self._workspace.get_window())
        else:
            if self._actions:
                self._actions.set_window(None)

        self._workspace.show_window_fn(value)

    @staticmethod
    def show_graph(prim_list: List[Usd.Prim]):
        """Show graph in Omni Graph window"""
        if not _extension_instance:
            return

        self = _extension_instance

        async def import_prims():
            if not self._workspace.get_window():  # noqa: protected-access
                self.show_window(True)
            else:
                self._workspace.get_window().focus()  # noqa: protected-access

            if prim_list:
                self._workspace.get_window()._import_prims(None, prim_list)  # noqa: protected-access

        asyncio.ensure_future(import_prims())

    def _on_extensions_changed(self, loaded: bool, ext_id: str):
        """Called when the Quick Search extension is loaded/unloaded"""
        if loaded:
            from omni.kit.window.quicksearch import QuickSearchRegistry

            # create the tree item style for the quick search
            def specialized_color_style(name, color):
                nstyle = {f"Graph.Node.Category::{name}": {"background_color": color}}
                return nstyle

            style = {
                # default node color
                "Graph.Node.Category": {"background_color": 0xFFADFB47},
                # background color
                "Graph.Node.Icon.Background": {"background_color": 0xFF31291E},
            }
            # node color by category
            for name, info in graph_config.CategoryStyles.STYLE_BY_CATEGORY.items():
                style.update(specialized_color_style(name, info[0]))
            with suppress(TypeError):  # FIXME: can remove when quicksearch 2.1 is published
                # Register Omni Graph Component nodes in Quick Search
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
            # Deregister Omni Graph Component nodes in Quick Search
            self._quicksearch_sub = None

    def _make_paste_filter(self):
        return lambda graph_path, prim_spec: self._filter_paste_nodes(graph_path, prim_spec)  # noqa:PLW0108

    def _filter_paste_nodes(self, graph_path: Sdf.Path, prim_spec: Sdf.PrimSpec) -> bool:
        """Return True for nodes that are valid to paste into this graph, False if they aren't valid.

        Args:
            graph_path (Sdf.Path): Path to the target graph
            prim_spec (Sdf.PrimSpec): PrimSpec to check for validity.

        Returns:
            bool: True for Valid, False for Invalid.
        """
        if prim_spec.typeName != "OmniGraphNode":
            return False

        graph = omni.graph.core.get_graph_by_path(str(graph_path))
        if graph is None:
            nm.post_notification(
                f"Pasting error: Graph {str(graph_path)} does not exist",
                status=nm.NotificationStatus.WARNING,
                duration=5,
            )
            return False

        # TODO: When pasting a lot of nodes at once, the variables should be cached
        varnames = {var.name for var in graph.get_variables()}
        if "inputs:variableName" in prim_spec.properties:
            depvar = prim_spec.properties["inputs:variableName"].default
            if depvar is not None and depvar != "" and depvar not in varnames:
                nm.post_notification(
                    f'Variable "{depvar}" does not exist in the pasted graph. Graph will not work until this is fixed',
                    status=nm.NotificationStatus.WARNING,
                    duration=5,
                )

        catalog = self._workspace.get_window().get_graph_widget()._catalog_model  # noqa: protected-access
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
        """Returns True if the OmniGraph remix graph window exists and has focus"""
        if self._workspace.get_window() and self._workspace.get_window().focused:
            # Save the position of the pointer so that we can put the created node there.
            windowing = _get_windowing()
            app_window = omni.appwindow.get_default_app_window()
            self._quicksearch_pos = windowing.get_cursor_position(app_window.get_window())

            # Workaround for OM-99274. See note in action_catalog_model.py.
            OmniGraphNodeQuickSearchModel._node_created = False  # noqa: protected-access
            return True

        self._quicksearch_pos = (None, None)
        return False

    @staticmethod
    def add_node(mime_data: str, is_drop: bool = True):
        """Adds a node to the current Graph window"""
        if not _extension_instance:
            return

        self = _extension_instance
        if not self._workspace.get_window():  # noqa: protected-access
            return

        class CustomEvent:
            def __init__(self, mime_data):
                self.mime_data = mime_data
                # If this is a drop from an actual drag, use the current pointer position. Otherwise this has been
                # triggered by selecting a QuickSearch entry, in which case we want to use the position of the
                # pointer when the QuickSearch window was summoned.
                if is_drop:
                    self.x = None
                    self.y = None
                else:
                    self.x = _extension_instance._quicksearch_pos[0]
                    self.y = _extension_instance._quicksearch_pos[1]

        graph_widget: RemixLogicGraphWidget = self._workspace.get_window().get_graph_widget()  # noqa: protected-access
        if graph_widget:
            graph_widget.on_drop(CustomEvent(mime_data))

    @staticmethod
    def _register_for_stage_open():
        """Register ourselves as an opener for any graphs"""

        def can_open(prims: List[Usd.Prim]):
            if prims:
                first_prim = prims[0]
                graph = og.get_graph_by_path(first_prim.GetPrimPath().pathString)
                return bool(graph)
            return False

        return register_stage_graph_opener(can_open, RemixLogicGraphExtension.show_graph, 1000)

    def _get_graph_widget(self) -> RemixLogicGraphWidget:
        window: RemixLogicGraphWindow = self._workspace.get_window()
        if window:
            return window.get_graph_widget()
        return None

    async def _show_and_get_graph_widget(self):
        self.show_window(True)
        # wait for the window to be fully built to receive next call
        for _ in range(10):
            graph_widget = self._get_graph_widget()
            if graph_widget:
                break
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

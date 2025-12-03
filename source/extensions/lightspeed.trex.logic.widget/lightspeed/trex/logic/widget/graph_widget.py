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

__all__ = ["RemixLogicGraphWidget"]

import webbrowser
from functools import partial
from pathlib import Path

import omni.graph.core as og
import omni.ui as ui
from lightspeed.common.constants import QUICK_START_GUIDE_URL
from lightspeed.trex.logic.core.graphs import LogicGraphCore
from omni.flux.utils.dialog import ErrorPopup
from omni.graph.window.core import OmniGraphWidget
from omni.kit.window.popup_dialog import InputDialog
from pxr import Sdf, Usd

EXT_PATH = Path(__file__).parent.parent.parent.parent.parent
ICON_PATH = EXT_PATH.joinpath("icons")
ICON_SIZE = 120

DEFAULT_GRAPH_PREFIX = "RemixLogicGraph"
DEFAULT_GRAPH_EVALUATOR = "component"


class RemixLogicGraphWidget(OmniGraphWidget):

    # Overridden Omni Graph methods

    # re-implemented create_graph method from omni.graph.window.core
    def create_graph(self, evaluator_type: str, name_prefix: str, menu_arg=None, value=None, use_dialog=False):
        """
        Override: Create a new component graph below the selected prim

        Note: USE_IMPLICIT_GLOBAL_GRAPH forces creation of subgraphs only

        Args:
            evaluator_type: the evaluator type to use for the new graph
            name_prefix: the desired name of the component graph node. Will be made unique
            menu_arg: menu info
            value: menu value
        """
        stage = self._usd_context.get_stage()

        # Create the graph at the selected prim
        selected_prim_paths = self._selection.get_selected_prim_paths()
        if len(selected_prim_paths) != 1:
            error_message = f"Please select exactly 1 prim, got {len(selected_prim_paths)}"
            if use_dialog:
                ErrorPopup("Select a single Prim", error_message).show()
                return
            raise ValueError(f"Please select exactly 1 prim, got {len(selected_prim_paths)}")

        prim = self._usd_context.get_stage().GetPrimAtPath(selected_prim_paths[0])
        graph_root_prim = LogicGraphCore.get_graph_root_prim(prim)
        if not graph_root_prim:
            error_message = (
                f"Please select a prim under a mesh or light asset replacement root, " f"got {selected_prim_paths[0]}"
            )
            if use_dialog:
                ErrorPopup("Select an asset replacement root", error_message).show()
                return
            raise ValueError(error_message)

        graph_root_path = prim.GetPath()

        def create_and_load_graph_at_path(graph_root_path: Sdf.Path, name_prefix: str):
            graph_path = LogicGraphCore.create_graph_at_path(stage, graph_root_path, name_prefix, evaluator_type)
            # select the new prim
            self._selection.set_prim_path_selected(str(graph_path), True, True, True, True)
            # Import it to the GraphView
            self._import_selection()

        def on_okay(dialog: InputDialog):
            input_prefix = dialog.get_value()
            create_and_load_graph_at_path(graph_root_path, input_prefix)
            dialog.hide()

        def on_cancel(dialog: InputDialog):
            dialog.hide()

        if use_dialog:
            dialog = InputDialog(
                title=f"Create {evaluator_type} Graph",
                message=f'Creating under "{graph_root_path}"\n Enter desired prim name for graph:',
                default_value=name_prefix,
                ok_handler=on_okay,
                cancel_handler=on_cancel,
            )
            dialog.show()
        else:
            create_and_load_graph_at_path(graph_root_path, name_prefix)

    def is_graph_editable(self, graph: og.Graph) -> bool:
        """Override: Returns True if the given graph is editable by this widget"""
        stage: Usd.Stage = self._usd_context.get_stage()
        graph_prim = stage.GetPrimAtPath(graph.get_path_to_graph())
        if not LogicGraphCore.is_graph_prim_editable(graph_prim):
            return False
        try:
            settings = og.get_graph_settings(graph)
            return settings.evaluator_type != "execution" or (settings.are_compounds_enabled() and graph.is_compound())
        except AttributeError:
            # Temporary fix for 2022.1 build
            return True

    def on_build_catalog(self):
        """Override: Build only the catalog for the graph widget, without the variables widget or any tabs."""
        with ui.VStack(spacing=4):
            self._catalog_frame = ui.Frame()
            with self._catalog_frame:
                # Skip OmniGraphWidget's on_build_catalog to avoid building the variables widget
                super(OmniGraphWidget, self).on_build_catalog()  # noqa: PLE1003

    def on_build_startup(self):
        """Overridden from base to customize startup panel UI"""
        with ui.ZStack():
            ui.Rectangle(style_type_name_override="Graph")
            with ui.HStack(content_clipping=True):
                with ui.VStack():
                    ui.Spacer()
                    with ui.HStack():
                        ui.Spacer()
                        ui.Button(
                            "Edit Graph",
                            name="Edit Graph",
                            height=0,
                            width=ICON_SIZE,
                            style_type_name_override="Graph",
                            image_width=ICON_SIZE,
                            image_height=ICON_SIZE,
                            image_url=f"{ICON_PATH}/push_graph_edit_dark.svg",
                            spacing=5,
                            clicked_fn=self._on_edit_graph_action,
                        )
                        ui.Button(
                            "New Graph",
                            name="New Graph",
                            height=0,
                            width=ICON_SIZE,
                            style_type_name_override="Graph",
                            image_width=ICON_SIZE,
                            image_height=ICON_SIZE,
                            image_url=f"{ICON_PATH}/push_graph_new_dark.svg",
                            spacing=5,
                            clicked_fn=partial(
                                self.create_graph, DEFAULT_GRAPH_EVALUATOR, DEFAULT_GRAPH_PREFIX, use_dialog=True
                            ),
                        )
                        ui.Spacer()
                    ui.Spacer()

    def _select_graph_dialog(self):
        """
        Overridden to make the dialog more readable by adding a scrolling frame left centering.

        Present a window for the user to select a graph to open
        """
        window = ui.Window("Select Graph To Open", width=800, height=500, flags=ui.WINDOW_FLAGS_MODAL)

        def close():
            if window:
                window.visible = False

        def select_graph(graph: og.Graph):
            if not graph:
                return
            self._open_graph(graph.get_path_to_graph())
            close()

        graphs = [g for g in og.get_all_graphs() if self.is_graph_editable(g)]
        graphs.sort(key=lambda g: g.get_path_to_graph())

        with window.frame:
            with ui.ScrollingFrame(
                name="WorkspaceBackground",
            ):
                with ui.VStack(
                    height=0,
                    spacing=8,
                    # copy styling override from OmniGraphWidget
                    style={"VStack::top_level_stack": {"margin": 5}, "Button": {"margin": 0}},
                ):
                    for graph in graphs:
                        with ui.HStack():
                            ui.Button(
                                graph.get_path_to_graph(),
                                name="SdfPathButton",
                                clicked_fn=partial(select_graph, graph),
                            )
                            ui.Spacer(width=0)
                    if not graphs:
                        ui.Button("No Graphs Found", clicked_fn=close)

    def _on_edit_graph_action(self):
        """Override: Always prompt for selection"""
        # TODO: Once we have a Stage Manager filter (REMIX-4719), rely on that for selection and just pop up an
        # error dialog here if the selection is not a graph. Until then, show the default dialog.
        self._select_graph_dialog()

    def on_toolbar_create_graph_clicked(self):
        """Override to change type of graph created"""
        self.create_graph(DEFAULT_GRAPH_EVALUATOR, DEFAULT_GRAPH_PREFIX, use_dialog=True)

    # TODO: Update once we have docs. Remix docs should probably link to ogn for background info.
    def on_toolbar_help_clicked(self):
        """Override to guide users to a Remix Specific docs page"""
        webbrowser.open(QUICK_START_GUIDE_URL)

    # New methods

    def on_create_graph_under_parent_action(self, parent: Usd.Prim):
        """Create a new graph at the given parent"""
        self._selection.set_prim_path_selected(str(parent.GetPath()), True, True, True, True)
        self.create_graph(DEFAULT_GRAPH_EVALUATOR, DEFAULT_GRAPH_PREFIX, use_dialog=True)

    def on_load_existing_graph_action(self, graph: Usd.Prim):
        """Edit the given graph"""
        self._selection.set_prim_path_selected(str(graph.GetPath()), True, True, True, True)
        self._import_selection()

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
from lightspeed.common.constants import LOGIC_DOCUMENTATION_URL
from lightspeed.trex.logic.core.graphs import LogicGraphCore
from omni.flux.utils.dialog import ErrorPopup
from omni.flux.utils.widget.tree_widget import AlternatingRowWidget, TreeWidget
from omni.graph.window.core import OmniGraphWidget
from omni.kit.window.popup_dialog import InputDialog
from pxr import Sdf, Usd

from .backdrop_delegate import RemixBackdropDelegate, trigger_backdrop_rename
from .graph_edit_tree import GraphEditTreeDelegate, GraphEditTreeModel
from .graph_node_delegate import RemixLogicNodeDelegate

EXT_PATH = Path(__file__).parent.parent.parent.parent.parent
ICON_PATH = EXT_PATH.joinpath("icons")
ICON_SIZE = 120

DEFAULT_GRAPH_PREFIX = "RemixLogicGraph"
DEFAULT_GRAPH_EVALUATOR = "component"


class RemixLogicGraphWidget(OmniGraphWidget):
    def __init__(self, **kwargs):
        graph_delegate = RemixLogicNodeDelegate(self)
        super().__init__(
            graph_delegate=graph_delegate,
            **kwargs,
        )

        # Replace default BackdropDelegate with styled version for inline rename
        self._router.add_route(RemixBackdropDelegate(), type="Backdrop")

        self._edit_model = GraphEditTreeModel()
        self._edit_delegate = GraphEditTreeDelegate()

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
            error_message = f"Select exactly 1 prim.\n{len(selected_prim_paths)} are currently selected."
            if use_dialog:
                ErrorPopup("Select Exactly 1 Prim", error_message, window_size=(400, 120)).show()
                return
            raise ValueError(f"Select exactly 1 prim. {len(selected_prim_paths)} are currently selected.")

        prim = self._usd_context.get_stage().GetPrimAtPath(selected_prim_paths[0])
        graph_root_prim = LogicGraphCore.get_graph_root_prim(prim)
        if not graph_root_prim:
            error_message = "The selected prim is not a valid graph root.\nSelect a child of a mesh or light prim."
            if use_dialog:
                ErrorPopup("Invalid Selection", error_message, window_size=(400, 120)).show()
                return
            raise ValueError(error_message)

        graph_root_path = graph_root_prim.GetPath()

        def create_and_load_graph_at_path(graph_root_path: Sdf.Path, name_prefix: str):
            graph_path = LogicGraphCore.create_graph_at_path(stage, graph_root_path, name_prefix, evaluator_type)
            # select the new prim
            self._selection.set_prim_path_selected(str(graph_path), True, True, True, True)
            # Import it to the GraphView
            self._import_selection()

        def show_graph_name_input_dialog(default_value: str, warning: str | None = None):
            """Show an input dialog, optionally with a validation warning."""

            def on_okay(dialog: InputDialog):
                input_prefix = dialog.get_value()
                if not Sdf.Path.IsValidIdentifier(input_prefix):
                    dialog.hide()
                    # Re-show dialog with warning and preserve user's input
                    show_graph_name_input_dialog(
                        default_value=input_prefix,
                        warning=(
                            f'"{input_prefix}" is not a valid prim name.\n'
                            "Names must start with a letter or underscore, and contain only "
                            "letters, numbers, and underscores (no spaces or special characters)."
                        ),
                    )
                    return
                create_and_load_graph_at_path(graph_root_path, input_prefix)
                dialog.hide()

            def on_cancel(dialog: InputDialog):
                dialog.hide()

            dialog = InputDialog(
                title="Create New Logic Graph",
                message=f"Creating a new graph under:\n{graph_root_path}\n\nEnter the desired graph name:",
                default_value=default_value,
                ok_label="Create",
                ok_handler=on_okay,
                cancel_handler=on_cancel,
                warning_message=warning,
            )
            dialog.show()

        if use_dialog:
            show_graph_name_input_dialog(default_value=name_prefix)
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
                super(OmniGraphWidget, self).on_build_catalog()

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
        window = ui.Window(
            "Select Graph To Edit",
            width=800,
            height=500,
            flags=ui.WINDOW_FLAGS_MODAL
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_COLLAPSE,
        )

        def close():
            if window:
                window.visible = False

        def select_graph():
            if not self._edit_tree.selection:
                return
            self._open_graph(self._edit_tree.selection[-1].prim_path)
            close()

        def selection_changed(items: list):
            if self._select_button:
                enabled = len(items) > 0
                self._select_button.enabled = enabled
                self._select_button.tooltip = (
                    "Edit the selected graph" if enabled else "Select a graph to edit in the list above"
                )
            if not items:
                return
            # Always select the last item in the selection (disable multi-select)
            self._edit_tree.selection = [items[-1]]

        graphs = [g for g in og.get_all_graphs() if self.is_graph_editable(g)]
        graphs.sort(key=lambda g: g.get_path_to_graph())

        self._edit_model.set_items(graphs)

        with window.frame:
            with ui.VStack():
                with ui.ZStack():
                    alternating_rows = AlternatingRowWidget(
                        self._edit_delegate.ROW_HEIGHT, self._edit_delegate.ROW_HEIGHT
                    )
                    scrolling_frame = ui.ScrollingFrame(
                        name="TreePanelBackground",
                        scroll_y_changed_fn=alternating_rows.sync_scrolling_frame,
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    )
                    with scrolling_frame:
                        self._edit_tree = TreeWidget(
                            self._edit_model,
                            delegate=self._edit_delegate,
                            root_visible=False,
                            header_visible=True,
                            column_widths=[ui.Fraction(1), ui.Fraction(3)],
                        )

                ui.Spacer(height=ui.Pixel(8))

                button_width = ui.Pixel(100)
                with ui.HStack(spacing=8, height=0):
                    ui.Spacer()
                    self._select_button = ui.Button("Select", clicked_fn=select_graph, width=button_width)
                    ui.Button("Cancel", clicked_fn=close, width=button_width, tooltip="Close the dialog")
                ui.Spacer(height=ui.Pixel(4))

            # Subscribe to item double clicked events
            self._item_double_clicked_sub = self._edit_delegate.subscribe_item_double_clicked(lambda _: select_graph())

            # Force update the select button state
            selection_changed(self._edit_tree.selection)

            # Sync the frame height when the content size changes
            scrolling_frame.set_computed_content_size_changed_fn(
                lambda: alternating_rows.sync_frame_height(self._edit_tree.computed_height)
            )

            # Subscribe to selection changes to update the select button state
            self._selection_changed_sub = self._edit_tree.subscribe_selection_changed(selection_changed)

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
        webbrowser.open(LOGIC_DOCUMENTATION_URL)

    # New methods

    def on_create_graph_under_parent_action(self, parent: Usd.Prim):
        """Create a new graph at the given parent"""
        self._selection.set_prim_path_selected(str(parent.GetPath()), True, True, True, True)
        self.create_graph(DEFAULT_GRAPH_EVALUATOR, DEFAULT_GRAPH_PREFIX, use_dialog=True)

    def on_load_existing_graph_action(self, graph: Usd.Prim):
        """Edit the given graph"""
        self._selection.set_prim_path_selected(str(graph.GetPath()), True, True, True, True)
        self._import_selection()

    def rename_selected_backdrop(self):
        """Rename the selected backdrop using inline editing."""
        if not self._graph_view or not self._graph_view.selection:
            return
        selection = self._graph_view.selection
        if len(selection) == 1 and hasattr(selection[0], "GetTypeName") and selection[0].GetTypeName() == "Backdrop":
            trigger_backdrop_rename(selection[0].GetPath())

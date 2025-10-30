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

import webbrowser
from functools import partial
from pathlib import Path

import omni.graph.core as og
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import QUICK_START_GUIDE_URL
from lightspeed.error_popup.window import ErrorPopup
from lightspeed.trex.utils.common.prim_utils import get_prototype, is_in_light_group, is_in_mesh_group
from omni.graph.window.core import OmniGraphWidget
from omni.kit.window.popup_dialog import InputDialog
from pxr import Sdf

EXT_PATH = Path(__file__).parent.parent.parent.parent.parent
ICON_PATH = EXT_PATH.joinpath("icons")
ICON_SIZE = 120

DEFAULT_GRAPH_PREFIX = "RemixLogicGraph"
DEFAULT_GRAPH_EVALUATOR = "component"


class RemixLogicGraphWidget(OmniGraphWidget):

    # re-implemented create_graph method from omni.graph.window.core
    def create_graph(self, evaluator_type: str, name_prefix: str, menu_arg=None, value=None, use_dialog=False):
        """Create a new component graph below the selected prim

        Note: USE_IMPLICIT_GLOBAL_GRAPH forces creation of subgraphs only

        Args:
            evaluator_type: the evaluator type to use for the new graph
            name_prefix: the desired name of the component graph node. Will be made unique
            menu_arg: menu info
            value: menu value
        """
        stage = self._usd_context.get_stage()

        # Create the graph at the selected prim
        self._selection = self._usd_context.get_selection()
        selected_prim_paths = self._selection.get_selected_prim_paths()
        if len(selected_prim_paths) != 1:
            error_message = f"Please select exactly 1 prim, got {len(selected_prim_paths)}"
            if use_dialog:
                ErrorPopup("Select a single Prim", error_message).show()
                return
            raise ValueError(f"Please select exactly 1 prim, got {len(selected_prim_paths)}")

        prim = get_prototype(self._usd_context.get_stage().GetPrimAtPath(selected_prim_paths[0]))
        if not prim or not (is_in_mesh_group(prim) or is_in_light_group(prim)):
            error_message = (
                f"Please select a prim under a mesh or light asset replacement root, " f"got {selected_prim_paths[0]}"
            )
            if use_dialog:
                ErrorPopup("Select an asset replacement root", error_message).show()
                return
            raise ValueError(error_message)

        graph_root_path = prim.GetPath()

        def create_graph_at_path(path: Sdf.Path):
            # FIXME: Just use the first one? We may want a clearer API here.
            graph = og.get_global_orchestration_graphs()[0]

            # Create the global compute graph
            og.cmds.CreateGraphAsNode(
                graph=graph,
                node_name=Sdf.Path(path).name,
                graph_path=path,
                evaluator_name=evaluator_type,
                is_global_graph=True,
                backed_by_usd=True,
                fc_backing_type=og.GraphBackingType.GRAPH_BACKING_TYPE_FLATCACHE_SHARED,
                pipeline_stage=og.GraphPipelineStage.GRAPH_PIPELINE_STAGE_SIMULATION,
            )

            # select the new prim
            self._selection.set_prim_path_selected(path, True, True, True, True)
            # Import it to the GraphView
            self._import_selection()

        def on_okay(dialog: omni.kit.window.popup_dialog.dialog.PopupDialog):
            input_prefix = dialog.get_value()
            graph_path = Sdf.Path(input_prefix).MakeAbsolutePath(graph_root_path)
            graph_path = omni.usd.get_stage_next_free_path(stage, graph_path, True)
            create_graph_at_path(graph_path)
            dialog.hide()

        def on_cancel(dialog: omni.kit.window.popup_dialog.dialog.PopupDialog):
            dialog.hide()

        if use_dialog:
            dialog = InputDialog(
                title=f"Create {evaluator_type} Graph",
                message=f"Creating under {graph_root_path} Enter desired prim name for graph:",
                default_value=name_prefix,
                ok_handler=on_okay,
                cancel_handler=on_cancel,
            )
            dialog.show()
        else:
            graph_path = Sdf.Path(name_prefix).MakeAbsolutePath(graph_root_path)
            graph_path = omni.usd.get_stage_next_free_path(stage, graph_path, True)
            create_graph_at_path(graph_path)

    def is_graph_editable(self, graph: og.Graph) -> bool:
        """Override: Returns True if the given graph is editable by this widget"""
        try:
            settings = og.get_graph_settings(graph)
            return settings.evaluator_type != "execution" or (settings.are_compounds_enabled() and graph.is_compound())
        except AttributeError:
            # Temporary fix for 2022.1 build
            return True

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

    def on_toolbar_create_graph_clicked(self):
        """Override to change type of graph created"""
        self.create_graph(DEFAULT_GRAPH_EVALUATOR, DEFAULT_GRAPH_PREFIX, use_dialog=True)

    # TODO: Update once we have docs. Remix docs should probably link to ogn for background info.
    def on_toolbar_help_clicked(self):
        """Override to guide users to a Remix Specific docs page"""
        webbrowser.open(QUICK_START_GUIDE_URL)

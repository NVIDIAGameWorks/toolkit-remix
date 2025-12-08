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

__all__ = ["LogicGraphWidgetPlugin"]

import omni.kit.commands
from lightspeed.common.constants import OMNI_GRAPH_NODE_TYPE, OMNI_GRAPH_TYPE, GlobalEventNames
from lightspeed.events_manager import get_instance
from lightspeed.trex.logic.core.graphs import LogicGraphCore
from lightspeed.trex.utils.common import prim_utils
from omni import ui
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel
from omni.flux.stage_manager.plugin.widget.usd.base import StageManagerStateWidgetPlugin
from omni.flux.utils.common.menus import MenuGroup, MenuItem
from omni.flux.utils.widget.resources import get_icons


class LogicGraphWidgetPlugin(StageManagerStateWidgetPlugin, StageManagerMenuMixin):
    def build_icon_ui(
        self,
        model: StageManagerTreeModel,
        item: StageManagerTreeItem,
        level: int,
        expanded: bool,
    ) -> None:
        # NOTE: we build an empty widget here
        ui.Spacer(height=0, width=0)
        item.build_widget()

    def build_overview_ui(self, *args, **kwargs):
        pass

    @classmethod
    def _create_logic_graph(cls, payload: dict) -> None:
        prim = payload["right_clicked_item"].data
        prim = LogicGraphCore.get_graph_root_prim(prim)
        event_man = get_instance()
        event_man.call_global_custom_event(GlobalEventNames.LOGIC_GRAPH_CREATE_REQUEST.value, prim)

    @classmethod
    def _edit_logic_graph(cls, payload: dict) -> None:
        prim = payload["right_clicked_item"].data
        if prim_utils.is_instance(prim):
            prim = prim_utils.get_prototype(prim)

        event_man = get_instance()
        event_man.call_global_custom_event(GlobalEventNames.LOGIC_GRAPH_EDIT_REQUEST.value, prim)

    @classmethod
    def _remove_logic_graph(cls, payload: dict) -> None:
        prim = payload["right_clicked_item"].data
        if prim_utils.is_instance(prim):
            prim = prim_utils.get_prototype(prim)

        omni.kit.commands.execute("DeletePrimsCommand", paths=[prim.GetPath()])

    @classmethod
    def _is_a_valid_graph_parent(cls, payload: dict) -> bool:
        prim = payload["right_clicked_item"].data
        if prim.GetTypeName() in {OMNI_GRAPH_TYPE, OMNI_GRAPH_NODE_TYPE}:
            return False
        prim = LogicGraphCore.get_graph_root_prim(prim)

        if not prim:
            return False

        return True

    @classmethod
    def _is_an_omnigraph_prim(cls, payload: dict) -> bool:
        prim = payload["right_clicked_item"].data
        if prim_utils.is_instance(prim):
            prim = prim_utils.get_prototype(prim)

        if prim.GetTypeName() == OMNI_GRAPH_TYPE:
            return True

        return False

    @classmethod
    def _get_menu_items(cls) -> list:
        submenu_icon = get_icons("LogicGraphIcon")
        plus_icon = get_icons("LogicGraphAddIcon")
        minus_icon = get_icons("LogicGraphDeleteIcon")
        edit_icon = get_icons("LogicGraphEditIcon")

        add_btn = {
            "name": MenuItem.LOGIC_GRAPH_ADD.value,
            "glyph": plus_icon,
            "onclick_fn": cls._create_logic_graph,
            "show_fn": cls._is_a_valid_graph_parent,
        }

        edit_btn = {
            "name": MenuItem.LOGIC_GRAPH_EDIT.value,
            "glyph": edit_icon,
            "onclick_fn": cls._edit_logic_graph,
            "show_fn": cls._is_an_omnigraph_prim,
        }

        remove_btn = {
            "name": MenuItem.LOGIC_GRAPH_REMOVE.value,
            "glyph": minus_icon,
            "onclick_fn": cls._remove_logic_graph,
            "show_fn": cls._is_an_omnigraph_prim,
        }

        btn_list = [add_btn, edit_btn, remove_btn]

        menu_item_dic = {MenuItem.LOGIC_GRAPH.value: btn_list}
        return [
            (
                {
                    "name": menu_item_dic,
                    "glyph": submenu_icon,
                    "appear_after": MenuItem.ASSIGN_CATEGORY.value,
                },
                MenuGroup.SELECTED_PRIMS.value,
                "",
            )
        ]

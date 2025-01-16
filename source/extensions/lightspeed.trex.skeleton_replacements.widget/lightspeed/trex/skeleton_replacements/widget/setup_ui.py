"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["SkeletonRemappingWidget"]

from lightspeed.trex.asset_replacements.core.shared import SkeletonReplacementBinding
from omni import ui
from omni.kit.widget.prompt import Prompt

from .joint_tree.delegate import JointDelegate
from .joint_tree.model import JointTreeModel


class SkeletonRemappingWidget:
    """Widget to remap replacement skeletons to captured skeletons"""

    def __init__(self):
        self._skel_replacement: SkeletonReplacementBinding = None
        self._tree_delegate: JointDelegate = None
        self._tree_model: JointTreeModel = None
        self._tree: ui.TreeView = None
        self._build_ui()

    def _build_ui(self):
        self._tree_model = JointTreeModel()
        self._tree_delegate = JointDelegate()

        with ui.VStack():
            with ui.ScrollingFrame(
                name="WorkspaceBackground",
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                self._tree = ui.TreeView(
                    self._tree_model,
                    delegate=self._tree_delegate,
                    root_visible=False,
                    header_visible=True,
                    columns_resizable=True,
                    column_widths=[ui.Percent(45), ui.Percent(10), ui.Percent(45)],
                    row_height=self._tree_delegate.ROW_HEIGHT,
                )
            with ui.HStack(height=24):
                ui.Button(
                    "Auto Remap Joints",
                    clicked_fn=self.reset,
                    tooltip="Use a basic name and ordering heuristic to populate joint mapping",
                )
                ui.Button(
                    "Apply", clicked_fn=self.accept, tooltip="Author the new joint influences to the bound mesh prim"
                )

    def reset(self):
        self._tree_model.refresh(self._skel_replacement, read_from_usd=False)
        self._tree.set_expanded(None, True, True)  # expand all initially

    def refresh(self, skel_replacement: SkeletonReplacementBinding = None):
        self._skel_replacement = skel_replacement
        self._tree_model.refresh(skel_replacement)
        self._tree.set_expanded(None, True, True)  # expand all initially

    def accept(self):
        joint_map = self._tree_model.get_joint_map()
        self._skel_replacement.apply(joint_map)
        Prompt("Applied!", "Joint influences have been remapped.").show()

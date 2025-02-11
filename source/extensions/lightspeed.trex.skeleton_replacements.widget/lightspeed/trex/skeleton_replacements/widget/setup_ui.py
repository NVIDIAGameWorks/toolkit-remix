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
from lightspeed.trex.utils.widget import TrexMessageDialog
from omni import ui
from omni.flux.utils.widget.tree_widget import AlternatingRowWidget

from .joint_tree.delegate import JointDelegate
from .joint_tree.model import JointTreeModel


class SkeletonRemappingWidget:
    """Widget to remap replacement skeletons to captured skeletons"""

    def __init__(self):
        self._skel_replacement: SkeletonReplacementBinding = None
        self._tree_delegate: JointDelegate = None
        self._tree_model: JointTreeModel = None
        self._tree: ui.TreeView = None
        self._tree_model_item_changed_sub = None
        self._build_ui()

    def _build_ui(self):
        self._tree_model = JointTreeModel()
        self._tree_delegate = JointDelegate()

        with ui.Frame():
            with ui.VStack(spacing=ui.Pixel(8)):
                ui.Spacer(height=0)
                with ui.HStack(height=24, spacing=ui.Pixel(8)):
                    ui.Spacer(width=0)
                    ui.Label(
                        "Select the corresponding capture joint for each joint on the replacement asset's skeleton."
                    )
                    ui.Spacer(width=0)

                ui.Rectangle(height=ui.Pixel(1), name="WizardSeparator")

                with ui.VStack():
                    with ui.ZStack():
                        self._alternating_row_widget = AlternatingRowWidget(
                            self._tree_delegate.ROW_HEIGHT, self._tree_delegate.ROW_HEIGHT
                        )
                        self._tree_scroll_frame = ui.ScrollingFrame(
                            name="TreePanelBackground",
                            scroll_y_changed_fn=self._alternating_row_widget.sync_scrolling_frame,
                            computed_content_size_changed_fn=(
                                lambda: self._alternating_row_widget.sync_frame_height(self._tree.computed_height)
                            ),
                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        )
                        with self._tree_scroll_frame:
                            self._tree = ui.TreeView(
                                self._tree_model,
                                delegate=self._tree_delegate,
                                root_visible=False,
                                header_visible=True,
                                columns_resizable=True,
                                column_widths=[ui.Percent(45), ui.Percent(10), ui.Percent(45)],
                                row_height=self._tree_delegate.ROW_HEIGHT,
                            )
                        self._tree_model_item_changed_sub = self._tree_model.subscribe_item_changed_fn(
                            lambda *_: self._alternating_row_widget.refresh(self._tree_model.item_count)
                        )
                    ui.Spacer(height=2)
                    with ui.HStack(height=24):
                        ui.Button(
                            "Collapse All",
                            clicked_fn=lambda: self._tree.set_expanded(
                                self._tree_model.get_item_children()[0], False, True
                            ),
                        )
                        ui.Button("Expand All", clicked_fn=lambda: self._tree.set_expanded(None, True, True))

                with ui.HStack(height=24):
                    ui.Button(
                        "Reset",
                        clicked_fn=lambda: self.refresh(skel_replacement=self._skel_replacement),
                        tooltip="Revert to mapping in USD stage",
                    )
                    ui.Button("Clear", clicked_fn=self.clear, tooltip="Set all joint influences to the root joint")
                    ui.Button(
                        "Auto Remap Joints",
                        clicked_fn=self.auto_remap,
                        tooltip="Use a basic name and ordering heuristic to populate joint mapping",
                    )

                ui.Rectangle(height=ui.Pixel(1), name="WizardSeparator")

                with ui.HStack(height=24):
                    ui.Button(
                        "Apply",
                        clicked_fn=self.accept,
                        tooltip="Author the new joint influences to the bound mesh prim",
                    )
                ui.Spacer(height=0)

    def clear(self):
        mesh_joints = self._skel_replacement.get_mesh_joints()
        refreshed_joint_map = [0] * len(mesh_joints)
        self._tree_model.apply_joint_map(refreshed_joint_map)

    def auto_remap(self):
        mesh_joints = self._skel_replacement.get_mesh_joints()
        capture_joints = self._skel_replacement.get_captured_joints()
        remapped_joint_map = self._skel_replacement.generate_joint_map(mesh_joints, capture_joints, fallback=True)
        self._tree_model.apply_joint_map(remapped_joint_map)

    def refresh(self, skel_replacement: SkeletonReplacementBinding = None):
        self._skel_replacement = skel_replacement
        self._tree_model.refresh(skel_replacement)
        self._tree.set_expanded(None, True, True)  # expand all initially

    def accept(self):
        joint_map = self._tree_model.get_joint_map()
        self._skel_replacement.apply(joint_map)
        TrexMessageDialog(
            message="Joint influences have been remapped.",
            title="Applied!",
            disable_cancel_button=True,
        )

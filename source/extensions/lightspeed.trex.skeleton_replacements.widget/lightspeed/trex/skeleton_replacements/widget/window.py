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

__all__ = ["SkeletonRemappingWindow"]

from lightspeed.trex.asset_replacements.core.shared import SkeletonReplacementBinding
from omni import ui

from .setup_ui import SkeletonRemappingWidget


class SkeletonRemappingWindow:
    """Window to remap replacement skeletons to captured skeletons"""

    POPUP_WIDTH = 600
    POPUP_HEIGHT = 600
    TITLE_PREFIX = "Remap Skeleton Binding On:"

    def __init__(self):
        self._widget: SkeletonRemappingWidget = None
        self.window = ui.Window(
            self.TITLE_PREFIX,
            name="SkeletonRemappingWindow",
            width=self.POPUP_WIDTH,
            height=self.POPUP_HEIGHT,
            visible=False,
            # non-modal so you can interact with viewport at the same time
            flags=(ui.WINDOW_FLAGS_NO_DOCKING | ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_SCROLLBAR),
        )
        self._tree = None
        self._build_ui()

    def _build_ui(self):
        with self.window.frame:
            with ui.ZStack():
                ui.Rectangle(name="WorkspaceBackground")
                self._widget = SkeletonRemappingWidget()

    def show_window(self, value: bool = True, skel_replacement: SkeletonReplacementBinding = None):
        self.window.visible = value
        if value:
            self._widget.refresh(skel_replacement)
            self.window.title = f"{self.TITLE_PREFIX} {skel_replacement.bound_prim.GetName()}"
            self.window.tabBar_tooltip = f"{self.TITLE_PREFIX} {skel_replacement.bound_prim.GetPath()}"

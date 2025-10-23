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

from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase as _WorkspaceWindowBase
from omni import ui

from .stage_manager import StageManagerWidget as _StageManagerWidget


class StageManagerWindow(_WorkspaceWindowBase):
    """Stage Manager window manager"""

    @property
    def title(self) -> str:
        return _WindowNames.STAGE_MANAGER

    def menu_path(self) -> str | None:
        return f"Editor/{self.title}"

    @property
    def flags(self) -> int:
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window_ui(self):
        return _StageManagerWidget()

    def _on_window_resized(self, value: float):
        self._content.resize_tabs()

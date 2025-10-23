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

from .setup_ui import ProjectSetupPane as _ProjectSetupPane


class ProjectSetupWindow(_WorkspaceWindowBase):
    """Project Setup window manager"""

    @property
    def title(self) -> str:
        return _WindowNames.PROJECT_SETUP

    def menu_path(self) -> str | None:
        return f"Setup & Packaging/{self.title}"

    @property
    def flags(self) -> int:
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_COLLAPSE

    def _create_window_ui(self):
        return _ProjectSetupPane(self._usd_context_name)

    def _on_visibility_changed(self, visible: bool):
        super()._on_visibility_changed(visible)
        self._content.show(visible)

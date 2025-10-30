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

__all__ = ["RemixLogicGraphWorkspaceWindow"]


from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase as _WorkspaceWindowBase
from omni import ui

from .graph_window import RemixLogicGraphWindow


class RemixLogicGraphWorkspaceWindow(_WorkspaceWindowBase):
    """Remix Logic Graph window manager"""

    @property
    def title(self) -> str:
        return _WindowNames.REMIX_LOGIC_GRAPH

    def menu_path(self) -> str:
        return f"Editor/Experimental/{self.title}"

    @property
    def flags(self) -> int:
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window(self) -> ui.Window:
        return RemixLogicGraphWindow(title=self.title, width=1000, height=800)

    # overrides for updating content, leave that to omni graph window
    def _update_ui(self):
        pass

    # overrides for updating content, leave that to omni graph window
    def _create_window_ui(self) -> ui.Widget:
        raise NotImplementedError("Should never be called.")

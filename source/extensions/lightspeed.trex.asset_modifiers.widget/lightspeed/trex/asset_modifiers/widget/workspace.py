"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["AssetModifiersWorkspace"]

from lightspeed.common.constants import WindowNames
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase
from omni import ui

from .widget import AssetModifiersWidget


class AssetModifiersWorkspace(WorkspaceWindowBase):
    """Host the Asset Modifiers controls in the StageCraft workspace."""

    _DEFAULT_WIDTH = 400
    _DEFAULT_HEIGHT = 600

    @property
    def title(self) -> str:
        """Return the Asset Modifiers window title."""
        return WindowNames.ASSET_MODIFIERS.value

    @property
    def flags(self) -> int:
        """Let the inputs scroll instead of the window."""
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def menu_path(self) -> str:
        """Return the Asset Modifiers path under the Window menu."""
        return f"Modifiers/{self.title}"

    def _create_window_ui(self) -> AssetModifiersWidget:
        """Create the controls for this workspace's USD context."""
        return AssetModifiersWidget(self._usd_context_name)

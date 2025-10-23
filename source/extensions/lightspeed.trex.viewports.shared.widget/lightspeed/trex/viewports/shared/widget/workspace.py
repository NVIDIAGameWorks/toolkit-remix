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


class MainViewportWindow(_WorkspaceWindowBase):
    """Global Main Viewport window manager"""

    def __init__(self, viewport_create_fn, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._viewport_create_fn = viewport_create_fn

    @property
    def title(self) -> str:
        return _WindowNames.VIEWPORT

    def menu_path(self) -> str | None:
        return f"Editor/{self.title}"

    @property
    def flags(self) -> int:
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def create_window(self):
        super().create_window()
        self._update_ui()  # Create UI on app init so we don't get HdRemix initialization timeout.

    def _create_window_ui(self):
        return self._viewport_create_fn(self._usd_context_name)

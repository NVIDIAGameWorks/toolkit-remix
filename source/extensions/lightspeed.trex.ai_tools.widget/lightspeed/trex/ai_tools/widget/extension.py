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

__all__ = ("AIToolsWindowExtension",)

import carb
import omni.ext
import omni.ui
from lightspeed.trex.contexts.setup import Contexts

from .artifact_handlers import register_apply_handlers, unregister_apply_handlers
from .workspace import AIToolsWorkspace


class AIToolsWindowExtension(omni.ext.IExt):
    """
    AI Tools Window Extension.

    Provides a workspace window for integrating with ComfyUI workflows,
    allowing users to submit AI-powered jobs and apply results to the USD stage.
    """

    _workspace_window: AIToolsWorkspace | None = None

    def on_startup(self, ext_id: str) -> None:
        """Initialize the extension and create the workspace window."""
        carb.log_info("[lightspeed.trex.ai_tools.widget] Startup")
        register_apply_handlers()
        self._workspace_window = AIToolsWorkspace(Contexts.STAGE_CRAFT.value)
        self._workspace_window.create_window(width=1600, height=800)
        omni.ui.Workspace.set_show_window_fn(self._workspace_window.title, self._workspace_window.show_window_fn)

    def on_shutdown(self) -> None:
        """Clean up resources and close the workspace window."""
        carb.log_info("[lightspeed.trex.ai_tools.widget] Shutdown")
        try:
            if self._workspace_window is not None:
                self._workspace_window.cleanup()
                omni.ui.Workspace.set_show_window_fn(self._workspace_window.title, lambda *_: None)
                self._workspace_window = None
        finally:
            unregister_apply_handlers()

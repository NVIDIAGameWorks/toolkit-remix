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

__all__ = ["AlphaCutoutWidgetExtension"]

import carb
import omni.ext
import omni.ui
from lightspeed.common.constants import GlobalEventNames
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts

from .workspace import AlphaCutoutWindow as _AlphaCutoutWindow


class AlphaCutoutWidgetExtension(omni.ext.IExt):
    """Register the alpha cutout window and route Stage Manager conversion requests to it."""

    def __init__(self):
        super().__init__()
        self._window: _AlphaCutoutWindow | None = None
        self._convert_request_sub = None

    def on_startup(self, ext_id: str):
        """Create the window and subscribe to conversion requests.

        Args:
            ext_id: Identifier assigned to this extension instance by Kit.
        """
        carb.log_info("[lightspeed.trex.alpha_cutout.widget] Startup")
        self._window = _AlphaCutoutWindow(_TrexContexts.STAGE_CRAFT.value)
        self._window.create_window()
        omni.ui.Workspace.set_show_window_fn(self._window.title, self._window.show_window_fn)
        self._convert_request_sub = _get_event_manager_instance().subscribe_global_custom_event(
            GlobalEventNames.ALPHA_CUTOUT_CONVERT_REQUEST.value, self._on_convert_request
        )

    def on_shutdown(self):
        """Release the subscription and destroy the window."""
        carb.log_info("[lightspeed.trex.alpha_cutout.widget] Shutdown")
        self._convert_request_sub = None
        if self._window:
            omni.ui.Workspace.set_show_window_fn(self._window.title, lambda *_: None)
            self._window.cleanup()
        self._window = None

    def _on_convert_request(self, prim_paths: list[str], context_name: str) -> None:
        """Open the window seeded with the requested meshes.

        Args:
            prim_paths: Prototype paths to queue.
            context_name: USD context the paths belong to.
        """
        if self._window:
            self._window.open_with_meshes(list(prim_paths), context_name)

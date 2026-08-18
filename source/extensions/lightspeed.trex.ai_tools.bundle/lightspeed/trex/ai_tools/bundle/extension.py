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

__all__ = ["AIToolsBundleExtension"]

import asyncio

import carb
from lightspeed.common.constants import LayoutFiles
from lightspeed.trex.sidebar import Groups, ItemDescriptor, register_items
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.flux.utils.widget.resources import get_quicklayout_config
from omni.ext import IExt


class AIToolsBundleExtension(IExt):
    """Register the full-app AI Tools sidebar entry and load its workspace layout."""

    def __init__(self) -> None:
        """Initialize owned asynchronous task and sidebar subscription state."""
        super().__init__()
        self._layout_task: asyncio.Task | None = None
        self._sub_sidebar_items = None

    def on_startup(self, ext_id: str) -> None:
        """Register the project-independent AI Tools sidebar item.

        Args:
            ext_id: Extension identifier supplied by Kit for this startup.
        """
        carb.log_info("[lightspeed.trex.ai_tools.bundle] Startup")

        self._register_sidebar_items()

    def on_shutdown(self) -> None:
        """Cancel owned tasks and release lifecycle subscriptions."""
        carb.log_info("[lightspeed.trex.ai_tools.bundle] Shutdown")
        if self._layout_task and not self._layout_task.done():
            self._layout_task.cancel()
        self._sub_sidebar_items = None

    def _register_sidebar_items(self):
        """Register the AI Tools sidebar entry for setup and queue access."""
        self._sub_sidebar_items = register_items(
            [
                ItemDescriptor(
                    name="AITools",
                    tooltip="AI Tools",
                    group=Groups.LAYOUTS,
                    mouse_released_fn=self._open_layout,
                    sort_index=11,
                )
            ]
        )

    def _open_layout(self, _mouse_x, _mouse_y, button, _modifier):
        """Open the AI Tools layout for a left-button sidebar release.

        Args:
            _mouse_x: Horizontal pointer coordinate supplied by the sidebar callback.
            _mouse_y: Vertical pointer coordinate supplied by the sidebar callback.
            button: Released mouse button index.
            _modifier: Keyboard modifier mask supplied by the sidebar callback.
        """
        if button != 0:
            return
        self._load_ai_tools_layout()

    def _load_ai_tools_layout(self) -> None:
        """Load the configured AI Tools layout when its resource exists."""
        layout_file = get_quicklayout_config(LayoutFiles.TEXTURECRAFT)
        if not layout_file:
            carb.log_warn("The AI Tools layout resource is unavailable.")
            return
        if self._layout_task and not self._layout_task.done():
            self._layout_task.cancel()
        task = load_layout(layout_file)
        if task is None:
            carb.log_warn(f"The AI Tools layout file does not exist: {layout_file}")
            return
        self._layout_task = task
        task.add_done_callback(self._on_layout_load_done)

    def _on_layout_load_done(self, task: asyncio.Task) -> None:
        """Release a completed layout task and report expected load failures.

        Args:
            task: Shared quick-layout task that completed.
        """
        if self._layout_task is task:
            self._layout_task = None
        if task.cancelled():
            return
        try:
            task.result()
        except (OSError, RuntimeError, ValueError) as error:
            carb.log_error(f"Failed to load the AI Tools layout: {error}")

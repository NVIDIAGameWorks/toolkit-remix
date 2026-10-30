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

__all__ = ["AssetModifiersWidgetExtension"]

from lightspeed.trex.contexts.setup import Contexts
from omni import ui
from omni.ext import IExt
from omni.flux.job_queue.widget import get_display_adapter_registry

from .display_adapter import AssetModifierDisplayAdapter
from .submitter import AssetModifierSubmitter
from .workspace import AssetModifiersWorkspace


class AssetModifiersWidgetExtension(IExt):
    """Register the Asset Modifiers workspace and Job Queue adapter."""

    def __init__(self):
        """Create the StageCraft workspace before Kit starts the extension."""
        super().__init__()
        self._workspace = AssetModifiersWorkspace(Contexts.STAGE_CRAFT.value)

    def on_startup(self, ext_id: str) -> None:
        """Create the window and register the adapter."""
        get_display_adapter_registry().register(AssetModifierDisplayAdapter)
        self._workspace.create_window()
        ui.Workspace.set_show_window_fn(self._workspace.title, self._workspace.show_window_fn)

    def on_shutdown(self) -> None:
        """Cancel pending submissions, release the window, and unregister the adapter."""
        AssetModifierSubmitter.cancel_pending_submissions()
        ui.Workspace.set_show_window_fn(self._workspace.title, lambda *_: None)
        self._workspace.cleanup()
        get_display_adapter_registry().unregister(AssetModifierDisplayAdapter)

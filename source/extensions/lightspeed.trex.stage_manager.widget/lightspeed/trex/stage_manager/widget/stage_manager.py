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

from lightspeed.trex.contexts.setup import Contexts
from lightspeed.trex.hotkeys import TrexHotkeyEvent, get_global_hotkey_manager
from lightspeed.trex.utils.widget import WorkspaceWidget as _WorkspaceWidget
from omni.flux.stage_manager.widget import StageManagerWidget as _StageManagerWidget

__all__ = ["StageManagerWidget"]


class StageManagerWidget(_StageManagerWidget, _WorkspaceWidget):
    """Compose the Remix Stage Manager and connect its app shortcuts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _WorkspaceWidget.__init__(self)
        self._select_all_hotkey_subscription = get_global_hotkey_manager().subscribe_hotkey_event(
            TrexHotkeyEvent.CTRL_A, self._on_select_all_hotkey, context=Contexts.STAGE_CRAFT
        )

    def show(self, visible: bool):
        """Implements WorkspaceWidget interface."""
        super().show(visible)

        if not visible:
            self._cancel_deferred_tab_selection()

        if not self._core:
            return

        enabled_interactions = [interaction for interaction in self._core.schema.interactions if interaction.enabled]
        if not visible:
            for interaction in enabled_interactions:
                interaction.set_active(False)
            if self._interaction_frame:
                self._interaction_frame.clear()
            return

        if 0 <= self._active_interaction < len(enabled_interactions):
            active_interaction = self._active_interaction
            self._active_interaction = -1
            self.select_tab(active_interaction)

    def destroy(self):
        """Implements WorkspaceWidget interface."""
        self._select_all_hotkey_subscription = None
        super().destroy()

    def _on_select_all_hotkey(self):
        """Select all retained items in the active Stage Manager tab."""
        if not self._core:
            return
        interaction = self._core.get_active_interaction()
        if interaction:
            interaction.select_all()

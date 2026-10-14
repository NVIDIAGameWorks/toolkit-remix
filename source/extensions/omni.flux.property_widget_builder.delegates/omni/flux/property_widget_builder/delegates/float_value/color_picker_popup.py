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

__all__ = ("ColorPickerPopup",)

import asyncio
from collections.abc import Callable
from uuid import uuid4

import carb
import omni.ui as ui
from omni.kit.app import get_app


class ColorPickerPopup(ui.Window):
    """Own the transient window and native teardown for embedded color controls."""

    def __init__(self, anchor: ui.Widget, width: float, height: float, close_fn: Callable[[], None]):
        """Open a popup near its swatch and route dismissal through its edit owner.

        Args:
            anchor: Swatch whose screen bounds determine the popup position.
            width: Popup width in UI points.
            height: Popup height in UI points.
            close_fn: Callback that commits focused input before retiring the popup.
        """
        self._close_fn = close_fn
        self._was_focused = False
        position_y = anchor.screen_position_y + anchor.computed_height
        if position_y + height > ui.Workspace.get_main_window_height():
            position_y = max(0.0, anchor.screen_position_y - height)
        # A new native ID prevents a replacement popup from inheriting the retired control's held input.
        super().__init__(
            f"ColorPicker_{uuid4()}",
            width=width,
            height=height,
            position_x=anchor.screen_position_x,
            position_y=position_y,
            flags=ui.WINDOW_FLAGS_POPUP
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_DOCKING
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_TITLE_BAR
            | ui.WINDOW_FLAGS_NO_MOVE,
        )
        self.set_key_pressed_fn(self._on_key_pressed)
        self.set_focused_changed_fn(self._on_focus_changed)
        self.set_visibility_changed_fn(self._on_visibility_changed)

    def retire(self, models, subscriptions):
        """Hide the popup and retain disabled input models until native dispatch finishes.

        Args:
            models: Retired input models whose getters remain valid for native controls.
            subscriptions: Input subscriptions retained until their native controls are destroyed.
        """
        self._close_fn = None
        self.set_key_pressed_fn(None)
        self.set_focused_changed_fn(None)
        self.set_visibility_changed_fn(None)
        self.visible = False
        asyncio.ensure_future(self._destroy_after_update(models, subscriptions))

    async def _destroy_after_update(self, models, subscriptions):
        """Release retired inputs and destroy hidden controls after native dispatch completes."""
        await get_app().next_update_async()
        subscriptions.clear()
        try:
            self.destroy()
        finally:
            models.clear()

    def _on_key_pressed(self, key, _modifier, down):
        """Request normal dismissal when Escape is pressed."""
        if down and key == int(carb.input.KeyboardInput.ESCAPE) and self._close_fn is not None:
            self._close_fn()

    def _on_focus_changed(self, focused):
        """Request normal dismissal when the previously focused popup loses focus."""
        if focused:
            self._was_focused = True
        elif self._was_focused and self._close_fn is not None:
            self._close_fn()

    def _on_visibility_changed(self, visible):
        """Commit focused input when native window dismissal hides the popup."""
        if not visible and self._close_fn is not None:
            self._close_fn()

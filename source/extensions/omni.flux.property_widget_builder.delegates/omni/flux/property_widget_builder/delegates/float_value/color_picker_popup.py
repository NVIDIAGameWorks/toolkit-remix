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

from collections.abc import Callable
from functools import partial

import omni.ui as ui

from ..field_popup_window import FieldPopupWindow


class ColorPickerPopup(FieldPopupWindow):
    """Route shared floating-window activation and dismissal through the color edit owner."""

    def __init__(
        self,
        *,
        title: str,
        context_name: str | None,
        build_fn: Callable[[FieldPopupWindow], None],
        close_fn: Callable[[], None],
        cancel_fn: Callable[[], None],
    ):
        """Construct a hidden host whose content and edits remain owned by the picker.

        Args:
            title: Friendly property name and editor title for the native window.
            context_name: Owning USD context, or None for a generic color field.
            build_fn: Callback that builds controls only after this host activates.
            close_fn: Callback that commits focused input before retiring the host.
            cancel_fn: Callback that discards input when activation or content construction fails.
        """
        self._build_fn = build_fn
        self._close_fn = close_fn
        self._cancel_fn = cancel_fn
        self._retired_inputs = ()
        super().__init__(title=title, context_name=context_name)
        self.flags |= ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def open(self, *, preferred_size, anchor_rect=None):
        """Fit the requested content size around native chrome after the first layout.

        Args:
            preferred_size: Desired width and height of the color controls in logical pixels.
            anchor_rect: Launcher bounds used by the shared host for placement.
        """
        if not self.is_open and not self._closing:
            self.frame.set_computed_content_size_changed_fn(
                partial(self._fit_content_size, preferred_size, anchor_rect)
            )
        super().open(preferred_size=preferred_size, anchor_rect=anchor_rect)

    def close(self):
        """Finish the owner's input before the shared host starts its deferred teardown."""
        if self._close_fn is not None:
            self._close_fn()
        else:
            super().close()

    def retire(self, models, subscriptions):
        """Retain disabled input getters through native teardown and close without reentering the owner.

        Args:
            models: Disabled input models whose getters must survive native control destruction.
            subscriptions: Input subscriptions retained alongside their native controls.
        """
        self._build_fn = self._close_fn = self._cancel_fn = None
        self.frame.set_computed_content_size_changed_fn(None)
        # Native destruction can still query disabled models; retain them with their window.
        self._retired_inputs = (models, subscriptions)
        super().close()

    def _fit_content_size(self, preferred_size, anchor_rect):
        """Include measured native insets once without constraining subsequent user resizing."""
        if self._closing or self.frame.computed_width <= 0 or self.frame.computed_height <= 0:
            return
        self.frame.set_computed_content_size_changed_fn(None)
        self._apply_geometry(
            (
                preferred_size[0] + max(0.0, self.width - self.frame.computed_width),
                preferred_size[1] + max(0.0, self.height - self.frame.computed_height),
            ),
            anchor_rect,
        )

    def _build_content(self):
        """Build the current opening after the shared host releases any outgoing editor."""
        if self._build_fn is not None:
            self._build_fn(self)

    def _release_content(self):
        """Cancel partially built input when the shared host finalizes without owner retirement."""
        cancel_fn, self._cancel_fn = self._cancel_fn, None
        self._build_fn = self._close_fn = None
        self.frame.set_computed_content_size_changed_fn(None)
        if cancel_fn is not None:
            cancel_fn()

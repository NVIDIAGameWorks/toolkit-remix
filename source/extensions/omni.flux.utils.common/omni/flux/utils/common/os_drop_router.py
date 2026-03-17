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

from __future__ import annotations

__all__ = ["WidgetDropRouter"]

from typing import Any

import carb
import omni.appwindow
import omni.ui as ui

from omni.flux.utils.common.mouse import get_mouse_position, is_point_inside_widget


class WidgetDropRouter:
    """
    Central router for OS file drop events. Any widget that wants to receive drops
    registers itself; the router checks each visible registrant's bounds against
    the mouse position and invokes drop_handler on the best match (smallest
    containing widget by area). If the mouse position cannot be determined, the
    drop is ignored and a warning is logged. Hit-testing uses the registered
    widget itself (e.g. a ui.Frame with screen_position_x/y and
    computed_width/height). A registrable widget must have: drop_handler(event)
    and visible (property or attribute).
    """

    _registered_widgets: set[ui.Frame] = set()
    _drop_subscription: Any = None

    @classmethod
    def _global_drop_widget_router_callback(cls, event) -> None:
        """Forward the drop to the visible handler whose bounds contain the cursor. Logs a warning and exits if the mouse position cannot be determined."""
        drop_pos = get_mouse_position()
        if drop_pos is None:
            carb.log_warn("WidgetDropRouter: mouse position could not be determined; drop event ignored.")
            return

        candidates = []
        for widget in list(cls._registered_widgets):
            if not widget.visible:
                continue
            if is_point_inside_widget(widget, drop_pos):
                try:
                    w = max(0, widget.computed_width)
                    h = max(0, widget.computed_height)
                    area = w * h
                except (AttributeError, TypeError):
                    area = 0
                candidates.append((widget, area))

        if candidates:
            candidates.sort(key=lambda p: (p[1], id(p[0])))
            widget = candidates[0][0]
            try:
                widget.drop_handler(event)  # type: ignore[union-attr]
            except Exception as e:  # noqa: BLE001
                # Catch any exception so one handler's failure is logged and does not crash the router;
                # other widgets remain registered for future drops.
                carb.log_error(f"WidgetDropRouter: drop_handler failed for {widget!r}: {e}")

    @classmethod
    def register_widget(cls, widget: ui.Frame) -> None:
        """
        Register a widget to receive OS drop events. The widget must have
        drop_handler(event) and visible (property or attribute). When position
        is known, the widget itself is hit-tested (it must have screen_position_x/y
        and computed_width/height, e.g. a ui.Frame).

        Args:
            widget: Object implementing the drop contract (drop_handler, visible).
        """
        if not callable(getattr(widget, "drop_handler", None)):
            raise TypeError(f"widget must implement drop_handler(event); {widget!r} has no callable drop_handler")

        if not hasattr(widget, "visible"):
            raise TypeError(f"widget must have visible attribute; {widget!r} has no visible")

        if widget in cls._registered_widgets:
            raise RuntimeError(f"{widget} is already registered")

        cls._registered_widgets.add(widget)

        if not cls._drop_subscription:
            app_window = omni.appwindow.get_default_app_window()
            cls._drop_subscription = app_window.get_window_drop_event_stream().create_subscription_to_pop(
                cls._global_drop_widget_router_callback,
                name="WidgetDropRouter",
                order=0,
            )

    @classmethod
    def unregister_widget(cls, widget: ui.Frame) -> None:
        """Unregister a widget so it no longer receives drop events."""
        cls._registered_widgets.discard(widget)

    @classmethod
    def reset(cls) -> None:
        """Clear all registered widgets and drop the event subscription. Use during extension shutdown or tests."""
        cls._registered_widgets.clear()
        cls._drop_subscription = None

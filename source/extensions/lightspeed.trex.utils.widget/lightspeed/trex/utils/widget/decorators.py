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

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar, cast

import omni.ui_query as uiq

F = TypeVar("F", bound=Callable[..., Any])

# Sentinel value returned by skip_when_widget_is_invisible when method is skipped
SKIPPED = "__SKIPPED__"


def skip_when_widget_is_invisible(widget: str) -> Callable[[F], F]:
    """
    Decorator to skip method execution when the specified UI widget is recursively invisible.

    It is stackable - you can apply multiple decorators to "AND" multiple widgets visibility.

    Args:
        widget: The name of the attribute on self that holds the omni.ui widget to check
                (e.g., "_tree", "_frame", "_root_frame")

    Returns:
        Wrapper function that returns earlier if the widget stack is invisible.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not hasattr(self, widget):
                raise AttributeError(
                    f"Widget attribute '{widget}' not found on {self.__class__.__name__}. "
                    f"Ensure the widget has a '{widget}' attribute (e.g., self.{widget} = ui.Frame())"
                )

            ui_widget = getattr(self, widget)

            if not _is_widget_visible(ui_widget):
                return SKIPPED

            return func(self, *args, **kwargs)

        return cast(F, wrapper)

    return decorator


def __get_ui_path_parent(path: str) -> str | None:
    """
    Extract parent path from UI widget path by removing last segment.

    Args:
        path: Full UI path (e.g., "Window//Frame/HStack[0]/Button[0]")

    Returns:
        Parent path (e.g., "Window//Frame/HStack[0]") or None if at root
    """
    if not path or "//" not in path:
        return None

    window_name, _, widget_path = path.partition("//")
    last_slash = widget_path.rfind("/")

    if last_slash == -1:
        return None  # At root level

    return f"{window_name}//{widget_path[:last_slash]}"


def __get_widget_ui_path_and_window(widget: Any) -> tuple[str, Any] | tuple[None, None]:
    """
    Get the UI path for a widget and its containing window.

    Args:
        widget: The UI widget to locate

    Returns:
        Tuple of (path, window) or (None, None) if not found
    """
    import omni.ui as ui

    for window in ui.Workspace.get_windows():
        try:
            path = uiq.OmniUIQuery.get_widget_path(window, widget)
            if path:
                return path, window
        except Exception:  # noqa: PLW0718
            continue

    return None, None


def __find_parent_widget(widget_path: str) -> Any | None:
    """
    Find parent widget from a widget's UI path.

    Args:
        widget_path: Full UI path of child widget

    Returns:
        Parent widget or None if not found
    """
    parent_path = __get_ui_path_parent(widget_path)
    if not parent_path:
        return None

    return uiq.OmniUIQuery.find_widget(parent_path)


def _is_widget_visible(widget: Any) -> bool:
    """
    Check if widget is visible, including all parents and containing window.

    Uses omni.ui_query to traverse parent chain via path parsing.

    Args:
        widget: The UI widget to check

    Returns:
        True if widget, all parents, and window are visible, False otherwise
    """
    if not getattr(widget, "visible", True):
        return False

    try:
        widget_path, window = __get_widget_ui_path_and_window(widget)
        if not widget_path:
            return True  # Can't find path, assume visible

        if window and not getattr(window, "visible", True):
            return False

        parent_widget = __find_parent_widget(widget_path)
        if parent_widget:
            return _is_widget_visible(parent_widget)

        return True  # No parent, widget is at root

    except Exception:  # noqa: PLW0718
        return True  # On error, assume visible

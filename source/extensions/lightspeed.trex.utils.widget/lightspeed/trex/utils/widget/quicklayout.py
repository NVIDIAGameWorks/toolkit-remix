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

__all__ = ["LAYOUT_LOADED_EVENT_NAME", "load_layout", "subscribe_layout_loaded"]

import asyncio
import json
from collections.abc import Callable, Iterator
from typing import Any

import carb
import omni.kit.app
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from omni import ui
from omni.flux.utils.common import EventSubscription
from omni.kit.quicklayout import QuickLayout

LAYOUT_LOADED_EVENT_NAME = "lightspeed.trex.utils.widget.layout_loaded"


def subscribe_layout_loaded(callback: Callable[[], None]) -> EventSubscription:
    """Subscribe to layout loads, and register the event when the first subscriber arrives.

    A layout load replaces window geometry. A window that owns a default size can restore that size when
    this event arrives. Every load that reaches `QuickLayout.load_file` calls the event, and a load that the
    caller cancels after that call calls it too, because the layout already replaced the geometry.

    The event manager rejects a subscription to an event that no caller registered, and this extension holds
    widgets only, so it has no startup hook that could register the event. This function owns that step, so
    that no subscriber has to know about it. A second registration of the same name does nothing.

    Args:
        callback: Observer that runs after a layout load.

    Returns:
        Subscription whose lifetime controls callback registration.
    """
    event_manager = _get_event_manager_instance()
    event_manager.register_global_custom_event(LAYOUT_LOADED_EVENT_NAME)
    return event_manager.subscribe_global_custom_event(LAYOUT_LOADED_EVENT_NAME, callback)


def load_layout(layout_file: str | None) -> asyncio.Task | None:
    """Load an existing layout after its windows are ready for docking.

    Args:
        layout_file: Path to a quick-layout JSON file, or None when no layout is configured.

    Returns:
        Named task owned by the caller, or None when no path is configured. The caller must retain the task and
        await or cancel it during teardown. File and layout errors are reported through the task.
    """
    if not layout_file:
        return None
    task = asyncio.ensure_future(_load_layout_async(layout_file))
    task.set_name("QuickLayoutLoad")
    return task


async def _load_layout_async(layout_file: str):
    """Load a layout and restore its tab-bar state even if the deferred update is cancelled.

    Args:
        layout_file: Path to the quick-layout JSON file to load.
    """
    with open(layout_file, encoding="utf-8") as f:
        layout_data = json.load(f)

    visible_windows = _find_visible_windows(layout_data)

    initialization_window_states = [
        (window_title, window.visible)
        for window_title in visible_windows
        if (window := ui.Workspace.get_window(window_title)) and not window.visible
    ]

    layout_loaded = False
    try:
        if initialization_window_states:
            for window_title, _ in initialization_window_states:
                ui.Workspace.show_window(window_title, True)
            await omni.kit.app.get_app().next_update_async()

        QuickLayout.load_file(layout_file)
        layout_loaded = True
        post_load_update = asyncio.create_task(omni.kit.app.get_app().next_update_async())
        try:
            await asyncio.shield(post_load_update)
        except asyncio.CancelledError:
            try:
                await _finish_task(post_load_update)
            except RuntimeError as update_error:
                carb.log_error(f"Deferred layout update failed during cancellation: {update_error}")
            raise
    finally:
        if layout_loaded:
            _reapply_tab_bar_settings(layout_data)
            event_manager = _get_event_manager_instance()
            event_manager.register_global_custom_event(LAYOUT_LOADED_EVENT_NAME)
            event_manager.call_global_custom_event(LAYOUT_LOADED_EVENT_NAME)
        else:
            for window_title, was_visible in initialization_window_states:
                ui.Workspace.show_window(window_title, was_visible)


async def _finish_task(task: asyncio.Task[Any]) -> Any:
    """Wait for owned work to settle despite repeated cancellation.

    Args:
        task: Started task that must finish before layout cleanup continues.

    Returns:
        Result produced by the task.
    """
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


def _iter_layout_nodes(layout_data: dict[str, Any] | list[Any]) -> Iterator[dict[str, Any]]:
    """Iterate dictionary nodes in a parsed quick-layout tree.

    Args:
        layout_data: Parsed quick-layout object tree to traverse.

    Yields:
        Dictionary nodes in the layout's existing stack traversal order.
    """
    stack = [layout_data]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            yield node
            if "children" in node:
                stack.extend(node["children"])


def _find_visible_windows(layout_data: dict[str, Any] | list[Any]):
    """Find all windows marked as visible in the layout data.

    Args:
        layout_data: Parsed quick-layout object tree to search.

    Returns:
        Window titles marked visible anywhere in the layout tree.
    """
    visible_windows = []
    for node in _iter_layout_nodes(layout_data):
        if "title" in node and node.get("visible", False):
            visible_windows.append(node["title"])

    return visible_windows


def _reapply_tab_bar_settings(layout_data: dict[str, Any] | list[Any]):
    """Reapply saved tab-bar settings for selected docked windows.

    Args:
        layout_data: Parsed quick-layout object tree containing saved dock settings.
    """
    for node in _iter_layout_nodes(layout_data):
        if (
            "title" in node
            and node.get("selected_in_dock", False)
            and (window := ui.Workspace.get_window(node["title"]))
        ):
            for attr in ["dock_tab_bar_visible", "dock_tab_bar_enabled"]:
                if (value := node.get(attr)) is not None:
                    setattr(window, attr, value)

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

__all__ = ["load_layout"]

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import carb
import omni.kit.app
from omni import ui
from omni.kit.quicklayout import QuickLayout


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

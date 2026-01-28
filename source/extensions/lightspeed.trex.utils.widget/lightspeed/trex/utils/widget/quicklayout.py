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

import asyncio
import json
from typing import Any

import omni.kit.app
from omni import ui
from omni.kit.quicklayout import QuickLayout


def load_layout(layout_file: str):
    """Wrapper around QuickLayout.load_file that ensures windows are ready for docking"""
    asyncio.ensure_future(_load_layout_async(layout_file))


async def _load_layout_async(layout_file: str):
    with open(layout_file, encoding="utf-8") as f:
        layout_data = json.load(f)

    visible_windows = _find_visible_windows(layout_data)

    needs_initialization = [
        window_title
        for window_title in visible_windows
        if (window := ui.Workspace.get_window(window_title)) and not window.visible
    ]

    if needs_initialization:
        for window_title in needs_initialization:
            ui.Workspace.show_window(window_title, True)
        await omni.kit.app.get_app().next_update_async()

    QuickLayout.load_file(layout_file)

    await omni.kit.app.get_app().next_update_async()
    _reapply_tab_bar_settings(layout_data)


def _find_visible_windows(layout_data: dict[str, Any] | list[Any]):
    """Find all windows marked as visible in the layout data"""
    visible_windows = []
    stack = [layout_data]

    while stack:
        node = stack.pop()

        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            if "title" in node and node.get("visible", False):
                visible_windows.append(node["title"])

            if "children" in node:
                stack.extend(node["children"])

    return visible_windows


def _reapply_tab_bar_settings(layout_data: dict[str, Any] | list[Any]):
    """Reapply the tab bar settings for the windows in the layout data"""
    stack = [layout_data]

    while stack:
        node = stack.pop()

        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            if (
                "title" in node
                and node.get("selected_in_dock", False)
                and (window := ui.Workspace.get_window(node["title"]))
            ):
                for attr in ["dock_tab_bar_visible", "dock_tab_bar_enabled"]:
                    if (value := node.get(attr)) is not None:
                        setattr(window, attr, value)

            if "children" in node:
                stack.extend(node["children"])

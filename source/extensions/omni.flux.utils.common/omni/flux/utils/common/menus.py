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

__all__ = ["Menu", "MenuGroup", "MenuItem"]

from enum import Enum


# Menus and Context Menus constants
class Menu(Enum):
    """
    IDs for grouping Context Menus.
    """

    STAGE_MANAGER = "stage_manager"


class MenuGroup(Enum):
    """
    IDs for grouping Menus and Context Menus items.
    """

    MAIN = "MENU"  # Also the base menu for any Omniverse Kit app.
    SELECTED_PRIMS = "MENU:PRIMS_SELECTED"  # To interact with selected prims.


class MenuItem(Enum):
    """
    Names for Menu Items.
    """

    COPY_PRIM_PATH = "Copy Prim Path"
    FOCUS_IN_VIEWPORT = "Focus in Viewport"
    DYNAMIC_SPLITTER = ""
    ASSIGN_CATEGORY = "Assign Render Categories..."  # ... is used to indicate that the menu item opens a modal
    PARTICLE_SYSTEM = "Particle System..."  # ... is used to indicate that the menu item is a submenu
    PARTICLE_SYSTEM_ADD = "Add"
    PARTICLE_SYSTEM_REMOVE = "Remove"
    LOGIC_GRAPH = "Remix Logic"
    LOGIC_GRAPH_ADD = "Create Remix Logic Graph"
    LOGIC_GRAPH_EDIT = "Edit Remix Logic Graph"
    LOGIC_GRAPH_REMOVE = "Remove Remix Logic Graph"

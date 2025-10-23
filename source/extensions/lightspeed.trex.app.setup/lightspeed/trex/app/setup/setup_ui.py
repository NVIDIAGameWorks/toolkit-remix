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

import asyncio
from fnmatch import fnmatch
from pathlib import Path

import carb
import omni.appwindow
import omni.kit
import omni.usd
from omni.flux.utils.widget.resources import get_menubar_ignore_file as _get_menubar_ignore_file
from omni.kit.menu.utils import MenuLayout

_HIDE_MENU = "/exts/lightspeed.trex.app.setup/hide_menu"
_APP_WINDOW_SETTING = "/app/window/enabled"  # setting affected by "--no-window" arg

MenuLayoutItemTypes = MenuLayout.Menu | MenuLayout.SubMenu | MenuLayout.Item


class SetupUI:
    def __init__(self):
        """Setup the main Lightspeed settings"""
        self.__settings = carb.settings.get_settings()

        if self.__settings.get(_HIDE_MENU):
            # Editor Menu API must be used when the app is ready.
            startup_event_stream = omni.kit.app.get_app().get_startup_event_stream()
            self.__sub_app_ready = startup_event_stream.create_subscription_to_pop_by_type(  # noqa PLW0238
                omni.kit.app.EVENT_APP_READY,
                self._hide_menu,
                name="Hide Menubar - App Ready",
            )

    def _hide_menu(self, *args):
        self.__sub_app_ready = None  # noqa PLW0238

        async def deferred_hide_menu():
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()

            menubar_ignore = MenubarIgnore()
            custom_layouts = menubar_ignore.get_menubar_layout()
            omni.kit.menu.utils.add_layout(custom_layouts)

        asyncio.ensure_future(deferred_hide_menu())


class MenubarIgnore:
    """
    Loads a menubar_ignore file and computes menu bar items/submenus visibility based on it.
    """

    def __init__(self):
        ignore_file_path = _get_menubar_ignore_file()
        if not ignore_file_path:
            carb.log_warn("No menubar ignore file found!")
            self.__rules = {"inclusions": set(), "exclusions": set()}
            return
        with open(ignore_file_path, "r", encoding="utf-8") as f:
            content = f.read()
            content = {line.strip() for line in content.split("\n") if line.strip() and not line.startswith("#")}

        # Add a "*" to dirs to be compatible with fnmatch's glob filter style.
        inclusions = {line + ("*" if line.endswith("/") else "") for line in content if line.startswith("!")}
        exclusions = {line + ("*" if line.endswith("/") else "") for line in content.difference(inclusions)}
        self.__rules = {
            "inclusions": {rule.replace("!", "") for rule in inclusions},
            "exclusions": exclusions,
        }

    def is_ignored(self, path: str | Path) -> bool:
        """Given a menu bar item/submenu path, returns whether it is ignored by the menubar_ignore file or not"""
        menu_path: str = str(path)
        excluded = any(fnmatch(menu_path, pattern) for pattern in self.__rules["exclusions"])
        included = any(fnmatch(menu_path, pattern) for pattern in self.__rules["inclusions"])
        return excluded and not included

    def get_menubar_layout(self) -> list[MenuLayout.Menu]:
        """
        Computes the omni.kit.menu.utils.MenuLayout list to be used with omni.kit.menu.utils.add_layout

        Example format:
        [
            MenuLayout.Menu("Window", [
                MenuLayout.Item("Item 1", remove=True),
                MenuLayout.Item("Item 2", remove=True),
            ])
        ]
        """
        all_menus = omni.kit.menu.utils.get_merged_menus()
        top_level_menus = {menu_name: menu for menu_name, menu in all_menus.items() if not menu.get("sub_menu")}

        def traverse_menus(target_menu, current_menu_path: str):
            all_items = {item for item in target_menu.get("items") if item.name}
            sub_menus = [item for item in all_items if item.sub_menu]
            final_items = all_items.difference(sub_menus)
            layouts = []
            has_visible_children = False
            for item in final_items:
                is_ignored = self.is_ignored(f"{current_menu_path}/{item.name}")
                has_visible_children |= not is_ignored
                if is_ignored:
                    layouts.append(MenuLayout.Item(item.name, remove=True))

            for menu in sub_menus:
                visible, sub_layouts = traverse_menus(all_menus[menu.sub_menu], f"{current_menu_path}/{menu.name}")
                has_visible_children |= visible
                if sub_layouts:
                    menu_layout = MenuLayout.SubMenu(menu.name, sub_layouts, remove=not visible)
                    layouts.append(menu_layout)

            return has_visible_children, layouts

        custom_layouts = []
        for menu_name, menu in top_level_menus.items():
            visible, menu_layouts = traverse_menus(menu, menu_name)
            if menu_layouts:
                menu_layout = MenuLayout.Menu(menu_name, menu_layouts, remove=not visible)
                custom_layouts.append(menu_layout)
            else:
                custom_layouts.append(MenuLayout.Menu(menu_name, remove=False))

        return custom_layouts

    def print_menus(self, target: MenuLayoutItemTypes | list[MenuLayoutItemTypes], path: str = "") -> None:
        """
        Util debug function to print out the menu layouts in plain format.

        Arguments:
            target: Just pass the return of get_menubar_layout, as it is actually used for recursive search.
            path: Omit that, also used for recursive search.
        """
        if isinstance(target, list):
            for menu in target:
                self.print_menus(menu, path)
        elif isinstance(target, (MenuLayout.Menu, MenuLayout.SubMenu)):
            print(f"{path}/{target.name}/")
            for item in target.items:
                self.print_menus(item, f"{path}/{target.name}")
        elif isinstance(target, MenuLayout.Item):
            print(f"{path}/{target.name}")

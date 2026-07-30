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

from typing import Any

import omni.ui as ui
from omni.kit import ui_test


async def wait_for_menu_items(menu: ui.Menu | None, labels: list[str]) -> list[ui.MenuItem]:
    for _ in range(100):
        if menu and menu.shown:
            menu_items = {
                child.text: child
                for child in ui.Inspector.get_children(menu)
                if isinstance(child, ui.MenuItem) and child.text in labels
            }
            if all(label in menu_items for label in labels):
                items = [menu_items[label] for label in labels]
                if all(item.computed_content_width > 0 and item.computed_content_height > 0 for item in items):
                    return items
        await ui_test.wait_n_updates(1)
    raise AssertionError(f"Menu items were not visible: {labels}")


def assert_menu_items_render_top_to_bottom(test_case: Any, items: list[ui.MenuItem]):
    for top_item, bottom_item in zip(items, items[1:]):
        test_case.assertGreater(bottom_item.screen_position_y, top_item.screen_position_y)
        test_case.assertLess(abs(bottom_item.screen_position_x - top_item.screen_position_x), 1)

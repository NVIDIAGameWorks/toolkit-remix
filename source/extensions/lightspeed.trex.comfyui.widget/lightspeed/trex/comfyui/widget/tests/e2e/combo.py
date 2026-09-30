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

from omni.kit import ui_test
from omni.kit.ui_test import Vec2, WidgetRef

__all__ = ("combo_labels", "select_combo_item")


def combo_labels(combo: WidgetRef) -> list[str]:
    """Return the option labels of one rendered ``ui.ComboBox``.

    Args:
        combo: Reference to the rendered combo box.

    Returns:
        Option labels in display order.
    """
    model = combo.widget.model
    return [model.get_item_value_model(item).as_string for item in model.get_item_children()]


async def select_combo_item(combo: WidgetRef, label: str) -> None:
    """Open one rendered ``ui.ComboBox`` and click the named option in its popup.

    The popup is an ImGui popup, so ``ui_test.find`` cannot locate its rows. ImGui draws the popup directly below
    the control and gives each row the height of the control.

    Args:
        combo: Reference to the rendered combo box.
        label: Display text of the option to select.
    """
    index = combo_labels(combo).index(label)
    await combo.click()
    await ui_test.human_delay()
    row_height = combo.size.y
    option = Vec2(combo.center.x, combo.position.y + row_height * (index + 1.5))
    await ui_test.emulate_mouse_move_and_click(option)
    await ui_test.human_delay()

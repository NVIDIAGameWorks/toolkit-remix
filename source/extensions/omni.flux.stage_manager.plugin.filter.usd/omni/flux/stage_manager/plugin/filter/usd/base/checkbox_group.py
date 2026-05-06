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

import abc

from omni import ui

from .usd_base import StageManagerUSDFilterPlugin

# Shared layout constants used by all checkbox-group filter headers
CHECKBOX_GROUP_SPACING_ROW: int = 8
CHECKBOX_GROUP_SPACING_LIST: int = 4


def get_aligned_checkbox_row_width(label_width: int) -> int:
    return label_width * 2 + CHECKBOX_GROUP_SPACING_ROW


def build_aligned_checkbox_row(label: str, label_width: int, identifier: str) -> ui.CheckBox:
    with ui.HStack(
        width=ui.Pixel(get_aligned_checkbox_row_width(label_width)),
        height=0,
        spacing=ui.Pixel(CHECKBOX_GROUP_SPACING_ROW),
    ):
        with ui.HStack(width=ui.Fraction(1)):
            ui.Spacer(width=0)
            ui.Label(
                label,
                name="FilterCheckboxLabel",
                width=ui.Pixel(label_width),
                alignment=ui.Alignment.RIGHT_CENTER,
                elided_text=True,
            )
        with ui.HStack(width=ui.Fraction(1)):
            checkbox = ui.CheckBox(identifier=identifier)
            ui.Spacer(width=0)
    return checkbox


class CheckboxGroupFilterPlugin(StageManagerUSDFilterPlugin, abc.ABC):
    """Base for filter plugins that display a group of OR-logic checkboxes.

    Subclasses implement ``_set_all_selected`` and optionally override
    ``can_set_all_selected`` so category-level bulk actions can update them.
    """

    @abc.abstractmethod
    def _set_all_selected(self, enabled: bool) -> None:
        """Select or deselect all items in this filter group."""

    def can_set_all_selected(self, enabled: bool) -> bool:
        """Whether selecting or deselecting all items would change this filter."""
        return True

    def set_all_selected(self, enabled: bool) -> None:
        """Public entry point — calls ``_set_all_selected``."""
        self._set_all_selected(enabled)

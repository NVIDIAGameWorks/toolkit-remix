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

__all__ = ("PrimListDelegate",)

from collections.abc import Callable

import omni.ui as ui

_ROW_HEIGHT = 24
_SPACING_MD = 8


class PrimListDelegate(ui.AbstractItemDelegate):
    """
    Delegate for rendering prim items in the TreeView.

    Uses TreeView's built-in hover and selection styling for full-row highlighting.
    """

    ROW_HEIGHT = _ROW_HEIGHT

    def __init__(
        self,
        row_build_fn: Callable[[str, str, int], None] | None = None,
    ):
        """
        Initialize the delegate.

        Args:
            row_build_fn: Optional custom row builder function. Signature:
                          (prim_path: str, prim_type: str, row_height: int) -> None
                          If not provided, a default row layout is used.
        """
        super().__init__()
        self._row_build_fn = row_build_fn

    def build_branch(self, model, item, column_id, level, expanded):
        pass

    def build_widget(self, model, item, column_id, level, expanded):
        if item is None:
            return

        if self._row_build_fn:
            # Use custom row builder
            self._row_build_fn(item.prim_path, item.prim_type, self.ROW_HEIGHT)
        else:
            # Default row layout - TreeView handles hover/selection styling
            with ui.HStack(height=ui.Pixel(self.ROW_HEIGHT)):
                ui.Spacer(width=ui.Pixel(_SPACING_MD))
                ui.Label(
                    item.prim_path,
                    name="StagePrimPickerItem",
                    alignment=ui.Alignment.LEFT_CENTER,
                    tooltip=item.tooltip,
                )
                ui.Spacer(width=ui.Pixel(_SPACING_MD))

    def build_header(self, column_id):
        pass

    def destroy(self):
        self._row_build_fn = None

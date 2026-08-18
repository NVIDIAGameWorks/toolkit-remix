"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from omni import ui

from ..constants import ROW_HEIGHT
from .delegate import DetailValueDelegate
from .item import DetailValueItem
from .model import DetailValueModel

__all__ = ("DetailValueTree",)


class DetailValueTree(ui.TreeView):
    """Own a compact native typed-value tree and its MVC components."""

    def __init__(
        self,
        values: Sequence[tuple[str, str, Any]],
        identifier: str,
        key_width: ui.Length,
    ) -> None:
        """Build a responsive two-column tree that begins fully expanded.

        Args:
            values: Port name, declared type name, and persisted value tuples.
            identifier: Stable E2E identifier for the tree and its cells.
            key_width: Responsive width of the key column.
        """
        self._detail_model = DetailValueModel(values)
        self._detail_delegate = DetailValueDelegate(identifier, self._set_item_expanded)
        super().__init__(
            self._detail_model,
            delegate=self._detail_delegate,
            root_visible=False,
            header_visible=False,
            columns_resizable=False,
            column_widths=[key_width, ui.Fraction(1)],
            row_height=ROW_HEIGHT,
            expand_on_branch_click=False,
            identifier=identifier,
        )
        self.set_expanded(None, True, True)
        self._sync_height()

    def _set_item_expanded(self, item: DetailValueItem, expanded: bool) -> None:
        """Apply one expansion change and keep the intrinsic tree height exact.

        Args:
            item: Container item whose children change visibility.
            expanded: Requested expansion state.
        """
        self.set_expanded(item, expanded, False)
        self._sync_height()

    def _sync_height(self) -> None:
        """Match the widget height to the currently visible native rows."""
        row_count = self._detail_model.get_visible_item_count(self.is_expanded)
        self.height = ui.Pixel(row_count * ROW_HEIGHT.value)

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

from omni import ui

__all__ = ("DetailValueItem",)


class DetailValueItem(ui.AbstractItem):
    """Represent one typed value as a compact key path, display value, declared type, and optional children."""

    def __init__(
        self,
        key_parts: Sequence[str],
        value: str,
        children: Sequence[DetailValueItem] = (),
        *,
        declared_type: str | None = None,
    ) -> None:
        """Initialize one immutable detail row.

        Args:
            key_parts: Readable keys represented by this compact tree row.
            value: Readable scalar or declared type.
            children: Nested rows revealed when this item is expanded.
            declared_type: Exact type declared by the top-level job port, or None for nested fields.
        """
        super().__init__()
        self.key_parts = tuple(key_parts)
        self.key_model = ui.SimpleStringModel(" > ".join(self.key_parts))
        self.value_model = ui.SimpleStringModel(value)
        self.value_tooltip = f"Declared type: {declared_type}\nValue: {value}" if declared_type else value
        self.children = tuple(children)

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

from collections.abc import Iterable
from typing import Protocol


class PropertyGroupExpansionWidget(Protocol):
    def expand_all_groups(self) -> None: ...

    def collapse_all_groups(self) -> None: ...


class PropertyGroupExpansionMixin:
    _property_widget: PropertyGroupExpansionWidget | None = None

    def _iter_property_group_widgets(self) -> Iterable[PropertyGroupExpansionWidget | None]:
        if self._property_widget is None:
            return
        yield self._property_widget

    def expand_all_groups(self) -> None:
        for widget in self._iter_property_group_widgets():
            if widget is not None:
                widget.expand_all_groups()

    def collapse_all_groups(self) -> None:
        for widget in self._iter_property_group_widgets():
            if widget is not None:
                widget.collapse_all_groups()

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

from typing import TYPE_CHECKING, Iterable

from omni import ui

from .base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin

if TYPE_CHECKING:
    from pxr import Usd


class SearchFilterPlugin(_StageManagerUSDFilterPlugin):
    # TODO StageManager: Build proper plugin

    display_name: str = "Search"
    tooltip: str = "Search through the list of prims"

    def filter_items(self, items: Iterable["Usd.Prim"]) -> list["Usd.Prim"]:
        return list(items)

    def build_ui(self):  # noqa PLW0221
        with ui.HStack(spacing=ui.Pixel(8)):
            ui.Label(self.display_name, width=0)
            ui.StringField(width=ui.Pixel(300), height=ui.Pixel(24))

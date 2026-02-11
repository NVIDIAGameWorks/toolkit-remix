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

import re

from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, PrivateAttr

from .base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin


class SearchFilterPlugin(_StageManagerUSDFilterPlugin):
    # TODO StageManager: Build proper plugin

    display_name: str = Field(default="Search", exclude=True)
    tooltip: str = Field(default="Search through the list of prims", exclude=True)
    search_term: str = Field(default="", exclude=False)

    _end_edit_sub: _EventSubscription | None = PrivateAttr(default=None)

    def filter_predicate(self, item: _StageManagerItem) -> bool:
        if not self.search_term:
            return True
        name = item.data.GetPath().name

        # Regex search with case-insensitive flag
        try:
            match = re.search(self.search_term, name, re.IGNORECASE)
        except re.error:
            # If the search term is not a valid regex, set the match to None
            match = None
        return match is not None

    def _on_edit(self, model):
        self.search_term = model.get_value_as_string()
        self._filter_items_changed()

    def build_ui(self):
        with ui.HStack(height=0):
            ui.Label("Search:", width=ui.Pixel(56))
            search_field = ui.StringField(
                width=ui.Pixel(160),
                height=ui.Pixel(24),
                identifier="search_field",
                tooltip="Search using regex. Special characters like ., *, +, etc. will be treated as regex characters",
            )
            self._end_edit_sub = search_field.model.subscribe_end_edit_fn(self._on_edit)

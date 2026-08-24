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
from functools import partial

from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, PrivateAttr

from .base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin

# Path-like search terms are handled literally against prim paths before regex detection. For non-path terms,
# backslash remains a regex metacharacter so explicit regex escapes like \d work as expected.
_REGEX_META_CHARS = frozenset(r"\.^$*+?{}[]|()")


class SearchFilterPlugin(_StageManagerUSDFilterPlugin):
    # TODO StageManager: Build proper plugin

    display_name: str = Field(default="Search", exclude=True)
    tooltip: str = Field(
        default=(
            "Search through the list of prims. Terms with / match full prim paths. "
            "Supports Regex (I.e: Special characters like ., *, +, etc.)"
        ),
        exclude=True,
    )
    search_term: str = Field(default="", exclude=False)

    _end_edit_sub: _EventSubscription | None = PrivateAttr(default=None)

    def model_post_init(self, _context: object) -> None:
        """Initialize filter activity when the term is supplied from schema data."""
        super().model_post_init(_context)
        self.filter_active = bool(self.search_term)

    def filter_predicate(
        self,
        item: _StageManagerItem,
        search_state: tuple[bool, str, re.Pattern | None, bool] | None = None,
    ) -> bool:
        """Return whether the item matches direct or prepared search state.

        Args:
            item: Stage Manager item to evaluate.
            search_state: Optional refresh-local literal or compiled-regex state.

        Returns:
            Whether the item matches the active search term.
        """
        if search_state is None:
            search_state = self._get_search_state(self.search_term)

        path_mode, literal_search_term, compiled_pattern, invalid_regex = search_state
        if invalid_regex:
            return False
        if not literal_search_term and compiled_pattern is None:
            return True
        if path_mode:
            return literal_search_term in str(item.data.GetPath()).casefold()

        name = item.data.GetName()
        if literal_search_term:
            if literal_search_term in name.casefold():
                return True
        elif compiled_pattern is not None and compiled_pattern.search(name):
            return True

        nickname_attr = item.data.GetAttribute("nickname")
        if not nickname_attr.IsValid() or not nickname_attr.HasValue():
            return False

        nickname = str(nickname_attr.Get())
        if literal_search_term:
            return literal_search_term in nickname.casefold()
        return compiled_pattern is not None and bool(compiled_pattern.search(nickname))

    def build_filter_predicate(self):
        """Build a search predicate with matching state computed once for the refresh."""
        return partial(self.filter_predicate, search_state=self._get_search_state(self.search_term))

    @staticmethod
    def _get_search_state(search_term: str) -> tuple[bool, str, re.Pattern | None, bool]:
        """Return immutable matching state for a search term.

        Args:
            search_term: Literal or regular-expression term to prepare.

        Returns:
            Path mode, literal term, compiled pattern, and invalid-regex state.
        """
        path_mode = "/" in search_term
        if path_mode or not any(char in _REGEX_META_CHARS for char in search_term):
            return path_mode, search_term.casefold(), None, False
        try:
            return path_mode, "", re.compile(search_term, re.IGNORECASE), False
        except re.error:
            return path_mode, "", None, True

    def _on_edit(self, model):
        """Update the search term from the text field and refresh filtering."""
        self.search_term = model.get_value_as_string()
        self.filter_active = bool(self.search_term)
        self._filter_items_changed()

    def build_ui(self):
        with ui.HStack(height=ui.Pixel(24)):
            ui.Label("Search:", width=ui.Pixel(56))
            search_field = ui.StringField(
                width=ui.Pixel(160),
                height=ui.Pixel(24),
                identifier="search_field",
            )
            self._end_edit_sub = search_field.model.subscribe_end_edit_fn(self._on_edit)

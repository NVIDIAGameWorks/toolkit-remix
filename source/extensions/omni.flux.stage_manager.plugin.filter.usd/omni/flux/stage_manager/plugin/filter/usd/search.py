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

# Path-like search terms are handled literally against prim paths before regex detection. For non-path terms,
# backslash remains a regex metacharacter so explicit regex escapes like \d work as expected.
_REGEX_META_CHARS = frozenset(r"\.^$*+?{}[]|()")


def _is_path_search_term(search_term: str) -> bool:
    """Return whether the term should be matched against full prim paths."""
    return "/" in search_term


def _get_search_state(search_term: str) -> tuple[bool, str, re.Pattern | None, bool]:
    """Return immutable matching state for a search term."""
    path_mode = _is_path_search_term(search_term)
    if path_mode or not any(char in _REGEX_META_CHARS for char in search_term):
        return path_mode, search_term.casefold(), None, False
    try:
        return path_mode, "", re.compile(search_term, re.IGNORECASE), False
    except re.error:
        return path_mode, "", None, True


def _matches_search_item(
    item: _StageManagerItem,
    path_mode: bool,
    literal_search_term: str,
    compiled_pattern: re.Pattern | None,
    invalid_regex: bool,
) -> bool:
    """Return whether an item matches immutable search state."""
    if invalid_regex:
        return False

    prim_path = item.data.GetPath()
    if path_mode:
        strings_to_search = [str(prim_path)]
    else:
        strings_to_search = [prim_path.name]
        nickname_attr = item.data.GetAttribute("nickname")
        if nickname_attr.IsValid() and nickname_attr.HasValue():
            strings_to_search.append(str(nickname_attr.Get()))

    if literal_search_term:
        return any(literal_search_term in value.casefold() for value in strings_to_search)
    if compiled_pattern is None:
        return False
    return any(compiled_pattern.search(value) for value in strings_to_search)


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
    _compiled_pattern: re.Pattern | None = PrivateAttr(default=None)
    _literal_search_term: str = PrivateAttr(default="")
    _invalid_regex: bool = PrivateAttr(default=False)
    _prepared_search_term: str = PrivateAttr(default="")

    def model_post_init(self, _context: object) -> None:
        """Initialize precomputed search state when the term is supplied from schema data."""
        super().model_post_init(_context)
        self._prepare_search_term(self.search_term)

    def filter_predicate(self, item: _StageManagerItem) -> bool:
        """Return whether the item matches the active search term."""
        # Re-prepare before the active check if direct predicate callers set search_term without going through _on_edit.
        if self.search_term != self._prepared_search_term:
            self._prepare_search_term(self.search_term)
        # Self-contained: filter_items_by_category pre-checks filter_active, but async filter_items and direct callers do not.
        if not self.filter_active:
            return True
        return _matches_search_item(
            item,
            _is_path_search_term(self.search_term),
            self._literal_search_term,
            self._compiled_pattern,
            self._invalid_regex,
        )

    def prepare_filter_predicate(self):
        """Capture immutable search state for worker filtering."""
        search_term = self.search_term
        search_state = _get_search_state(search_term)
        return lambda item: not search_term or _matches_search_item(item, *search_state)

    def _on_edit(self, model):
        """Update the search term from the text field and refresh filtering."""
        self.search_term = model.get_value_as_string()
        self._prepare_search_term(self.search_term)
        self._filter_items_changed()

    def _prepare_search_term(self, search_term: str):
        """Precompute literal or regex matching state for the current search term."""
        _, self._literal_search_term, self._compiled_pattern, self._invalid_regex = _get_search_state(search_term)
        self._prepared_search_term = search_term
        self.filter_active = bool(search_term)

    def build_ui(self):
        with ui.HStack(height=ui.Pixel(24)):
            ui.Label("Search:", width=ui.Pixel(56))
            search_field = ui.StringField(
                width=ui.Pixel(160),
                height=ui.Pixel(24),
                identifier="search_field",
            )
            self._end_edit_sub = search_field.model.subscribe_end_edit_fn(self._on_edit)

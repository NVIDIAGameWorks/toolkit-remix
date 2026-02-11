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

from __future__ import annotations

__all__ = ("PrimCollection",)

import fnmatch
from collections.abc import Callable

import omni.usd
from pxr import Usd


class PrimCollection:
    """Handles collecting and filtering prims from a USD stage with pagination support."""

    DEFAULT_INITIAL_ITEMS = 20
    DEFAULT_PAGE_SIZE = 20
    DEFAULT_MAX_ITEMS = 10000

    def __init__(
        self,
        context_name: str = "",
        prim_filter: Callable[[Usd.Prim], bool] | None = None,
        prim_types: list[str] | None = None,
        path_patterns: list[str] | None = None,
        initial_items: int = DEFAULT_INITIAL_ITEMS,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_items: int = DEFAULT_MAX_ITEMS,
    ):
        """
        Initialize the PrimCollection.

        Args:
            context_name: USD context name. Empty string uses default context.
            prim_filter: Optional custom filter function. Return True for prims to include.
            prim_types: Optional list of prim type names to include (e.g., ["Mesh", "Xform"]).
                       If None, all types are included.
            path_patterns: Optional list of glob patterns for prim paths (e.g., ["/World/Geometry/*", "**/Light*"]).
                          Patterns are OR'd - prim matches if ANY pattern matches. Optimizes traversal.
            initial_items: Initial number of prims to load (default: 20).
            page_size: Number of prims to load per "show more" action (default: 20).
            max_items: Absolute maximum prims to prevent memory issues (default: 10000).
        """
        self._context_name = context_name
        self._prim_filter = prim_filter
        self._prim_types = prim_types
        self._path_patterns = path_patterns
        self._initial_items = initial_items
        self._page_size = page_size
        self._max_items = max_items
        self._current_limit = initial_items

    def get_prim_paths(self, search_filter: str = "") -> tuple[list[tuple[str, str]], bool]:
        """
        Get prim paths from the stage up to current limit.

        Args:
            search_filter: Optional text to filter prim paths (case-insensitive).

        Returns:
            Tuple of (prim_items, has_more) where prim_items is list of (path, type) tuples.
            has_more is True only if there are actually more items beyond the current limit.
        """
        prim_items = []
        search_lower = search_filter.lower() if search_filter else ""
        has_more = False

        for prim_path, prim_type in self._generate_prim_paths():
            # Apply search filter
            if not search_lower or search_lower in prim_path.lower():
                if len(prim_items) >= self._current_limit:
                    # Found an item beyond the limit - there's definitely more
                    has_more = True
                    break
                prim_items.append((prim_path, prim_type))

        return prim_items, has_more

    def load_more(self) -> int:
        """
        Increase the current limit to load more prims.

        Returns:
            The new current limit.
        """
        self._current_limit = min(self._current_limit + self._page_size, self._max_items)
        return self._current_limit

    def reset_limit(self):
        """Reset the current limit back to initial_items."""
        self._current_limit = self._initial_items

    def get_prim_type(self, prim_path: str) -> str:
        """
        Get the type name of a prim by path.

        Args:
            prim_path: USD prim path

        Returns:
            Prim type name or empty string if not found
        """
        context = omni.usd.get_context(self._context_name)
        stage = context.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return ""

        return prim.GetTypeName()

    def _matches_any_pattern(self, prim_path: str) -> bool:
        """
        Check if prim path matches any of the configured glob patterns.

        Supports: *, **, ?
        Patterns are OR'd - returns True if ANY pattern matches.

        Args:
            prim_path: The prim path to check.

        Returns:
            True if path matches any pattern (OR logic), or if no patterns configured.
        """
        if self._path_patterns is None:
            return True

        return any(fnmatch.fnmatch(prim_path, pattern) for pattern in self._path_patterns)

    def _should_traverse_children(self, prim_path: str) -> bool:
        """Check if children could potentially match any pattern."""
        if self._path_patterns is None:
            return True

        for pattern in self._path_patterns:
            if "**" in pattern:
                return True

            if "*" not in pattern:
                continue

            pattern_parts = pattern.split("/")
            path_parts = prim_path.split("/")

            if len(path_parts) >= len(pattern_parts):
                continue

            for path_part, pattern_part in zip(path_parts, pattern_parts):
                if "*" not in pattern_part and path_part != pattern_part:
                    break
            else:
                return True

        return False

    def _generate_prim_paths(self):
        """Generator that yields (prim_path, prim_type) tuples from the stage."""
        context = omni.usd.get_context(self._context_name)
        stage = context.get_stage()

        if not stage:
            return

        def traverse_prims(prim):
            prim_path = str(prim.GetPath())
            prim_type = prim.GetTypeName()

            # Check path pattern first (optimization - can skip entire subtrees)
            path_matches = self._matches_any_pattern(prim_path)
            should_traverse = self._should_traverse_children(prim_path)

            if not path_matches and not should_traverse:
                return

            # Yield if path matches and passes all filters
            passes_type_filter = self._prim_types is None or prim_type in self._prim_types
            passes_custom_filter = self._prim_filter is None or self._prim_filter(prim)

            if path_matches and passes_type_filter and passes_custom_filter:
                yield (prim_path, prim_type)

            # Always traverse children if path patterns allow
            # (even if current prim matched, children might also match with ** patterns)
            if should_traverse or path_matches:
                for child in prim.GetChildren():
                    yield from traverse_prims(child)

        for root_prim in stage.GetPseudoRoot().GetChildren():
            yield from traverse_prims(root_prim)

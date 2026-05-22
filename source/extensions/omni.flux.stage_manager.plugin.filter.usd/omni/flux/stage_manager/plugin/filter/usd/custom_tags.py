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

import contextlib

from omni import ui
from omni.flux.custom_tags.core import CustomTagsCore as _CustomTagsCore
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.factory.plugins.filter_plugin import FilterCategory as _FilterCategory
from pydantic import Field, PrivateAttr
from pxr import Sdf

from .base import CheckboxGroupFilterPlugin as _CheckboxGroupFilterPlugin
from .base.checkbox_group import CHECKBOX_GROUP_SPACING_LIST as _SPACING_LIST
from .base.checkbox_group import build_aligned_checkbox_row as _build_aligned_checkbox_row
from .base.checkbox_group import get_aligned_checkbox_row_width as _get_aligned_checkbox_row_width

_DISPLAY_NAME = "Custom Tags Filter"
_TOOLTIP_PLUGIN = (
    "Select one or more categories to filter the tree. When no categories are selected, all prims are shown."
)
_LABEL_NO_CATEGORIES = "No categories"
_LABEL_UNTAGGED = "Untagged"

_SPACING_OUTER = 2
_ROW_HEIGHT = 18
_TAG_CHECKBOX_IDENTIFIER_PREFIX = "filter_checkbox_custom_tags_"
_CHECKBOX_ID_UNTAGGED = f"{_TAG_CHECKBOX_IDENTIFIER_PREFIX}untagged"
_IDENTIFIER_FALLBACK_ROOT = "root"

_CACHE_INVALIDATING_FIELDS: frozenset[str] = frozenset({"selected_tags", "include_untagged"})


def _get_tag_checkbox_identifier(tag_path_str: str) -> str:
    safe_tag_path = "".join(c if c.isalnum() else "_" for c in tag_path_str).strip("_")
    return f"{_TAG_CHECKBOX_IDENTIFIER_PREFIX}{safe_tag_path or _IDENTIFIER_FALLBACK_ROOT}"


class CustomTagsFilterPlugin(_CheckboxGroupFilterPlugin):
    display_name: str = Field(default=_DISPLAY_NAME, exclude=True)
    tooltip: str = Field(default=_TOOLTIP_PLUGIN, exclude=True)
    filter_category: _FilterCategory = Field(default=_FilterCategory.TAGS, exclude=True)

    # default=[] rather than default_factory=list so on_reset_all can read field_info.default;
    # Pydantic v2 copies the default per instance, and on_reset_all copies it again before setattr.
    selected_tags: list[str] = Field(default=[])
    include_untagged: bool = Field(default=False)

    _LABEL_WIDTH: int = PrivateAttr(default=140)

    _core: _CustomTagsCore | None = PrivateAttr(default=None)
    _tag_subs: list = PrivateAttr(default_factory=list)
    _all_tag_paths: list | None = PrivateAttr(default=None)
    _prim_counts: dict | None = PrivateAttr(default=None)
    _selected_tag_paths: list = PrivateAttr(default_factory=list)
    _checkboxes_frame: ui.Frame | None = PrivateAttr(default=None)
    _rebuilding: bool = PrivateAttr(default=False)
    _filter_enabled: bool = PrivateAttr(default=False)
    _model_ready: bool = PrivateAttr(default=False)

    def model_post_init(self, _context: object) -> None:
        self._selected_tag_paths = [Sdf.Path(t) for t in self.selected_tags]
        self._filter_enabled = bool(self.selected_tags) or self.include_untagged
        self.filter_active = self._filter_enabled
        self._model_ready = True

    def set_context_name(self, name: str) -> None:
        if self._core is not None:
            self._core.destroy()
        self._core = _CustomTagsCore(context_name=name)
        self._all_tag_paths = None
        self._prim_counts = None
        super().set_context_name(name)

    def __setattr__(self, name: str, value) -> None:
        super().__setattr__(name, value)
        if name == "_filter_enabled":
            self.filter_active = bool(value)
            return
        if name not in _CACHE_INVALIDATING_FIELDS:
            return
        # Skip side effects during Pydantic __init__: fields are set one by one so
        # sibling fields (e.g. include_untagged) may not be set yet, causing premature
        # enabled=False. model_post_init sets _model_ready once all fields are ready.
        if not getattr(self, "_model_ready", False):
            return
        if name == "selected_tags":
            self._selected_tag_paths = [Sdf.Path(t) for t in value]
        self._all_tag_paths = None
        self._prim_counts = None
        self._filter_enabled = bool(self.selected_tags) or self.include_untagged
        self.enabled = self._filter_enabled

    def filter_predicate(self, item: _StageManagerItem) -> bool:
        if not self._filter_enabled:
            return True
        if not self.selected_tags and not self.include_untagged:
            return True
        if self._core is None:
            return True
        prim = item.data
        selected_paths = self._selected_tag_paths
        if selected_paths and self._core.prim_has_any_tag(prim, selected_paths):
            return True
        return self.include_untagged and not self._core.prim_has_any_tag(
            prim, self._get_all_tag_paths(refresh_stage=self._all_tag_paths is None)
        )

    def _filter_items_changed(self):
        self._all_tag_paths = None
        self._prim_counts = None
        super()._filter_items_changed()

    def refresh_filter_items(self):
        self._all_tag_paths = None
        self._prim_counts = None
        super().refresh_filter_items()

    def clear_subscriptions(self):
        self._tag_subs.clear()

    def _get_prim_count(self, tag_path) -> int:
        if self._core is None:
            return 0
        tag_str = str(tag_path)
        if self._prim_counts is None:
            self._prim_counts = {}
        if tag_str not in self._prim_counts:
            self._prim_counts[tag_str] = len(self._core.get_tag_prims(tag_path) or [])
        return self._prim_counts[tag_str]

    def _get_all_tag_paths(self, refresh_stage: bool = False) -> list[Sdf.Path]:
        if self._core is None:
            return []
        if refresh_stage:
            self._core.refresh_stage()
            self._all_tag_paths = None
        if self._all_tag_paths is None:
            self._all_tag_paths = [tp for tp in (self._core.get_all_tags() or []) if tp and not tp.isEmpty]
        return self._all_tag_paths

    def _get_checkboxes_height(self, all_tags: list[Sdf.Path] | None = None) -> int:
        all_tags = self._get_all_tag_paths() if all_tags is None else all_tags
        n_rows = 1 + max(1, len(all_tags))
        return n_rows * _ROW_HEIGHT + max(0, n_rows - 1) * _SPACING_LIST

    def _get_checkboxes_width(self) -> int:
        return _get_aligned_checkbox_row_width(self._LABEL_WIDTH)

    def build_ui(self):
        self._tag_subs.clear()
        self._prim_counts = None
        all_tags = self._get_all_tag_paths(refresh_stage=True)

        with ui.VStack(spacing=ui.Pixel(_SPACING_OUTER), tooltip=self.tooltip):
            self._checkboxes_frame = ui.Frame(
                width=ui.Pixel(self._get_checkboxes_width()),
                height=ui.Pixel(self._get_checkboxes_height(all_tags)),
                build_fn=self._build_checkboxes,
            )

    def _build_checkboxes(self):
        self._tag_subs.clear()
        all_tags = self._get_all_tag_paths()

        self._rebuilding = True
        try:
            with ui.VStack(
                width=ui.Pixel(self._get_checkboxes_width()),
                height=ui.Pixel(self._get_checkboxes_height(all_tags)),
                spacing=ui.Pixel(_SPACING_LIST),
            ):
                cb = _build_aligned_checkbox_row(_LABEL_UNTAGGED, self._LABEL_WIDTH, _CHECKBOX_ID_UNTAGGED)
                cb.model.set_value(self.include_untagged)
                self._tag_subs.append(
                    cb.model.subscribe_value_changed_fn(lambda m: self._on_untagged_toggled(m.as_bool))
                )

                if not all_tags:
                    with ui.HStack(height=0):
                        ui.Spacer(width=0)
                        ui.Label(_LABEL_NO_CATEGORIES)

                for tag_path in all_tags:
                    tag_name = _CustomTagsCore.get_tag_name(tag_path)
                    tag_path_str = str(tag_path)
                    prim_count = self._get_prim_count(tag_path)
                    label = f"{tag_name or tag_path_str} ({prim_count})"
                    cb = _build_aligned_checkbox_row(
                        label, self._LABEL_WIDTH, _get_tag_checkbox_identifier(tag_path_str)
                    )
                    cb.model.set_value(tag_path_str in self.selected_tags)
                    self._tag_subs.append(
                        cb.model.subscribe_value_changed_fn(
                            lambda m, tp=tag_path_str: self._on_tag_toggled(tp, m.as_bool)
                        )
                    )
        finally:
            self._rebuilding = False

    def _set_all_selected(self, enabled: bool) -> None:
        if enabled:
            self.selected_tags = [str(tp) for tp in self._get_all_tag_paths()]
            self.include_untagged = True
            self._filter_enabled = True
            self.enabled = True
        else:
            self.selected_tags = []
            self.include_untagged = False

        if self._checkboxes_frame is not None:
            self._checkboxes_frame.rebuild()
        self._filter_items_changed()

    def can_set_all_selected(self, enabled: bool) -> bool:
        if enabled:
            all_tags = {str(tp) for tp in self._get_all_tag_paths()}
            return not self.include_untagged or any(tag not in self.selected_tags for tag in all_tags)
        return self.include_untagged or bool(self.selected_tags)

    def _on_tag_toggled(self, tag_path_str: str, checked: bool):
        if self._rebuilding:
            return
        changed = False
        if checked and tag_path_str not in self.selected_tags:
            self.selected_tags = [*self.selected_tags, tag_path_str]
            changed = True
        elif not checked and tag_path_str in self.selected_tags:
            self.selected_tags = [t for t in self.selected_tags if t != tag_path_str]
            changed = True
        if changed:
            self._filter_enabled = bool(self.selected_tags) or self.include_untagged
            self.enabled = self._filter_enabled

            self._filter_items_changed()

    def _on_untagged_toggled(self, checked: bool):
        if self._rebuilding or self.include_untagged == checked:
            return
        self.include_untagged = checked
        self._filter_enabled = bool(self.selected_tags) or self.include_untagged
        self.enabled = self._filter_enabled

        self._filter_items_changed()

    def __del__(self):
        with contextlib.suppress(Exception):
            self.destroy()

    def destroy(self):
        self._tag_subs.clear()
        if self._core is not None:
            self._core.destroy()
        self._core = None
        self._all_tag_paths = None
        self._prim_counts = None
        self._selected_tag_paths = []
        self._checkboxes_frame = None
        self._rebuilding = False
        self._filter_enabled = False

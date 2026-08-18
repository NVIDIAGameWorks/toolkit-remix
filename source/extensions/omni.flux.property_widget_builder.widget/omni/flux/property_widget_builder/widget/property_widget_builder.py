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

__all__ = ("PropertyWidget",)

import asyncio
import math

from omni import kit, ui, usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.tree_widget import TreeWidget as _TreeWidget

from .tree.delegate import Delegate
from .tree.model import ItemGroup, Model

_DEFAULT_NAME_COLUMN_PERCENT = 30
_DEFAULT_MIN_COLUMN_WIDTH = 100
_RESPONSIVE_NAME_COLUMN_MIN_WIDTH = _DEFAULT_MIN_COLUMN_WIDTH
_RESPONSIVE_VALUE_COLUMN_MIN_WIDTH = 90
# TreeView row chrome and field spacing take horizontal space outside the explicit value column.
_RESPONSIVE_TREE_ROW_RESERVED_WIDTH = 32


class PropertyWidget:
    """Widget that let you build property widget(s) from any data"""

    def __init__(
        self,
        model: Model | None = None,
        delegate: Delegate | None = None,
        tree_column_widths: list[ui.Length] | None = None,
        tree_min_column_widths: list[ui.Length] | None = None,
        columns_resizable: bool = False,
        select_all_children: bool = False,
    ):
        """
        Property widget displaying attribute names and values in a tree structure

        Args:
            model: model to use for the treeview
            delegate: delegate to use for the treeview
            tree_column_widths: optional column widths to use for the treeview
            tree_min_column_widths: optional minimum column widths to use for the treeview
            columns_resizable: whether the treeview columns can be resized
            select_all_children: whether selecting a parent also selects all its children
        """
        self._default_attr = {
            "_model": None,
            "_delegate": None,
            "_tree_column_widths": None,
            "_tree_min_column_widths": None,
            "_columns_resizable": None,
            "_select_all_children": None,
            "_update_task": None,
            "_expansion_state": None,
            "_on_item_expanded_sub": None,
            "_on_item_changed_sub": None,
            "_tree_view": None,
            "_root_frame": None,
            "_last_name_column_width": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._model = Model() if model is None else model
        self._delegate = Delegate() if delegate is None else delegate
        self._tree_column_widths = tree_column_widths
        self._tree_min_column_widths = (
            [ui.Pixel(100), ui.Pixel(100)] if tree_min_column_widths is None else tree_min_column_widths
        )
        self._columns_resizable = columns_resizable
        self._select_all_children = select_all_children

        self._update_task = None
        self._expansion_state = {}

        self._on_item_expanded_sub = self._delegate.subscribe_item_expanded(self._on_item_expanded)
        self._on_item_changed_sub = self._model.subscribe_item_changed_fn(self._on_item_changed)

        self._build_ui()
        self._delegate.set_apply_item_expanded_fn(self._apply_item_expanded)

        if self._model.get_all_items():
            self._update_expansion_state_deferred()

    @property
    def tree_view(self) -> _TreeWidget:
        """Treeview of the widget"""
        return self._tree_view

    def _build_ui(self):
        self._root_frame = ui.Frame(
            width=ui.Fraction(1),
            horizontal_clipping=True,
            computed_content_size_changed_fn=self._on_content_size_changed,
        )
        with self._root_frame:
            self._tree_view = _TreeWidget(
                self._model,
                self._delegate,
                root_visible=False,
                header_visible=False,
                width=ui.Fraction(1),
                column_widths=self._get_column_widths(),
                min_column_widths=self._get_min_column_widths(),
                columns_resizable=self._columns_resizable,
                select_all_children=self._select_all_children,
                name="PropertyWidget",
            )

    def _uses_responsive_pixel_columns(self) -> bool:
        return (
            self._tree_column_widths is not None
            and len(self._tree_column_widths) >= 2
            and self._tree_column_widths[0].unit == ui.UnitType.PIXEL
        )

    def _get_column_widths(self) -> list[ui.Length]:
        column_widths = (
            [ui.Percent(_DEFAULT_NAME_COLUMN_PERCENT), ui.Fraction(1)]
            if self._tree_column_widths is None
            else self._tree_column_widths
        )
        if not self._uses_responsive_pixel_columns():
            return column_widths

        available_width = self._root_frame.computed_width if self._root_frame else 0
        max_name_width = column_widths[0].value
        if not available_width or math.isclose(available_width, 0):
            name_width = max_name_width
        else:
            name_width = min(
                max_name_width,
                max(
                    _RESPONSIVE_NAME_COLUMN_MIN_WIDTH,
                    available_width - _RESPONSIVE_VALUE_COLUMN_MIN_WIDTH - _RESPONSIVE_TREE_ROW_RESERVED_WIDTH,
                ),
            )
        return [ui.Pixel(name_width), *column_widths[1:]]

    def _get_min_column_widths(self) -> list[ui.Length]:
        if not self._uses_responsive_pixel_columns():
            return self._tree_min_column_widths
        return [
            ui.Pixel(min(_RESPONSIVE_NAME_COLUMN_MIN_WIDTH, self._tree_column_widths[0].value)),
            ui.Pixel(_RESPONSIVE_VALUE_COLUMN_MIN_WIDTH),
        ]

    def _on_content_size_changed(self):
        if not self._tree_view or not self._uses_responsive_pixel_columns():
            return

        column_widths = self._get_column_widths()
        name_column_width = column_widths[0].value
        if self._last_name_column_width is not None and math.isclose(self._last_name_column_width, name_column_width):
            return

        self._last_name_column_width = name_column_width
        self._tree_view.column_widths = column_widths
        self._tree_view.min_column_widths = self._get_min_column_widths()
        self._tree_view.dirty_widgets()

    def _update_expansion_state_deferred(self, *_):
        if self._update_task:
            self._update_task.cancel()
        self._update_task = asyncio.ensure_future(self._update_expansion_state_async())

    @usd.handle_exception
    async def _update_expansion_state_async(self):
        # Wait for items to be created by the widget
        await kit.app.get_app().next_update_async()
        items = self._model.get_all_items()
        for item in items:
            if not item.name_models:
                continue
            name = item.name_models[0].get_value_as_string()

            # Check if user has manually set expansion state for this item
            if name in self._expansion_state:
                desired_state = self._expansion_state[name]
            elif isinstance(item, ItemGroup) and item.expanded:
                desired_state = True
            else:
                continue

            if self._tree_view.is_expanded(item) != desired_state:
                self._tree_view.set_expanded(item, desired_state, False)

    def _on_item_expanded(self, item, value):
        if not item.name_models:
            return
        self._expansion_state[item.name_models[0].get_value_as_string()] = value

    def _apply_item_expanded(self, item: ItemGroup, value: bool) -> None:
        if self._tree_view is None:
            return
        if self._tree_view.is_expanded(item) != value:
            self._tree_view.set_expanded(item, value, False)
        self._on_item_expanded(item, value)

    def set_all_item_groups_expanded(self, value: bool) -> None:
        if self._model is None or self._tree_view is None:
            return
        for item in self._model.get_all_items():
            if isinstance(item, ItemGroup):
                self._apply_item_expanded(item, value)

    def expand_all_groups(self) -> None:
        self.set_all_item_groups_expanded(True)

    def collapse_all_groups(self) -> None:
        self.set_all_item_groups_expanded(False)

    def _on_item_changed(self, model, item):
        if item is None:
            self._delegate.resolve_claims(model)
            self._tree_view.dirty_widgets()
        self._update_expansion_state_deferred()
        if item is not None:
            items = [item]
        else:
            items = model.get_all_items()
        for _item in items:
            self._delegate.value_model_updated(_item)

    def destroy(self):
        if self._update_task:
            self._update_task.cancel()
        if self._delegate is not None:
            self._delegate.set_apply_item_expanded_fn(None)
        _reset_default_attrs(self)

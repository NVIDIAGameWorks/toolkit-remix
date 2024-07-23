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
from typing import List, Optional

from omni import kit, ui, usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.tree_widget import TreeWidget as _TreeWidget

from .tree.delegate import Delegate
from .tree.model import Model


class PropertyWidget:
    """Widget that let you build property widget(s) from any data"""

    def __init__(
        self,
        model: Optional[Model] = None,
        delegate: Optional[Delegate] = None,
        tree_column_widths: List[ui.Length] = None,
    ):
        """
        Property widget displaying attribute names and values in a tree structure

        Args:
            model: model to use for the treeview
            delegate: delegate to use for the treeview
        """
        self._default_attr = {
            "_model": None,
            "_delegate": None,
            "_tree_column_widths": None,
            "_update_task": None,
            "_expansion_state": None,
            "_on_item_expanded_sub": None,
            "_on_item_changed_sub": None,
            "_tree_view": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._model = Model() if model is None else model
        self._delegate = Delegate() if delegate is None else delegate
        self._tree_column_widths = tree_column_widths

        self._update_task = None
        self._expansion_state = {}

        self._on_item_expanded_sub = self._delegate.subscribe_item_expanded(self._on_item_expanded)
        self._on_item_changed_sub = self._model.subscribe_item_changed_fn(self._on_item_changed)

        self._build_ui()

    @property
    def tree_view(self) -> _TreeWidget:
        """Treeview of the widget"""
        return self._tree_view

    def _build_ui(self):
        self._tree_view = _TreeWidget(
            self._model,
            self._delegate,
            root_visible=False,
            header_visible=False,
            column_widths=(
                [ui.Percent(40), ui.Percent(60)] if self._tree_column_widths is None else self._tree_column_widths
            ),
            name="PropertyWidget",
        )

    def _update_expansion_state_deferred(self, *_):
        if self._update_task:
            self._update_task.cancel()
        self._update_task = asyncio.ensure_future(self._update_expansion_state_async())

    @usd.handle_exception
    async def _update_expansion_state_async(self):
        # Wait for items to be created by the widget
        await kit.app.get_app().next_update_async()
        # Update expansion state
        items = self._model.get_all_items()
        for name, value in self._expansion_state.items():
            try:
                item = next(item for item in items if item.name_models[0].get_value_as_string() == name)
            except StopIteration:
                continue
            else:
                self._tree_view.set_expanded(item, value, False)

    def _on_item_expanded(self, item, value):
        self._expansion_state[item.name_models[0].get_value_as_string()] = value

    def _on_item_changed(self, model, item):
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
        _reset_default_attrs(self)

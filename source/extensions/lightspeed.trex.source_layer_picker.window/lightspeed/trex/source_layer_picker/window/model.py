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

__all__ = ["SearchableLayerModel", "_item_matches_search", "_subtree_has_search_match"]

from pathlib import Path

from omni.flux.layer_tree.usd.widget import LayerModel as _LayerModel


def _item_matches_search(item, search: str) -> bool:
    """Case-insensitive substring match against the item's layer basename."""
    search = search.strip()
    if not search:
        return True
    layer = item.data.get("layer") if item.data else None
    if layer is None:
        return False
    return search.lower() in Path(layer.identifier).name.lower()


def _subtree_has_search_match(item, search: str) -> bool:
    """True iff this item or any descendant matches the search."""
    if _item_matches_search(item, search):
        return True
    return any(_subtree_has_search_match(child, search) for child in item.children)


class SearchableLayerModel(_LayerModel):
    """LayerModel with a case-insensitive substring filter on layer basenames.

    Only the TreeView render path (``get_item_children`` without ``recursive=True``)
    is filtered. Internal layer-tree refresh calls use ``recursive=True`` to restore
    expansion/selection state and must see the full set; we pass those through
    unchanged so the host widget's bookkeeping stays consistent with what USD
    actually contains.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._search: str = ""

    def set_search(self, text: str, force: bool = False) -> None:
        new_search = (text or "").strip().lower()
        if new_search == self._search and not force:
            return
        self._search = new_search
        self._item_changed(None)

    def get_item_children(self, parent=None, recursive: bool = False, item=None):
        # Mirror LayerModel.get_item_children's signature exactly so both positional
        # (`model.get_item_children(item)` from the TreeView) and keyword
        # (`model.get_item_children(parent=item, recursive=True)`) call shapes work.
        children = super().get_item_children(parent=parent, recursive=recursive, item=item)
        if recursive or not self._search:
            return children
        return [child for child in children if _subtree_has_search_match(child, self._search)]

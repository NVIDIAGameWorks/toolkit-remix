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

import asyncio
from contextlib import suppress

from omni import ui
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget
from omni.flux.utils.widget.tree_widget import TreeDelegateBase, TreeItemBase, TreeModelBase
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows

__all__ = ["TestScrollingTreeWidgetLifecycle"]


class _TreeItem(TreeItemBase):
    def __init__(self, name: str = "Root"):
        super().__init__()
        self.name = name


class _TreeModel(TreeModelBase[_TreeItem]):
    def __init__(self, items: list[_TreeItem]):
        super().__init__()
        self._items = items

    @property
    def default_attr(self) -> dict[str, None]:
        return {"_items": None}

    def get_item_children(self, item: _TreeItem | None) -> list[_TreeItem]:
        return self._items if item is None else item.children

    def get_item_value_model_count(self, _item: _TreeItem) -> int:
        return 1


class _TreeDelegate(TreeDelegateBase):
    @property
    def default_attr(self) -> dict[str, None]:
        return {"_selection": None}

    def _build_widget(self, _model, item, _column_id, _level, _expanded):
        ui.Label(item.name)


class TestScrollingTreeWidgetLifecycle(AsyncTestCase):
    async def test_selection_finishes_when_widget_is_destroyed_during_scroll_frame_wait(self):
        """Stop selection before it touches a TreeView destroyed while awaiting Kit's next frame."""
        # Arrange
        item = _TreeItem()
        model = _TreeModel([item])
        delegate = _TreeDelegate()
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSelectionDestroyedDuringScroll", height=400, width=400)
        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, frame_selection=True, select_all_children=False)
        selection_task = asyncio.create_task(widget.set_selection_async([item]))

        try:
            # Act
            await asyncio.sleep(0)
            selection_was_waiting = not selection_task.done()
            widget.destroy()
            await asyncio.wait_for(selection_task, timeout=2)

            # Assert
            self.assertTrue(selection_was_waiting)
        finally:
            selection_task.cancel()
            with suppress(asyncio.CancelledError):
                await selection_task
            widget.destroy()
            window.destroy()
            delegate.destroy()
            model.destroy()

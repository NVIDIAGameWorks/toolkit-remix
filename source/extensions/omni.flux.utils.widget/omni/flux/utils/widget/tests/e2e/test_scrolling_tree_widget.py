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
from types import SimpleNamespace

from omni import ui
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget
from omni.flux.utils.widget.tree_widget import TreeDelegateBase, TreeItemBase, TreeModelBase
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows

__all__ = ["TestScrollingTreeWidgetLifecycle"]


class _TreeItem(TreeItemBase):
    def __init__(self, name: str = "Root", path: str | None = None, parent: "_TreeItem | None" = None):
        super().__init__(parent)
        self.name = name
        self.path = path

    @property
    def can_have_children(self) -> bool:
        return bool(self.children)


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


class _RefreshTreeModel(_TreeModel):
    def __init__(self, items: list[_TreeItem], refresh_results: list[SimpleNamespace]):
        super().__init__(items)
        self._refresh_results = iter(refresh_results)
        self._refresh_count = 0
        self.first_result_published = asyncio.Event()
        self.release_second_refresh = asyncio.Event()

    async def refresh_threaded(self):
        self._refresh_count += 1
        if self._refresh_count == 2:
            await self.release_second_refresh.wait()
        return next(self._refresh_results)

    def publish_refresh_result(self, result):
        self._items = result.root_items
        self._item_changed(None)
        if self._refresh_count == 1:
            self.first_result_published.set()


class _TreeDelegate(TreeDelegateBase):
    @property
    def default_attr(self) -> dict[str, None]:
        return {"_selection": None}

    def _build_widget(self, _model, item, _column_id, _level, _expanded):
        ui.Label(item.name)


class TestScrollingTreeWidgetLifecycle(AsyncTestCase):
    async def test_refresh_model_when_superseded_during_expansion_commits_one_complete_result(self):
        # Arrange
        old_root = _TreeItem("Old", "/Group")
        _TreeItem("Old Child", "/Group/Old", old_root)
        root_a = _TreeItem("A", "/Group")
        _TreeItem("A Child", "/Group/A", root_a)
        root_b = _TreeItem("B", "/Group")
        _TreeItem("B Child", "/Group/B", root_b)

        def _result(root):
            items = [root, *root.children]
            return SimpleNamespace(
                root_items=[root],
                item_by_hash={hash(item): item for item in items},
                items_by_path={item.path: [item] for item in items},
                path_by_hash={hash(item): item.path for item in items},
            )

        result_a = _result(root_a)
        result_b = _result(root_b)
        model = _RefreshTreeModel([old_root], [result_a, result_b])
        delegate = _TreeDelegate()
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestAtomicTreeRefresh", height=400, width=400)
        with window.frame:
            widget = ScrollingTreeWidget(
                model,
                delegate,
                expansion_caching=True,
                frame_selection=False,
                select_all_children=False,
            )
        widget._item_expansion_states = {hash(old_root): True}
        widget._item_paths_by_hash = {hash(old_root): old_root.path}

        first_refresh = asyncio.create_task(widget.refresh_model())
        second_refresh = None
        try:
            await model.first_result_published.wait()

            # Act
            second_refresh = asyncio.create_task(widget.refresh_model())
            await first_refresh
            first_state = (
                model.get_item_children(None),
                widget._item_paths_by_hash,
                dict(widget._item_expansion_states),
            )
            model.release_second_refresh.set()
            await second_refresh
            second_state = (
                model.get_item_children(None),
                widget._item_paths_by_hash,
                dict(widget._item_expansion_states),
            )

            # Assert
            self.assertEqual(([root_a], result_a.path_by_hash, {hash(root_a): True}), first_state)
            self.assertEqual(([root_b], result_b.path_by_hash, {hash(root_b): True}), second_state)
        finally:
            model.release_second_refresh.set()
            for task in (first_refresh, second_refresh):
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            widget.destroy()
            window.destroy()
            delegate.destroy()
            model.destroy()

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

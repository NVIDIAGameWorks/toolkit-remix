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

from __future__ import annotations

__all__ = [
    "StageManagerTreeDelegate",
    "StageManagerTreeItem",
    "StageManagerTreeItemProxy",
    "StageManagerTreeModel",
    "StageManagerTreePlugin",
]

import abc
import asyncio
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

import carb.settings
import omni.kit.context_menu
from omni import ui, usd
from omni.flux.utils.common.menus import Menu as _Menu
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.widget.tree_widget import TreeDelegateBase as _TreeDelegateBase
from omni.flux.utils.widget.tree_widget import TreeItemBase as _TreeItemBase
from omni.flux.utils.widget.tree_widget import TreeModelBase as _TreeModelBase
from omni.flux.utils.widget.usd.prims.string_field import UsdPrimNameField as _UsdPrimNameField
from pydantic import Field

from ..items import StageManagerItem as _StageManagerItem
from ..utils import StageManagerUtils as _StageManagerUtils
from .base import StageManagerPluginBase as _StageManagerPluginBase
from .filter_plugin import StageManagerFilterPlugin as _StageManagerFilterPlugin

if TYPE_CHECKING:
    from pxr import Usd

    from .column_plugin import StageManagerColumnPlugin as _StageManagerColumnPlugin


_T = TypeVar("_T")


class StageManagerTreeItem(_TreeItemBase):
    """
    A TreeView item used in TreeView models

    Args:
        display_name: The string to display in the TreeView
        data: The data associated with the item
        tooltip: The tooltip to display when hovering over the item
        display_name_ancestor: A string to prepend to the display name with
    """

    def __init__(
        self,
        display_name: str,
        data: Any,
        tooltip: str = "",
        display_name_ancestor: str | None = None,
        path: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._display_name = display_name
        self._tooltip = tooltip
        self._data = data
        self._display_name_ancestor = display_name_ancestor
        self._path = path

        self._parent = None

        self._settings = carb.settings.get_settings()
        self._long_display_path_name = None

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_display_name": None,
                "_tooltip": None,
                "_data": None,
                "_path": None,
                "_parent_name": None,
                "_settings": None,
                "_nickname_field": None,
                "_proxy": None,
            }
        )
        return default_attr

    @property
    def proxy(self) -> StageManagerTreeItemProxy | None:
        """Return this item's proxy for the active full-refresh generation.

        The proxy may be temporarily absent from the visible filtered hierarchy.
        """
        return self._proxy

    @property
    def is_virtual(self) -> bool:
        """Whether this item is a virtual grouping node."""
        return False

    @property
    def display_name(self) -> str:
        """
        The display name for the item. Can be used by the widgets
        """
        return self._display_name

    @property
    def display_name_ancestor(self) -> str:
        """
        The display name of the item's ancestor. Can be used for sorting
        """
        return self._display_name_ancestor

    @property
    def tooltip(self) -> str:
        """
        The tooltip displayed when hovering the item. Can be used by the widgets
        """
        return self._tooltip

    @_TreeItemBase.parent.setter
    def parent(self, item: StageManagerTreeItem):
        # NOTE: clear out the long name cache any time parent changes
        if item != self.parent:
            self.clear_long_display_path_name_cache()
            children = self.children
            while children:
                child = children.pop()
                child.clear_long_display_path_name_cache()
                children.extend(child.children)

        # NOTE: execute the original setter
        _TreeItemBase.parent.fset(self, item)

    def clear_long_display_path_name_cache(self):
        self._long_display_path_name = None

    @property
    def long_display_path_name(self) -> str:
        if self._long_display_path_name is not None:
            return self._long_display_path_name

        name_parts = []
        item = self
        while item:
            name_parts.append(item.display_name)
            item = item.parent

        name_parts.reverse()
        self._long_display_path_name = "/".join(name_parts)
        return self._long_display_path_name

    @property
    def data(self) -> Any:
        """
        Custom data held in the item. Can be used by the widgets
        """
        return self._data

    @property
    def path(self) -> str | None:
        """
        Stable data path represented by this tree item, when one exists.
        """
        return self._path

    @path.setter
    def path(self, value: str | None):
        """
        Set the stable data path represented by this tree item.
        """
        self._path = value

    @property
    def icon(self) -> str | None:
        """
        The icon style name associated with the item. Can be used by the widgets
        """
        return None

    @property
    def show_nickname_key(self) -> str:
        """
        Key for the carb.settings key to store the show_nickname override
        """
        return f"{str(self.__hash__())}_show_nickname"

    @property
    def nickname_field(self) -> _UsdPrimNameField | None:
        """The live UsdPrimNameField widget for this item, if built."""
        return self._nickname_field

    def build_widget(self):
        """Build the UsdPrimNameField widget for this item."""
        if not self._data or not self._data.IsValid():
            return
        with ui.HStack(spacing=0, height=0):
            self._nickname_field = _UsdPrimNameField(
                prim=self._data,
                editable_check_fn=self.is_prim_editable,
                field_id=self.show_nickname_key,
                show_display_name_ancestor=bool(self._display_name_ancestor),
            )

    def is_prim_editable(self, prim: Usd.Prim) -> bool:
        """
        Determine if the prim is editable.
        """
        if not prim or not prim.IsValid():
            return False

        return bool(self.parent and self.parent.parent)

    def __eq__(self, other):
        if isinstance(other, StageManagerTreeItem):
            return self.display_name == other.display_name and self.data == other.data
        return False

    def __hash__(self):
        return hash(self.long_display_path_name)


class StageManagerTreeItemProxy(_TreeItemBase):
    """Represent one canonical item with independent links for the visible hierarchy.

    Filtering may detach the proxy while it retains its canonical item reference.
    """

    def __init__(self, original_tree_item: StageManagerTreeItem):
        super().__init__()
        self._original_tree_item = original_tree_item
        original_tree_item._proxy = self  # noqa: SLF001 - paired canonical/proxy ownership

    @property
    def original_tree_item(self) -> StageManagerTreeItem:
        """Return the canonical item represented by this proxy."""
        return self._original_tree_item

    def __hash__(self):
        return hash(self._original_tree_item)


@dataclass(frozen=True)
class TreeRefreshResult:
    """
    Fully prepared tree data ready to publish on the main thread.

    The lookup tables are built with the tree in one worker pass. They contain
    references to the tree items rather than copies and avoid later tree scans
    during publication, selection synchronization, and expansion restoration.

    Attributes:
        canonical_root_items: Complete canonical hierarchy owned by the tree model.
        root_items: Visible proxy hierarchy published to the TreeView.
        items_by_path: All visible data-backed rows for each stable path, including duplicates.
        item_by_hash: Every visible row indexed for exact expansion-state restoration.
        path_by_hash: Visible stable-path fallback retained after the previous tree is released.
        input_items_count: Context items considered before user filtering.
        output_items_count: Context items retained after user filtering.
    """

    canonical_root_items: list[StageManagerTreeItem]
    root_items: list[StageManagerTreeItemProxy]
    items_by_path: dict[str, list[StageManagerTreeItemProxy]]
    item_by_hash: dict[int, StageManagerTreeItemProxy]
    path_by_hash: dict[int, str]
    input_items_count: int
    output_items_count: int


class StageManagerTreeModel(_TreeModelBase[StageManagerTreeItemProxy]):
    """
    A TreeView model used to define the structure of the tree
    """

    def __init__(self):
        self._canonical_root_items = []
        self._items = []

        super().__init__()

        self._context_items: list[_StageManagerItem] = []
        self._user_filter_plugins: list[_StageManagerFilterPlugin] = []
        self._column_count = 0
        self._selection: list[StageManagerTreeItemProxy] = []
        self._items_by_path: dict[str, list[StageManagerTreeItemProxy]] = {}
        self._item_by_hash: dict[int, StageManagerTreeItemProxy] = {}
        self._refresh_cancel_event: threading.Event | None = None

    def destroy(self):
        if self._refresh_cancel_event:
            self._refresh_cancel_event.set()
        self._detach_item_proxies(self._canonical_root_items)
        super().destroy()

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_canonical_root_items": None,
                "_items": None,
                "_context_items": None,
                "_column_count": None,
                "_selection": None,
                "_items_by_path": None,
                "_item_by_hash": None,
                "_refresh_cancel_event": None,
            }
        )
        return default_attr

    @property
    def items_dict(self) -> dict[int, StageManagerTreeItemProxy]:
        """
        Get a dictionary of item hashes and items
        """
        return (
            dict(self._item_by_hash)
            if self._item_by_hash
            else {hash(item): item for item in self.iter_items_children()}
        )

    @property
    def selection(self) -> list[StageManagerTreeItemProxy]:
        """The tree items currently selected in the UI."""
        return list(self._selection)

    @selection.setter
    def selection(self, items: Iterable[StageManagerTreeItemProxy]):
        """
        Store the currently selected tree items.

        A copy of ``items`` is stored; mutating the original list after calling
        this setter has no effect on the stored selection.

        Called by the interaction plugin whenever the tree selection changes.
        """
        self._selection = list(items)

    def get_items_by_path(self, path: str) -> list[StageManagerTreeItemProxy]:
        """
        Get all tree items for a USD path without walking the tree.
        """
        return list(self._items_by_path.get(path, []))

    def set_context_items(self, items: list[_StageManagerItem]):
        """
        Take ownership of items fetched in the context worker without copying.

        The interaction pipeline schedules the model refresh after this handoff.
        """
        self._context_items = items

    def clear_items(self):
        """Clear rendered tree state without dropping source context data."""
        self._detach_item_proxies(self._canonical_root_items)
        self._canonical_root_items = []
        self._items = []
        self.selection = []
        self._items_by_path = {}
        self._item_by_hash = {}
        self._item_changed(None)

    @property
    def column_count(self) -> int:
        """
        Get the number of columns to build
        """
        return self._column_count

    @column_count.setter
    def column_count(self, value: int):
        """
        Set the number of columns to build
        """
        self._column_count = value

    @usd.handle_exception
    async def refresh(self):
        """
        Method called when the `self._items` attribute should be refreshed
        """
        result = await self.refresh_threaded()
        if result is None:
            return
        self.publish_refresh_result(result)

    async def _run_cancellable_worker(self, worker: Callable[..., _T], *args) -> _T | None:
        """Run one worker off-thread, superseding any previous tree work.

        Args:
            worker: Synchronous callable receiving ``*args`` followed by a cancellation event.
            *args: Arguments forwarded to the worker before the cancellation event.

        Returns:
            The worker result, or ``None`` when the work was superseded.

        Raises:
            asyncio.CancelledError: When the calling task is cancelled after signaling the worker.
        """
        previous_cancel_event = self._refresh_cancel_event
        if previous_cancel_event is not None:
            previous_cancel_event.set()

        cancel_event = threading.Event()
        self._refresh_cancel_event = cancel_event

        try:
            result = await asyncio.to_thread(worker, *args, cancel_event)
        except asyncio.CancelledError:
            cancel_event.set()
            raise
        finally:
            if self._refresh_cancel_event is cancel_event:
                self._refresh_cancel_event = None

        return None if cancel_event.is_set() else result

    async def refresh_threaded(self) -> TreeRefreshResult | None:
        """
        Prepare a complete tree refresh result off the UI thread.
        """
        context_items = self._context_items
        user_filter_plugins = [
            filter_plugin for filter_plugin in self._user_filter_plugins if filter_plugin.filter_active
        ]
        return await self._run_cancellable_worker(
            self._prepare_refresh_result,
            context_items,
            user_filter_plugins,
        )

    async def apply_filters(self) -> tuple[int, int] | None:
        """Recompute and publish only the visible proxy hierarchy.

        Returns:
            The input and output context-item counts, or ``None`` when the work
            was cancelled or targeted an obsolete canonical generation.
        """
        canonical_root_items = self._canonical_root_items
        context_items = self._context_items
        user_filter_plugins = [
            filter_plugin for filter_plugin in self._user_filter_plugins if filter_plugin.filter_active
        ]
        result = await self._run_cancellable_worker(
            self._prepare_filter_projection,
            canonical_root_items,
            context_items,
            user_filter_plugins,
        )

        if result is None or canonical_root_items is not self._canonical_root_items:
            return None

        (
            canonical_items,
            root_items,
            visible_children_by_proxy,
            items_by_path,
            item_by_hash,
            input_items_count,
            output_items_count,
        ) = result
        self._set_visible_proxy_children(canonical_items, visible_children_by_proxy)
        self._items = root_items
        self._items_by_path = items_by_path
        self._item_by_hash = item_by_hash
        self._item_changed(None)
        return input_items_count, output_items_count

    def publish_refresh_result(self, result: TreeRefreshResult):
        """
        Publish a prepared threaded refresh result on the main thread.

        This is the low-level publication step used by ``refresh()`` and
        ``ScrollingTreeWidget.refresh_model()``. Callers should normally use
        one of those complete refresh entry points.
        """
        self._detach_item_proxies(self._canonical_root_items)
        self._canonical_root_items = result.canonical_root_items
        self._items = result.root_items
        self.selection = []
        self._items_by_path = result.items_by_path
        self._item_by_hash = result.item_by_hash
        self._item_changed(None)

    def notify_item_changed(self, item: StageManagerTreeItem | StageManagerTreeItemProxy | None = None):
        """Notify with a proxy, converting canonical items and ignoring obsolete ones.

        Passing ``None`` emits a global change notification.
        """
        if isinstance(item, StageManagerTreeItem):
            item = item.proxy
            if item is None:
                return
        self._item_changed(item)

    def find_items(self, predicate: Callable[[StageManagerTreeItemProxy], bool]) -> list[StageManagerTreeItemProxy]:
        """
        Find all items matching a predicate.

        Args:
            predicate: Function that returns True for items that should be included

        Returns:
            List of items matching the predicate
        """
        return [item for item in self.iter_items_children() if predicate(item)]

    @usd.handle_exception
    async def find_items_async(
        self,
        predicate: Callable[[StageManagerTreeItemProxy], bool],
    ) -> list[StageManagerTreeItemProxy]:
        """
        Find all items matching a predicate without blocking the UI.

        Runs the search in a background thread and returns the results asynchronously.

        Args:
            predicate: Function that returns True for items that should be included

        Returns:
            List of items matching the predicate
        """
        return await asyncio.to_thread(self.find_items, predicate)

    def get_item_children(self, item: StageManagerTreeItemProxy | None):
        """
        Returns all the children of any given item.
        """
        if item is None:
            return self._items
        return item.children or []

    def get_item_value_model_count(self, item: StageManagerTreeItemProxy):
        return self.column_count

    def add_user_filter_plugins(self, value: list[_StageManagerFilterPlugin]):
        """
        Extend the filter plugins to apply to the items during filtering
        """
        self._user_filter_plugins.extend(value)

    def clear_user_filter_plugins(self):
        """
        Clear the filter plugins to apply to the items during filtering
        """
        self._user_filter_plugins.clear()

    def sort_items(self, items, sort_children: bool = True):
        """
        Sort the tree items in alphabetical order
        """
        items.sort(key=lambda x: (x.display_name, x.display_name_ancestor or ""))
        if sort_children:
            for item in items:
                self.sort_items(item.children)

    def get_context_menu_payload(self, item: StageManagerTreeItemProxy) -> dict[str, Any]:
        """Build an action payload that exposes the proxy's canonical item."""
        original_item = item.original_tree_item
        return {
            "model": self,
            "right_clicked_item": original_item,
        }

    def _build_item(self, *args, **kwargs) -> StageManagerTreeItem:
        """
        Factory method to create a StageManagerTreeItem instance.

        Args:
            *args: Positional arguments forwarded to StageManagerTreeItem (display_name, data, ...).
            **kwargs: Keyword arguments forwarded to StageManagerTreeItem.

        Returns:
            A new StageManagerTreeItem instance.
        """
        return StageManagerTreeItem(*args, **kwargs)

    def _prepare_refresh_result(
        self,
        context_items: list[_StageManagerItem],
        user_filter_plugins: list[_StageManagerFilterPlugin],
        cancel_event: threading.Event,
    ) -> TreeRefreshResult | None:
        """Build canonical items and the visible proxy projection for one refresh.

        Args:
            context_items: Read-only source wrappers in parent-before-child order.
            user_filter_plugins: Active filters to apply to the proxy projection.
            cancel_event: Signal set when this refresh has been superseded.

        Returns:
            The prepared tree result, or None when cancellation is requested.
        """
        if cancel_event.is_set():
            return None

        canonical_root_items = self._build_items(context_items, cancel_event) or []
        if cancel_event.is_set():
            return None

        canonical_items = self._create_item_proxies(canonical_root_items, cancel_event)
        if canonical_items is None or cancel_event.is_set():
            return None

        projection = self._prepare_filter_projection(
            canonical_root_items,
            context_items,
            user_filter_plugins,
            cancel_event,
            canonical_items,
        )
        if projection is None or cancel_event.is_set():
            return None

        (
            canonical_items,
            root_items,
            visible_children_by_proxy,
            items_by_path,
            item_by_hash,
            input_items_count,
            output_items_count,
        ) = projection
        self._set_visible_proxy_children(canonical_items, visible_children_by_proxy)
        path_by_hash = {
            item_hash: item.original_tree_item.path
            for item_hash, item in item_by_hash.items()
            if item.original_tree_item.path is not None
        }

        return TreeRefreshResult(
            canonical_root_items=canonical_root_items,
            root_items=root_items,
            items_by_path=items_by_path,
            item_by_hash=item_by_hash,
            path_by_hash=path_by_hash,
            input_items_count=input_items_count,
            output_items_count=output_items_count,
        )

    def _prepare_filter_projection(
        self,
        canonical_root_items: list[StageManagerTreeItem],
        context_items: list[_StageManagerItem],
        user_filter_plugins: list[_StageManagerFilterPlugin],
        cancel_event: threading.Event,
        canonical_items: list[StageManagerTreeItem] | None = None,
    ) -> tuple | None:
        """Prepare visible proxy state, reusing a supplied traversal or returning ``None`` when cancelled."""
        if canonical_items is None:
            canonical_items = self._collect_canonical_items(canonical_root_items, cancel_event)
            if canonical_items is None:
                return None

        filtered_items = context_items
        if user_filter_plugins:
            filtered_items = _StageManagerUtils.filter_items_by_category(
                context_items,
                user_filter_plugins,
                cancel_event,
            )
            if filtered_items is None or cancel_event.is_set():
                return None

        visible_paths = {str(item.data.GetPath()) for item in filtered_items} if user_filter_plugins else set()
        projection = self._project_item_proxies(
            canonical_items,
            canonical_root_items,
            visible_paths,
            bool(user_filter_plugins),
            cancel_event,
        )
        if projection is None or cancel_event.is_set():
            return None
        return canonical_items, *projection, len(context_items), len(filtered_items)

    @staticmethod
    def _detach_item_proxies(root_items: list[StageManagerTreeItem] | None) -> None:
        """Detach canonical items from proxies while preserving each proxy's original-item link."""
        item_stack = list(root_items or [])
        while item_stack:
            item = item_stack.pop()
            item._proxy = None  # noqa: SLF001 - generation ownership cleanup
            item_stack.extend(item.children)

    @staticmethod
    def _collect_canonical_items(
        root_items: list[StageManagerTreeItem], cancel_event: threading.Event | None = None
    ) -> list[StageManagerTreeItem] | None:
        """Return canonical items in traversal order, or ``None`` when cancelled."""
        canonical_items = []
        item_stack = list(reversed(root_items))
        while item_stack:
            if cancel_event is not None and cancel_event.is_set():
                return None

            item = item_stack.pop()
            canonical_items.append(item)
            item_stack.extend(reversed(item.children))
        return canonical_items

    @staticmethod
    def _create_item_proxies(
        root_items: list[StageManagerTreeItem], cancel_event: threading.Event
    ) -> list[StageManagerTreeItem] | None:
        """Create one proxy per canonical item and return traversal order, or ``None`` when cancelled."""
        canonical_items = []
        item_stack = list(reversed(root_items))
        while item_stack:
            if cancel_event.is_set():
                return None

            item = item_stack.pop()
            canonical_items.append(item)
            if item.proxy is None:
                StageManagerTreeItemProxy(item)
            item_stack.extend(reversed(item.children))
        return canonical_items

    @staticmethod
    def _project_item_proxies(
        canonical_items: list[StageManagerTreeItem],
        canonical_root_items: list[StageManagerTreeItem],
        visible_paths: set[str],
        filters_active: bool,
        cancel_event: threading.Event,
    ) -> tuple | None:
        """Return visible proxy roots, links, and lookups, or ``None`` when cancelled."""
        matched_branch_proxies = set()
        if filters_active:
            for item in canonical_items:
                if cancel_event.is_set():
                    return None
                proxy = item.proxy
                parent_proxy = item.parent.proxy if item.parent is not None else None
                if item.path in visible_paths or (item.path is None and parent_proxy in matched_branch_proxies):
                    matched_branch_proxies.add(proxy)

        visible_proxies = set()
        visible_children_by_proxy = {}
        for item in reversed(canonical_items):
            if cancel_event.is_set():
                return None

            proxy = item.proxy
            visible_children = [child.proxy for child in item.children if child.proxy in visible_proxies]

            if filters_active and proxy not in matched_branch_proxies and not visible_children:
                continue

            visible_proxies.add(proxy)
            visible_children_by_proxy[proxy] = visible_children

        root_items = [item.proxy for item in canonical_root_items if item.proxy in visible_proxies]

        items_by_path: dict[str, list[StageManagerTreeItemProxy]] = {}
        item_by_hash: dict[int, StageManagerTreeItemProxy] = {}
        for canonical_item in canonical_items:
            if cancel_event.is_set():
                return None

            item = canonical_item.proxy
            if item not in visible_proxies:
                continue

            item_hash = hash(item)
            item_by_hash[item_hash] = item
            path = canonical_item.path
            if path is None:
                continue

            items_by_path.setdefault(path, []).append(item)

        return root_items, visible_children_by_proxy, items_by_path, item_by_hash

    @staticmethod
    def _set_visible_proxy_children(
        canonical_items: list[StageManagerTreeItem],
        visible_children_by_proxy: dict[StageManagerTreeItemProxy, list[StageManagerTreeItemProxy]],
    ):
        """Clear existing proxy links and attach the currently visible children."""
        for item in canonical_items:
            item.proxy.clear_children()

        for parent_proxy, child_proxies in visible_children_by_proxy.items():
            for child_proxy in child_proxies:
                child_proxy.parent = parent_proxy

    def _build_items(
        self,
        items: list[_StageManagerItem],
        cancel_event: threading.Event,
    ) -> list[StageManagerTreeItem] | None:
        """
        Recursively build the model items from Stage Manager items

        Args:
            items: Read-only Stage Manager items in parent-before-child order.
            cancel_event: Signal set when this refresh has been superseded.

        Returns:
            Root tree items, or None when cancellation is requested.
        """

        tree_items = []
        tree_item_by_stage_item = {}
        for item in items:
            if cancel_event.is_set():
                return None
            path = item.data.GetPath()
            path_str = str(path)
            display_name = path.name
            tree_item = self._build_item(display_name, item.data, tooltip=path_str)
            tree_item.path = path_str
            tree_item_by_stage_item[item] = tree_item

            if item.parent is None:
                # Add to the root
                tree_items.append(tree_item)
            else:
                # Add to the parent
                tree_item.parent = tree_item_by_stage_item[item.parent]

        return tree_items


class StageManagerTreeDelegate(_TreeDelegateBase):
    """
    A TreeView delegate used to define the look of every element in the tree
    """

    def __init__(self, header_height: int = 24, row_height: int = 24):
        super().__init__()

        self._header_height = header_height
        self._row_height = row_height

        self._column_widget_builders = {}
        self._column_header_builders = {}

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_header_height": None,
                "_row_height": None,
                "_column_widget_builders": None,
                "_column_header_builders": None,
            }
        )
        return default_attr

    @property
    def header_height(self) -> int:
        return self._header_height

    @header_height.setter
    def header_height(self, value: int):
        self._header_height = max(0, value)

    @property
    def row_height(self) -> int:
        return self._row_height

    @row_height.setter
    def row_height(self, value: int):
        self._row_height = max(0, value)

    def set_column_builders(self, columns: list[_StageManagerColumnPlugin]):
        for index, column in enumerate(columns):
            self._column_widget_builders[index] = column.build_ui
            self._column_header_builders[index] = column.build_header

    def call_item_clicked(
        self,
        button: int,
        should_validate: bool,
        model: StageManagerTreeModel,
        item: StageManagerTreeItem,
    ):
        """Forward a widget click from a canonical item to the TreeView.

        The widget emits a canonical item. Its current proxy is forwarded to the TreeView; without a proxy, the item
        belongs to an obsolete generation and the click is ignored.

        Args:
            button: The mouse button that triggered the event
            should_validate: Whether the TreeView selection should be validated or not
            model: The tree model
            item: The canonical tree item emitted by the widget
        """
        proxy_item = item.proxy
        if proxy_item is None:
            return
        self._item_clicked(button, should_validate, model, proxy_item)

    def _build_widget(
        self,
        model: StageManagerTreeModel,
        item: StageManagerTreeItemProxy,
        column_id: int,
        level: int,
        expanded: bool,
    ):
        with ui.Frame(height=self.row_height):
            if column_id in self._column_widget_builders:
                original_item = item.original_tree_item
                self._column_widget_builders[column_id](model, original_item, level, expanded)

    def _build_branch(self, _model: _TreeModelBase, item: _TreeItemBase, column_id: int, level: int, expanded: bool):
        with ui.Frame(height=self.row_height):
            super()._build_branch(_model, item, column_id, level, expanded)

    def _build_header(self, column_id: int):
        with ui.Frame(height=self.header_height):
            if column_id in self._column_header_builders:
                self._column_header_builders[column_id]()

    def _show_context_menu(self, model: StageManagerTreeModel, item: StageManagerTreeItemProxy):
        super()._show_context_menu(model, item)

        context_menu = omni.kit.context_menu.get_instance()
        registered_menus = omni.kit.context_menu.get_menu_dict(_MenuGroup.SELECTED_PRIMS.value, "")

        omni.kit.context_menu.reorder_menu_dict(registered_menus)
        context_menu.show_context_menu(
            _Menu.STAGE_MANAGER.value, model.get_context_menu_payload(item), registered_menus
        )


class StageManagerTreePlugin(_StageManagerPluginBase, abc.ABC):
    """
    A plugin that provides a TreeView model and delegate
    """

    model: StageManagerTreeModel = Field(description="The tree model", exclude=True)
    delegate: StageManagerTreeDelegate = Field(description="The tree delegate", exclude=True)

    async def apply_filters(self) -> tuple[int, int] | None:
        """Delegate filter-only publication, returning counts or ``None`` for cancelled or stale work."""
        return await self.model.apply_filters()

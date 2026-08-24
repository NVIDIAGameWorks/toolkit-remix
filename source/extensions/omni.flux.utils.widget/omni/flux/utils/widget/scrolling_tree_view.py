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

__all__ = ["ScrollingTreeWidget"]

import asyncio
import threading
from asyncio import Future, ensure_future
from collections import deque
from collections.abc import Callable, Iterable
from contextlib import asynccontextmanager

import omni.kit.app
import omni.usd
from carb.events import IEvent
from omni import appwindow, ui
from omni.flux.utils.widget.tree_widget import (
    AlternatingRowWidget,
    TreeDelegateBase,
    TreeItemBase,
    TreeModelBase,
    TreeWidget,
)
from omni.ui import Length


class ScrollingTreeWidget:
    """
    A scrollable tree widget with optional alternating row backgrounds.

    This widget wraps TreeWidget with scroll handling, automatic content size
    updates, and optional alternating row visual effects.

    Args:
        model: The tree widget's data model
        delegate: The tree widget's delegate for custom rendering
        alternating_rows: Whether to display alternating row background colors
        header_height: Height of the header row in pixels (default: 28)
        row_height: Height of each data row in pixels (default: 28)
        select_all_children: Whether selecting a parent item also selects all
            its children
        frame_selection: Whether to automatically expand and scroll to items
            when the selection changes (default: False)
        validate_action_selection: Whether to validate and update selection
            to include the right-clicked item
        horizontal_scrollbar_policy: Visibility policy for the horizontal scrollbar.
        **kwargs: Additional arguments passed to the underlying ui.TreeView
    """

    def __init__(
        self,
        model: TreeModelBase,
        delegate: TreeDelegateBase,
        alternating_rows: bool = False,
        header_height: int = 28,  # Default: 24px content + 4px spacing (Sane default value)
        row_height: int = 28,  # Default: 24px content + 4px spacing (Sane default value)
        select_all_children: bool = True,
        frame_selection: bool = False,
        validate_action_selection: bool = True,
        expansion_caching: bool = False,
        horizontal_scrollbar_policy: ui.ScrollBarPolicy = ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
        **kwargs,
    ):
        self._alternating_row_widget: AlternatingRowWidget | None = None
        self._root_frame: ui.Frame | None = None
        self._tree_frame: ui.Frame | None = None
        self._tree_scroll_frame: ui.ScrollingFrame | None = None
        self._tree_widget: TreeWidget | None = None

        self._model = model
        self._delegate = delegate

        self._alternating_rows = alternating_rows
        self._select_all_children = select_all_children
        self._frame_selection = frame_selection

        # NOTE: if header is invisible let's set the header height to 0 for alternating rows
        self._header_height = header_height
        if not kwargs.get("header_visible", True):
            self._header_height = 0

        self._row_height = row_height
        self._previous_frame_height: float = 1.0

        self._extra_tree_view_args = kwargs

        self._update_content_size_task: Future | None = None

        self._validate_action_selection = validate_action_selection
        self._expansion_caching = expansion_caching
        self._horizontal_scrollbar_policy = horizontal_scrollbar_policy

        if self._expansion_caching:
            # NOTE: Disable the C++ TreeView's built-in expand-on-branch-click so that
            # ALL expansion is routed through our set_expanded() override, which keeps
            # _item_expansion_states in sync. Without this, the C++ side handles branch
            # clicks internally — it toggles is_expanded() and rebuilds the branch widget,
            # destroying the delegate's mouse_released_fn callback before it fires. That
            # makes the delegate subscription unreliable and leaves the cache stale.
            #
            # With expand_on_branch_click=False the C++ does nothing on click, the old
            # ui.Frame survives, the delegate callback fires reliably, and the lambda
            # subscription (below) calls set_expanded() to perform the expansion and
            # update the cache in one place.
            #
            # CAVEAT: This may also suppress keyboard arrow-key expansion if the C++
            # TreeView uses the same flag for both. If keyboard expand/collapse stops
            # working, a separate handler for key events would be needed.
            self._extra_tree_view_args.setdefault("expand_on_branch_click", False)

        self._selection_update_task: Future | None = None
        self._model_change_sync_task: Future | None = None
        self._suppress_model_change_sync = False
        self._suppress_selection_changed = False
        self._destroyed = False

        self._item_expansion_states: dict[int, bool] = {}
        self._item_paths_by_hash: dict[int, str] = {}
        self._expansion_resolve_cancel_event: threading.Event | None = None
        self._refresh_commit_lock = asyncio.Lock()
        self._keep_alive_disable_lock = asyncio.Lock()

        self._build_ui()

        # NOTE: Auto-subscribe to model changes to keep alternating rows in sync
        self._item_expanded_sub = None
        if self._expansion_caching:
            self._item_expanded_sub = self._delegate.subscribe_item_expanded(
                lambda item, expanded: self.set_expanded(item, expanded, False)
            )

        self._item_changed_sub = self._model.subscribe_item_changed_fn(self._on_model_item_changed)

        # NOTE: this event subscription makes sure that the number of alternating rows always matches
        # the size of the tree view window regardless of the count of visible items on the tree
        # I tried using the tree_frame and scroll frame but the main app window
        # is the required window_resize_event_stream
        self._app_window_size_changed_sub = (
            appwindow.get_default_app_window()
            .get_window_resize_event_stream()
            .create_subscription_to_pop(self._on_window_resized, name="AppWindowResized")
        )

    def _on_window_resized(self, _: IEvent) -> None:
        if not self._tree_widget:
            return
        self._tree_widget.dirty_widgets()

    @property
    def selection(self) -> list[TreeItemBase]:
        """The currently selected items in the tree."""
        return self._tree_widget.selection

    @selection.setter
    def selection(self, items: list[TreeItemBase]):
        if self._selection_update_task and not self._selection_update_task.done():
            self._selection_update_task.cancel()

        self._selection_update_task = ensure_future(self.set_selection_async(items))

    async def set_selection_async(self, items: list[TreeItemBase]):
        """
        Apply tree selection after optional frame-to-selection work.
        """
        if self._destroyed:
            return

        if self._frame_selection:
            await self.frame_items(items)
            if self._destroyed:
                return
        self._set_tree_selection_without_notification(items)

    async def frame_items(self, items: list[TreeItemBase], update_cache: bool = True) -> None:
        """Expand ancestors before scrolling to items.

        Setting ``update_cache`` to ``False`` preserves saved expansion state. Empty input and destroyed widgets are
        ignored.
        """
        if self._destroyed or not items:
            return
        await self.expand_to_items(items, update_cache=update_cache)
        if not self._destroyed:
            await self.scroll_to_items(items)

    def _set_tree_selection_without_notification(self, items: list[TreeItemBase]):
        previous_suppression = self._suppress_selection_changed
        self._suppress_selection_changed = True
        try:
            self._tree_widget.selection = items
        finally:
            self._suppress_selection_changed = previous_suppression

    @property
    def delegate(self) -> TreeDelegateBase:
        """The tree widget's delegate for custom rendering."""
        return self._delegate

    @property
    def model(self) -> TreeModelBase:
        """The tree widget's data model."""
        return self._model

    @property
    def height(self) -> Length:
        """
        Get or set the height of the scrolling tree widget.

        This controls the height of the internal ScrollingFrame, allowing
        external resize manipulators to adjust the widget's visible area.

        Returns:
            The current height of the scroll frame.
        """
        return self._tree_scroll_frame.height

    @height.setter
    def height(self, value: Length):
        self._tree_scroll_frame.height = value

    @property
    def visible(self) -> bool:
        """
        Get or set the visibility of the entire scrolling tree widget.

        When set to False, hides the root frame which contains both the
        TreeWidget and any alternating row backgrounds. This is useful
        for showing loading overlays or temporarily hiding the tree.

        Returns:
            True if the widget is visible, False otherwise.
        """
        return self._root_frame.visible

    @visible.setter
    def visible(self, value: bool):
        self._root_frame.visible = value

    @asynccontextmanager
    async def keep_alive_disabled(self):
        """Disable item retention and restore its prior value after one Kit update.

        Restoration survives exceptions and caller cancellation. No update occurs when the widget is unavailable,
        destroyed, or already disabled.
        """
        async with self._keep_alive_disable_lock:
            tree_widget = self._tree_widget
            if self._destroyed or tree_widget is None:
                yield
                return

            keep_alive = tree_widget.keep_alive
            if not keep_alive:
                yield
                return

            tree_widget.keep_alive = False
            try:
                yield
            finally:
                try:
                    await omni.kit.app.get_app().next_update_async()
                finally:
                    if not self._destroyed and self._tree_widget is tree_widget:
                        tree_widget.keep_alive = keep_alive

    def _build_ui(self):
        scroll_change_fn = None
        self._root_frame = ui.ZStack()
        with self._root_frame:
            if self._alternating_rows:
                self._alternating_row_widget = AlternatingRowWidget(self._header_height, self._row_height)
                scroll_change_fn = self._alternating_row_widget.sync_scrolling_frame

            with ui.HStack(content_clipping=self._alternating_rows):
                self._tree_scroll_frame = ui.ScrollingFrame(
                    name="TreePanelBackground",
                    scroll_y_changed_fn=scroll_change_fn,
                    horizontal_scrollbar_policy=self._horizontal_scrollbar_policy,
                )

                with self._tree_scroll_frame:
                    self._tree_frame = ui.ZStack(
                        content_clipping=True,
                        computed_content_size_changed_fn=self._on_content_size_changed,
                    )
                    with self._tree_frame:
                        self._tree_widget = TreeWidget(
                            self._model,
                            delegate=self._delegate,
                            select_all_children=self._select_all_children,
                            validate_action_selection=self._validate_action_selection,
                            **self._extra_tree_view_args,
                        )

    def _on_content_size_changed(self):
        # Destroying the tree widget changes its computed size, so this callback can fire during teardown. Scheduling
        # more work then would resume against released widgets.
        if self._destroyed:
            return
        if self._update_content_size_task:
            self._update_content_size_task.cancel()
        self._update_content_size_task = ensure_future(self._update_content_size_deferred())

    async def refresh_model(
        self,
        expand_filtered_roots: bool = False,
    ):
        """
        Run a full model refresh through the prepare/publish pipeline.

        Returns:
            The successfully published refresh result, or None when refresh work is discarded.
        """
        previous_cancel_event = self._expansion_resolve_cancel_event
        if previous_cancel_event is not None:
            previous_cancel_event.set()

        cancel_event = threading.Event()
        self._expansion_resolve_cancel_event = cancel_event
        try:
            model = self._model
            result = await model.refresh_threaded()
            if result is None or cancel_event.is_set() or self._destroyed:
                return None

            expansion_plan = ([], [], {})
            if self._item_expansion_states or expand_filtered_roots:
                expansion_plan = await asyncio.to_thread(
                    self._resolve_expansion_plan,
                    dict(self._item_expansion_states),
                    self._item_paths_by_hash,
                    result.item_by_hash,
                    result.items_by_path,
                    result.root_items,
                    expand_filtered_roots,
                    cancel_event,
                )
                if expansion_plan is None or cancel_event.is_set() or self._destroyed:
                    return None

            commit_task = asyncio.create_task(self._commit_refresh_result(model, result, expansion_plan, cancel_event))
            try:
                committed = await asyncio.shield(commit_task)
            except asyncio.CancelledError:
                cancel_event.set()
                await commit_task
                raise
            if not committed:
                return None
            return result
        except asyncio.CancelledError:
            cancel_event.set()
            raise
        finally:
            if self._expansion_resolve_cancel_event is cancel_event:
                self._expansion_resolve_cancel_event = None

    async def _commit_refresh_result(self, model, result, expansion_plan, cancel_event: threading.Event) -> bool:
        """Publish model and expansion state as one serialized main-thread commit."""
        async with self._refresh_commit_lock:
            if cancel_event.is_set() or self._destroyed:
                return False

            self._suppress_model_change_sync = True
            self._suppress_selection_changed = True
            try:
                model.publish_refresh_result(result)
                if self._destroyed:
                    return False
                self._tree_widget.selection = []
                if self._destroyed:
                    return False

                if self._model_change_sync_task and not self._model_change_sync_task.done():
                    self._model_change_sync_task.cancel()

                if self._alternating_rows and self._alternating_row_widget:
                    self._alternating_row_widget.refresh(item_count=self._model.get_children_count())
                    if self._destroyed:
                        return False

                recursive_items, ordered_items, expansion_cache_state = expansion_plan
                if recursive_items or ordered_items:
                    await omni.kit.app.get_app().next_update_async()
                    if self._destroyed:
                        return False

                for item in recursive_items:
                    if self._destroyed:
                        return False
                    if not self._tree_widget.is_expanded(item):
                        self.set_expanded(item, True, True, update_cache=False)

                for item in ordered_items:
                    if self._destroyed:
                        return False
                    if not self._tree_widget.is_expanded(item):
                        self.set_expanded(item, True, False, update_cache=False)

                if self._expansion_caching:
                    self._item_expansion_states = expansion_cache_state
                self._item_paths_by_hash = result.path_by_hash
                return True
            finally:
                self._suppress_model_change_sync = False
                self._suppress_selection_changed = False

    @staticmethod
    def _resolve_expansion_plan(
        expansion_state_by_hash: dict[int, bool],
        previous_path_by_hash: dict[int, str],
        item_by_hash: dict[int, TreeItemBase],
        items_by_path: dict[str, list[TreeItemBase]],
        root_items: list[TreeItemBase],
        expand_filtered_roots: bool,
        cancel_event: threading.Event,
    ) -> tuple[list[TreeItemBase], list[TreeItemBase], dict[int, bool]] | None:
        """
        Resolve cached expansion against one rebuilt tree.

        Args:
            expansion_state_by_hash: Expansion state captured from the current tree.
            previous_path_by_hash: Stable paths associated with the current tree hashes.
            item_by_hash: Rebuilt items indexed by hash.
            items_by_path: Rebuilt items indexed by stable path.
            root_items: Rebuilt root items.
            expand_filtered_roots: Whether roots with filtered children should expand recursively.
            cancel_event: Signal that stops resolution for a superseded refresh.

        Returns:
            Recursive roots, ancestor-first restored items, and replacement cache state, or None when cancelled.
        """
        target_items: dict[int, TreeItemBase] = {}
        for item_hash, expanded in expansion_state_by_hash.items():
            if cancel_event.is_set():
                return None
            if not expanded:
                continue

            exact_item = item_by_hash.get(item_hash)
            if exact_item is not None:
                target_items.setdefault(hash(exact_item), exact_item)

            path = previous_path_by_hash.get(item_hash)
            if path is None:
                continue
            for item in items_by_path.get(path, []):
                if cancel_event.is_set():
                    return None
                target_items.setdefault(hash(item), item)

        ordered_items = []
        ordered_hashes = set()
        for item in target_items.values():
            if cancel_event.is_set():
                return None

            item_chain = [item]
            parent = item.parent
            while parent:
                if cancel_event.is_set():
                    return None
                item_chain.append(parent)
                parent = parent.parent

            for chained_item in reversed(item_chain):
                item_hash = hash(chained_item)
                if item_hash in ordered_hashes:
                    continue
                ordered_hashes.add(item_hash)
                ordered_items.append(chained_item)

        recursive_items = []
        if expand_filtered_roots:
            for item in root_items:
                if cancel_event.is_set():
                    return None
                if item.children:
                    recursive_items.append(item)

        return recursive_items, ordered_items, dict.fromkeys(ordered_hashes, True)

    def iter_visible_items(self, recursive=True) -> Iterable[TreeItemBase]:
        """
        Iterate through all currently visible (expanded) items in the tree.

        Yields items in breadth-first order, respecting the expansion state of parent items.
        Only items whose parents are expanded will be yielded.

        Args:
            recursive: If True, recursively yields children of expanded items.
                If False, yields only top-level items.

        Yields:
            TreeItemBase: Each visible item in breadth-first traversal order.

        """
        stack = deque(self._model.get_item_children(item=None))
        if not stack:
            return

        while stack:
            item = stack.popleft()
            yield item
            if recursive and self._tree_widget.is_expanded(item):
                children = list(self._model.get_item_children(item=item))
                # NOTE: Reverse before extendleft() to preserve original order: extendleft([A,B,C])
                # inserts C, then B, then A at the front, yielding [A,B,C,...]. Without reversing,
                # children would appear in reverse order when popped.
                children.reverse()
                stack.extendleft(children)

    async def expand_to_items(self, items: Iterable[TreeItemBase], update_cache: bool = True):
        """
        Expand all parent items necessary to reveal the specified items.

        Traverses each item's ancestry and expands parents from root downward, ensuring proper render order. When a
        parent is newly expanded, waits two Kit updates for layout recalculation; otherwise, returns without waiting.

        Args:
            items: The items whose parents should be expanded.
            update_cache: Whether programmatic expansion should become the user's saved expansion state.
        """
        force_layout_recalculation = False
        expanded = set()
        for item in items:
            parent = item.parent
            ancestors = []
            while parent:
                ancestors.append(parent)
                parent = parent.parent

            # NOTE: we want to start from the root downwards
            # and make sure everything is expanded and rendered in order
            ancestors.reverse()
            for ancestor in ancestors:
                if ancestor in expanded:
                    continue
                expanded.add(ancestor)

                # Only trigger layout recalculation if we're actually expanding something new
                if not self._tree_widget.is_expanded(ancestor):
                    self.set_expanded(ancestor, True, False, update_cache=update_cache)
                    force_layout_recalculation = True

        if not force_layout_recalculation:
            return

        # NOTE: Force layout recalculation after expansion.
        #
        # When items are expanded via set_expanded(), the TreeView updates its internal
        # expansion state immediately, but the actual layout (computed_content_height,
        # scroll_y_max) isn't recalculated until the next render pass. For items at the
        # bottom of the tree, scrolling fails because scroll_y_max is still based on
        # the pre-expansion content size.
        #
        # dirty_widgets() invalidates the layout, forcing recalculation. The 2-frame
        # wait is required because:
        #   Frame 1: Layout invalidation is processed
        #   Frame 2: Render pass completes with updated dimensions
        #
        # This is the standard Kit UI pattern - there's no synchronous "wait for layout"
        # API or callback for "layout complete". Alternatives like _item_changed(None)
        # are heavier (full tree rebuild) and still require frame waits.

        self._tree_widget.dirty_widgets()
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()

    async def scroll_to_items(self, items: list[TreeItemBase], center_ratio: float = 0.2):
        """
        Scroll to reveal the first item in `items`.

        Args:
            items: The items to scroll to
            center_ratio: where to frame first item (0.0: top, 0.5: center, 1.0: bottom)
        """
        await omni.kit.app.get_app().next_update_async()
        if self._destroyed:
            return

        if self._update_content_size_task:
            self._update_content_size_task.cancel()

        items_set = set(items)
        for i, child in enumerate(self.iter_visible_items()):
            if child in items_set:
                idx_item = i
                break
        else:
            return

        # Find out how far down the first item's center is
        scroll_y = (idx_item + 0.5) * self._row_height
        # Since that would scroll to the item, subtract some height to center the item
        target_from_top = self._tree_scroll_frame.computed_content_height * center_ratio
        self._tree_scroll_frame.scroll_y = scroll_y - target_from_top

    async def _deferred_expansion_state_restore(self):
        """Restore cached expansion after one Kit update without changing the saved expansion state."""
        await omni.kit.app.get_app().next_update_async()

        for item in self.model.iter_items_children():
            item_hash = hash(item)
            expanded = item_hash in self._item_expansion_states
            if self._tree_widget.is_expanded(item) != expanded:
                self.set_expanded(item, expanded, False, update_cache=False)

    async def wait_for_model_change_sync(self):
        """Wait for pending model-change UI synchronization, if one exists.

        The task is absent before synchronization is scheduled and after teardown. If newer model publication
        replaces it while waiting, this follows the replacement. Caller cancellation propagates without cancelling
        widget-owned synchronization.
        """
        while model_change_sync_task := self._model_change_sync_task:
            try:
                await asyncio.shield(model_change_sync_task)
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling() or model_change_sync_task is self._model_change_sync_task:
                    raise
            if model_change_sync_task is self._model_change_sync_task:
                return

    async def _sync_ui_after_model_change(self, restore_expansion: bool = True):
        """
        Synchronize cached tree UI state after a model change.

        Args:
            restore_expansion: Whether the model change replaced the tree hierarchy.
        """
        if self._destroyed:
            return

        if self._suppress_model_change_sync:
            return

        if self._alternating_rows and self._alternating_row_widget:
            self._alternating_row_widget.refresh(item_count=self._model.get_children_count())

        if self._expansion_caching and restore_expansion:
            await self._deferred_expansion_state_restore()

    @omni.usd.handle_exception
    async def _update_content_size_deferred(self):
        """
        Update the scroll position when the content size changes to force the ScrollFrame to resize.
        """
        if self._destroyed:
            return

        # Sync the alternating row widget frame height with the tree frame
        if self._alternating_rows and self._alternating_row_widget:
            self._alternating_row_widget.sync_frame_height(self._tree_frame.computed_height)

        # Only update the scroll position when shrinking the frame
        if self._tree_widget.computed_height < self._previous_frame_height:
            # Cache the current scroll position
            previous_scroll_y = self._tree_scroll_frame.scroll_y
            # Scroll to the top of the tree
            self._tree_scroll_frame.scroll_y = 0
            # Wait for the updated widget to be drawn

            await omni.kit.app.get_app().next_update_async()
            if self._destroyed:
                return
            # Scroll to the bottom of the tree or the previous scroll position if still valid
            self._tree_scroll_frame.scroll_y = min(previous_scroll_y, self._tree_scroll_frame.scroll_y_max)
        # Cache the current frame height for the next update
        self._previous_frame_height = self._tree_widget.computed_height

    def _on_model_item_changed(self, _model: TreeModelBase, item: TreeItemBase | None) -> None:
        """
        Callback triggered when the model's items change.

        Refreshes alternating backgrounds only for structural invalidations. Updating one retained item cannot change
        the visible row count, so rebuilding every decorative row would cause unnecessary flicker.

        Args:
            _model: Model that emitted the invalidation.
            item: Changed retained item, or None when tree structure changed.
        """
        if self._destroyed:
            return
        if item is not None:
            return

        if self._suppress_model_change_sync:
            return

        if self._model_change_sync_task and not self._model_change_sync_task.done():
            self._model_change_sync_task.cancel()

        self._model_change_sync_task = ensure_future(self._sync_ui_after_model_change(restore_expansion=item is None))

    def subscribe_selection_changed(self, callback: Callable[[list[TreeItemBase]], None]):
        """
        Subscribe to selection change events.

        Args:
            callback: Function called when selection changes, receives
                the list of currently selected items.

        Returns:
            EventSubscription: Subscription handle. Keep a reference to
                maintain the subscription; releasing it unsubscribes.
        """

        def _on_selection_changed(items):
            if self._suppress_selection_changed:
                return
            callback(items)

        return self._tree_widget.subscribe_selection_changed(_on_selection_changed)

    def dirty_widgets(self, *args, **kwargs):
        """
        Mark the tree widget as dirty, forcing a redraw on the next frame.
        """
        return self._tree_widget.dirty_widgets(*args, **kwargs)

    def set_expanded(self, item, expanded, recursive, update_cache: bool = True):
        """
        Set the expansion state of an item.

        Args:
            item: The tree item to expand or collapse
            expanded: True to expand, False to collapse
            recursive: If True, also applies to all children
        """
        self._tree_widget.set_expanded(item, expanded, recursive)
        if self._expansion_caching and update_cache:
            items = [item]
            if recursive:
                items.extend(self._model.iter_items_children([item]))
            for i in items:
                item_hash = hash(i)
                if expanded:
                    self._item_expansion_states[item_hash] = True
                else:
                    self._item_expansion_states.pop(item_hash, None)

    def is_expanded(self, *args, **kwargs):
        """
        Check if an item is currently expanded.

        Args:
            item: The tree item to check

        Returns:
            True if the item is expanded, False otherwise.
        """
        return self._tree_widget.is_expanded(*args, **kwargs)

    def on_selection_changed(self, *args, **kwargs):
        """
        Handle selection changes in the tree widget.

        This method is called when the tree selection changes and handles
        auto-selecting children when `select_all_children=True`. Pass-through
        to the underlying TreeWidget.

        Args:
            items: The list of newly selected items.

        Note:
            When `select_all_children=False`, this is effectively a no-op.
            Typically called from a selection changed callback to ensure
            child selection behavior is applied.
        """
        return self._tree_widget.on_selection_changed(*args, **kwargs)

    def destroy(self) -> None:
        """Destroy owned subwidgets and release subscriptions and tasks."""
        self._destroyed = True
        if self._expansion_resolve_cancel_event:
            self._expansion_resolve_cancel_event.set()
            self._expansion_resolve_cancel_event = None
        if self._update_content_size_task:
            self._update_content_size_task.cancel()
            self._update_content_size_task = None
        if self._selection_update_task:
            self._selection_update_task.cancel()
            self._selection_update_task = None
        if self._model_change_sync_task:
            self._model_change_sync_task.cancel()
            self._model_change_sync_task = None

        self._app_window_size_changed_sub = None
        self._item_changed_sub = None
        self._item_expanded_sub = None

        if self._tree_widget is not None:
            self._tree_widget.destroy()
        if self._alternating_row_widget is not None:
            self._alternating_row_widget.destroy()
        if self._root_frame is not None:
            self._root_frame.clear()

        self._tree_widget = None
        self._tree_frame = None
        self._tree_scroll_frame = None
        self._root_frame = None
        self._alternating_row_widget = None
        self._model = None
        self._delegate = None

    def __del__(self):
        """Release resources when explicit destruction was omitted."""
        self.destroy()

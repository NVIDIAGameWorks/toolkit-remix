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

import asyncio
import uuid
from collections.abc import Callable, Coroutine, Iterable, Mapping

import carb
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation, JobState
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import Job, JobProgress
from omni.flux.utils.common import Event, EventSubscription
from omni.flux.utils.widget.tree_widget.model import TreeModelBase
from omni.kit.notification_manager import NotificationStatus, post_notification

from . import adapter_interaction
from .constants import (
    ACTIVE_APPLY_OPERATIONS,
    ADAPTER_ERRORS,
    AGGREGATE_PRECEDENCE,
    ALL_APPLY_FILTERS,
    APPLY_DISPOSITION_TO_DISPLAY,
    APPLY_OPERATION_TO_DISPLAY,
    FAILED_FILTER_STATES,
    GRAPH_DELETE_ERRORS,
    HANDLER_AVAILABILITY_ERRORS,
    JOB_STATE_TO_DISPLAY,
    OPERATION_ERRORS,
    READY_TO_APPLY_FILTER_STATES,
    SNAPSHOT_READ_ERRORS,
    TASK_SCHEDULING_ERRORS,
    TERMINAL_JOB_STATES,
    UUID_TEXT_PATTERN,
)
from .enums import BulkOperationPhase, DisplayState
from .queue_item import QueueGraphItem, QueueItem
from .row import Row

__all__ = ("QueueModel",)


class QueueModel(TreeModelBase):
    """Expose durable job graphs as stable native TreeView items."""

    def __init__(self, interface: QueueInterface, apply_executor: ApplyExecutor, context_name: str) -> None:
        """Initialize a hierarchical queue model.

        Args:
            interface: Typed queue API used for snapshots and graph mutations.
            apply_executor: Result executor used by Check and X actions.
            context_name: USD context supplied to product display adapters.
        """
        super().__init__()
        self.interface = interface
        self.apply_executor = apply_executor
        self.context_name = context_name
        self._graphs_by_id: dict[uuid.UUID, QueueGraphItem] = {}
        self._items_by_id: dict[uuid.UUID, QueueItem] = {}
        self._all_graphs: list[QueueGraphItem] = []
        self._all_items: list[QueueItem] = []
        self._visible_children_by_graph: dict[uuid.UUID, list[QueueItem]] = {}
        self._visible_job_ids: set[uuid.UUID] = set()
        self._visible_graph_names: set[str] | None = None
        self._visible_job_stage_names: set[str] | None = None
        self._visible_states: set[DisplayState] | None = None
        self._visible_apply_dispositions: set[ApplyDisposition] = set(ALL_APPLY_FILTERS)
        self._search_text = ""
        self._busy_job_ids: dict[uuid.UUID, object] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._selected_items: list[QueueGraphItem | QueueItem] = []
        self._selection_changed_event = Event()
        self._reveal_item_event = Event()
        self._progress_changed_event = Event()
        self._schedule_condition_keys: dict[uuid.UUID, tuple[object, ...]] = {}
        self._handler_availability: dict[uuid.UUID, bool] = {}

    @property
    def default_attr(self) -> dict[str, None]:
        """Return the base tree root storage initialized before model setup.

        Returns:
            Default lifecycle attribute mapping.
        """
        return {"_items": None}

    @property
    def all_graphs(self) -> list[QueueGraphItem]:
        """Return graph roots in durable display order.

        Returns:
            All graph roots.
        """
        return self._all_graphs

    @property
    def all_items(self) -> list[QueueItem]:
        """Return every job child in graph and topological order.

        Returns:
            All job children.
        """
        return self._all_items

    @property
    def visible_job_items(self) -> list[QueueItem]:
        """Return the current filtered child set in tree order.

        Returns:
            Visible job children.
        """
        return [child for graph in self._items for child in self._visible_children_by_graph.get(graph.graph_id, ())]

    def is_item_visible(self, item: QueueItem) -> bool:
        """Return whether one child passes the active filters.

        Args:
            item: Existing queue child.

        Returns:
            Whether the child is currently exposed to the native tree.
        """
        return item.row.job_id in self._visible_job_ids

    @property
    def selected_items(self) -> list[QueueGraphItem | QueueItem]:
        """Return the current model-owned selection in TreeView order.

        Returns:
            Copy of selected graph/job items.
        """
        return list(self._selected_items)

    @property
    def visible_states(self) -> set[DisplayState] | None:
        """Return the active status filter, or None for all states.

        Returns:
            Selected states, or None for All.
        """
        return self._visible_states

    @property
    def visible_graph_names(self) -> set[str] | None:
        """Return graph names accepted by the Job / Stage filter.

        Returns:
            Selected graph names, or None for every graph.
        """
        return self._visible_graph_names

    @property
    def visible_job_stage_names(self) -> set[str] | None:
        """Return child names accepted by the Job / Stage filter.

        Returns:
            Selected child-stage names, or None for every stage.
        """
        return self._visible_job_stage_names

    @property
    def visible_apply_dispositions(self) -> set[ApplyDisposition]:
        """Return apply dispositions accepted by the active filter.

        Returns:
            Accepted durable Apply dispositions.
        """
        return self._visible_apply_dispositions

    @property
    def search_text(self) -> str:
        """Return the literal graph/stage search text.

        Returns:
            Current search text.
        """
        return self._search_text

    @property
    def filters_active(self) -> bool:
        """Return whether any centralized queue filter differs from its default.

        Returns:
            Whether Reset All has work to do.
        """
        return bool(
            self._search_text
            or self._visible_graph_names is not None
            or self._visible_job_stage_names is not None
            or self._visible_states is not None
            or self._visible_apply_dispositions != ALL_APPLY_FILTERS
        )

    def refresh(self, force: bool = False) -> None:
        """Synchronize the full hierarchy while preserving items by durable IDs.

        Args:
            force: Whether to invalidate every visible item after synchronization.
        """
        previous_selection = list(self._selected_items)
        self._handler_availability.clear()
        snapshots = self.interface.get_graph_snapshots()
        remaining_graphs = dict(self._graphs_by_id)
        remaining_items = dict(self._items_by_id)
        next_graphs: list[QueueGraphItem] = []
        next_items: list[QueueItem] = []

        for graph_snapshot in snapshots:
            graph = remaining_graphs.pop(graph_snapshot.graph_id, None)
            if graph is None:
                graph = QueueGraphItem(graph_snapshot.graph_id, graph_snapshot.name, graph_snapshot.position)
            else:
                graph.name = graph_snapshot.name
                graph.position = graph_snapshot.position
                graph.clear_children()
            next_graphs.append(graph)

            for snapshot in graph_snapshot.jobs:
                fresh_row = Row.from_snapshot(snapshot, self.interface)
                child = remaining_items.pop(snapshot.job_id, None)
                if child is None:
                    child = QueueItem(fresh_row, parent=graph)
                else:
                    child.row.update_from(fresh_row)
                    child.parent = graph
                next_items.append(child)

        for child in remaining_items.values():
            child.parent = None
        for graph in remaining_graphs.values():
            graph.clear_children()

        self._all_graphs = next_graphs
        self._all_items = next_items
        self._graphs_by_id = {graph.graph_id: graph for graph in next_graphs}
        self._items_by_id = {item.row.job_id: item for item in next_items}
        membership_changed = self._apply_filters(notify=False)
        self._schedule_condition_keys = {item.row.job_id: self._schedule_condition_key(item) for item in next_items}
        available_items = set(next_graphs) | set(next_items)
        next_selection = [item for item in previous_selection if item in available_items]
        if next_selection != previous_selection:
            self.set_items_selected(next_selection)
        if membership_changed:
            self._item_changed(None)
        if force:
            self.invalidate_visible_items()

    def invalidate_visible_items(self) -> None:
        """Rebuild every visible cell after a display preference changes."""
        for graph in self._items:
            self._item_changed(graph)
            for child in self.get_item_children(graph):
                self._item_changed(child)

    def update_item(self, job_id: uuid.UUID, force_notify: bool = False) -> None:
        """Refresh one changed child and its aggregate graph root.

        Args:
            job_id: Durable job identifier received from a queue event.
            force_notify: Whether to invalidate even when snapshot values are unchanged.
        """
        child = self._items_by_id.get(job_id)
        if child is None:
            self.refresh()
            return
        try:
            snapshot = self.interface.get_job_snapshot(job_id)
        except SNAPSHOT_READ_ERRORS:
            self.refresh()
            return
        self._handler_availability.pop(job_id, None)
        changed = child.row.update_from(Row.from_snapshot(snapshot, self.interface))
        parent = child.parent
        membership_changed = self._update_filter_membership(child)
        if changed or force_notify:
            self._schedule_condition_keys[job_id] = self._schedule_condition_key(child)
            if membership_changed:
                self._item_changed(None)
                return
            if job_id in self._visible_job_ids:
                self._item_changed(child)
            if parent is not None and parent in self._items:
                self._item_changed(parent)

    def update_progress_batch(self, updates: Mapping[uuid.UUID, JobProgress]) -> set[uuid.UUID]:
        """Update committed progress without rebuilding native tree cells.

        Args:
            updates: Latest committed progress keyed by durable job identifier.

        Returns:
            Job identifiers that are not represented by this model.
        """
        missing: set[uuid.UUID] = set()
        changed_items: list[QueueItem] = []
        for job_id, progress in updates.items():
            child = self._items_by_id.get(job_id)
            if child is None:
                missing.add(job_id)
                continue
            if child.row.progress == progress:
                continue
            child.row.progress = progress
            self._schedule_condition_keys[job_id] = self._schedule_condition_key(child)
            changed_items.append(child)
        if changed_items:
            self._progress_changed_event(tuple(changed_items))
        return missing

    def refresh_schedule_conditions(self, job_types: set[type[Job]] | None = None) -> None:
        """Rebuild changed readiness rows, optionally limited to exact adapter job types.

        Args:
            job_types: Exact adapter job types to evaluate, or None to evaluate every row.
        """
        self._handler_availability.clear()
        changed_items: list[QueueItem] = []
        filter_key_changed = False
        for item in self._all_items:
            adapter = item.row.adapter
            if job_types is not None and (adapter is None or adapter.job_type not in job_types):
                continue
            job_id = item.row.job_id
            previous_key = self._schedule_condition_keys.get(job_id)
            current_key = self._schedule_condition_key(item)
            self._schedule_condition_keys[job_id] = current_key
            if previous_key == current_key:
                continue
            changed_items.append(item)
            filter_key_changed = filter_key_changed or previous_key is None or previous_key[:2] != current_key[:2]

        membership_changed = self._apply_filters() if filter_key_changed else False
        if membership_changed:
            return
        changed_parents = {
            item.parent for item in changed_items if item.parent is not None and item.parent in self._items
        }
        for item in changed_items:
            if item.row.job_id in self._visible_job_ids:
                self._item_changed(item)
        for parent in changed_parents:
            self._item_changed(parent)

    def _schedule_condition_key(self, item: QueueItem) -> tuple[object, ...]:
        """Return presentation values affected by external scheduler conditions.

        Args:
            item: Job row whose adapter-owned readiness and actions are evaluated.

        Returns:
            Comparable state, help, and action values.
        """
        row = item.row
        state = self.resolve_display_state(row)
        apply_block_reason = (
            self.get_check_block_reason(item, allow_reapply=True) if row.job_id in self._visible_job_ids else None
        )
        return (
            state,
            row.apply_disposition,
            self.get_status_label(row, state),
            self.get_state_tooltip(row, state),
            adapter_interaction.get_graph_actions(row, self.context_name),
            adapter_interaction.get_job_actions(row, self.context_name),
            apply_block_reason,
        )

    def _update_filter_membership(self, item: QueueItem) -> bool:
        """Evaluate one changed row against active filters and update only its graph membership.

        Args:
            item: Existing child whose filter-relevant state may have changed.

        Returns:
            Whether visible tree membership changed.
        """
        parent = item.parent
        if parent is None:
            return False
        currently_visible = item.row.job_id in self._visible_job_ids
        should_be_visible = self._matches_filters(item)
        if currently_visible == should_be_visible:
            return False

        visible_children = self._visible_children_by_graph[parent.graph_id]
        if should_be_visible:
            insertion = next(
                (index for index, child in enumerate(visible_children) if child.row.position > item.row.position),
                len(visible_children),
            )
            visible_children.insert(insertion, item)
            self._visible_job_ids.add(item.row.job_id)
            if parent not in self._items:
                graph_insertion = next(
                    (index for index, graph in enumerate(self._items) if graph.position > parent.position),
                    len(self._items),
                )
                self._items.insert(graph_insertion, parent)
        else:
            visible_children.remove(item)
            self._visible_job_ids.remove(item.row.job_id)
            if not visible_children:
                self._items.remove(parent)
        return True

    def has_item(self, job_id: uuid.UUID) -> bool:
        """Return whether the hierarchy contains a child with ``job_id``.

        Args:
            job_id: Durable job identifier.

        Returns:
            Whether the child is known.
        """
        return job_id in self._items_by_id

    def get_item_value_model_count(self, _item: QueueGraphItem | QueueItem) -> int:
        """Return the number of compact queue columns.

        Args:
            _item: Native item requesting its column count.

        Returns:
            Visible column count.
        """
        return len(Row.keys())

    def get_item_children(self, item: QueueGraphItem | QueueItem | None = None):
        """Return visible roots or filtered children for one root.

        Args:
            item: Graph root, job leaf, or None for roots.

        Returns:
            Visible roots/children, or an empty list for a leaf.
        """
        if item is None:
            return self._items
        if isinstance(item, QueueGraphItem):
            return self._visible_children_by_graph.get(item.graph_id, [])
        return []

    def get_children_count(self, items=None, recursive: bool = True) -> int:
        """Count only rows currently visible through the active filters.

        Args:
            items: Optional root subset.
            recursive: Whether visible children are included.

        Returns:
            Visible row count.
        """
        roots = list(self._items if items is None else items)
        if not recursive:
            return len(roots)
        return len(roots) + sum(len(self.get_item_children(root)) for root in roots if isinstance(root, QueueGraphItem))

    def iter_items_children(self, items=None, recursive: bool = True):
        """Iterate visible tree rows using the same hierarchy supplied to TreeView.

        Args:
            items: Optional root subset.
            recursive: Whether visible children are included.

        Yields:
            Visible graph roots and/or children.
        """
        roots = list(self._items if items is None else items)
        if items is None:
            yield from roots
            if not recursive:
                return
        for root in roots:
            children = self.get_item_children(root)
            yield from children

    def resolve_display_state(self, row: Row) -> DisplayState:
        """Resolve core execution and Apply lifecycle into one user-facing state.

        Args:
            row: Child presentation data.

        Returns:
            Resolved display state.
        """
        if row.is_corrupted:
            return DisplayState.CORRUPTED
        if row.state is JobState.QUEUED and self.get_waiting_reason(row):
            return DisplayState.WAITING
        if (
            row.state is JobState.DONE
            and row.apply_operation
            in (
                ApplyOperation.IDLE,
                ApplyOperation.APPLY_FAILED,
                ApplyOperation.REAPPLY_FAILED,
                ApplyOperation.REVERT_FAILED,
            )
            and row.apply_disposition in (ApplyDisposition.PENDING, ApplyDisposition.APPLIED, ApplyDisposition.DECLINED)
            and not self._is_handler_available(row)
        ):
            return DisplayState.HANDLER_UNAVAILABLE
        if row.apply_operation in APPLY_OPERATION_TO_DISPLAY:
            return APPLY_OPERATION_TO_DISPLAY[row.apply_operation]
        if row.state is JobState.DONE:
            return APPLY_DISPOSITION_TO_DISPLAY.get(row.apply_disposition, DisplayState.DONE)
        return JOB_STATE_TO_DISPLAY.get(row.state, DisplayState.QUEUED)

    def get_waiting_reason(self, row: Row) -> str | None:
        """Return adapter-owned safe waiting text for a queued job.

        Args:
            row: Queued child presentation data.

        Returns:
            Product waiting reason, or None.
        """
        if row.state is not JobState.QUEUED or row.adapter is None or row.job is None:
            return None
        try:
            return row.adapter.get_waiting_reason(row.job, self.context_name)
        except ADAPTER_ERRORS as error:
            carb.log_warn(f"Could not resolve waiting text for queue job {row.job_id}: {error}")
            return None

    def resolve_graph_display_state(self, graph: QueueGraphItem) -> DisplayState:
        """Aggregate a graph state from all children, including filtered-out children.

        Args:
            graph: Graph root to aggregate.

        Returns:
            Decisive aggregate display state.
        """
        children = graph.children
        child_states = {self.resolve_display_state(child.row) for child in children}
        decisive = next((state for state in AGGREGATE_PRECEDENCE if state in child_states), None)
        if decisive is not None:
            return decisive
        graph_disposition = self.resolve_graph_apply_disposition(graph)
        if graph_disposition is ApplyDisposition.APPLIED:
            return DisplayState.APPLIED
        if graph_disposition is ApplyDisposition.DECLINED:
            return DisplayState.DECLINED
        applicable = [
            child.row.apply_disposition
            for child in children
            if child.row.apply_disposition not in (ApplyDisposition.NOT_READY, ApplyDisposition.NOT_APPLICABLE)
        ]
        if applicable and all(value in (ApplyDisposition.APPLIED, ApplyDisposition.DECLINED) for value in applicable):
            return DisplayState.PARTIALLY_APPLIED
        if any(child.row.state is JobState.SKIPPED for child in children):
            return DisplayState.SKIPPED
        return DisplayState.DONE

    @staticmethod
    def resolve_graph_apply_disposition(graph: QueueGraphItem) -> ApplyDisposition | None:
        """Return the shared stable Apply disposition of a graph's applicable children.

        Args:
            graph: Graph root whose complete child set defines the result.

        Returns:
            Shared disposition, or None when the graph has no applicable children or mixed dispositions.
        """
        applicable = {
            child.row.apply_disposition
            for child in graph.children
            if child.row.apply_disposition not in (ApplyDisposition.NOT_READY, ApplyDisposition.NOT_APPLICABLE)
        }
        return next(iter(applicable)) if len(applicable) == 1 else None

    def get_status_label(self, row: Row, state: DisplayState | None = None) -> str:
        """Return an adapter-specific active label with a generic fallback.

        Args:
            row: Child presentation data.
            state: Optional pre-resolved state.

        Returns:
            Safe user-facing status label.
        """
        state = state or self.resolve_display_state(row)
        label = self._get_base_status_label(row, state)
        progress_label = self.get_active_progress_label(row)
        if progress_label is None and state is DisplayState.IN_PROGRESS and row.progress is not None:
            progress_label = row.progress.detail or None
        if (
            progress_label is None
            and row.progress is not None
            and row.progress.completed is not None
            and row.progress.total is not None
        ):
            progress_label = f"{row.progress.completed}/{row.progress.total}"
        return f"{label} · {progress_label}" if progress_label else label

    @staticmethod
    def _get_base_status_label(row: Row, state: DisplayState) -> str:
        """Return the state label before progress is appended.

        Args:
            row: Child presentation data.
            state: Resolved display state.

        Returns:
            Adapter-specific active state label or the generic state label.
        """
        label = state.label
        if state is DisplayState.IN_PROGRESS and row.adapter is not None and row.job is not None:
            try:
                active_label = row.adapter.get_active_status_label(row.job, row.progress)
            except ADAPTER_ERRORS as error:
                carb.log_warn(f"Could not resolve active status text for queue job {row.job_id}: {error}")
                active_label = None
            if active_label:
                label = active_label
        return label

    @staticmethod
    def get_name_tooltip(row: Row) -> str:
        """Return adapter name help without allowing product failures into rendering.

        Args:
            row: Child presentation data.

        Returns:
            Safe name tooltip.
        """
        if row.adapter is None or row.job is None:
            return row.name
        try:
            return row.adapter.get_name_tooltip(row.job)
        except ADAPTER_ERRORS as error:
            carb.log_warn(f"Could not resolve name help for queue job {row.job_id}: {error}")
            return row.name

    @staticmethod
    def get_active_progress_label(row: Row) -> str | None:
        """Return safe adapter progress text for one active row.

        Args:
            row: Child presentation data.

        Returns:
            Safe active progress label, or None.
        """
        if row.state is not JobState.IN_PROGRESS or row.adapter is None or row.job is None:
            return None
        try:
            return row.adapter.get_active_progress_label(row.job, row.progress)
        except ADAPTER_ERRORS as error:
            carb.log_warn(f"Could not resolve active progress text for queue job {row.job_id}: {error}")
            return None

    def get_graph_status_label(self, graph: QueueGraphItem) -> str:
        """Return the decisive active child's product label for a graph root.

        Args:
            graph: Graph root to label.

        Returns:
            Safe aggregate status label.
        """
        state = self.resolve_graph_display_state(graph)
        label = state.label
        if state is DisplayState.IN_PROGRESS:
            decisive = next(
                (
                    child
                    for child in graph.children
                    if self.resolve_display_state(child.row) is DisplayState.IN_PROGRESS
                ),
                None,
            )
            if decisive is not None:
                label = self._get_base_status_label(decisive.row, state)
        completed = sum(child.row.state in TERMINAL_JOB_STATES for child in graph.children)
        total = len(graph.children)
        unit = "job" if total == 1 else "jobs"
        return f"{label} · {completed}/{total} {unit}"

    def get_state_tooltip(self, row: Row, display_state: DisplayState | None = None) -> str:
        """Return concise state help with adapter specialization when available.

        Args:
            row: Child presentation data.
            display_state: Optional pre-resolved state.

        Returns:
            Safe user-facing state explanation.
        """
        state = display_state or self.resolve_display_state(row)
        if state is DisplayState.WAITING:
            return self.get_waiting_reason(row) or state.detail_tooltip or ""
        if row.adapter is not None and row.job is not None:
            try:
                tooltip = row.adapter.get_state_tooltip(row.job, state, row.state_reason)
            except ADAPTER_ERRORS as error:
                carb.log_warn(f"Could not resolve state help for queue job {row.job_id}: {error}")
                tooltip = None
            if tooltip:
                return tooltip
        if (
            state
            in (
                DisplayState.APPLY_FAILED,
                DisplayState.REAPPLY_FAILED,
                DisplayState.REVERT_FAILED,
            )
            and row.apply_reason
        ):
            return self._safe_reason(row.apply_reason)
        if (
            state in (DisplayState.FAILED, DisplayState.SKIPPED, DisplayState.WAITING_FOR_DEPENDENCIES)
            and row.state_reason
        ):
            return self._safe_reason(row.state_reason)
        return state.detail_tooltip or state.tooltip or ""

    @staticmethod
    def _safe_reason(reason: str) -> str:
        """Remove durable identifiers from otherwise user-facing status text.

        Args:
            reason: Persisted sanitized status reason.

        Returns:
            Reason with any UUID replaced by readable generic text.
        """
        return UUID_TEXT_PATTERN.sub("another job", reason)

    def get_graph_state_tooltip(self, graph: QueueGraphItem) -> str:
        """Explain the decisive aggregate state and whether its child is hidden.

        Args:
            graph: Graph root to explain.

        Returns:
            Safe aggregate state explanation.
        """
        state = self.resolve_graph_display_state(graph)
        counts: dict[str, int] = {}
        for child in graph.children:
            child_state = self.resolve_display_state(child.row)
            counts[child_state.label] = counts.get(child_state.label, 0) + 1
        summary = ", ".join(f"{label}: {count}" for label, count in counts.items())
        decisive = [child for child in graph.children if self.resolve_display_state(child.row) is state]
        visible = set(self._visible_children_by_graph.get(graph.graph_id, ()))
        hidden_descriptions = [
            f"{child.row.name}: {self.get_state_tooltip(child.row, state)}"
            for child in decisive
            if child not in visible
        ]
        hidden = (
            f" Hidden decisive jobs: {'; '.join(hidden_descriptions)} (hidden by the current filters)."
            if hidden_descriptions
            else ""
        )
        return f"{summary}.{hidden}"

    def set_status_filter(self, states: set[DisplayState] | None) -> None:
        """Set accepted status groups; None accepts every status.

        Args:
            states: Accepted statuses, or None for All.
        """
        self._visible_states = states
        self._apply_filters()

    def set_job_stage_filter(self, graph_names: set[str] | None, stage_names: set[str] | None) -> None:
        """Set the graph names and child stages accepted by the combined column filter.

        Args:
            graph_names: Accepted graph names, or None for every graph.
            stage_names: Accepted child names, or None for every stage.
        """
        self._visible_graph_names = graph_names
        self._visible_job_stage_names = stage_names
        self._apply_filters()

    def clear_filters(self) -> None:
        """Restore every filter group and refresh visible membership once."""
        self._search_text = ""
        self._visible_graph_names = None
        self._visible_job_stage_names = None
        self._visible_states = None
        self._visible_apply_dispositions = set(ALL_APPLY_FILTERS)
        self._apply_filters()

    def set_search_filter(self, text: str) -> None:
        """Filter graph and adapter-rendered stage names by literal text.

        Args:
            text: Case-insensitive text contained by a graph or stage name.
        """
        self._search_text = text.strip()
        self._apply_filters()

    def get_graph_filter_options(self) -> tuple[str, ...]:
        """Return unique graph names in durable display order.

        Returns:
            Graph filter options.
        """
        return tuple(dict.fromkeys(graph.name for graph in self._all_graphs))

    def get_stage_filter_options(self) -> tuple[str, ...]:
        """Return unique child-stage names in display order.

        Returns:
            Child-stage filter options.
        """
        return tuple(dict.fromkeys(item.row.name for item in self._all_items))

    def set_apply_filter(self, dispositions: set[ApplyDisposition]) -> None:
        """Set accepted durable Apply dispositions.

        Args:
            dispositions: Accepted durable dispositions.
        """
        self._visible_apply_dispositions = dispositions
        self._apply_filters()

    def _matches_filters(self, item: QueueItem) -> bool:
        """Return whether one child satisfies every active filter.

        Args:
            item: Child to evaluate.

        Returns:
            Whether the child remains visible.
        """
        row = item.row
        graph_name = row.graph_name
        if self._search_text:
            search_text = self._search_text.casefold()
            if search_text not in graph_name.casefold() and search_text not in row.name.casefold():
                return False
        if self._visible_graph_names is not None and graph_name not in self._visible_graph_names:
            return False
        if self._visible_job_stage_names is not None and row.name not in self._visible_job_stage_names:
            return False
        if self._visible_states is not None:
            state = self.resolve_display_state(row)
            if not any(self._matches_status_group(state, filter_state) for filter_state in self._visible_states):
                return False
        return row.apply_disposition in self._visible_apply_dispositions

    @staticmethod
    def _matches_status_group(state: DisplayState, filter_state: DisplayState) -> bool:
        """Return whether a display state belongs to one filter group.

        Args:
            state: Resolved child display state.
            filter_state: Selected direct or grouped status option.

        Returns:
            Whether the filter accepts the state.
        """
        if filter_state is DisplayState.READY_TO_APPLY:
            return state in READY_TO_APPLY_FILTER_STATES
        if filter_state is DisplayState.FAILED:
            return state in FAILED_FILTER_STATES
        return state is filter_state

    def _filter_key(self, item: QueueItem) -> tuple[DisplayState, ApplyDisposition]:
        """Return values that can change filter membership.

        Args:
            item: Child whose membership key is requested.

        Returns:
            Status and Apply-disposition key.
        """
        row = item.row
        return self.resolve_display_state(row), row.apply_disposition

    def _apply_filters(self, notify: bool = True) -> bool:
        """Rebuild visible roots and children from current filter state.

        Args:
            notify: Whether structural membership changes invalidate the tree root.

        Returns:
            Whether root or child membership changed.
        """
        previous_roots = tuple(self._items)
        previous_children = {
            graph_id: tuple(children) for graph_id, children in self._visible_children_by_graph.items()
        }
        visible_children = {
            graph.graph_id: [child for child in graph.children if self._matches_filters(child)]
            for graph in self._all_graphs
        }
        self._visible_children_by_graph = visible_children
        self._visible_job_ids = {child.row.job_id for children in visible_children.values() for child in children}
        self._items = [graph for graph in self._all_graphs if visible_children[graph.graph_id]]
        membership_changed = previous_roots != tuple(self._items) or previous_children != {
            graph_id: tuple(children) for graph_id, children in visible_children.items()
        }
        if notify and membership_changed:
            self._item_changed(None)
        return membership_changed

    def is_busy(self, item: QueueItem) -> bool:
        """Return whether this widget owns an unfinished async action for a child.

        Args:
            item: Child to inspect.

        Returns:
            Whether an action is in flight.
        """
        return item.row.job_id in self._busy_job_ids

    def can_delete_graph(self, graph: QueueGraphItem) -> bool:
        """Return whether every child is idle for whole-graph deletion.

        Args:
            graph: Graph root to inspect.

        Returns:
            Whether deletion may start.
        """
        return all(
            child.row.state not in (JobState.SCHEDULED, JobState.IN_PROGRESS)
            and child.row.apply_operation not in ACTIVE_APPLY_OPERATIONS
            and not self.is_busy(child)
            for child in graph.children
        )

    def get_delete_action_graphs(self, anchor: QueueGraphItem) -> tuple[QueueGraphItem, ...]:
        """Return the selected roots owned by an anchored Delete action.

        Args:
            anchor: Graph whose row contains the invoked action.

        Returns:
            Selected roots in tree order when the anchor is selected, otherwise only the anchor.
        """
        if anchor not in self._selected_items:
            return (anchor,)
        selected = {item for item in self._selected_items if isinstance(item, QueueGraphItem)}
        return tuple(graph for graph in self._all_graphs if graph in selected)

    def can_delete_graphs(self, graphs: tuple[QueueGraphItem, ...]) -> bool:
        """Return whether every selected root remains idle and available.

        Args:
            graphs: Exact root selection captured by one action.

        Returns:
            Whether the complete selection may be deleted atomically.
        """
        return bool(graphs) and all(graph in self._all_graphs and self.can_delete_graph(graph) for graph in graphs)

    def delete_graphs(self, graphs: tuple[QueueGraphItem, ...]) -> None:
        """Schedule atomic graph and artifact deletion off the UI thread.

        Args:
            graphs: Idle graphs selected for deletion.
        """
        if self.can_delete_graphs(graphs):
            deleted_graphs = set(graphs)
            retained_selection = [
                item
                for item in self._selected_items
                if item not in deleted_graphs and not (isinstance(item, QueueItem) and item.parent in deleted_graphs)
            ]
            if retained_selection != self._selected_items:
                self.set_items_selected(retained_selection)
            children = tuple(child for graph in graphs for child in graph.children)
            self._schedule_reserved(self._delete_graphs(graphs), children)

    def get_graphs_artifact_file_count(
        self,
        graphs: tuple[QueueGraphItem, ...],
        on_complete: Callable[[int], None],
    ) -> None:
        """Request an exact core-owned file count without blocking the UI thread.

        Args:
            graphs: Graphs whose queue-owned output files should be counted.
            on_complete: Callback receiving the exact recursive regular-file count.
        """
        self._retain_background_task(self._get_graphs_artifact_file_count(graphs, on_complete))

    async def _get_graphs_artifact_file_count(
        self,
        graphs: tuple[QueueGraphItem, ...],
        on_complete: Callable[[int], None],
    ) -> None:
        """Inventory selected graphs through core and report completion on the UI loop.

        Args:
            graphs: Graphs whose queue-owned output files should be counted.
            on_complete: Callback receiving the exact recursive regular-file count.
        """
        graph_ids = tuple(graph.graph_id for graph in graphs)
        try:
            file_count = await asyncio.to_thread(self.interface.get_graphs_artifact_file_count, graph_ids)
        except GRAPH_DELETE_ERRORS as error:
            carb.log_warn(f"Could not inventory queue output files for graphs {graph_ids}: {error}")
            self._notify_inventory_failure(len(graphs))
            return
        on_complete(file_count)

    async def _delete_graphs(self, graphs: tuple[QueueGraphItem, ...]) -> None:
        """Delete selected graphs through core and report the committed outcome.

        Args:
            graphs: Idle graphs selected for deletion.
        """
        graph_ids = tuple(graph.graph_id for graph in graphs)
        try:
            retained_cleanup_paths = await asyncio.to_thread(self.interface.delete_graphs, graph_ids)
        except GRAPH_DELETE_ERRORS as error:
            carb.log_warn(f"Could not delete queue graphs {graph_ids}: {error}")
            graph_count = len(graphs)
            post_notification(
                f"Could not delete {graph_count} selected graph{'s' if graph_count != 1 else ''}. "
                "Their jobs and output folders were not changed.",
                status=NotificationStatus.WARNING,
            )
            return
        self.refresh()
        if retained_cleanup_paths:
            graph_count = len(graphs)
            paths = '", "'.join(str(path) for path in retained_cleanup_paths)
            post_notification(
                f"Deleted {graph_count} selected graph{'s' if graph_count != 1 else ''}, but inactive output "
                f'folders remain at "{paths}". Cleanup will be retried when the job queue starts.',
                status=NotificationStatus.WARNING,
            )

    @staticmethod
    def _notify_inventory_failure(graph_count: int) -> None:
        """Report that deletion stopped before mutation because inventory was incomplete.

        Args:
            graph_count: Number of selected graphs that remained unchanged.
        """
        post_notification(
            f"Could not inspect all output files for {graph_count} selected graph"
            f"{'s' if graph_count != 1 else ''}. Their jobs and files were not changed.",
            status=NotificationStatus.WARNING,
        )

    def apply_item(self, item: QueueItem) -> None:
        """Apply, retry, or reapply one child without blocking the UI callback.

        Args:
            item: Eligible child targeted by Check.
        """
        if self.can_check_item(item, allow_reapply=True):
            self._schedule_reserved(self._run_single("Apply", item, self.apply_executor.apply), (item,))

    def decline_item(self, item: QueueItem) -> None:
        """Decline pending results or revert applied results for one child.

        Args:
            item: Eligible child targeted by X.
        """
        if not self.can_x_item(item):
            return
        if item.row.apply_disposition is ApplyDisposition.PENDING:
            self._schedule_reserved(self._run_single("Decline", item, self.apply_executor.decline), (item,))
        elif item.row.apply_disposition is ApplyDisposition.APPLIED:
            self._schedule_reserved(self._run_single("Revert", item, self.apply_executor.revert), (item,))

    def revert_item(self, item: QueueItem) -> None:
        """Schedule the exact Revert action captured by a confirmation prompt.

        Args:
            item: Child confirmed for Revert.
        """
        self._schedule_reserved(self._run_single("Revert", item, self.apply_executor.revert), (item,))

    def apply_items(self, items: Iterable[QueueItem], scope: str) -> asyncio.Task[None]:
        """Capture and schedule currently matching Apply or Reapply children.

        Args:
            items: Current matching child sequence captured by the caller.
            scope: Human-readable filter scope included in notifications.

        Returns:
            Scheduled task that settles after every captured item is handled.
        """
        captured = self._unique_items(items)
        candidates = tuple(item for item in captured if self.can_check_item(item, allow_reapply=True))
        skipped = len(captured) - len(candidates)
        return self._schedule_reserved(self._run_bulk_check(candidates, scope, skipped), candidates)

    def group_decline_or_revert_items(
        self, items: Iterable[QueueItem]
    ) -> tuple[tuple[QueueItem, ...], tuple[QueueItem, ...], int]:
        """Capture exact Decline, Revert, and skip groups from current state.

        Args:
            items: Current matching child sequence captured by the caller.

        Returns:
            Pending items to Decline, applied items to Revert, and skipped count.
        """
        captured = self._unique_items(items)
        actionable = tuple(item for item in captured if self.can_x_item(item))
        declines = tuple(item for item in actionable if item.row.apply_disposition is ApplyDisposition.PENDING)
        reverts = tuple(item for item in actionable if item.row.apply_disposition is ApplyDisposition.APPLIED)
        skipped = len(captured) - len(declines) - len(reverts)
        return declines, reverts, skipped

    def decline_or_revert_items(
        self,
        declines: tuple[QueueItem, ...],
        reverts: tuple[QueueItem, ...],
        skipped: int,
        scope: str,
    ) -> asyncio.Task[None]:
        """Schedule exact action groups captured before any confirmation delay.

        Args:
            declines: Items confirmed for Decline.
            reverts: Items confirmed for Revert.
            skipped: Items confirmed as unavailable.
            scope: Human-readable filter scope included in notifications.

        Returns:
            Scheduled task that settles after every confirmed action is handled.
        """
        actionable = (*declines, *reverts)
        return self._schedule_reserved(self._run_bulk_x(declines, reverts, scope, skipped), actionable)

    def can_check_item(self, item: QueueItem, allow_reapply: bool) -> bool:
        """Return whether Check can Apply or Reapply one child.

        Args:
            item: Child to inspect.
            allow_reapply: Whether already-applied results remain eligible.

        Returns:
            Whether Check is executable.
        """
        return self.get_check_block_reason(item, allow_reapply) is None

    def get_check_block_reason(self, item: QueueItem, allow_reapply: bool) -> str | None:
        """Return why Check cannot Apply or Reapply one child now.

        Args:
            item: Child to inspect.
            allow_reapply: Whether an already-applied result may run again.

        Returns:
            User-facing recovery guidance, or ``None`` when Check is executable.
        """
        if self.is_busy(item) or item.row.apply_operation in ACTIVE_APPLY_OPERATIONS:
            return "A result update is already running for this job."
        unavailable_reason = self.get_unavailable_reason(item)
        if unavailable_reason is not None:
            return unavailable_reason
        if item.row.apply_disposition not in (ApplyDisposition.PENDING, ApplyDisposition.DECLINED) and (
            not allow_reapply or item.row.apply_disposition is not ApplyDisposition.APPLIED
        ):
            return "This job has no result available to apply."
        try:
            operation = (
                ApplyOperation.REAPPLYING
                if item.row.apply_disposition is ApplyDisposition.APPLIED
                else ApplyOperation.APPLYING
            )
            return self.apply_executor.get_apply_block_reason(item.row.job_id, operation)
        except HANDLER_AVAILABILITY_ERRORS as error:
            carb.log_warn(f"Could not determine Apply prerequisites for queue job {item.row.job_id}: {error}")
            return "Apply availability could not be checked. Try again."

    def get_x_block_reason(self, item: QueueItem) -> str | None:
        """Return why X cannot Decline or Revert one child now.

        Pending Decline is a database-only decision and therefore remains available when a valid handler's external
        target is temporarily unavailable. Revert must pass the handler's current target preflight because it mutates
        that target.

        Args:
            item: Child to inspect.

        Returns:
            User-facing recovery guidance, or ``None`` when X is executable.
        """
        if self.is_busy(item) or item.row.apply_operation in ACTIVE_APPLY_OPERATIONS:
            return "A result update is already running for this job."
        unavailable_reason = self.get_unavailable_reason(item)
        if unavailable_reason is not None:
            return unavailable_reason
        if item.row.apply_disposition is ApplyDisposition.PENDING:
            return None
        if item.row.apply_disposition is ApplyDisposition.APPLIED:
            try:
                return self.apply_executor.get_apply_block_reason(item.row.job_id, ApplyOperation.REVERTING)
            except HANDLER_AVAILABILITY_ERRORS as error:
                carb.log_warn(f"Could not determine Revert prerequisites for queue job {item.row.job_id}: {error}")
                return "Revert availability could not be checked. Try again."
        if item.row.apply_disposition is ApplyDisposition.DECLINED:
            return "Results are declined."
        return "This job has no result available to decline or revert."

    def get_unavailable_reason(self, item: QueueItem) -> str | None:
        """Return why a child cannot expose either result action.

        Args:
            item: Child to inspect.

        Returns:
            A precise unavailable-state explanation, or ``None`` when the job and exact handler are available.
        """
        if item.row.is_corrupted:
            return "This saved job type is unavailable. Delete the job and submit it again."
        if item.row.apply_disposition not in (
            ApplyDisposition.PENDING,
            ApplyDisposition.APPLIED,
            ApplyDisposition.DECLINED,
        ):
            return None
        if not self._is_handler_available(item.row):
            return "The feature needed to update this job's result is unavailable."
        return None

    @staticmethod
    def _unique_items(items: Iterable[QueueItem]) -> tuple[QueueItem, ...]:
        """Retain the first captured child for each durable job ID.

        Args:
            items: Captured child sequence that may contain repeated objects.

        Returns:
            Unique children in first-capture order.
        """
        unique: dict[uuid.UUID, QueueItem] = {}
        for item in items:
            unique.setdefault(item.row.job_id, item)
        return tuple(unique.values())

    def can_x_item(self, item: QueueItem) -> bool:
        """Return whether X can Decline or Revert one child.

        Args:
            item: Child to inspect.

        Returns:
            Whether X is executable.
        """
        return self.get_x_block_reason(item) is None

    def _is_handler_available(self, row: Row) -> bool:
        """Return whether the row's exact Apply handler is available now.

        Args:
            row: Completed child presentation data.

        Returns:
            Whether the executor can resolve the exact configured handler.
        """
        cached = self._handler_availability.get(row.job_id)
        if cached is not None:
            return cached
        try:
            available = self.apply_executor.is_handler_available(row.job_id)
        except HANDLER_AVAILABILITY_ERRORS as error:
            carb.log_warn(f"Could not determine Apply handler availability for queue job {row.job_id}: {error}")
            available = False
        self._handler_availability[row.job_id] = available
        return available

    async def _run_single(
        self,
        action: str,
        item: QueueItem,
        operation: Callable[[uuid.UUID], Coroutine[None, None, None]],
    ) -> None:
        """Run one desired-state operation and report a failure.

        Args:
            action: User-facing action name.
            item: Captured child.
            operation: Apply-executor coroutine method.
        """
        succeeded = await self._run_item_operation(action, item, operation)
        if not succeeded:
            post_notification(f"{action} failed for {item.row.name}.", status=NotificationStatus.WARNING)

    async def _run_bulk_check(self, candidates: tuple[QueueItem, ...], scope: str, skipped: int) -> None:
        """Apply or Reapply eligible captured items sequentially with exact summaries.

        Args:
            candidates: Synchronously reserved children.
            scope: User-facing capture scope.
            skipped: Ineligible captured count.
        """
        reapply_count = sum(item.row.apply_disposition is ApplyDisposition.APPLIED for item in candidates)
        apply_count = len(candidates) - reapply_count
        post_notification(
            self._check_summary(BulkOperationPhase.STARTING, scope, apply_count, reapply_count, skipped, 0)
        )
        apply_failed = 0
        reapply_failed = 0
        for item in candidates:
            reapply = item.row.apply_disposition is ApplyDisposition.APPLIED
            action = "Reapply" if reapply else "Apply"
            if not await self._run_item_operation(action, item, self.apply_executor.apply):
                if reapply:
                    reapply_failed += 1
                else:
                    apply_failed += 1
        post_notification(
            self._check_summary(
                BulkOperationPhase.FINISHED,
                scope,
                apply_count - apply_failed,
                reapply_count - reapply_failed,
                skipped,
                apply_failed + reapply_failed,
            ),
            status=NotificationStatus.WARNING if apply_failed or reapply_failed else NotificationStatus.INFO,
        )

    async def _run_bulk_x(
        self,
        declines: tuple[QueueItem, ...],
        reverts: tuple[QueueItem, ...],
        scope: str,
        skipped: int,
    ) -> None:
        """Decline/Revert eligible captured items with exact summaries.

        Args:
            declines: Synchronously reserved children to decline.
            reverts: Synchronously reserved children to revert.
            scope: User-facing capture scope.
            skipped: Ineligible captured count.
        """
        post_notification(self._x_summary(BulkOperationPhase.STARTING, scope, len(declines), len(reverts), skipped, 0))
        decline_failed = 0
        revert_failed = 0
        for item in declines:
            if not await self._run_item_operation("Decline", item, self.apply_executor.decline):
                decline_failed += 1
        for item in reverts:
            if not await self._run_item_operation("Revert", item, self.apply_executor.revert):
                revert_failed += 1
        post_notification(
            self._x_summary(
                BulkOperationPhase.FINISHED,
                scope,
                len(declines) - decline_failed,
                len(reverts) - revert_failed,
                skipped,
                decline_failed + revert_failed,
            ),
            status=NotificationStatus.WARNING if decline_failed or revert_failed else NotificationStatus.INFO,
        )

    async def _run_item_operation(
        self,
        action: str,
        item: QueueItem,
        operation: Callable[[uuid.UUID], Coroutine[None, None, None]],
    ) -> bool:
        """Run one reserved operation and convert product failures to a false result.

        Args:
            action: User-facing action name.
            item: Captured child.
            operation: Apply-executor coroutine method.

        Returns:
            Whether the operation completed without a handled failure.
        """
        job_id = item.row.job_id
        try:
            await operation(job_id)
            return True
        except OPERATION_ERRORS as error:
            carb.log_warn(f"{action} failed for queue job {job_id}: {error}")
            return False

    @staticmethod
    def _check_summary(
        phase: BulkOperationPhase,
        scope: str,
        applied: int,
        reapplied: int,
        skipped: int,
        failed: int,
    ) -> str:
        """Format natural-language bulk Check counts for a native notification.

        Args:
            phase: Whether the notification starts or finishes the operation.
            scope: User-facing capture scope.
            applied: Apply count for the phase.
            reapplied: Reapply count for the phase.
            skipped: Ineligible captured count.
            failed: Handled failure count.

        Returns:
            Exact native notification text.
        """
        if phase is BulkOperationPhase.STARTING:
            return (
                f"Starting result updates for {scope}: applying {applied}, reapplying {reapplied}, "
                f"and skipping {skipped}."
            )
        return (
            f"Finished result updates for {scope}: applied {applied}, reapplied {reapplied}, "
            f"skipped {skipped}, and failed {failed}."
        )

    @staticmethod
    def _x_summary(
        phase: BulkOperationPhase,
        scope: str,
        declined: int,
        reverted: int,
        skipped: int,
        failed: int,
    ) -> str:
        """Format natural-language bulk X counts for a native notification.

        Args:
            phase: Whether the notification starts or finishes the operation.
            scope: User-facing capture scope.
            declined: Decline count for the phase.
            reverted: Revert count for the phase.
            skipped: Ineligible captured count.
            failed: Handled failure count.

        Returns:
            Exact native notification text.
        """
        if phase is BulkOperationPhase.STARTING:
            return (
                f"Starting result choices for {scope}: declining {declined}, reverting {reverted}, "
                f"and skipping {skipped}."
            )
        return (
            f"Finished result choices for {scope}: declined {declined}, reverted {reverted}, "
            f"skipped {skipped}, and failed {failed}."
        )

    def _schedule_reserved(
        self,
        coroutine: Coroutine[None, None, None],
        items: tuple[QueueItem, ...],
    ) -> asyncio.Task[None]:
        """Reserve captured jobs before scheduling their gesture-owned coroutine.

        Args:
            coroutine: Complete single or bulk action for this reservation.
            items: Eligible captured children owned by the action.

        Returns:
            Retained task that releases the reservation when it settles.

        Raises:
            RuntimeError: If a captured job is already reserved or scheduling fails.
            TypeError: If the event loop rejects the supplied coroutine.
        """
        token, job_ids = self._reserve_items(items)
        try:
            task = self._retain_background_task(coroutine)
        except TASK_SCHEDULING_ERRORS:
            coroutine.close()
            self._release_reservation(token, job_ids)
            raise
        task.add_done_callback(lambda settled: self._on_reserved_task_done(settled, token, job_ids))
        return task

    def _reserve_items(self, items: tuple[QueueItem, ...]) -> tuple[object, tuple[uuid.UUID, ...]]:
        """Synchronously reserve unique captured IDs and invalidate their controls.

        Args:
            items: Eligible children captured by one user gesture.

        Returns:
            Opaque reservation token and unique job IDs in capture order.

        Raises:
            RuntimeError: If another local gesture already owns a captured job.
        """
        unique_items = {item.row.job_id: item for item in items}
        job_ids = tuple(unique_items)
        already_reserved = next((job_id for job_id in job_ids if job_id in self._busy_job_ids), None)
        if already_reserved is not None:
            raise RuntimeError(f"Queue job {already_reserved} is already reserved by this view")
        token = object()
        self._busy_job_ids.update((job_id, token) for job_id in job_ids)
        for item in unique_items.values():
            self._item_changed(item)
            if item.parent is not None:
                self._item_changed(item.parent)
        return token, job_ids

    def _on_reserved_task_done(
        self,
        _task: asyncio.Task[None],
        token: object,
        job_ids: tuple[uuid.UUID, ...],
    ) -> None:
        """Release one gesture reservation after success, failure, or cancellation.

        Args:
            _task: Settled action task supplied by asyncio.
            token: Opaque owner token created for the gesture.
            job_ids: Unique reserved job IDs.
        """
        self._release_reservation(token, job_ids)

    def _release_reservation(self, token: object, job_ids: tuple[uuid.UUID, ...]) -> None:
        """Release only IDs still owned by a reservation and refresh their rows.

        Args:
            token: Opaque owner token created for the gesture.
            job_ids: Unique job IDs captured by the gesture.
        """
        released = []
        for job_id in job_ids:
            if self._busy_job_ids.get(job_id) is token:
                del self._busy_job_ids[job_id]
                released.append(job_id)
        for job_id in released:
            if self.has_item(job_id):
                self.update_item(job_id, force_notify=True)

    def _retain_background_task(self, coroutine: Coroutine[None, None, None]) -> asyncio.Task[None]:
        """Retain and return one scheduled UI action until it settles.

        Args:
            coroutine: UI action to schedule on the current event loop.

        Returns:
            Retained task for optional caller synchronization.
        """
        task = asyncio.ensure_future(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)
        return task

    def _on_background_task_done(self, task: asyncio.Task[None]) -> None:
        """Release a settled task and log unexpected failures.

        Args:
            task: Settled retained task.
        """
        self._background_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            carb.log_error(f"Job queue action failed: {error}")

    async def wait_for_background_tasks(self) -> None:
        """Wait for retained UI actions during deterministic shutdown and tests."""
        while self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks))

    def get_drag_mime_data(self, item: QueueGraphItem | QueueItem | None) -> str:
        """Return drag data for roots only.

        Args:
            item: Native drag source.

        Returns:
            Serialized graph ID, or an empty string for non-roots.
        """
        return str(item.graph_id) if isinstance(item, QueueGraphItem) else ""

    def _resolve_graph(self, source: str | QueueGraphItem | QueueItem) -> QueueGraphItem | None:
        """Resolve drag data to a known graph root.

        Args:
            source: Native drag source or serialized graph ID.

        Returns:
            Known graph root, or None for invalid/child sources.
        """
        if isinstance(source, QueueGraphItem):
            return source
        if isinstance(source, QueueItem):
            return None
        try:
            return self._graphs_by_id.get(uuid.UUID(str(source)))
        except ValueError:
            return None

    def drop_accepted(
        self,
        target_item: QueueGraphItem | QueueItem | None,
        source: str | QueueGraphItem | QueueItem,
        _drop_location: int = -1,
    ) -> bool:
        """Return whether a root may be reordered onto a root or a native insertion slot.

        Args:
            target_item: Proposed graph target, or None for a between-items insertion slot.
            source: Native drag source or serialized graph ID.
            _drop_location: Unused native location during acceptance.

        Returns:
            Whether the drop is accepted.
        """
        source_graph = self._resolve_graph(source)
        valid_target = target_item is None or isinstance(target_item, QueueGraphItem)
        return source_graph is not None and valid_target and source_graph is not target_item

    def drop(
        self,
        target_item: QueueGraphItem | QueueItem | None,
        source: str | QueueGraphItem | QueueItem,
        drop_location: int = -1,
    ) -> None:
        """Reorder graph roots and persist their durable positions.

        Args:
            target_item: Graph receiving the drop, or None for a between-items insertion slot.
            source: Native drag source or serialized graph ID.
            drop_location: Before/after native drop location.
        """
        source_graph = self._resolve_graph(source)
        valid_target = target_item is None or isinstance(target_item, QueueGraphItem)
        if source_graph is None or not valid_target or source_graph is target_item:
            return
        source_index = self._all_graphs.index(source_graph)
        roots = [graph for graph in self._all_graphs if graph is not source_graph]
        if target_item is None:
            visible_roots = list(self._items)
            if source_graph not in visible_roots:
                return
            visible_insertion = drop_location if drop_location >= 0 else len(visible_roots)
            visible_insertion = max(0, min(visible_insertion, len(visible_roots)))
            visible_source_index = visible_roots.index(source_graph)
            visible_without_source = [graph for graph in visible_roots if graph is not source_graph]
            if visible_source_index < visible_insertion:
                visible_insertion -= 1
            visible_without_source.insert(visible_insertion, source_graph)
            if visible_without_source == visible_roots:
                return

            next_visible_index = visible_insertion + 1
            if next_visible_index < len(visible_without_source):
                insertion = roots.index(visible_without_source[next_visible_index])
            elif visible_insertion > 0:
                insertion = roots.index(visible_without_source[visible_insertion - 1]) + 1
            else:
                return
            roots.insert(insertion, source_graph)
        else:
            target_index = self._all_graphs.index(target_item)
            insertion = roots.index(target_item)
            insert_before = drop_location == 0 or (drop_location not in (0, 1) and source_index > target_index)
            roots.insert(insertion if insert_before else insertion + 1, source_graph)
        self._all_graphs = roots
        for position, graph in enumerate(roots):
            graph.position = position
        self.interface.update_graph_positions([graph.graph_id for graph in roots])
        self._apply_filters()

    def remove_item(self, _item) -> None:
        """Satisfy AbstractItemModel; queue deletion is graph-scoped.

        Args:
            _item: Native item ignored by this graph-scoped queue.
        """

    def set_items_selected(self, items: list[QueueGraphItem | QueueItem]) -> None:
        """Update item selection state and notify details consumers.

        Args:
            items: Requested current selection.
        """
        previous_graphs = {item for item in self._selected_items if isinstance(item, QueueGraphItem)}
        available = set(self._all_graphs) | set(self._all_items)
        normalized = [item for item in items if item in available]
        self._selected_items = normalized
        selected_graphs = {item for item in normalized if isinstance(item, QueueGraphItem)}
        self._selection_changed_event(normalized)
        for graph in previous_graphs | selected_graphs:
            self._item_changed(graph)

    def subscribe_selection_changed(self, function: Callable[[list], None]) -> EventSubscription:
        """Subscribe to model-owned selection changes.

        Args:
            function: Selection callback.

        Returns:
            Subscription released when discarded.
        """
        return EventSubscription(self._selection_changed_event, function)

    def reveal_item(self, job_id: uuid.UUID) -> None:
        """Request that the widget expand, select, and frame one visible child.

        Args:
            job_id: Child job to reveal.
        """
        item = self._items_by_id.get(job_id)
        if item is not None:
            visible = self._visible_children_by_graph.get(item.row.graph_id, ())
            if item not in visible:
                return
            self._reveal_item_event(item)

    def subscribe_reveal_item(self, function: Callable[[QueueItem], None]) -> EventSubscription:
        """Subscribe to graph-details child navigation requests.

        Args:
            function: Reveal callback.

        Returns:
            Subscription released when discarded.
        """
        return EventSubscription(self._reveal_item_event, function)

    def subscribe_progress_changed(self, function: Callable[[tuple[QueueItem, ...]], None]) -> EventSubscription:
        """Subscribe to presentation-only progress changes.

        Args:
            function: Callback receiving existing changed children in one UI-frame batch.

        Returns:
            Subscription retained by the caller.
        """
        return EventSubscription(self._progress_changed_event, function)

    def destroy(self) -> None:
        """Cancel outstanding UI actions and release tree-model references."""
        for task in tuple(self._background_tasks):
            task.cancel()
        super().destroy()

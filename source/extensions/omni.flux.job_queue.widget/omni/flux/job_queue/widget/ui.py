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

import asyncio
import concurrent.futures
import contextlib
import dataclasses
import datetime
import enum
import functools
import gc
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from typing import Any
from collections.abc import Callable, Coroutine, Iterator

import carb
import omni.flux.job_queue.core.execute
import omni.flux.job_queue.core.interface
import omni.flux.job_queue.core.job
import omni.kit.app
from omni import ui
from omni.flux.utils.common import Event, EventSubscription

__all__ = (
    "ApplyState",
    "CallbackExecutor",
    "DeleteState",
    "QueueItem",
    "QueueItemDelegate",
    "QueueModel",
    "QueueView",
    "QueueWidget",
)


class ApplyState(enum.Enum):
    """State of a job apply operation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeleteState(enum.Enum):
    """State of a job deletion operation."""

    PENDING = "pending"
    DELETING = "deleting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclasses.dataclass
class CallbackExecution:
    """Tracks the state and result of a callback execution."""

    job_id: uuid.UUID
    state: ApplyState = ApplyState.PENDING
    error: Exception | None = None
    task: asyncio.Task | concurrent.futures.Future | None = None


# Type alias for apply handler functions
ApplyHandlerFunc = Callable[
    [omni.flux.job_queue.core.interface.QueueInterface, omni.flux.job_queue.core.job.Job],
    None | Coroutine[Any, Any, None],
]

# Type alias for can_apply check function
CanApplyFunc = Callable[[omni.flux.job_queue.core.job.Job], bool]

# Type alias for has_been_applied check function
HasBeenAppliedFunc = Callable[
    [omni.flux.job_queue.core.interface.QueueInterface, omni.flux.job_queue.core.job.Job],
    bool,
]


def force_delete_directory(path: pathlib.Path, max_retries: int = 5) -> bool:
    """Attempt to delete a directory."""
    for attempt in range(max_retries):
        try:
            # Force garbage collection to release any Python file handles
            gc.collect()

            # Try deleting files individually first
            if path.exists():
                for item in path.rglob("*"):
                    if item.is_file():
                        with contextlib.suppress(PermissionError):
                            item.unlink()

            shutil.rmtree(path)
            return True

        except PermissionError:
            if attempt < max_retries - 1:
                # Longer delays for OneDrive sync
                time.sleep(1.0 * (attempt + 1))
            continue
        except Exception:  # noqa: BLE001
            break

    return False


class CallbackExecutor:
    """
    Manages the execution of job apply handlers on the main thread.

    This class ensures that apply handlers are properly executed on Kit's main asyncio
    event loop, which is required for USD commands and UI operations.

    Callbacks are queued and executed sequentially - only one callback runs at a time.

    Thread-safe: Can be called from any thread; handlers will be scheduled
    on the main event loop.

    Parameters:
        interface: The job queue interface.
        apply_handler: Function to apply job results. Required.
        can_apply: Function to check if a job can be applied. Required.
        has_been_applied: Function to check if job was already applied. Required.
    """

    def __init__(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        apply_handler: ApplyHandlerFunc,
        can_apply: CanApplyFunc,
        has_been_applied: HasBeenAppliedFunc,
    ):
        self._interface = interface
        self._apply_handler = apply_handler
        self._can_apply = can_apply
        self._has_been_applied = has_been_applied
        self._executions: dict[uuid.UUID, CallbackExecution] = {}
        self._state_changed_event = Event()
        # Capture the main event loop at construction time (should be on main thread)
        self._main_loop = asyncio.get_event_loop()
        # Queue for pending jobs - ensures sequential execution
        self._pending_queue: list[omni.flux.job_queue.core.job.Job] = []
        self._queue_lock = asyncio.Lock()
        # Threading lock for schedule() to be thread-safe
        self._schedule_lock = threading.Lock()
        self._processing = False

    @property
    def interface(self) -> omni.flux.job_queue.core.interface.QueueInterface:
        return self._interface

    def can_apply(self, job: omni.flux.job_queue.core.job.Job) -> bool:
        """Check if a job can be applied."""
        return self._can_apply(job)

    def has_been_applied(self, job: omni.flux.job_queue.core.job.Job) -> bool:
        """Check if a job has already been applied."""
        return self._has_been_applied(self._interface, job)

    def subscribe_state_changed(
        self, callback: Callable[[uuid.UUID, ApplyState, Exception | None], None]
    ) -> EventSubscription:
        """Subscribe to callback execution state changes."""
        return EventSubscription(self._state_changed_event, callback)

    def get_execution_state(self, job_id: uuid.UUID) -> ApplyState | None:
        """Get the current execution state for a job, or None if not tracked."""
        execution = self._executions.get(job_id)
        return execution.state if execution else None

    def is_running(self, job_id: uuid.UUID) -> bool:
        """Check if a callback is currently running for the given job."""
        state = self.get_execution_state(job_id)
        return state in (ApplyState.PENDING, ApplyState.RUNNING)

    def cancel(self, job_id: uuid.UUID) -> bool:
        """
        Cancel a pending or running callback execution.

        Returns True if the execution was cancelled, False if it wasn't found or already completed.
        """
        execution = self._executions.get(job_id)
        if execution is None:
            return False

        if execution.state in (
            ApplyState.COMPLETED,
            ApplyState.FAILED,
            ApplyState.CANCELLED,
        ):
            return False

        if execution.task and not execution.task.done():
            execution.task.cancel()

        execution.state = ApplyState.CANCELLED
        self._state_changed_event(job_id, ApplyState.CANCELLED, None)
        return True

    def schedule(self, job: omni.flux.job_queue.core.job.Job) -> None:
        """
        Schedule a job for apply execution on the main thread.

        Jobs are queued and executed sequentially - only one runs at a time.
        If a job is already queued/running or has been applied, it will be skipped.

        Thread-safe: uses a lock to prevent race conditions when called from multiple threads.
        """
        job_id = job.job_id

        with self._schedule_lock:
            # Skip if already running or pending
            if self.is_running(job_id):
                carb.log_info(f"[CallbackExecutor] Job {job_id} is already running/pending, skipping schedule")
                return

            # Skip if already in the pending queue
            if any(j.job_id == job_id for j in self._pending_queue):
                carb.log_info(f"[CallbackExecutor] Job {job_id} is already in queue, skipping schedule")
                return

            # Skip if already applied (check database event)
            if self.has_been_applied(job):
                carb.log_info(f"[CallbackExecutor] Job {job_id} has already been applied, skipping schedule")
                return

            # Validate we have a way to apply this job
            if not self.can_apply(job):
                raise ValueError(f"Job {job_id} cannot be applied: no handler registered for this job type")

            # Add to queue and start processing if not already running
            self._pending_queue.append(job)
            carb.log_info(f"[CallbackExecutor] Job {job_id} added to queue (queue size: {len(self._pending_queue)})")

            # Start the queue processor if not already running
            if not self._processing:
                asyncio.run_coroutine_threadsafe(self._process_queue(), self._main_loop)

    async def _process_queue(self) -> None:
        """Process jobs from the queue sequentially."""
        if self._processing:
            return

        self._processing = True
        try:
            while self._pending_queue:
                job = self._pending_queue.pop(0)
                job_id = job.job_id

                # Double-check hasn't been applied while waiting in queue
                if self.has_been_applied(job):
                    carb.log_info(f"[CallbackExecutor] Job {job_id} was applied while in queue, skipping")
                    continue

                await self._execute_job(job)
        finally:
            self._processing = False

    async def _execute_job(self, job: omni.flux.job_queue.core.job.Job) -> None:
        """Execute a single job's apply handler."""
        job_id = job.job_id

        # Create the execution tracker
        execution = CallbackExecution(job_id=job_id, state=ApplyState.PENDING)
        self._executions[job_id] = execution
        self._state_changed_event(job_id, ApplyState.PENDING, None)

        try:
            # Wait for the next frame to ensure we're on the main thread
            await omni.kit.app.get_app().next_update_async()

            execution.state = ApplyState.RUNNING
            self._state_changed_event(job_id, ApplyState.RUNNING, None)

            # Execute the apply handler
            result = self._apply_handler(self._interface, job)

            # If the handler returned a coroutine, await it
            if asyncio.iscoroutine(result):
                await result

            execution.state = ApplyState.COMPLETED
            self._state_changed_event(job_id, ApplyState.COMPLETED, None)

        except asyncio.CancelledError:
            execution.state = ApplyState.CANCELLED
            self._state_changed_event(job_id, ApplyState.CANCELLED, None)
            carb.log_warn(f"[CallbackExecutor] Apply cancelled for job {job_id}")

        except Exception as e:  # noqa: BLE001
            execution.state = ApplyState.FAILED
            execution.error = e
            self._state_changed_event(job_id, ApplyState.FAILED, e)
            carb.log_error(f"[CallbackExecutor] Apply failed for job {job_id}: {e}")

    def clear_completed(self) -> None:
        """Remove all completed, failed, or cancelled executions from tracking."""
        to_remove = [
            job_id
            for job_id, execution in self._executions.items()
            if execution.state in (ApplyState.COMPLETED, ApplyState.FAILED, ApplyState.CANCELLED)
        ]
        for job_id in to_remove:
            del self._executions[job_id]


@dataclasses.dataclass
class Row:
    _job_id: uuid.UUID
    _graph_id: uuid.UUID
    _interface: omni.flux.job_queue.core.interface.QueueInterface
    graph: str = dataclasses.field(
        metadata={
            "header": "Graph",
            # "width": ui.Pixel(300),
        }
    )
    name: str = dataclasses.field(
        metadata={
            "header": "Name",
            # width=ui.Pixel(400),
        }
    )
    state: str = dataclasses.field(
        metadata={
            "header": "State",
            "width": ui.Pixel(120),
        }
    )
    priority: str = dataclasses.field(
        metadata={
            "header": "Priority",
            "width": ui.Pixel(65),
        }
    )
    submitted_at: str = dataclasses.field(
        metadata={
            "header": "Submitted At",
            "width": ui.Pixel(160),
        }
    )
    completed_at: str | None = dataclasses.field(
        default=None,
        metadata={
            "header": "Completed At",
            "width": ui.Pixel(160),
        },
    )
    has_apply_callback: bool = dataclasses.field(
        default=False,
        metadata={
            "header": "Apply",
            "width": ui.Pixel(120),
        },
    )

    def update_from(self, other: Row) -> bool:
        """
        Update this row's fields from another row.

        Args:
            other: The row to copy values from (must have the same job_id).

        Returns:
            True if any fields changed, False otherwise.
        """
        changed = False
        if self.graph != other.graph:
            self.graph = other.graph
            changed = True
        if self.name != other.name:
            self.name = other.name
            changed = True
        if self.state != other.state:
            self.state = other.state
            changed = True
        if self.priority != other.priority:
            self.priority = other.priority
            changed = True
        if self.submitted_at != other.submitted_at:
            self.submitted_at = other.submitted_at
            changed = True
        if self.completed_at != other.completed_at:
            self.completed_at = other.completed_at
            changed = True
        if self.has_apply_callback != other.has_apply_callback:
            self.has_apply_callback = other.has_apply_callback
            changed = True
        return changed

    @property
    def job_id(self) -> uuid.UUID:
        return self._job_id

    @property
    def graph_id(self) -> uuid.UUID:
        return self._graph_id

    @property
    def job(self) -> omni.flux.job_queue.core.job.Job | None:
        try:
            return self._interface.get_job_by_id(self.job_id)
        except Exception as e:  # noqa: BLE001
            carb.log_error(
                f"Failed to load job {self.job_id} from database: {e}. "
                f"The job may have been created with an incompatible version."
            )
            return None

    @classmethod
    def keys(cls):
        return [x.name for x in dataclasses.fields(cls) if not x.name.startswith("_")]

    @classmethod
    def get_column_headers(cls) -> list[str]:
        return [
            field.metadata.get("header", field.name)
            for field in dataclasses.fields(cls)
            if not field.name.startswith("_")
        ]

    @classmethod
    def get_column_widths(cls) -> list[ui.Length]:
        return [
            field.metadata.get("width", ui.Fraction(1))
            for field in dataclasses.fields(cls)
            if not field.name.startswith("_")
        ]

    @classmethod
    def iter_from_queue(
        cls,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        can_apply: CanApplyFunc,
    ) -> Iterator[Row]:
        """
        Iterate over rows from the queue.

        Args:
            interface: The job queue interface.
            can_apply: Function to check if a job can be applied.
        """
        for snapshot in interface.get_snapshot():
            has_apply_callback = False
            completed_at = None
            is_corrupted = False

            if snapshot.state == omni.flux.job_queue.core.interface.JobState.DONE:
                completed_at = snapshot.state_change_timestamp

                try:
                    job = interface.get_job_by_id(snapshot.job_id)
                    has_apply_callback = can_apply(job)
                except Exception as e:  # noqa: BLE001
                    carb.log_error(
                        f"Failed to load job {snapshot.job_id} from database: {e}. "
                        f"The job may have been created with an incompatible version. "
                        f"Consider purging the queue or deleting {interface.db_path}"
                    )
                    # Mark as corrupted but continue - don't crash the UI
                    is_corrupted = True

            yield cls(
                _job_id=snapshot.job_id,
                _graph_id=snapshot.graph_id,
                _interface=interface,
                graph=snapshot.graph_name,
                name=snapshot.job_name if not is_corrupted else f"{snapshot.job_name} (corrupted)",
                priority=str(snapshot.priority),
                state="corrupted" if is_corrupted else snapshot.state.value,
                submitted_at=snapshot.timestamp,
                completed_at=completed_at,
                has_apply_callback=False if is_corrupted else has_apply_callback,
            )


class QueueItem(ui.AbstractItem):
    def __init__(self, row: Row):
        super().__init__()
        self.row = row
        self.keys = row.keys()
        self.selected = False

    def get(self, index: int) -> tuple[str, Any]:
        key = self.keys[index]
        return key, getattr(self.row, key)


class QueueModel(ui.AbstractItemModel):
    """
    Model for the job queue TreeView.

    This model manages the list of queue items and delegates apply execution
    to a CallbackExecutor instance.

    The model performs incremental updates to preserve selection state and
    avoid jarring UI rebuilds. Items are tracked by job_id, and only changed
    items trigger UI updates.
    """

    def __init__(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        callback_executor: CallbackExecutor,
    ):
        super().__init__()
        self.interface = interface
        self._items: list[QueueItem] = []
        self._items_by_id: dict[uuid.UUID, QueueItem] = {}  # Index for fast lookup by job_id
        self.auto_apply = False
        self._callback_executor = callback_executor

        # Track jobs being deleted
        self._deleting_jobs: dict[uuid.UUID, DeleteState] = {}
        self._delete_state_changed_event = Event()

        # Subscribe to executor state changes to refresh UI
        self._executor_subscription = self._callback_executor.subscribe_state_changed(self._on_callback_state_changed)

        self._selection_changed_event = Event()

        self.refresh()

    @property
    def items(self):
        return self._items

    @property
    def callback_executor(self) -> CallbackExecutor:
        """The callback executor used by this model."""
        return self._callback_executor

    def subscribe_selection_changed(self, func: Callable[[list[QueueItem]], None]) -> EventSubscription:
        return EventSubscription(self._selection_changed_event, func)

    def subscribe_delete_state_changed(self, func: Callable[[uuid.UUID, DeleteState], None]) -> EventSubscription:
        """Subscribe to job deletion state changes."""
        return EventSubscription(self._delete_state_changed_event, func)

    def is_deleting(self, job_id: uuid.UUID) -> bool:
        """Check if a job is currently being deleted."""
        return self._deleting_jobs.get(job_id) in (DeleteState.PENDING, DeleteState.DELETING)

    def get_delete_state(self, job_id: uuid.UUID) -> DeleteState | None:
        """Get the current delete state for a job, or None if not being deleted."""
        return self._deleting_jobs.get(job_id)

    def _on_callback_state_changed(self, job_id: uuid.UUID, state: ApplyState, error: Exception | None) -> None:
        """Handle callback execution state changes."""
        # Only update the specific item that changed, not the entire list
        item = self._items_by_id.get(job_id)
        if item is not None:
            self._item_changed(item)
        else:
            # Item not found, do a full refresh
            self.refresh()

    def _run_auto_apply(self):
        """Run auto-apply for all eligible items."""
        for item in self.items:
            job_id = item.row.job_id
            job = item.row.job
            if job is None:
                continue
            if (
                item.row.has_apply_callback
                and not self._callback_executor.is_running(job_id)
                and not self._callback_executor.has_been_applied(job)
            ):
                self._schedule_job(job)

    def refresh(self, force=False, run_auto_apply=True):
        """
        Refresh the queue items from the database.

        This method performs incremental updates to preserve selection state:
        - Existing items are updated in-place if their content changed
        - New items are added to the list
        - Removed items are deleted from the list
        - Only triggers full UI rebuild when items are added/removed

        Args:
            force: If True, trigger UI update for all changed items even if structure unchanged.
            run_auto_apply: If True and auto_apply is enabled, run auto-apply after refresh.
                           Set to False when refreshing just to update UI state.
        """
        # Get fresh data from the database
        new_rows = list(Row.iter_from_queue(self.interface, can_apply=self._callback_executor.can_apply))
        new_job_ids = {row.job_id for row in new_rows}
        current_job_ids = set(self._items_by_id.keys())

        # Determine what changed
        added_ids = new_job_ids - current_job_ids
        removed_ids = current_job_ids - new_job_ids
        common_ids = new_job_ids & current_job_ids

        # Track if we need a structural change (add/remove items)
        structure_changed = bool(added_ids) or bool(removed_ids)

        # Update existing items in-place
        items_updated: list[QueueItem] = []
        new_rows_by_id = {row.job_id: row for row in new_rows}
        for job_id in common_ids:
            existing_item = self._items_by_id[job_id]
            new_row = new_rows_by_id[job_id]
            if existing_item.row.update_from(new_row):
                items_updated.append(existing_item)

        # Remove deleted items
        if removed_ids:
            self._items = [item for item in self._items if item.row.job_id not in removed_ids]
            for job_id in removed_ids:
                del self._items_by_id[job_id]

        # Add new items (maintain order from database)
        if added_ids:
            # Build new items list in the order from the database
            new_items_list: list[QueueItem] = []
            for row in new_rows:
                if row.job_id in self._items_by_id:
                    new_items_list.append(self._items_by_id[row.job_id])
                else:
                    new_item = QueueItem(row)
                    new_items_list.append(new_item)
                    self._items_by_id[row.job_id] = new_item
            self._items = new_items_list

        # Run auto-apply if enabled
        if run_auto_apply and self.auto_apply:
            self._run_auto_apply()

        # Trigger appropriate UI updates
        if structure_changed:
            # Items were added or removed - need full rebuild
            self._item_changed(None)
        elif force or items_updated:
            # Only content changed - update individual items
            if force:
                # Force update all items
                for item in self._items:
                    self._item_changed(item)
            else:
                # Update only changed items
                for item in items_updated:
                    self._item_changed(item)

    def iter_selected_items(self):
        for item in self.items:
            if item.selected:
                yield item

    def apply_selected(self, skip_in_progress=True, allow_reapply=True, validate=True):
        for item in self.iter_selected_items():
            if item.row.has_apply_callback:
                job_id = item.row.job_id
                job = item.row.job
                if job is None:
                    continue
                if skip_in_progress and self._callback_executor.is_running(job_id):
                    continue
                if not allow_reapply and self._callback_executor.has_been_applied(job):
                    continue
                if validate and not self._callback_executor.can_apply(job):
                    raise RuntimeError(f"Job {job_id} cannot be applied - no handler registered.")
                self.schedule_callback(item)
        self.refresh(force=True)

    def delete_selected(self):
        """
        Delete the selected jobs.

        This method deletes jobs from the database immediately and schedules
        file cleanup to run in the background. Rows being deleted will display
        a "Deleting..." state until cleanup is complete.
        """
        # Collect info for all selected items before we start
        jobs_to_delete: list[tuple[uuid.UUID, uuid.UUID, pathlib.Path]] = []

        for item in self.iter_selected_items():
            job_id = item.row.job_id
            graph_id = item.row.graph_id

            # Skip if already being deleted
            if self.is_deleting(job_id):
                continue

            job_dir = omni.flux.job_queue.core.execute.get_default_job_directory(self.interface, job_id)
            jobs_to_delete.append((job_id, graph_id, job_dir))

            # Mark as pending deletion
            self._deleting_jobs[job_id] = DeleteState.PENDING
            self._delete_state_changed_event(job_id, DeleteState.PENDING)

        if not jobs_to_delete:
            return

        # Refresh UI to show "Deleting..." state
        self.refresh(force=True)

        # Delete jobs from database immediately (fast operation)
        graphs_to_check: set[uuid.UUID] = set()
        for job_id, graph_id, _ in jobs_to_delete:
            self.interface.delete_job(job_id)
            graphs_to_check.add(graph_id)

        # Check each graph and delete if empty
        for graph_id in graphs_to_check:
            remaining_jobs = self.interface.get_jobs_by_graph_id(graph_id)
            if not remaining_jobs:
                self.interface.delete_job_graph(graph_id)

        # Schedule background file cleanup for each job
        for job_id, _, job_dir in jobs_to_delete:
            asyncio.ensure_future(self._delete_job_files_async(job_id, job_dir))

        self._selection_changed_event([])

    async def _delete_job_files_async(self, job_id: uuid.UUID, job_dir: pathlib.Path) -> None:
        """
        Delete job files in the background.

        This runs the blocking file deletion in a thread pool executor
        to avoid blocking the UI.
        """
        self._deleting_jobs[job_id] = DeleteState.DELETING
        self._delete_state_changed_event(job_id, DeleteState.DELETING)
        self.refresh(force=True, run_auto_apply=False)

        try:
            if job_dir.exists():
                # Run blocking file deletion in a thread pool
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, force_delete_directory, job_dir)
                if not success:
                    carb.log_warn(f"Failed to delete job directory: {job_dir}")
                    self._deleting_jobs[job_id] = DeleteState.FAILED
                    self._delete_state_changed_event(job_id, DeleteState.FAILED)
                else:
                    self._deleting_jobs[job_id] = DeleteState.COMPLETED
                    self._delete_state_changed_event(job_id, DeleteState.COMPLETED)
            else:
                self._deleting_jobs[job_id] = DeleteState.COMPLETED
                self._delete_state_changed_event(job_id, DeleteState.COMPLETED)
        except Exception as e:  # noqa: BLE001
            carb.log_error(f"Error deleting job directory {job_dir}: {e}")
            self._deleting_jobs[job_id] = DeleteState.FAILED
            self._delete_state_changed_event(job_id, DeleteState.FAILED)
        finally:
            # Refresh to update UI and potentially remove the row from the list
            self.refresh(force=True)

    def purge(self):
        self.interface.purge()
        self.refresh(force=True)

    def get_item_value_model_count(self, item) -> int:
        return len(Row.keys())

    def get_item_children(self, item=None) -> list[ui.AbstractItem]:
        if item is None:
            return self.items
        return []

    def remove_item(self, item) -> None:
        raise NotImplementedError()

    def set_items_selected(self, items: list[QueueItem]) -> None:
        for item in self.items:
            item.selected = item in items
        self._selection_changed_event(items)

    def _schedule_job(self, job: omni.flux.job_queue.core.job.Job) -> None:
        """
        Internal method to schedule a job for execution.

        Args:
            job: The job to schedule (must not be None).
        """
        if not self._callback_executor.can_apply(job):
            raise RuntimeError(f"Job {job.job_id} cannot be applied - no handler registered.")

        self._callback_executor.schedule(job)

    def schedule_callback(self, item: QueueItem) -> None:
        """
        Schedule a job's apply for execution.

        This delegates to the CallbackExecutor which ensures proper main-thread execution.
        """
        job = item.row.job
        if job is None:
            raise RuntimeError(f"Job {item.row.job_id} cannot be applied - failed to load job data.")

        self._schedule_job(job)

        # Trigger immediate UI refresh so button shows "Running..." state
        # Don't run auto-apply here - we may already be inside _run_auto_apply
        self.refresh(force=True, run_auto_apply=False)


class QueueItemDelegate(ui.AbstractItemDelegate):
    def __init__(self, model: QueueModel) -> None:
        super().__init__()
        self.model = model

    def build_header(self, column_id: int = 0) -> None:
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(8))
            with ui.HStack():
                ui.Spacer(width=ui.Pixel(8))
                ui.Label(Row.get_column_headers()[column_id])
                ui.Spacer()
                ui.Rectangle(name="WizardSeparator", width=ui.Pixel(1))
            ui.Spacer(height=ui.Pixel(8))

    def build_widget(
        self,
        model: ui.AbstractItemModel,
        item: QueueItem = None,
        index: int = 0,
        level: int = 0,
        expanded: bool = False,
    ) -> None:
        if not isinstance(item, QueueItem):
            return

        key, value = item.get(index)

        # Check if this job is being deleted
        is_deleting = self.model.is_deleting(item.row.job_id)

        with ui.HStack():
            ui.Spacer(width=ui.Pixel(8))

            # Show "Deleting..." for the state column when job is being deleted
            if key == "state" and is_deleting:
                delete_state = self.model.get_delete_state(item.row.job_id)
                if delete_state == DeleteState.PENDING:
                    state_text = "pending deletion..."
                elif delete_state == DeleteState.DELETING:
                    state_text = "deleting..."
                else:
                    state_text = value
                ui.Label(
                    state_text,
                    height=ui.Pixel(30),
                    style={"color": 0xFF888888},  # Gray out deleting items
                )
            elif isinstance(value, str):
                style = {"color": 0xFF888888} if is_deleting else {}
                ui.Label(
                    value,
                    height=ui.Pixel(30),
                    style=style,
                )
            elif isinstance(value, datetime.datetime):
                ui.Label(
                    value.strftime("%Y-%m-%d %H:%M:%S"),
                    height=ui.Pixel(30),
                )
            elif key == "has_apply_callback" and value:
                job = item.row.job
                is_running = self.model.callback_executor.is_running(item.row.job_id)

                if job is None:
                    # Job failed to deserialize - show disabled button
                    label = "Error"
                    enabled = False
                    tooltip = "Failed to load job data - job may be corrupted"
                elif is_running:
                    label = "Running..."
                    enabled = False
                    tooltip = "Callback currently running..."
                elif self.model.callback_executor.has_been_applied(job):
                    enabled = False
                    label = "Applied"
                    tooltip = "Job results have already been applied in this context"
                else:
                    enabled = True
                    label = "Apply"
                    tooltip = "Apply the job results to the current context"

                btn = ui.Button(
                    label,
                    tooltip=tooltip,
                    width=ui.Percent(90),
                    height=ui.Pixel(30),
                    enabled=enabled,
                )
                btn.set_clicked_fn(functools.partial(self.model.schedule_callback, item))
            ui.Spacer(width=ui.Pixel(8))


class QueueView(ui.Frame):
    def __init__(self, model: QueueModel, delegate: QueueItemDelegate, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model = model
        self.delegate = delegate
        with self:
            self.tree = ui.TreeView(
                self.model,
                delegate=self.delegate,
                header_visible=True,
                columns_resizable=True,
                column_widths=Row.get_column_widths(),
                min_column_width=ui.Pixel(20),
                padding=8,
            )
            self.tree.set_selection_changed_fn(self.model.set_items_selected)


class JobDetails(ui.Frame):
    """
    Displays details and logs for a selected job.

    The log view auto-refreshes periodically while a job is selected,
    allowing users to watch logs update in real-time for running jobs.
    """

    # Refresh interval in seconds
    REFRESH_INTERVAL = 2.0

    def __init__(self, interface: omni.flux.job_queue.core.interface.QueueInterface, **kwargs) -> None:
        super().__init__(**kwargs)
        self.interface = interface
        self.row: Row | None = None
        self._log_container: ui.VStack | None = None
        self._refresh_task: asyncio.Task | None = None
        self._last_log_hash: int = 0  # Track log content to avoid unnecessary rebuilds

    def set_job(self, row: Row | None) -> None:
        self.row = row
        self._stop_refresh()
        self._last_log_hash = 0
        self.rebuild()
        if row is not None:
            self._start_refresh()

    def destroy(self) -> None:
        """Clean up resources when the widget is destroyed."""
        self._stop_refresh()
        super().destroy()

    def _start_refresh(self) -> None:
        """Start the periodic refresh task."""
        if self._refresh_task is not None:
            return
        self._refresh_task = asyncio.ensure_future(self._refresh_loop())

    def _stop_refresh(self) -> None:
        """Stop the periodic refresh task."""
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            self._refresh_task = None

    async def _refresh_loop(self) -> None:
        """Periodically refresh the log content."""
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await asyncio.sleep(self.REFRESH_INTERVAL)
                if self.row is not None and self._log_container is not None:
                    self._update_logs()

    def _update_logs(self) -> None:
        """Update just the log content without rebuilding the entire UI."""
        if self.row is None or self._log_container is None:
            return

        logs = self._get_combined_logs(self.row.job)

        # Compute a hash to check if logs have changed
        log_hash = hash(tuple(logs))
        if log_hash == self._last_log_hash:
            return  # No changes, skip rebuild
        self._last_log_hash = log_hash

        # Clear and rebuild just the log container
        self._log_container.clear()
        with self._log_container:
            for line, color in logs:
                ui.Label(line, style={"color": color})
            ui.Spacer()

    def rebuild(self) -> None:
        self.clear()
        self._log_container = None

        if self.row is None:
            return

        job_dir = getattr(self.row.job, "job_dir", None)
        if job_dir is None:
            job_dir = omni.flux.job_queue.core.execute.get_default_job_directory(self.interface, self.row.job_id)

        with self:
            with ui.VStack(spacing=ui.Pixel(8)):
                with ui.HStack(height=0, width=0, spacing=ui.Pixel(8)):
                    if job_dir.exists():
                        ui.Button(
                            "Open Job Folder",
                            width=ui.Pixel(100),
                            height=ui.Pixel(30),
                            clicked_fn=lambda: self._open_job_folder(self.row.job),
                        )
                        ui.Rectangle(name="WizardSeparator", width=ui.Pixel(1))
                    ui.Label(f"{self.row.job_id}")
                    if self.row.completed_at:
                        ui.Rectangle(name="WizardSeparator", width=ui.Pixel(1))
                        duration = self.row.completed_at - self.row.submitted_at
                        ui.Label(f"{duration.total_seconds():.02f} s")
                    ui.Spacer()

                ui.Rectangle(name="WizardSeparator", height=ui.Pixel(1))
                with ui.ScrollingFrame():
                    logs = self._get_combined_logs(self.row.job)
                    self._log_container = ui.VStack(height=0)
                    with self._log_container:
                        for line, color in logs:
                            ui.Label(line, style={"color": color})
                        ui.Spacer()

    def _get_combined_logs(self, job) -> list[tuple[str, str]]:
        job_dir = getattr(job, "job_dir", None)
        if job_dir is None:
            job_dir = omni.flux.job_queue.core.execute.get_default_job_directory(self.interface, job.job_id)

        stdout_path = job_dir / "logs" / "stdout.log"
        stderr_path = job_dir / "logs" / "stderr.log"

        log_lines = []
        # regex for timestamp: [2026-01-15T11:15:41.936600]
        timestamp_re = re.compile(r"^\[(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\]")

        def parse_line(line, color):
            match = timestamp_re.match(line)
            if match:
                try:
                    ts = datetime.datetime.strptime(match.group("ts"), "%Y-%m-%dT%H:%M:%S.%f")
                except Exception:  # noqa: BLE001
                    ts = None
            else:
                ts = None
            return ts, line.rstrip(), color

        if stdout_path and stdout_path.exists():
            with open(stdout_path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip():
                        log_lines.append(parse_line(line, "green"))
        if stderr_path and stderr_path.exists():
            with open(stderr_path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip():
                        log_lines.append(parse_line(line, "red"))
        # Sort by timestamp, fallback to original order if no timestamp
        log_lines.sort(key=lambda x: (x[0] is None, x[0] or datetime.datetime.min))
        return [(line, color) for _, line, color in log_lines]

    def _open_job_folder(self, job: omni.flux.job_queue.core.job.Job) -> None:
        job_dir = getattr(job, "job_dir", None)
        if job_dir is None:
            job_dir = omni.flux.job_queue.core.execute.get_default_job_directory(self.interface, job.job_id)

        if job_dir and job_dir.exists():
            if sys.platform == "win32":
                command = ["explorer", str(job_dir)]
            elif sys.platform == "darwin":
                command = ["open", str(job_dir)]
            else:
                command = ["xdg-open", str(job_dir)]

            try:
                with subprocess.Popen(command):
                    pass
            except OSError as exc:
                carb.log_warn(f"[QueueItemDelegate] Failed to open job folder '{job_dir}': {exc}")


class QueueWidget:
    """
    Complete job queue widget with controls and job list.

    Includes:
    - Start/Stop scheduler controls
    - Manual refresh button
    - Delete selected button
    - Auto-apply toggle
    - Apply selected button
    - Job list with details panel

    Args:
        interface: The job queue interface.
        callback_executor: Executor for applying job results.
        executor: Optional custom executor for job execution.
        scheduler: Optional custom scheduler. Created automatically if not provided.
    """

    def __init__(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        callback_executor: CallbackExecutor,
        executor: omni.flux.job_queue.core.execute.JobExecutor | None = None,
        scheduler: omni.flux.job_queue.core.execute.JobScheduler | None = None,
    ) -> None:
        self._owns_executor = executor is None and scheduler is None
        self._owns_scheduler = scheduler is None

        if executor is None:
            executor = omni.flux.job_queue.core.execute.JobExecutor(
                interface=interface,
                executor=concurrent.futures.ThreadPoolExecutor(max_workers=1),
            )

        # Use provided scheduler or create a new one
        if scheduler is not None:
            self.scheduler = scheduler
        else:
            self.scheduler = omni.flux.job_queue.core.execute.JobScheduler(
                interface=interface,
                executor=executor,
            )
        self._scheduler_changed_event = Event()

        self.model = QueueModel(interface, callback_executor=callback_executor)
        self.delegate = QueueItemDelegate(self.model)

        self.event_subscriber = omni.flux.job_queue.core.interface.EventSubscriber(interface)

        with ui.VStack():
            with ui.HStack(height=ui.Pixel(30), spacing=ui.Pixel(8)):
                start_button = ui.Image(
                    "",
                    name="Start",
                    tooltip="Start the job scheduler",
                    height=ui.Pixel(24),
                    width=ui.Pixel(24),
                    mouse_pressed_fn=lambda *_: self.start_scheduler(),
                )
                stop_button = ui.Image(
                    "",
                    name="Stop",
                    tooltip="Stop the job scheduler",
                    height=ui.Pixel(24),
                    width=ui.Pixel(24),
                    mouse_pressed_fn=lambda *_: self.stop_scheduler(),
                )
                ui.Rectangle(name="WizardSeparator", width=ui.Pixel(1))
                ui.Image(
                    "",
                    name="Refresh",
                    tooltip="Manually refresh the job queue",
                    height=ui.Pixel(24),
                    width=ui.Pixel(24),
                    mouse_pressed_fn=lambda *_: self.model.refresh(force=True),
                )
                self._delete_selected_btn = ui.Image(
                    "",
                    name="TrashCan",
                    tooltip="Delete Selected Jobs",
                    height=ui.Pixel(24),
                    width=ui.Pixel(24),
                    mouse_pressed_fn=lambda *_: self.model.delete_selected(),
                )
                ui.Spacer()
                with ui.HStack(width=0, height=0, spacing=ui.Pixel(8)):
                    ui.Label(
                        "Auto Apply",
                        width=0,
                        tooltip="Automatically apply jobs once they complete.",
                    )
                    self._auto_apply_btn = ui.CheckBox(width=0)
                ui.Rectangle(name="WizardSeparator", width=ui.Pixel(1))
                with ui.HStack(width=0, height=0, spacing=ui.Pixel(8)):
                    self._apply_selected_btn = ui.Button(
                        "Apply Selected",
                        tooltip="Apply the selected jobs' callbacks",
                        clicked_fn=self.model.apply_selected,
                        width=ui.Pixel(100),
                        height=ui.Pixel(30),
                    )
                ui.Spacer(width=0)
            ui.Spacer(height=ui.Pixel(8))

            with ui.VStack():
                with ui.ScrollingFrame():
                    self.view = QueueView(
                        self.model,
                        self.delegate,
                    )

                self._job_details_frame = ui.CollapsableFrame("Job Details", height=0, collapsed=True)
                with self._job_details_frame:
                    self.job_details = JobDetails(self.model.interface)

                def _on_collapsed(collapsed: bool):
                    self._job_details_frame.height = ui.Percent(0 if collapsed else 50)
                    if not collapsed:
                        self._on_selection_changed(list(self.model.iter_selected_items()))

                self._job_details_frame.set_collapsed_changed_fn(_on_collapsed)

        # Wire up Start/Stop buttons
        def _on_scheduler_running_changed(running: bool):
            start_button.enabled = not running
            stop_button.enabled = running

        _on_scheduler_running_changed(self.is_scheduler_running())
        self._scheduler_changed_subscription = self.subscribe_scheduler_running_event(
            _on_scheduler_running_changed,
        )

        self._selection_changed_subscription = self.model.subscribe_selection_changed(self._on_selection_changed)
        self._on_selection_changed(list(self.model.iter_selected_items()))

        def _on_auto_apply_changed(enabled: bool):
            self.model.auto_apply = enabled

        self._auto_apply_btn.set_checked_changed_fn(_on_auto_apply_changed)

        # Wire up events to refresh the model
        self.event_subscriber.subscribe(self._on_queue_event)
        self.event_subscriber.start()

    def destroy(self) -> None:
        self.event_subscriber.stop()
        if self._owns_scheduler and self.scheduler.is_running():
            self.scheduler.stop(wait=True)
        if self._owns_executor:
            self.scheduler.executor.shutdown(wait=True)

    def subscribe_scheduler_running_event(self, callback: Callable[[bool], None]) -> EventSubscription:
        return EventSubscription(self._scheduler_changed_event, callback)

    def is_scheduler_running(self) -> bool:
        return self.scheduler.is_running()

    def start_scheduler(self, poll_interval: float = 5.0, timeout: float | None = None) -> None:
        self.scheduler.start(poll_interval=poll_interval, timeout=timeout)
        self._scheduler_changed_event(True)

    def stop_scheduler(self) -> None:
        """
        Stop the scheduler from picking up new jobs.

        The scheduler will finish the currently executing job (if any) before fully stopping.
        """
        self.scheduler.stop(wait=True)
        self._scheduler_changed_event(False)

    def _on_selection_changed(self, selected_items: list[QueueItem]) -> None:
        has_selected = bool(selected_items)
        self._apply_selected_btn.enabled = has_selected
        self._delete_selected_btn.enabled = has_selected

        if not self._job_details_frame.collapsed:
            if len(selected_items) == 1:
                self.job_details.set_job(selected_items[0].row)
            else:
                self.job_details.set_job(None)

    def _on_queue_event(self, _job_id, _event) -> None:
        # FIXME: We could likely be more efficient here by only updating affected rows
        self.model.refresh(force=True)

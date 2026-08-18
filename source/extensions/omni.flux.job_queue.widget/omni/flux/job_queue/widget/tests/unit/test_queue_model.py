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
import dataclasses
import datetime
import pathlib
import sqlite3
import threading
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation, JobState
from omni.flux.job_queue.core.errors import JobError
from omni.flux.job_queue.core.models import QueueGraphSnapshot, QueueJobSnapshot
from omni.flux.job_queue.core.job import Job, JobInputs, JobOutputs, JobProgress, JobProgressCallback
from omni.flux.job_queue.widget.constants import APPLY_FILTER_OPTIONS
from omni.flux.job_queue.widget.enums import DisplayState
from omni.flux.job_queue.widget.model import QueueModel
from omni.kit.test import AsyncTestCase

__all__ = ("TestQueueModel",)

_CONTEXT_NAME = "stagecraft"
_REGISTRY_FUNCTION = "omni.flux.job_queue.widget.row.get_display_adapter_registry"


@dataclasses.dataclass
class _MockJob(Job):
    """Concrete typed job used by queue-model tests."""

    async def execute(
        self,
        _job_directory: pathlib.Path,
        _inputs: JobInputs,
        _progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return no outputs for a deterministic test job.

        Args:
            _job_directory: Queue-owned directory for test artifacts.
            _inputs: Resolved inputs supplied to the test job.
            _progress_callback: Callback for reporting execution progress.

        Returns:
            Empty job outputs.
        """
        return JobOutputs()


def _snapshot(
    *,
    graph_id: uuid.UUID,
    graph_name: str = "Graph",
    graph_position: int = 0,
    job_id: uuid.UUID | None = None,
    job_name: str = "Job",
    position: int = 0,
    state: JobState = JobState.DONE,
    progress: JobProgress | None = None,
    disposition: ApplyDisposition = ApplyDisposition.NOT_APPLICABLE,
    operation: ApplyOperation = ApplyOperation.IDLE,
    state_reason: str | None = None,
    apply_reason: str | None = None,
    error: JobError | None = None,
    apply_error: JobError | None = None,
    apply_handler_id: str | None = None,
    started_at: datetime.datetime | None = None,
    completed_at: datetime.datetime | None = None,
) -> QueueJobSnapshot:
    """Build one frozen core snapshot with readable defaults.

    Args:
        graph_id: Durable graph identifier.
        graph_name: User-facing graph name.
        graph_position: Durable graph order.
        job_id: Optional durable job identifier.
        job_name: User-facing job name.
        position: Job order within the graph.
        state: Execution lifecycle state.
        progress: Optional execution progress.
        disposition: Durable Apply disposition.
        operation: Transient Apply operation.
        state_reason: Safe execution-state reason.
        apply_reason: Safe Apply-state reason.
        error: Optional execution diagnostic.
        apply_error: Optional Apply diagnostic.
        apply_handler_id: Stable exact Apply handler identity.
        started_at: Optional execution start time.
        completed_at: Optional execution completion time.

    Returns:
        Frozen job snapshot.
    """
    now = datetime.datetime.now()
    return QueueJobSnapshot(
        graph_id=graph_id,
        graph_name=graph_name,
        graph_position=graph_position,
        job_id=job_id or uuid.uuid4(),
        job_name=job_name,
        job_type="test.MockJob",
        position=position,
        submitted_at=now,
        started_at=started_at,
        completed_at=completed_at,
        state=state,
        state_reason=state_reason,
        progress=progress,
        error=error,
        apply_disposition=disposition,
        apply_operation=operation,
        apply_handler_id=apply_handler_id,
        apply_reason=apply_reason,
        apply_error=apply_error,
    )


def _graph(*jobs: QueueJobSnapshot) -> QueueGraphSnapshot:
    """Build a graph snapshot from jobs sharing one graph.

    Args:
        *jobs: Ordered snapshots that share graph metadata.

    Returns:
        Graph snapshot containing the supplied jobs.
    """
    first = jobs[0]
    return QueueGraphSnapshot(
        graph_id=first.graph_id,
        name=first.graph_name,
        position=first.graph_position,
        submitted_at=first.submitted_at,
        jobs=jobs,
    )


def _model(
    graphs: list[QueueGraphSnapshot],
    jobs: dict[uuid.UUID, Job] | None = None,
    adapter=None,
    *,
    handler_available: bool = True,
    handler_availability_error: Exception | None = None,
) -> QueueModel:
    """Build and refresh a model from mocked core snapshots.

    Args:
        graphs: Graph snapshots exposed by the mocked interface.
        jobs: Optional typed jobs keyed by durable identifier.
        adapter: Optional display adapter returned for typed jobs.
        handler_available: Whether configured Apply handlers resolve.
        handler_availability_error: Optional registry failure raised while resolving handlers.

    Returns:
        Refreshed queue model with mocked runtime dependencies.
    """
    interface = MagicMock()
    interface.get_graph_snapshots.return_value = graphs
    snapshots = {snapshot.job_id: snapshot for graph in graphs for snapshot in graph.jobs}
    interface.get_job_snapshot.side_effect = snapshots.get
    interface.get_job.side_effect = (jobs or {}).get
    apply_executor = MagicMock()
    apply_executor.apply = AsyncMock()
    apply_executor.decline = AsyncMock()
    apply_executor.revert = AsyncMock()
    apply_executor.is_handler_available.return_value = handler_available
    apply_executor.is_handler_available.side_effect = handler_availability_error
    apply_executor.get_apply_block_reason.return_value = None
    interface.delete_graphs.return_value = ()
    model = QueueModel(interface, apply_executor, _CONTEXT_NAME)
    with patch(_REGISTRY_FUNCTION) as get_registry:
        get_registry.return_value.get_adapter.return_value = adapter
        model.refresh()
    return model


class TestQueueModel(AsyncTestCase):
    """Verify hierarchical queue presentation and captured bulk actions."""

    async def test_refresh_same_named_graphs_builds_distinct_roots_with_children(self):
        """Graph identity comes from graph ID and one-job graphs remain hierarchical."""
        # Arrange
        first = _snapshot(graph_id=uuid.uuid4(), graph_name="Same", graph_position=0)
        second = _snapshot(graph_id=uuid.uuid4(), graph_name="Same", graph_position=1)

        # Act
        model = _model([_graph(first), _graph(second)])

        # Assert
        roots = model.get_item_children(None)
        self.assertEqual([root.graph_id for root in roots], [first.graph_id, second.graph_id])
        self.assertEqual([root.name for root in roots], ["Same", "Same"])
        self.assertEqual([len(model.get_item_children(root)) for root in roots], [1, 1])
        self.assertEqual(model.get_graph_filter_options(), ("Same",))

    async def test_refresh_existing_graph_and_job_preserves_object_identity(self):
        """A full synchronization reuses native tree items by durable IDs."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4())
        model = _model([_graph(snapshot)])
        first_root = model.get_item_children(None)[0]
        first_child = model.get_item_children(first_root)[0]
        model.interface.get_graph_snapshots.return_value = [_graph(dataclasses.replace(snapshot, job_name="Updated"))]

        # Act
        with patch(_REGISTRY_FUNCTION) as get_registry:
            get_registry.return_value.get_adapter.return_value = None
            model.refresh()

        # Assert
        self.assertIs(model.get_item_children(None)[0], first_root)
        self.assertIs(model.get_item_children(first_root)[0], first_child)
        self.assertEqual(first_child.row.name, "Updated")

    async def test_refresh_clears_removed_selection_before_structural_invalidation(self):
        """Details consumers stop reading a deleted item before the tree rebuilds."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4())
        model = _model([_graph(snapshot)])
        selected = model.all_graphs[0]
        model.set_items_selected([selected])
        events = []
        selection_subscription = model.subscribe_selection_changed(
            lambda items: events.append(("selection", tuple(items)))
        )
        model_changed_subscription = model.subscribe_item_changed_fn(
            lambda _model, item: events.append(("structure", item))
        )
        model.interface.get_graph_snapshots.return_value = []

        # Act
        model.refresh()

        # Assert
        self.assertEqual(events[0], ("selection", ()))
        self.assertIn(("structure", None), events[1:])
        self.assertIsNotNone(selection_subscription)
        self.assertIsNotNone(model_changed_subscription)

    async def test_status_filter_retains_root_and_only_matching_children(self):
        """A matching child retains its root without exposing non-matching siblings."""
        # Arrange
        graph_id = uuid.uuid4()
        failed = _snapshot(graph_id=graph_id, job_name="Failed", state=JobState.FAILED, position=0)
        done = _snapshot(graph_id=graph_id, job_name="Done", state=JobState.DONE, position=1)
        model = _model([_graph(failed, done)])

        # Act
        model.set_status_filter({DisplayState.DONE})

        # Assert
        roots = model.get_item_children(None)
        self.assertEqual(len(roots), 1)
        self.assertEqual([item.row.name for item in model.get_item_children(roots[0])], ["Done"])
        self.assertEqual(model.resolve_graph_display_state(roots[0]), DisplayState.FAILED)

    async def test_job_stage_filters_compose_graph_and_child_names(self):
        """The combined Job / Stage column filters graphs and child stages independently."""
        # Arrange
        first_graph_id = uuid.uuid4()
        second_graph_id = uuid.uuid4()
        first_generation = _snapshot(
            graph_id=first_graph_id,
            graph_name="First Material",
            job_name="Generation",
            position=0,
        )
        first_processing = _snapshot(
            graph_id=first_graph_id,
            graph_name="First Material",
            job_name="Asset processing",
            position=1,
        )
        second_generation = _snapshot(
            graph_id=second_graph_id,
            graph_name="Second Material",
            graph_position=1,
            job_name="Generation",
        )
        model = _model([_graph(first_generation, first_processing), _graph(second_generation)])

        # Act
        model.set_job_stage_filter({"First Material"}, {"Asset processing"})

        # Assert
        roots = model.get_item_children(None)
        self.assertEqual([root.name for root in roots], ["First Material"])
        self.assertEqual([item.row.name for item in model.get_item_children(roots[0])], ["Asset processing"])

    async def test_apply_filter_options_match_durable_dispositions_one_to_one(self):
        """Apply filtering exposes every durable disposition without aliases."""
        # Arrange
        graph_id = uuid.uuid4()
        snapshots = tuple(
            _snapshot(
                graph_id=graph_id,
                job_name=disposition.value,
                position=position,
                disposition=disposition,
            )
            for position, disposition in enumerate(ApplyDisposition)
        )
        expected = {
            "Not Ready": ApplyDisposition.NOT_READY,
            "No Apply Needed": ApplyDisposition.NOT_APPLICABLE,
            "Ready to Apply": ApplyDisposition.PENDING,
            "Applied": ApplyDisposition.APPLIED,
            "Declined": ApplyDisposition.DECLINED,
        }

        for disposition, label in APPLY_FILTER_OPTIONS:
            with self.subTest(label=label):
                model = _model([_graph(*snapshots)])

                # Act
                model.set_apply_filter({disposition})

                # Assert
                self.assertEqual(
                    tuple(item.row.apply_disposition for item in model.visible_job_items), (expected[label],)
                )

    async def test_graph_tooltip_names_hidden_child_that_determines_status(self):
        """Aggregate status help identifies a decisive child hidden by filters."""
        # Arrange
        graph_id = uuid.uuid4()
        failed = _snapshot(graph_id=graph_id, job_name="Hidden Failure", state=JobState.FAILED, position=0)
        done = _snapshot(graph_id=graph_id, job_name="Visible", state=JobState.DONE, position=1)
        model = _model([_graph(failed, done)])
        root = model.get_item_children(None)[0]
        model.set_status_filter({DisplayState.DONE})

        # Act
        tooltip = model.get_graph_state_tooltip(root)

        # Assert
        self.assertIn("Failed: 1", tooltip)
        self.assertIn("Done: 1", tooltip)
        self.assertIn("Hidden Failure", tooltip)
        self.assertIn("hidden by the current filters", tooltip)

    async def test_active_graph_uses_decisive_child_adapter_status_label(self):
        """A graph root reflects product progress text without implementation names."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4(), state=JobState.IN_PROGRESS)
        job = _MockJob()
        adapter = MagicMock()
        adapter.get_name_display.return_value = "Texture pass"
        adapter.get_source_name.return_value = "Materials"
        adapter.get_active_status_label.return_value = "Processing textures"
        model = _model([_graph(snapshot)], {snapshot.job_id: job}, adapter)
        root = model.get_item_children(None)[0]

        # Act
        label = model.get_graph_status_label(root)

        # Assert
        self.assertEqual(label, "Processing textures · 0/1 job")
        self.assertNotIn(type(job).__name__, label)

    async def test_active_status_uses_human_readable_progress_detail_before_raw_counts(self):
        """Generic active status preserves human-readable progress detail."""
        # Arrange
        snapshot = _snapshot(
            graph_id=uuid.uuid4(),
            state=JobState.IN_PROGRESS,
            progress=JobProgress(completed=1, total=3, detail="Downloading textures"),
        )
        job = _MockJob()
        adapter = MagicMock()
        adapter.get_name_display.return_value = "Texture pass"
        adapter.get_source_name.return_value = "Materials"
        adapter.get_active_status_label.return_value = None
        adapter.get_active_progress_label.return_value = None
        model = _model([_graph(snapshot)], {snapshot.job_id: job}, adapter)

        # Act
        label = model.get_status_label(model.all_items[0].row)

        # Assert
        self.assertEqual(label, "Running · Downloading textures")

    async def test_unknown_state_is_unavailable(self):
        """Unknown persisted state is presented as corrupted instead of queued."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4(), state=JobState.UNKNOWN)
        model = _model([_graph(snapshot)])

        # Act
        state = model.resolve_display_state(model.all_items[0].row)

        # Assert
        self.assertEqual(state, DisplayState.CORRUPTED)

    async def test_unregistered_apply_handler_is_displayed_as_unavailable(self):
        """A completed job overlays its durable Apply state when its exact handler is missing."""
        # Arrange
        snapshot = _snapshot(
            graph_id=uuid.uuid4(),
            disposition=ApplyDisposition.PENDING,
            apply_handler_id="test.Handler",
        )
        model = _model([_graph(snapshot)], handler_available=False)

        # Act
        state = model.resolve_display_state(model.all_items[0].row)

        # Assert
        self.assertEqual(state, DisplayState.HANDLER_UNAVAILABLE)
        item = model.all_items[0]
        expected_reason = "The feature needed to update this job's result is unavailable."
        self.assertEqual(model.get_check_block_reason(item, allow_reapply=True), expected_reason)
        self.assertEqual(model.get_x_block_reason(item), expected_reason)
        self.assertFalse(model.can_check_item(item, allow_reapply=True))
        self.assertFalse(model.can_x_item(item))

    async def test_handler_availability_database_failure_is_displayed_as_unavailable(self):
        """A transient snapshot read failure cannot escape status rendering."""
        # Arrange
        snapshot = _snapshot(
            graph_id=uuid.uuid4(),
            disposition=ApplyDisposition.PENDING,
            apply_handler_id="test.Handler",
        )
        model = _model(
            [_graph(snapshot)],
            handler_availability_error=sqlite3.OperationalError("database busy"),
        )

        # Act
        state = model.resolve_display_state(model.all_items[0].row)

        # Assert
        self.assertEqual(state, DisplayState.HANDLER_UNAVAILABLE)
        item = model.all_items[0]
        expected_reason = "The feature needed to update this job's result is unavailable."
        self.assertEqual(model.get_check_block_reason(item, allow_reapply=True), expected_reason)
        self.assertEqual(model.get_x_block_reason(item), expected_reason)
        self.assertFalse(model.can_check_item(item, allow_reapply=True))
        self.assertFalse(model.can_x_item(item))

    async def test_adapter_waiting_reason_marks_queued_job_waiting(self):
        """A product scheduling condition uses the waiting state and safe reason."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4(), state=JobState.QUEUED)
        job = _MockJob(job_id=snapshot.job_id)
        adapter = MagicMock()
        adapter.get_name_display.return_value = "Waiting job"
        adapter.get_source_name.return_value = "Product"
        adapter.get_waiting_reason.return_value = "Waiting for the product server."
        model = _model([_graph(snapshot)], {snapshot.job_id: job}, adapter)
        row = model.all_items[0].row

        # Act
        state = model.resolve_display_state(row)

        # Assert
        self.assertEqual(state, DisplayState.WAITING)
        self.assertEqual(model.get_state_tooltip(row, state), "Waiting for the product server.")

    async def test_failure_tooltip_uses_safe_reason_not_diagnostic(self):
        """Primary status help never leaks the durable exception message."""
        # Arrange
        diagnostic = JobError("SecretError", "internal database address", "traceback")
        snapshot = _snapshot(
            graph_id=uuid.uuid4(),
            state=JobState.FAILED,
            state_reason="The job could not process its input.",
            error=diagnostic,
        )
        model = _model([_graph(snapshot)])
        row = model.all_items[0].row

        # Act
        tooltip = model.get_state_tooltip(row)

        # Assert
        self.assertEqual(tooltip, "The job could not process its input.")
        self.assertNotIn(diagnostic.message, tooltip)

    async def test_failure_tooltip_removes_durable_job_identifier(self):
        """Fallback status help replaces implementation UUIDs with readable text."""
        # Arrange
        prerequisite_id = uuid.uuid4()
        snapshot = _snapshot(
            graph_id=uuid.uuid4(),
            state=JobState.SKIPPED,
            state_reason=f"Skipped because prerequisite {prerequisite_id} failed.",
        )
        model = _model([_graph(snapshot)])

        # Act
        tooltip = model.get_state_tooltip(model.all_items[0].row)

        # Assert
        self.assertNotIn(str(prerequisite_id), tooltip)
        self.assertIn("another job", tooltip)

    async def test_apply_failure_tooltip_uses_safe_apply_reason(self):
        """Apply status help uses the sanitized Apply reason, not diagnostics."""
        # Arrange
        diagnostic = JobError("SecretApplyError", "private target", "traceback")
        snapshot = _snapshot(
            graph_id=uuid.uuid4(),
            operation=ApplyOperation.APPLY_FAILED,
            apply_reason="The result could not be added to the project.",
            apply_error=diagnostic,
        )
        model = _model([_graph(snapshot)])
        row = model.all_items[0].row

        # Act
        tooltip = model.get_state_tooltip(row)

        # Assert
        self.assertEqual(tooltip, "The result could not be added to the project.")
        self.assertNotIn(diagnostic.message, tooltip)

    async def test_apply_action_exposes_transient_product_prerequisite(self):
        """Check stays disabled with exact recovery guidance while its product target is unavailable."""
        # Arrange
        snapshot = _snapshot(
            graph_id=uuid.uuid4(),
            disposition=ApplyDisposition.PENDING,
            apply_handler_id="test.ApplyHandler",
        )
        model = _model([_graph(snapshot)])
        item = model.all_items[0]
        expected_reason = "This job belongs to a different project. Open its project before applying."
        model.apply_executor.get_apply_block_reason.return_value = expected_reason

        # Act
        block_reason = model.get_check_block_reason(item, allow_reapply=True)

        # Assert
        self.assertEqual(block_reason, expected_reason)
        self.assertFalse(model.can_check_item(item, allow_reapply=True))
        self.assertIsNone(model.get_x_block_reason(item))
        self.assertTrue(model.can_x_item(item))

    async def test_applied_result_uses_product_prerequisite_for_reapply_and_revert(self):
        """Applied results keep their disposition while the product target blocks both mutations."""
        # Arrange
        snapshot = _snapshot(
            graph_id=uuid.uuid4(),
            disposition=ApplyDisposition.APPLIED,
            apply_handler_id="test.ApplyHandler",
        )
        model = _model([_graph(snapshot)])
        item = model.all_items[0]
        expected_reason = "Open the project used to create this job before applying its results."
        model.apply_executor.get_apply_block_reason.return_value = expected_reason

        # Act
        check_reason = model.get_check_block_reason(item, allow_reapply=True)
        x_reason = model.get_x_block_reason(item)

        # Assert
        self.assertEqual(check_reason, expected_reason)
        self.assertEqual(x_reason, expected_reason)
        self.assertFalse(model.can_check_item(item, allow_reapply=True))
        self.assertFalse(model.can_x_item(item))

    async def test_corrupted_job_uses_one_explicit_unavailable_reason_for_both_actions(self):
        """An unreadable saved job never falls through to misleading result or availability errors."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4(), disposition=ApplyDisposition.PENDING)
        model = _model([_graph(snapshot)])
        item = model.all_items[0]
        item.row.is_corrupted = True
        expected_reason = "This saved job type is unavailable. Delete the job and submit it again."

        # Act
        check_reason = model.get_check_block_reason(item, allow_reapply=True)
        x_reason = model.get_x_block_reason(item)

        # Assert
        self.assertEqual(check_reason, expected_reason)
        self.assertEqual(x_reason, expected_reason)
        self.assertFalse(model.can_check_item(item, allow_reapply=True))
        self.assertFalse(model.can_x_item(item))

    async def test_graph_is_applied_only_when_all_applicable_children_are_applied(self):
        """One applied child does not hide another child's pending result."""
        # Arrange
        graph_id = uuid.uuid4()
        applied = _snapshot(graph_id=graph_id, position=0, disposition=ApplyDisposition.APPLIED)
        pending = _snapshot(graph_id=graph_id, position=1, disposition=ApplyDisposition.PENDING)
        model = _model([_graph(applied, pending)])
        root = model.get_item_children(None)[0]

        # Act
        state = model.resolve_graph_display_state(root)

        # Assert
        self.assertEqual(state, DisplayState.READY_TO_APPLY)

    async def test_graph_mixed_applied_and_declined_is_partially_applied(self):
        """A fully decided mixed result set remains visibly partially applied."""
        # Arrange
        graph_id = uuid.uuid4()
        applied = _snapshot(graph_id=graph_id, position=0, disposition=ApplyDisposition.APPLIED)
        declined = _snapshot(graph_id=graph_id, position=1, disposition=ApplyDisposition.DECLINED)
        model = _model([_graph(applied, declined)])
        root = model.get_item_children(None)[0]

        # Act
        state = model.resolve_graph_display_state(root)

        # Assert
        self.assertEqual(state, DisplayState.PARTIALLY_APPLIED)
        self.assertEqual(state.label, "Partially Applied")

    async def test_graph_tooltip_combines_equal_waiting_labels(self):
        """Temporary and dependency waiting counts share one unambiguous label."""
        # Arrange
        graph_id = uuid.uuid4()
        blocked = _snapshot(graph_id=graph_id, position=0, state=JobState.QUEUED)
        dependent = _snapshot(graph_id=graph_id, position=1, state=JobState.WAITING_FOR_DEPENDENCIES)
        blocked_job = _MockJob(job_id=blocked.job_id)
        dependent_job = _MockJob(job_id=dependent.job_id)
        adapter = MagicMock()
        adapter.get_name_display.side_effect = lambda job: job.name
        adapter.get_source_name.return_value = "Product"
        adapter.get_waiting_reason.return_value = "Waiting for the product server."
        model = _model(
            [_graph(blocked, dependent)],
            {blocked.job_id: blocked_job, dependent.job_id: dependent_job},
            adapter,
        )

        # Act
        tooltip = model.get_graph_state_tooltip(model.all_graphs[0])

        # Assert
        self.assertIn("Waiting: 2", tooltip)
        self.assertEqual(tooltip.count("Waiting:"), 1)

    async def test_drag_graph_updates_only_graph_positions(self):
        """Dropping a graph root persists graph order without reparenting children."""
        # Arrange
        first = _snapshot(graph_id=uuid.uuid4(), graph_position=0)
        second = _snapshot(graph_id=uuid.uuid4(), graph_position=1)
        model = _model([_graph(first), _graph(second)])
        first_root, second_root = model.get_item_children(None)

        # Act
        model.drop(first_root, second_root, 0)

        # Assert
        model.interface.update_graph_positions.assert_called_once_with([second.graph_id, first.graph_id])
        self.assertEqual([root.graph_id for root in model.all_graphs], [second.graph_id, first.graph_id])

    async def test_drag_graph_between_filtered_roots_preserves_hidden_graph_order(self):
        """A visible insertion slot maps through visible neighbors without moving hidden roots relative to each other."""
        # Arrange
        chair_id = uuid.uuid4()
        table_id = uuid.uuid4()
        lamp_id = uuid.uuid4()
        door_id = uuid.uuid4()
        model = _model(
            [
                _graph(_snapshot(graph_id=chair_id, graph_name="Chair Success", graph_position=0)),
                _graph(_snapshot(graph_id=table_id, graph_name="Table Failed", graph_position=1)),
                _graph(_snapshot(graph_id=lamp_id, graph_name="Lamp Success", graph_position=2)),
                _graph(_snapshot(graph_id=door_id, graph_name="Door Failed", graph_position=3)),
            ]
        )
        model.set_job_stage_filter({"Table Failed", "Door Failed"}, None)
        table_root, _door_root = model.get_item_children(None)

        # Act
        model.drop(None, table_root, 2)

        # Assert
        expected_order = [chair_id, lamp_id, door_id, table_id]
        model.interface.update_graph_positions.assert_called_once_with(expected_order)
        self.assertEqual([root.graph_id for root in model.all_graphs], expected_order)

    async def test_child_has_no_drag_data(self):
        """A job child cannot start a graph reorder drag."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4())
        model = _model([_graph(snapshot)])
        child = model.get_item_children(model.get_item_children(None)[0])[0]

        # Act
        drag_data = model.get_drag_mime_data(child)

        # Assert
        self.assertEqual(drag_data, "")

    async def test_child_does_not_accept_graph_drop(self):
        """A job child cannot become a graph reorder target."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4())
        model = _model([_graph(snapshot)])
        root = model.get_item_children(None)[0]
        child = model.get_item_children(root)[0]

        # Act
        accepted = model.drop_accepted(child, root)

        # Assert
        self.assertFalse(accepted)

    async def test_apply_items_deduplicates_capture_and_reapplies_applied_jobs(self):
        """Bulk Check applies or reapplies each captured eligible ID exactly once."""
        # Arrange
        graph_id = uuid.uuid4()
        pending = _snapshot(
            graph_id=graph_id,
            position=0,
            disposition=ApplyDisposition.PENDING,
        )
        applied = _snapshot(
            graph_id=graph_id,
            position=1,
            disposition=ApplyDisposition.APPLIED,
        )
        model = _model([_graph(pending, applied)])
        captured = (*model.visible_job_items, model.visible_job_items[0])

        # Act
        with patch("omni.flux.job_queue.widget.model.post_notification") as notify:
            await model.apply_items(captured, "current filters")

        # Assert
        self.assertEqual(
            model.apply_executor.apply.await_args_list,
            [call(pending.job_id), call(applied.job_id)],
        )
        self.assertIn("applying 1", notify.call_args_list[0].args[0])
        self.assertIn("reapplying 1", notify.call_args_list[0].args[0])
        self.assertIn("applied 1", notify.call_args_list[-1].args[0])
        self.assertIn("reapplied 1", notify.call_args_list[-1].args[0])
        self.assertIn("skipped 0", notify.call_args_list[-1].args[0])
        self.assertIn("current filters", notify.call_args_list[-1].args[0])

    async def test_decline_or_revert_items_runs_exact_confirmed_groups(self):
        """Bulk X executes the exact Decline and Revert groups supplied by its caller."""
        # Arrange
        graph_id = uuid.uuid4()
        pending = _snapshot(graph_id=graph_id, position=0, disposition=ApplyDisposition.PENDING)
        applied = _snapshot(graph_id=graph_id, position=1, disposition=ApplyDisposition.APPLIED)
        model = _model([_graph(pending, applied)])
        pending_item, applied_item = model.visible_job_items

        # Act
        with patch("omni.flux.job_queue.widget.model.post_notification") as notify:
            await model.decline_or_revert_items((pending_item,), (applied_item,), 0, "current filters")

        # Assert
        model.apply_executor.decline.assert_awaited_once_with(pending.job_id)
        model.apply_executor.revert.assert_awaited_once_with(applied.job_id)
        self.assertIn("declined 1", notify.call_args_list[-1].args[0])
        self.assertIn("reverted 1", notify.call_args_list[-1].args[0])

    async def test_apply_items_continues_after_product_failure_and_reports_completion(self):
        """One product failure does not prevent later captured jobs from applying."""
        # Arrange
        graph_id = uuid.uuid4()
        first = _snapshot(graph_id=graph_id, position=0, disposition=ApplyDisposition.PENDING)
        second = _snapshot(graph_id=graph_id, position=1, disposition=ApplyDisposition.PENDING)
        model = _model([_graph(first, second)])
        model.apply_executor.apply.side_effect = [OSError("unavailable"), None]

        # Act
        with patch("omni.flux.job_queue.widget.model.post_notification") as notify:
            await model.apply_items(tuple(model.visible_job_items), "current filters")

        # Assert
        self.assertEqual(model.apply_executor.apply.await_count, 2)
        self.assertIn("applied 1", notify.call_args_list[-1].args[0])
        self.assertIn("failed 1", notify.call_args_list[-1].args[0])

    async def test_bulk_check_reserves_every_candidate_before_scheduling(self):
        """One bulk Check reserves every candidate before asynchronous work begins."""
        # Arrange
        graph_id = uuid.uuid4()
        first = _snapshot(graph_id=graph_id, position=0, disposition=ApplyDisposition.PENDING)
        second = _snapshot(graph_id=graph_id, position=1, disposition=ApplyDisposition.PENDING)
        model = _model([_graph(first, second)])
        items = tuple(model.visible_job_items)

        # Act
        task = model.apply_items(items, "current filters")

        # Assert
        try:
            self.assertTrue(all(model.is_busy(item) for item in items))
            self.assertTrue(all(not model.can_check_item(item, allow_reapply=True) for item in items))
        finally:
            # Cleanup
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_graph_delete_disabled_while_child_is_active(self):
        """A graph cannot be deleted while any child is executing or applying."""
        # Arrange
        graph_id = uuid.uuid4()
        active = _snapshot(graph_id=graph_id, state=JobState.IN_PROGRESS)
        model = _model([_graph(active)])
        root = model.get_item_children(None)[0]

        # Act
        can_delete = model.can_delete_graph(root)

        # Assert
        self.assertFalse(can_delete)

    async def test_delete_action_uses_all_selected_graph_roots_when_anchor_is_selected(self):
        """A root action captures every selected graph without including selected child rows."""
        # Arrange
        first = _snapshot(graph_id=uuid.uuid4(), graph_name="First", graph_position=0)
        second = _snapshot(graph_id=uuid.uuid4(), graph_name="Second", graph_position=1)
        model = _model([_graph(first), _graph(second)])
        first_root, second_root = model.all_graphs
        model.set_items_selected([first_root, model.all_items[0], second_root])

        # Act
        graphs = model.get_delete_action_graphs(first_root)

        # Assert
        self.assertEqual(graphs, (first_root, second_root))

    async def test_graph_artifact_file_count_forwards_exact_core_count_off_ui_thread(self):
        """Delete confirmation receives the exact core-owned count without blocking the UI."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4())
        model = _model([_graph(snapshot)])
        ui_thread = threading.get_ident()
        inventory_threads = []

        def get_graphs_artifact_file_count(_graph_ids):
            inventory_threads.append(threading.get_ident())
            return 2

        model.interface.get_graphs_artifact_file_count.side_effect = get_graphs_artifact_file_count
        counts = []

        # Act
        model.get_graphs_artifact_file_count((model.all_graphs[0],), counts.append)
        await model.wait_for_background_tasks()

        # Assert
        model.interface.get_graphs_artifact_file_count.assert_called_once_with((snapshot.graph_id,))
        self.assertEqual(len(inventory_threads), 1)
        self.assertNotEqual(inventory_threads[0], ui_thread)
        self.assertEqual(counts, [2])

    async def test_graph_artifact_inventory_failure_reports_no_changes(self):
        """An incomplete file inventory prevents a destructive prompt or deletion."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4())
        model = _model([_graph(snapshot)])
        model.interface.get_graphs_artifact_file_count.side_effect = OSError("access denied")
        counts = []

        # Act
        with patch("omni.flux.job_queue.widget.model.post_notification") as notify:
            model.get_graphs_artifact_file_count((model.all_graphs[0],), counts.append)
            await model.wait_for_background_tasks()

        # Assert
        self.assertEqual(counts, [])
        self.assertIn("were not changed", notify.call_args.args[0])
        model.interface.delete_graphs.assert_not_called()

    async def test_graph_delete_failure_keeps_graph_and_reports_unchanged_folders(self):
        """A database failure leaves the visible graph intact and starts no cleanup."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4())
        model = _model([_graph(snapshot)])
        model.interface.delete_graphs.side_effect = RuntimeError("database busy")
        root = model.get_item_children(None)[0]

        # Act
        with patch("omni.flux.job_queue.widget.model.post_notification") as notify:
            model.delete_graphs((root,))
            await model.wait_for_background_tasks()

        # Assert
        self.assertEqual(model.get_item_children(None), [root])
        self.assertIn("were not changed", notify.call_args.args[0])

    async def test_graph_delete_clears_affected_selection_before_database_work(self):
        """Details stop reading selected graph rows before asynchronous deletion starts."""
        # Arrange
        first = _snapshot(graph_id=uuid.uuid4(), graph_name="First", graph_position=0)
        second = _snapshot(graph_id=uuid.uuid4(), graph_name="Second", graph_position=1)
        model = _model([_graph(first), _graph(second)])
        first_root, second_root = model.all_graphs
        model.set_items_selected([first_root, model.all_items[0], second_root])

        # Act
        model.delete_graphs((first_root,))

        # Assert
        self.assertEqual(model.selected_items, [second_root])
        await model.wait_for_background_tasks()

    async def test_graph_delete_cleanup_failure_reports_core_retained_path(self):
        """A committed graph reports the inactive path retained by core cleanup."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4())
        model = _model([_graph(snapshot)])
        retained_path = pathlib.Path("inactive") / str(snapshot.graph_id)
        ui_thread = threading.get_ident()
        delete_threads = []

        def delete_graphs(_graph_ids):
            delete_threads.append(threading.get_ident())
            model.interface.get_graph_snapshots.return_value.clear()
            return (retained_path,)

        model.interface.delete_graphs.side_effect = delete_graphs
        root = model.get_item_children(None)[0]

        # Act
        with patch("omni.flux.job_queue.widget.model.post_notification") as notify:
            model.delete_graphs((root,))
            await model.wait_for_background_tasks()

        # Assert
        self.assertEqual(model.get_item_children(None), [])
        self.assertEqual(len(delete_threads), 1)
        self.assertNotEqual(delete_threads[0], ui_thread)
        self.assertIn(str(retained_path), notify.call_args.args[0])

    async def test_update_item_invalidates_changed_child_and_parent(self):
        """One job event refreshes its child and aggregate graph row only."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4(), state=JobState.QUEUED)
        model = _model([_graph(snapshot)])
        root = model.get_item_children(None)[0]
        child = model.get_item_children(root)[0]
        model.interface.get_job_snapshot.side_effect = lambda _job_id: dataclasses.replace(
            snapshot, state=JobState.DONE
        )

        # Act
        with patch(_REGISTRY_FUNCTION) as get_registry, patch.object(model, "_item_changed") as item_changed:
            get_registry.return_value.get_adapter.return_value = None
            model.update_item(snapshot.job_id)

        # Assert
        self.assertEqual(item_changed.call_args_list, [call(child), call(root)])
        self.assertEqual(child.row.state, JobState.DONE)

    async def test_update_item_evaluates_only_changed_row_when_filter_membership_changes(self):
        """A targeted state event updates its own filtered membership without rescanning every row."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4(), state=JobState.QUEUED)
        model = _model([_graph(snapshot)])
        child = model.all_items[0]
        model.set_status_filter({DisplayState.DONE})
        model.interface.get_job_snapshot.side_effect = lambda _job_id: dataclasses.replace(
            snapshot, state=JobState.DONE
        )

        # Act
        with patch(_REGISTRY_FUNCTION) as get_registry, patch.object(model, "_item_changed") as item_changed:
            get_registry.return_value.get_adapter.return_value = None
            with patch.object(model, "_apply_filters") as apply_filters:
                model.update_item(snapshot.job_id)

        # Assert
        apply_filters.assert_not_called()
        self.assertTrue(model.is_item_visible(child))
        self.assertEqual(model.get_item_children(None), [child.parent])
        self.assertEqual(item_changed.call_args_list, [call(None)])

    async def test_progress_only_update_notifies_existing_item_without_tree_invalidation(self):
        """Structured progress updates the retained child without rebuilding tree cells."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4(), state=JobState.IN_PROGRESS, progress=JobProgress(1, 3))
        model = _model([_graph(snapshot)])
        child = model.all_items[0]
        changed_items = []
        subscription = model.subscribe_progress_changed(changed_items.append)
        progress = JobProgress(2, 3)

        # Act
        with (
            patch.object(model, "_apply_filters") as apply_filters,
            patch.object(model, "_item_changed") as item_changed,
        ):
            missing = model.update_progress_batch({snapshot.job_id: progress})

        # Assert
        self.assertEqual(missing, set())
        self.assertEqual(child.row.progress, progress)
        self.assertEqual(changed_items, [(child,)])
        apply_filters.assert_not_called()
        item_changed.assert_not_called()
        self.assertIsNotNone(subscription)

    async def test_schedule_condition_refresh_filters_job_types_and_invalidates_changed_items(self):
        """A product refresh evaluates only its job type and invalidates changed rows."""
        # Arrange
        snapshot = _snapshot(graph_id=uuid.uuid4(), state=JobState.QUEUED)
        job = _MockJob(job_id=snapshot.job_id)
        adapter = MagicMock()
        adapter.job_type = _MockJob
        adapter.get_name_display.return_value = snapshot.job_name
        adapter.get_source_name.return_value = "Test"
        adapter.get_waiting_reason.return_value = "Waiting for a service connection."
        adapter.get_graph_actions.return_value = ()
        adapter.get_job_actions.return_value = ()
        model = _model([_graph(snapshot)], jobs={snapshot.job_id: job}, adapter=adapter)
        root = model.all_graphs[0]
        child = model.all_items[0]
        adapter.get_waiting_reason.return_value = None

        # Act
        with (
            patch.object(model, "refresh") as refresh,
            patch.object(model, "_item_changed") as item_changed,
        ):
            model.refresh_schedule_conditions({type("OtherJob", (), {})})
            item_changed.assert_not_called()
            model.refresh_schedule_conditions({_MockJob})

        # Assert
        refresh.assert_not_called()
        self.assertEqual(item_changed.call_args_list, [call(child), call(root)])

    async def test_schedule_condition_refresh_restores_hidden_job_when_handler_becomes_available(self):
        """An externally restored handler returns its hidden job to a readiness filter."""
        # Arrange
        snapshot = _snapshot(
            graph_id=uuid.uuid4(),
            disposition=ApplyDisposition.PENDING,
            apply_handler_id="test.ApplyHandler",
        )
        model = _model([_graph(snapshot)], handler_available=False)
        child = model.all_items[0]
        model.set_status_filter({DisplayState.READY_TO_APPLY})
        self.assertFalse(model.is_item_visible(child))
        model.apply_executor.is_handler_available.return_value = True

        # Act
        model.refresh_schedule_conditions()

        # Assert
        self.assertTrue(model.is_item_visible(child))
        self.assertEqual(model.visible_job_items, [child])

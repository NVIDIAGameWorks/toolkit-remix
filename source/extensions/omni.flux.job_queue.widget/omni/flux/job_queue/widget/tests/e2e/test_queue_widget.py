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
import dataclasses
import pathlib
import re
import tempfile
import uuid
from typing import ClassVar

import carb.input
import carb.settings
import omni.kit.clipboard
import omni.kit.ui_test as ui_test
from omni import ui
import omni.flux.job_queue.core.persistence as persistence
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.apply_handler_registry import ApplyHandlerRegistry
from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation, ApplyPolicy, JobState, TimestampMode
from omni.flux.job_queue.core.errors import JobError
from omni.flux.job_queue.core.execute import JobExecutor, JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import (
    ApplyBinding,
    Job,
    JobGraph,
    JobInputPort,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgress,
    JobProgressCallback,
)
from omni.flux.job_queue.core.persistence import PersistenceCodec
from omni.flux.job_queue.core.settings import (
    AUTO_APPLY_SETTING_PATH,
    SCHEDULER_ENABLED_SETTING_PATH,
    TIMESTAMP_MODE_SETTING_PATH,
    JobQueueSettings,
)
from omni.flux.job_queue.widget.constants import (
    ACTIONS_COLUMN_WIDTH,
    ICON_SIZE_MEDIUM,
    MONOSPACE_FONT_PATH,
    PADDING_MEDIUM,
    PADDING_SMALL,
    ROW_HEIGHT,
    SCROLLBAR_SPACING,
)
from omni.flux.job_queue.widget.details import JobDetailsPanel
from omni.flux.job_queue.widget.display_adapter_base import (
    JobAction,
    JobDetailDirectories,
    JobDetailField,
    JobDetailSection,
    JobDisplayAdapter,
)
from omni.flux.job_queue.widget.enums import JobDetailSectionPlacement
from omni.flux.job_queue.widget.extension import get_display_adapter_registry
from omni.flux.job_queue.widget.row import Row
from omni.flux.job_queue.widget.widget import QueueWidget
from omni.kit.notification_manager import destroy_all_notifications, get_all_notifications
from omni.kit.test import AsyncTestCase

__all__ = ("TestQueueWidget",)

RESULT = JobOutputPort("result", int)
DETAILS = JobOutputPort("details", dict)
REQUEST = JobInputPort("request", dict)


@dataclasses.dataclass(frozen=True, slots=True)
class _ApplyTarget:
    """Identify one observable test target."""

    name: str


@dataclasses.dataclass(frozen=True, slots=True)
class _ApplyReceipt:
    """Retain the original target and most recently applied value."""

    original_name: str
    applied_value: int


class _TestApplyHandler(ApplyHandler[int, _ApplyTarget, _ApplyReceipt]):
    """Record real Apply and Revert calls made through the queue widget."""

    name = "tests.e2e.WidgetApplyHandler"
    input_type = int
    target_type = _ApplyTarget
    receipt_type = _ApplyReceipt
    apply_policy = ApplyPolicy.ALWAYS_MANUAL
    applied_targets: ClassVar[list[str]] = []
    reverted_targets: ClassVar[list[str]] = []
    apply_started: ClassVar[asyncio.Event | None] = None
    apply_release: ClassVar[asyncio.Event | None] = None
    block_reason: ClassVar[str | None] = None
    operation_block_reasons: ClassVar[dict[ApplyOperation, str]] = {}

    def get_apply_block_reason(self, _target: _ApplyTarget, operation: ApplyOperation) -> str | None:
        """Return the current real-handler prerequisite configured by the UI workflow.

        Args:
            _target: Observable target owned by the test.
            operation: Exact operation being considered by the queue.

        Returns:
            Current user-facing block reason, or ``None`` when the target is available.
        """
        return self.operation_block_reasons.get(operation, self.block_reason)

    async def capture_receipt(self, value: int, target: _ApplyTarget) -> _ApplyReceipt:
        """Capture the test target before Apply mutates it.

        Args:
            value: Result value being added to the test target.
            target: Observable target owned by the test.

        Returns:
            Receipt containing the original target and applied value.
        """
        return _ApplyReceipt(target.name, value)

    async def apply(self, value: int, target: _ApplyTarget, receipt: _ApplyReceipt) -> None:
        """Record one idempotent Apply using its durable receipt.

        Args:
            value: Result value being added to the test target.
            target: Observable target owned by the test.
            receipt: Receipt captured before the first Apply attempt.
        """
        del value, receipt
        self.applied_targets.append(target.name)
        if self.apply_started is not None:
            self.apply_started.set()
        if self.apply_release is not None:
            await self.apply_release.wait()

    async def revert(self, _value: int, target: _ApplyTarget, _receipt: _ApplyReceipt) -> None:
        """Record one Revert for the target.

        Args:
            _value: Result value associated with the prior Apply.
            target: Observable target owned by the test.
            _receipt: Receipt captured by the prior Apply.
        """
        self.reverted_targets.append(target.name)


@dataclasses.dataclass
class _WidgetJob(Job):
    """Produce one integer result for real hierarchy and Apply workflows."""

    value: int = 0
    request: dict[str, object] = dataclasses.field(
        default_factory=lambda: {"source": pathlib.Path("textures/source.png")}
    )
    details: dict[str, object] = dataclasses.field(
        default_factory=lambda: {
            "request": {
                "texture": pathlib.Path("textures/input.png"),
                "passes": {"first_intermediate_container": {"second_intermediate_container": ["Albedo", "Normal"]}},
                "metadata": {"title": "Readable title"},
                "an_excessively_long_nested_key_that_must_ellipsize": "Aligned value",
            }
        }
    )
    input_ports = (REQUEST,)
    output_ports = (RESULT, DETAILS)
    execution_started: ClassVar[asyncio.Event | None] = None
    execution_release: ClassVar[asyncio.Event | None] = None

    async def execute(
        self,
        _job_directory: pathlib.Path,
        _inputs: JobInputs,
        _progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return the configured integer output.

        Args:
            _job_directory: Queue-owned directory for test artifacts.
            _inputs: Resolved inputs supplied to the test job.
            _progress_callback: Callback for reporting execution progress.

        Returns:
            Outputs containing the configured integer result.
        """
        if self.execution_started is not None:
            self.execution_started.set()
        if self.execution_release is not None:
            await self.execution_release.wait()
        return JobOutputs({RESULT: self.value, DETAILS: self.details})


class _WidgetDisplayAdapter(JobDisplayAdapter):
    """Expose stable user-facing labels for the concrete E2E job."""

    name = "tests.e2e.WidgetDisplayAdapter"
    job_type = _WidgetJob

    def get_source_name(self, _job: _WidgetJob) -> str:
        """Return the test workflow source.

        Args:
            _job: Exact widget test job handled by this adapter.

        Returns:
            Stable test workflow label.
        """
        return "Test workflow"

    def get_name_display(self, job: _WidgetJob) -> str:
        """Return the persisted child name.

        Args:
            job: Exact widget test job handled by this adapter.

        Returns:
            Persisted test job name.
        """
        return job.name

    def get_active_status_label(self, _job: _WidgetJob, _progress: JobProgress | None) -> str:
        """Return the longest product-facing active status used by the queue layout.

        Args:
            _job: Exact widget test job handled by this adapter.
            _progress: Latest structured progress, when available.

        Returns:
            Stable active status used to verify status-column geometry.
        """
        return "Generating textures"

    def get_active_progress_label(self, _job: _WidgetJob, progress: JobProgress | None) -> str | None:
        """Return product-specific progress for measurable texture work.

        Args:
            _job: Exact widget test job handled by this adapter.
            progress: Latest structured progress, when available.

        Returns:
            Texture-specific progress phrase, or None when no counts exist.
        """
        if progress is None or progress.completed is None or progress.total is None:
            return None
        return f"{progress.completed} of {progress.total} textures"

    def get_graph_actions(self, job: _WidgetJob, _context_name: str) -> tuple[JobAction, ...]:
        """Expose one graph-owned workflow action for the generation fixture.

        Args:
            job: Exact widget test job handled by this adapter.
            _context_name: Context associated with the focus request.

        Returns:
            One graph action for the generation job, or no actions.
        """
        if job.name != "ComfyUI generation":
            return ()
        return (JobAction("open_test_workflow", "Open Workflow", "EditJob", "Open this workflow", True),)

    def get_job_actions(self, job: _WidgetJob, _context_name: str) -> tuple[JobAction, ...]:
        """Expose one child-owned output action for the processing fixture.

        Args:
            job: Exact widget test job handled by this adapter.
            _context_name: Context associated with the action request.

        Returns:
            One child action for the processing job, or no actions.
        """
        if job.name != "Asset processing":
            return ()
        return (
            JobAction(
                "reveal_test_output",
                "Reveal in File Explorer",
                "OpenFolder",
                "Reveal output in File Explorer",
                True,
            ),
        )

    def get_detail_directories(
        self,
        job: _WidgetJob,
        _details,
        _context_name: str,
    ) -> JobDetailDirectories:
        """Expose explicit fixture directories for the selected processing job.

        Args:
            job: Exact widget test job handled by this adapter.
            _details: Public typed details for the selected job.
            _context_name: Context associated with the details panel.

        Returns:
            Input and output directories declared by the processing fixture.
        """
        if job.name != "Asset processing":
            return JobDetailDirectories()
        input_directory = job.details.get("input_directory")
        return JobDetailDirectories(pathlib.Path(input_directory) if isinstance(input_directory, str) else None)

    def get_detail_sections(
        self,
        job: _WidgetJob,
        _details,
        _context_name: str,
    ) -> tuple[JobDetailSection, ...]:
        """Expose fixture processed outputs after the generic output-port section.

        Args:
            job: Exact widget test job handled by this adapter.
            _details: Public typed details for the selected job.
            _context_name: Context associated with the details panel.

        Returns:
            One processed-output section when the fixture declares an output directory.
        """
        output_directory = job.details.get("output_directory")
        processed_output = job.details.get("processed_output")
        if job.name != "Asset processing" or not isinstance(processed_output, str):
            return ()
        return (
            JobDetailSection(
                "processed_outputs",
                "Processed outputs",
                (JobDetailField("processed_output.0", "Albedo", processed_output),),
                JobDetailSectionPlacement.AFTER_OUTPUTS,
                pathlib.Path(output_directory) if isinstance(output_directory, str) else None,
            ),
        )

    def execute_action(self, action_id: str, _job: _WidgetJob, _context_name: str) -> None:
        """Accept the fixture's declared actions without product side effects.

        Args:
            action_id: Stable action selected by the E2E test.
            _job: Exact widget test job handled by this adapter.
            _context_name: Context associated with the action request.

        Raises:
            KeyError: If an undeclared action is requested.
        """
        if action_id not in {"open_test_workflow", "reveal_test_output"}:
            raise KeyError(action_id)


def _encode_job(
    job: _WidgetJob,
) -> tuple[uuid.UUID, str, str | None, ApplyBinding | None, int, dict[str, object]]:
    """Encode explicit stable fields for one widget job.

    Args:
        job: Widget test job to serialize.

    Returns:
        Stable fields needed to reconstruct the job.
    """
    return job.job_id, job.name, job.skip_reason, job.apply_binding, job.value, job.details


def _decode_job(
    value: tuple[uuid.UUID, str, str | None, ApplyBinding | None, int, dict[str, object]],
) -> _WidgetJob:
    """Decode one widget job from explicit stable fields.

    Args:
        value: Stable fields produced by :func:`_encode_job`.

    Returns:
        Reconstructed widget test job.
    """
    job_id, name, skip_reason, apply_binding, result, details = value
    return _WidgetJob(
        job_id=job_id,
        name=name,
        skip_reason=skip_reason,
        apply_binding=apply_binding,
        value=result,
        details=details,
    )


_PERSISTENCE_CODECS = (
    PersistenceCodec("tests.e2e.WidgetJob", _WidgetJob, _encode_job, _decode_job),
    PersistenceCodec(_TestApplyHandler.name, _TestApplyHandler),
    PersistenceCodec(
        "tests.e2e.WidgetApplyTarget",
        _ApplyTarget,
        lambda value: (value.name,),
        lambda value: _ApplyTarget(*value),
    ),
    PersistenceCodec(
        "tests.e2e.WidgetApplyReceipt",
        _ApplyReceipt,
        lambda value: (value.original_name, value.applied_value),
        lambda value: _ApplyReceipt(*value),
    ),
)


class TestQueueWidget(AsyncTestCase):
    """Drive the real queue hierarchy through native UI elements."""

    async def setUp(self):
        """Create real persistence, Apply, queue, and UI boundaries."""
        self._settings = carb.settings.get_settings()
        self._original_timestamp_mode = self._settings.get(TIMESTAMP_MODE_SETTING_PATH)
        JobQueueSettings().set_timestamp_mode(TimestampMode.RELATIVE)
        self._isolate_auto_apply_setting = self._testMethodName.startswith("test_auto_apply_defaults_")
        if self._isolate_auto_apply_setting:
            self._original_auto_apply = self._settings.get(AUTO_APPLY_SETTING_PATH)
            self._settings.destroy_item(AUTO_APPLY_SETTING_PATH)
        self._isolate_scheduler_setting = self._testMethodName.startswith("test_scheduler_controls_")
        if self._isolate_scheduler_setting:
            self._original_scheduler_enabled = self._settings.get(SCHEDULER_ENABLED_SETTING_PATH)
            self._settings.destroy_item(SCHEDULER_ENABLED_SETTING_PATH)
        persistence.get_registry().register_codecs(_PERSISTENCE_CODECS)
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="queue-widget-e2e-")
        database_path = pathlib.Path(self._temporary_directory.name) / "queue.sqlite"
        self._interface = QueueInterface(str(database_path))
        self._apply_registry = ApplyHandlerRegistry()
        self._apply_registry.register_plugins([_TestApplyHandler])
        self._apply_executor = ApplyExecutor(self._interface, self._apply_registry)
        get_display_adapter_registry().register(_WidgetDisplayAdapter)
        _TestApplyHandler.applied_targets = []
        _TestApplyHandler.reverted_targets = []
        _TestApplyHandler.apply_started = None
        _TestApplyHandler.apply_release = None
        _TestApplyHandler.block_reason = None
        _TestApplyHandler.operation_block_reasons = {}
        _WidgetJob.execution_started = None
        _WidgetJob.execution_release = None
        destroy_all_notifications()

        self._window = ui.Window(f"QueueWidgetE2E_{uuid.uuid4()}", width=1000, height=500)
        with self._window.frame:
            with ui.HStack():
                with ui.Frame(width=ui.Fraction(2)):
                    self._widget = QueueWidget(self._interface, self._apply_executor, "stagecraft")
                with ui.Frame(width=ui.Fraction(1)):
                    self._details = JobDetailsPanel(self._widget.model)
        self._widget.show(True)
        self._details.show(True)
        await ui_test.human_delay()

    async def tearDown(self):
        """Settle actions and destroy every owned runtime object."""
        if _TestApplyHandler.apply_release is not None:
            _TestApplyHandler.apply_release.set()
        if _WidgetJob.execution_release is not None:
            _WidgetJob.execution_release.set()
        await self._widget.model.wait_for_background_tasks()
        self._details.destroy()
        self._widget.destroy()
        self._window.destroy()
        if self._original_timestamp_mode is None:
            self._settings.destroy_item(TIMESTAMP_MODE_SETTING_PATH)
        else:
            self._settings.set(TIMESTAMP_MODE_SETTING_PATH, self._original_timestamp_mode)
        if self._isolate_auto_apply_setting:
            if self._original_auto_apply is None:
                self._settings.destroy_item(AUTO_APPLY_SETTING_PATH)
            else:
                self._settings.set(AUTO_APPLY_SETTING_PATH, self._original_auto_apply)
        if self._isolate_scheduler_setting:
            if self._original_scheduler_enabled is None:
                self._settings.destroy_item(SCHEDULER_ENABLED_SETTING_PATH)
            else:
                self._settings.set(SCHEDULER_ENABLED_SETTING_PATH, self._original_scheduler_enabled)
        await self._apply_executor.shutdown()
        self._apply_registry.destroy()
        get_display_adapter_registry().unregister(_WidgetDisplayAdapter)
        destroy_all_notifications()
        persistence.get_registry().unregister_codecs(_PERSISTENCE_CODECS)
        self._temporary_directory.cleanup()
        await ui_test.human_delay()

    def _submit_graph(self, name: str, *jobs: _WidgetJob) -> JobGraph:
        """Submit one real graph through the public queue API.

        Args:
            name: User-facing test graph name.
            *jobs: Jobs owned by the graph.

        Returns:
            Submitted graph.
        """
        graph = JobGraph(name=name, jobs=list(jobs))
        for job in jobs:
            graph.bind(job, REQUEST, job.request)
        self._interface.submit(graph)
        return graph

    def _complete(self, job: _WidgetJob) -> None:
        """Persist one successful execution through public state transitions.

        Args:
            job: Submitted test job to complete.

        Raises:
            RuntimeError: If any required queue transition is rejected.
        """
        if job.job_id not in self._interface.claim_runnable_jobs():
            raise RuntimeError(f"Could not schedule test job {job.job_id}")
        if not self._interface.start_job(job.job_id):
            raise RuntimeError(f"Could not start test job {job.job_id}")
        if not self._interface.complete_job(job.job_id, JobOutputs({RESULT: job.value, DETAILS: job.details})):
            raise RuntimeError(f"Could not complete test job {job.job_id}")

    async def _wait_for_disposition(
        self,
        job_id: uuid.UUID,
        expected: ApplyDisposition,
    ) -> None:
        """Wait for one targeted lifecycle event without polling SQLite.

        Args:
            job_id: Durable job identifier to observe.
            expected: Apply disposition that completes the wait.
        """
        changed = asyncio.Event()
        loop = asyncio.get_running_loop()

        def on_changed(changed_id: uuid.UUID) -> None:
            """Wake the waiter when the targeted job reaches its expected disposition.

            Args:
                changed_id: Durable identifier of the job reported by the event.
            """
            if changed_id == job_id and self._interface.get_job_snapshot(job_id).apply_disposition is expected:
                loop.call_soon_threadsafe(changed.set)

        subscription = self._interface.subscribe_job_changed(on_changed)
        try:
            if self._interface.get_job_snapshot(job_id).apply_disposition is not expected:
                await asyncio.wait_for(changed.wait(), 2)
        finally:
            del subscription

    def _find(self, query: str):
        """Find one widget under the owned test window.

        Args:
            query: UI-test query relative to the test window.

        Returns:
            Matching UI-test widget wrapper, or None.
        """
        return ui_test.find(f"{self._window.title}//Frame/**/{query}")

    def _find_all(self, query: str):
        """Find every matching widget under the owned test window.

        Args:
            query: UI-test query relative to the test window.

        Returns:
            Matching UI-test widget wrappers.
        """
        return ui_test.find_all(f"{self._window.title}//Frame/**/{query}")

    def _find_popup(self, identifier: str):
        """Find one widget in the currently visible native filter popup.

        Args:
            identifier: Stable identifier assigned to the popup control.

        Returns:
            Matching native widget, or None.
        """
        popup = self._widget._filter_menu
        widgets = [popup] if popup is not None else []
        while widgets:
            widget = widgets.pop()
            if widget.identifier == identifier:
                return widget
            widgets.extend(ui.Inspector.get_children(widget))
        return None

    @staticmethod
    async def _click_popup(widget) -> None:
        """Click a popup control without refocusing the queue window and closing the menu.

        Args:
            widget: Native control in the current popup.
        """
        center = ui_test.Vec2(
            widget.screen_position_x + (widget.computed_width / 2),
            widget.screen_position_y + (widget.computed_height / 2),
        )
        await ui_test.emulate_mouse_move_and_click(center)
        await ui_test.human_delay()

    async def _open_filter_popup(self) -> None:
        """Open the complete queue filter popup directly from its toolbar icon."""
        filter_button = self._find("Image[*].identifier=='queue_filters'")
        self.assertIsNotNone(filter_button)
        await filter_button.click()
        await ui_test.human_delay()

    async def _scroll_filter_popup_to_bottom(self) -> None:
        """Scroll the open filter popup to its final Apply section with the mouse wheel."""
        scrolling_frame = self._find_popup("queue_filters_popup")
        self.assertIsNotNone(scrolling_frame)
        center = ui_test.Vec2(
            scrolling_frame.screen_position_x + (scrolling_frame.computed_width / 2),
            scrolling_frame.screen_position_y + (scrolling_frame.computed_height / 2),
        )
        await ui_test.emulate_mouse_move(center)
        await ui_test.input.emulate_mouse_scroll(ui_test.Vec2(0, -1200))
        await ui_test.human_delay()

    async def test_queue_and_details_report_destroyed_state_to_their_workspace_window(self):
        """An owning workspace window reads `destroyed` to decide whether to rebuild its content."""
        # Build a second real queue and details pair, then destroy it like a closed workspace window.
        window = ui.Window(f"QueueWidgetLifecycleE2E_{uuid.uuid4()}", width=400, height=200)
        with window.frame:
            with ui.HStack():
                widget = QueueWidget(self._interface, self._apply_executor, "stagecraft")
                details = JobDetailsPanel(widget.model)
        await ui_test.human_delay()

        # A live pair keeps its content, so the window must not replace it.
        self.assertFalse(widget.destroyed)
        self.assertFalse(details.destroyed)

        details.destroy()
        widget.destroy()
        window.destroy()

        # A destroyed pair reports its state, so the window rebuilds instead of reusing dead content.
        self.assertTrue(widget.destroyed)
        self.assertTrue(details.destroyed)

    async def test_empty_queue_keeps_tree_mounted_under_submit_overlay(self):
        """The empty queue retains native stripes beneath compact centered guidance."""
        # Open the empty queue and inspect the real tree and guidance overlay together.
        await ui_test.human_delay()

        # The empty overlay sits above the mounted tree without creating a fake selectable row.
        tree = self._find("TreeWidget[*].identifier=='job_queue_tree'")
        overlay = self._find("Rectangle[*].identifier=='queue_empty_overlay'")
        icon = self._find("Image[*].identifier=='queue_empty_icon'")
        title = self._find("Label[*].identifier=='queue_empty_title'")
        subtitle = self._find("Label[*].identifier=='queue_empty_subtitle'")
        self.assertIsNotNone(tree)
        self.assertIsNotNone(overlay)
        self.assertIsNotNone(icon)
        self.assertIsNotNone(title)
        self.assertIsNotNone(subtitle)
        self.assertEqual(overlay.widget.name, "TreePanelBackground")
        self.assertGreater(overlay.widget.computed_width, 0)
        self.assertGreater(overlay.widget.computed_height, 0)
        self.assertEqual(title.widget.text, "No jobs in queue")
        self.assertFalse(self._widget._empty_frame.opaque_for_mouse_events)
        self.assertLess(icon.center.y, title.center.y)
        self.assertLess(title.center.y, subtitle.center.y)
        self.assertLess(subtitle.center.y - title.center.y, 40)

        # Job Details uses the same compact icon-first empty-state hierarchy.
        detail_icon = self._find("Image[*].identifier=='queue_detail_empty_icon'")
        detail_title = self._find("Label[*].identifier=='queue_detail_empty_title'")
        detail_subtitle = self._find("Label[*].identifier=='queue_detail_empty_subtitle'")
        self.assertIsNotNone(detail_icon)
        self.assertIsNotNone(detail_title)
        self.assertIsNotNone(detail_subtitle)
        self.assertLess(detail_icon.center.y, detail_title.center.y)
        self.assertLess(detail_title.center.y, detail_subtitle.center.y)
        self.assertLess(detail_subtitle.center.y - detail_title.center.y, 40)

    async def test_empty_queue_has_no_rendered_tree_root(self):
        """An empty queue hides the native model root instead of exposing a blank row."""
        # Open the empty queue and compare its model roots with the rendered native tree.
        await ui_test.human_delay()

        roots = self._widget.model.get_item_children()
        tree = self._find("TreeWidget[*].identifier=='job_queue_tree'")

        self.assertEqual(roots, [])
        self.assertIsNotNone(tree)
        self.assertFalse(tree.widget.root_visible)

    async def test_column_headers_are_padded_without_embedded_filter_icons(self):
        """Column titles keep native edge padding while filters live in the toolbar popup."""
        # Inspect the rendered queue headers and confirm filtering remains a toolbar action.
        headers = {header.widget.text: header for header in self._find_all("Label[*].name=='ColumnHeader'")}
        header_cells = {
            key: self._find(f"HStack[*].identifier=='queue_header_cell_{key}'")
            for key in ("job_stage", "status", "completed", "apply", "actions")
        }

        self.assertEqual(set(headers), {"Job / Stage", "Status", "Completed", "Apply", "Actions"})
        self.assertTrue(all(cell is not None for cell in header_cells.values()))
        self.assertEqual(self._find_all("Image[*].name=='QueueFilter'"), [])
        for key, label_text in zip(header_cells, ("Job / Stage", "Status", "Completed", "Apply", "Actions")):
            label = headers[label_text]
            cell = header_cells[key]
            frame_left = cell.center.x - (cell.widget.computed_width / 2)
            label_left = label.center.x - (label.widget.computed_width / 2)
            self.assertGreaterEqual(label_left - frame_left, PADDING_MEDIUM.value - 1)
            self.assertAlmostEqual(label.center.y, cell.center.y, delta=1)
        tree = self._find("TreeWidget[*].identifier=='job_queue_tree'")
        self.assertIsNotNone(tree)
        tree_right = tree.center.x + (tree.widget.computed_width / 2)
        actions_frame = header_cells["actions"]
        actions_right = actions_frame.center.x + (actions_frame.widget.computed_width / 2)
        self.assertLessEqual(actions_right, tree_right)

    async def test_active_progress_is_rendered_in_the_status_column(self):
        """Structured progress stays with execution state while completion time remains empty."""
        # Start a real queued job, expand its graph, and read progress from the visible row.
        active = _WidgetJob(name="Generating material", value=1)
        graph = self._submit_graph("Material workflow", active)
        self.assertIn(active.job_id, self._interface.claim_runnable_jobs())
        self.assertTrue(self._interface.start_job(active.job_id))
        await ui_test.human_delay()
        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)
        await branch.click()
        await ui_test.human_delay()
        graph_label = next(
            label for label in self._find_all("Label[*].name=='CellLabel'") if label.widget.text == "Material workflow"
        )
        await graph_label.click()
        await ui_test.human_delay()
        graph_status_before = self._find(f"Label[*].identifier=='queue_graph_status_{graph.graph_id}_label'")
        job_status_before = self._find(f"Label[*].identifier=='queue_job_status_{active.job_id}_label'")
        details_summary_before = self._find("Label[*].identifier=='graph_details_summary'")
        details_progress_before = self._find("Label[*].identifier=='graph_details_progress'")
        self.assertIsNotNone(graph_status_before)
        self.assertIsNotNone(job_status_before)
        self.assertIsNotNone(details_summary_before)
        self.assertIsNotNone(details_progress_before)

        # Publish successive progress events through the queue interface used by workers.
        self.assertTrue(
            self._interface.update_progress(
                active.job_id,
                JobProgress(completed=1, total=4, detail="Receiving generated files"),
            )
        )
        self.assertTrue(
            self._interface.update_progress(
                active.job_id,
                JobProgress(completed=2, total=4, detail="Downloading generated files"),
            )
        )
        await ui_test.human_delay()

        # Only the existing targeted labels update; completion remains blank until the job finishes.
        graph_status = self._find(f"Label[*].identifier=='queue_graph_status_{graph.graph_id}_label'")
        job_status = self._find(f"Label[*].identifier=='queue_job_status_{active.job_id}_label'")
        completed = self._find(f"Label[*].identifier=='queue_job_completed_{active.job_id}'")
        self.assertIsNotNone(graph_status)
        self.assertIsNotNone(job_status)
        self.assertIsNotNone(completed)
        self.assertIs(graph_status.widget, graph_status_before.widget)
        self.assertIs(job_status.widget, job_status_before.widget)
        self.assertIs(self._find("Label[*].identifier=='graph_details_summary'").widget, details_summary_before.widget)
        self.assertIs(
            self._find("Label[*].identifier=='graph_details_progress'").widget, details_progress_before.widget
        )
        self.assertEqual(details_progress_before.widget.text, "2 of 4")
        self.assertEqual(graph_status.widget.text, "Generating textures · 0/1 job")
        self.assertEqual(job_status.widget.text, "Generating textures · 2 of 4 textures")
        self.assertEqual(completed.widget.text, "")

    async def test_active_job_details_render_before_first_progress_update(self):
        """An active child remains inspectable before its worker reports structured progress."""
        # Start a real job without publishing progress, expand its graph, and select the child.
        active = _WidgetJob(name="Generating material", value=1)
        self._submit_graph("Material workflow", active)
        self.assertIn(active.job_id, self._interface.claim_runnable_jobs())
        self.assertTrue(self._interface.start_job(active.job_id))
        await ui_test.human_delay()
        await self._find("Image[*].identifier=='queue_graph_branch'").click()
        await ui_test.human_delay()
        job_label = next(
            label
            for label in self._find_all("Label[*].name=='CellLabel'")
            if label.widget.text == "Generating material"
        )
        await job_label.click()
        await ui_test.human_delay()

        # The details panel renders its normal active fallback rather than requiring progress counts.
        title = self._find("Label[*].identifier=='job_details_title'")
        progress = self._find("Label[*].identifier=='job_details_progress'")
        self.assertIsNotNone(title)
        self.assertIsNotNone(progress)
        self.assertEqual(title.widget.text, "Generating material")
        self.assertEqual(progress.widget.text, "In progress")

    async def test_completed_header_toggles_all_completion_times(self):
        """The Completed header switches graph and child timestamps between relative and absolute formats."""
        # Complete a graph, expand it, and use the visible header to change every timestamp mode.
        completed_job = _WidgetJob(name="Completed job", value=1)
        graph = self._submit_graph("Completed workflow", completed_job)
        self._complete(completed_job)
        await ui_test.human_delay()
        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)
        await branch.click()
        await ui_test.human_delay()
        header = self._find("Label[*].identifier=='queue_header_completed'")
        graph_time = self._find(f"Label[*].identifier=='queue_graph_completed_{graph.graph_id}'")
        job_time = self._find(f"Label[*].identifier=='queue_job_completed_{completed_job.job_id}'")
        self.assertIsNotNone(header)
        self.assertIsNotNone(graph_time)
        self.assertIsNotNone(job_time)
        self.assertEqual(graph_time.widget.text, "Just now")
        self.assertEqual(job_time.widget.text, "Just now")

        await header.click()
        await ui_test.human_delay()

        absolute_pattern = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        graph_time = self._find(f"Label[*].identifier=='queue_graph_completed_{graph.graph_id}'")
        job_time = self._find(f"Label[*].identifier=='queue_job_completed_{completed_job.job_id}'")
        self.assertRegex(graph_time.widget.text, absolute_pattern)
        self.assertRegex(job_time.widget.text, absolute_pattern)
        self.assertIs(JobQueueSettings().timestamp_mode, TimestampMode.ABSOLUTE)

    async def test_graph_completion_waits_for_failed_and_skipped_children(self):
        """A graph shows completion only after every failed or skipped child has finished."""
        # Fail one real child, let dependency handling skip the next, and inspect graph completion.
        failed = _WidgetJob(name="Failed generation", value=1)
        skipped = _WidgetJob(name="Skipped processing", value=2)
        graph = self._submit_graph("Unsuccessful workflow", failed, skipped)
        self.assertEqual(self._interface.claim_runnable_jobs(), [failed.job_id])
        self.assertTrue(self._interface.start_job(failed.job_id))
        self.assertTrue(
            self._interface.fail_job(
                failed.job_id,
                JobError("RuntimeError", "execution failure", "trace"),
                "Texture generation failed.",
            )
        )
        await ui_test.human_delay()
        graph_time = self._find(f"Label[*].identifier=='queue_graph_completed_{graph.graph_id}'")
        self.assertIsNotNone(graph_time)
        self.assertEqual(graph_time.widget.text, "")

        self.assertTrue(self._interface.skip_job(skipped.job_id, "No generated textures were available."))
        await ui_test.human_delay()

        graph_time = self._find(f"Label[*].identifier=='queue_graph_completed_{graph.graph_id}'")
        self.assertEqual(graph_time.widget.text, "Just now")

    async def test_hidden_timestamp_mode_change_renders_when_shown(self):
        """A hidden widget uses the latest persistent completion-time mode when reopened."""
        # Hide a completed queue, change its saved time mode, then reopen it to synchronize the view.
        completed_job = _WidgetJob(name="Completed job", value=1)
        graph = self._submit_graph("Hidden workflow", completed_job)
        self._complete(completed_job)
        await ui_test.human_delay()
        graph_time = self._find(f"Label[*].identifier=='queue_graph_completed_{graph.graph_id}'")
        self.assertIsNotNone(graph_time)
        self.assertEqual(graph_time.widget.text, "Just now")
        self._widget.show(False)

        JobQueueSettings().set_timestamp_mode(TimestampMode.ABSOLUTE)
        self._widget.show(True)
        await ui_test.human_delay()

        graph_time = self._find(f"Label[*].identifier=='queue_graph_completed_{graph.graph_id}'")
        self.assertRegex(graph_time.widget.text, re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"))

    async def test_graph_row_uses_padded_columns_and_aligned_native_actions(self):
        """Graph controls share native columns and explicit backgrounds with a non-selectable footer."""
        pending = _WidgetJob(
            name="Asset processing",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("pending")),
        )
        without_apply = _WidgetJob(name="ComfyUI generation")
        graph = self._submit_graph("Material workflow", pending, without_apply)
        self._complete(pending)
        await ui_test.human_delay()

        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)
        await branch.click()
        await ui_test.human_delay()

        row_frame = self._find(f"Frame[*].identifier=='queue_graph_{graph.graph_id}_job_stage'")
        status_frame = self._find(f"Frame[*].identifier=='queue_graph_{graph.graph_id}_status'")
        status_pill = self._find(f"Rectangle[*].identifier=='queue_graph_status_{graph.graph_id}'")
        drag = self._find(f"Image[*].identifier=='queue_graph_drag_handle_{graph.graph_id}'")
        label = self._find("Label[*].text=='Material workflow'")
        row_apply = self._find(f"Image[*].identifier=='apply_graph_{graph.graph_id}'")
        row_decline = self._find(f"Image[*].identifier=='decline_graph_{graph.graph_id}'")
        actions_frame = self._find(f"Frame[*].identifier=='queue_graph_{graph.graph_id}_actions'")
        row_delete = self._find(f"Image[*].identifier=='delete_graph_{graph.graph_id}'")
        footer = self._find("Frame[*].identifier=='job_queue_footer'")
        graph_open = self._find(
            f"Image[*].identifier=='open_test_workflow_graph_{graph.graph_id}_job_{without_apply.job_id}'"
        )
        footer_apply = self._find("Image[*].identifier=='apply_filtered_jobs'")
        footer_decline = self._find("Image[*].identifier=='decline_filtered_jobs'")
        child_label = self._find(f"Label[*].identifier=='job_name_{pending.job_id}'")
        child_apply = self._find(f"Image[*].identifier=='apply_job_{pending.job_id}'")
        child_decline = self._find(f"Image[*].identifier=='decline_job_{pending.job_id}'")
        child_reveal = self._find(f"Image[*].identifier=='reveal_test_output_job_{pending.job_id}'")
        disabled_apply = self._find(f"Image[*].identifier=='apply_job_{without_apply.job_id}'")
        disabled_decline = self._find(f"Image[*].identifier=='decline_job_{without_apply.job_id}'")
        controls = (
            row_frame,
            status_frame,
            status_pill,
            drag,
            branch,
            label,
            row_apply,
            row_decline,
            actions_frame,
            row_delete,
            footer,
            graph_open,
            footer_apply,
            footer_decline,
            child_label,
            child_apply,
            child_decline,
            child_reveal,
            disabled_apply,
            disabled_decline,
        )
        self.assertTrue(all(control is not None for control in controls))
        column_keys = Row.keys()
        for key in column_keys:
            header_cell = self._find(f"Label[*].identifier=='queue_header_{key.value}'")
            self.assertIsNotNone(header_cell)
        footer_label_cell = self._find("Frame[*].identifier=='queue_footer_job_stage'")
        footer_apply_cell = self._find("Frame[*].identifier=='queue_footer_apply'")
        self.assertIsNotNone(footer_label_cell)
        self.assertIsNotNone(footer_apply_cell)
        row_left = row_frame.center.x - (row_frame.widget.computed_width / 2)
        label_left = label.center.x - (label.widget.computed_width / 2)
        self.assertGreaterEqual(label_left - row_left, PADDING_SMALL.value - 1)
        self.assertAlmostEqual(status_pill.center.x, status_frame.center.x, delta=1)
        self.assertLess(drag.center.x, branch.center.x)
        self.assertLess(branch.center.x, label.center.x)
        for control in (drag, branch, row_apply, row_decline, row_delete):
            self.assertAlmostEqual(control.center.y, label.center.y, delta=1)
        self.assertAlmostEqual(row_apply.center.x, footer_apply.center.x, delta=1)
        self.assertAlmostEqual(row_decline.center.x, footer_decline.center.x, delta=1)
        for control in (child_apply, child_decline, child_reveal):
            self.assertAlmostEqual(control.center.y, child_label.center.y, delta=1)
        actions_left = actions_frame.center.x - (actions_frame.widget.computed_width / 2)
        delete_left = row_delete.center.x - (row_delete.widget.computed_width / 2)
        self.assertAlmostEqual(actions_frame.widget.computed_width, ACTIONS_COLUMN_WIDTH.value, delta=1)
        self.assertAlmostEqual(delete_left - actions_left, PADDING_MEDIUM.value, delta=1)
        self.assertLess(row_delete.center.x, graph_open.center.x)
        self.assertEqual(self._find_all(f"Image[*].identifier=='delete_job_{pending.job_id}'"), [])
        self.assertEqual(self._find_all(f"Image[*].identifier=='focus_job_{pending.job_id}'"), [])
        self.assertEqual(self._find_all(f"Image[*].identifier=='edit_job_{pending.job_id}'"), [])
        self.assertEqual(self._find_all(f"Image[*].identifier=='open_test_workflow_job_{pending.job_id}'"), [])
        self.assertEqual(self._find_all(f"Image[*].identifier=='open_test_workflow_job_{without_apply.job_id}'"), [])
        self.assertFalse(disabled_apply.widget.enabled)
        self.assertFalse(disabled_decline.widget.enabled)
        self.assertIn("no result", disabled_apply.widget.tooltip.lower())
        self.assertIn("no result", disabled_decline.widget.tooltip.lower())

    async def test_graph_drag_handle_reorders_tree_and_persists_graph_positions(self):
        """Dragging a real graph handle reorders native rows and durable queue positions."""
        # Submit three graphs and drag the first visible handle onto the last graph row.
        first = self._submit_graph("First workflow", _WidgetJob(name="First stage"))
        second = self._submit_graph("Second workflow", _WidgetJob(name="Second stage"))
        third = self._submit_graph("Third workflow", _WidgetJob(name="Third stage"))
        await ui_test.human_delay()

        first_handle = self._find(f"Image[*].identifier=='queue_graph_drag_handle_{first.graph_id}'")
        third_row = self._find(f"Frame[*].identifier=='queue_graph_{third.graph_id}_job_stage'")
        self.assertIsNotNone(first_handle)
        self.assertIsNotNone(third_row)

        await ui_test.emulate_mouse_drag_and_drop(first_handle.center, third_row.center)
        await ui_test.human_delay()

        snapshots = self._interface.get_graph_snapshots()
        self.assertEqual(
            [snapshot.graph_id for snapshot in snapshots], [second.graph_id, third.graph_id, first.graph_id]
        )
        ordered_rows = [
            self._find(f"Frame[*].identifier=='queue_graph_{graph.graph_id}_job_stage'")
            for graph in (second, third, first)
        ]
        self.assertTrue(all(row is not None for row in ordered_rows))
        self.assertLess(ordered_rows[0].center.y, ordered_rows[1].center.y)
        self.assertLess(ordered_rows[1].center.y, ordered_rows[2].center.y)

    async def test_graph_drag_handle_reorders_between_rows_and_persists_graph_positions(self):
        """Dragging between real graph rows uses the native insertion target."""
        # Submit four graphs and drag the last handle into the native gap between two rows.
        first = self._submit_graph("First workflow", _WidgetJob(name="First stage"))
        second = self._submit_graph("Second workflow", _WidgetJob(name="Second stage"))
        third = self._submit_graph("Third workflow", _WidgetJob(name="Third stage"))
        fourth = self._submit_graph("Fourth workflow", _WidgetJob(name="Fourth stage"))
        await ui_test.human_delay()

        first_row = self._find(f"Frame[*].identifier=='queue_graph_{first.graph_id}_job_stage'")
        second_row = self._find(f"Frame[*].identifier=='queue_graph_{second.graph_id}_job_stage'")
        fourth_handle = self._find(f"Image[*].identifier=='queue_graph_drag_handle_{fourth.graph_id}'")
        self.assertTrue(all(widget is not None for widget in (first_row, second_row, fourth_handle)))
        before_second = ui_test.Vec2(
            first_row.center.x,
            second_row.center.y - (ROW_HEIGHT.value * 0.4),
        )

        await ui_test.emulate_mouse_drag_and_drop(fourth_handle.center, before_second)
        await ui_test.human_delay()

        snapshots = self._interface.get_graph_snapshots()
        self.assertEqual(
            [snapshot.graph_id for snapshot in snapshots],
            [first.graph_id, fourth.graph_id, second.graph_id, third.graph_id],
        )

    async def test_apply_controls_preserve_disposition_and_explain_product_availability(self):
        """Project availability controls mutations without hiding stable Apply state or database-only Decline."""
        # Complete a real result-bearing job while its handler reports that the target project is unavailable.
        generation = _WidgetJob(name="ComfyUI generation")
        processing = _WidgetJob(
            name="Texture optimization",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("processed")),
        )
        graph = self._submit_graph("Material workflow", generation, processing)
        self._complete(generation)
        self._complete(processing)
        expected_reason = "Open the project used to create this job before applying its results."
        _TestApplyHandler.block_reason = expected_reason
        self._widget.model.refresh_schedule_conditions()
        await ui_test.human_delay()

        # Expand the graph and verify Apply is blocked by the exact reason while pending Decline remains available.
        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)
        await branch.click()
        await ui_test.human_delay()
        graph_check = self._find(f"Image[*].identifier=='apply_graph_{graph.graph_id}'")
        graph_x = self._find(f"Image[*].identifier=='decline_graph_{graph.graph_id}'")
        child_check = self._find(f"Image[*].identifier=='apply_job_{processing.job_id}'")
        child_x = self._find(f"Image[*].identifier=='decline_job_{processing.job_id}'")
        footer_check = self._find("Image[*].identifier=='apply_filtered_jobs'")
        footer_x = self._find("Image[*].identifier=='decline_filtered_jobs'")
        controls = (graph_check, graph_x, child_check, child_x, footer_check, footer_x)
        self.assertTrue(all(control is not None for control in controls))
        for control in (graph_check, child_check):
            self.assertFalse(control.widget.enabled)
            self.assertEqual(control.widget.tooltip, expected_reason)
        self.assertTrue(footer_check.widget.enabled)
        self.assertEqual(footer_check.widget.tooltip, "Apply or reapply matching results from top to bottom")
        for control in (graph_x, child_x, footer_x):
            self.assertTrue(control.widget.enabled)

        # Decline the pending result, then verify the red active state remains visible but cannot be selected again.
        await child_x.click()
        await self._wait_for_disposition(processing.job_id, ApplyDisposition.DECLINED)
        await self._widget.model.wait_for_background_tasks()
        await ui_test.human_delay()
        child_check = self._find(f"Image[*].identifier=='apply_job_{processing.job_id}'")
        child_x = self._find(f"Image[*].identifier=='decline_job_{processing.job_id}'")
        graph_check = self._find(f"Image[*].identifier=='apply_graph_{graph.graph_id}'")
        graph_x = self._find(f"Image[*].identifier=='decline_graph_{graph.graph_id}'")
        footer_check = self._find("Image[*].identifier=='apply_filtered_jobs'")
        footer_x = self._find("Image[*].identifier=='decline_filtered_jobs'")
        self.assertEqual(child_check.widget.tooltip, expected_reason)
        self.assertFalse(child_check.widget.enabled)
        self.assertEqual(child_x.widget.name, "DeclineJobActive")
        self.assertFalse(child_x.widget.enabled)
        self.assertEqual(child_x.widget.tooltip, "Results are declined.")
        self.assertFalse(graph_check.widget.enabled)
        self.assertEqual(graph_check.widget.tooltip, expected_reason)
        self.assertFalse(graph_x.widget.enabled)
        self.assertEqual(graph_x.widget.tooltip, "Results are declined.")
        self.assertEqual(graph_x.widget.name, "DeclineJobActive")
        for control in (footer_check, footer_x):
            self.assertTrue(control.widget.enabled)
        self.assertEqual(footer_check.widget.tooltip, "Apply or reapply matching results from top to bottom")
        self.assertEqual(footer_x.widget.tooltip, "Decline or revert matching results from top to bottom")

        # Restore the target, Apply the declined result, then remove the target again to block Reapply and Revert.
        _TestApplyHandler.block_reason = None
        self._widget.model.refresh_schedule_conditions()
        await ui_test.human_delay()
        child_check = self._find(f"Image[*].identifier=='apply_job_{processing.job_id}'")
        await child_check.click()
        await self._wait_for_disposition(processing.job_id, ApplyDisposition.APPLIED)
        await self._widget.model.wait_for_background_tasks()
        applied_reasons = {
            ApplyOperation.REAPPLYING: (
                "These results were applied in a different project. Reload the original project to reapply them."
            ),
            ApplyOperation.REVERTING: (
                "These results were applied in a different project. Reload the original project to revert them."
            ),
        }
        _TestApplyHandler.operation_block_reasons = applied_reasons
        self._widget.model.refresh_schedule_conditions()
        await ui_test.human_delay()

        graph_check = self._find(f"Image[*].identifier=='apply_graph_{graph.graph_id}'")
        graph_x = self._find(f"Image[*].identifier=='decline_graph_{graph.graph_id}'")
        child_check = self._find(f"Image[*].identifier=='apply_job_{processing.job_id}'")
        child_x = self._find(f"Image[*].identifier=='decline_job_{processing.job_id}'")
        footer_check = self._find("Image[*].identifier=='apply_filtered_jobs'")
        footer_x = self._find("Image[*].identifier=='decline_filtered_jobs'")
        for control in (graph_check, graph_x, child_check, child_x):
            self.assertFalse(control.widget.enabled)
        for control in (graph_check, child_check):
            self.assertEqual(control.widget.tooltip, applied_reasons[ApplyOperation.REAPPLYING])
        for control in (graph_x, child_x):
            self.assertEqual(control.widget.tooltip, applied_reasons[ApplyOperation.REVERTING])
        for control in (footer_check, footer_x):
            self.assertTrue(control.widget.enabled)
        self.assertEqual(footer_check.widget.tooltip, "Apply or reapply matching results from top to bottom")
        self.assertEqual(footer_x.widget.tooltip, "Decline or revert matching results from top to bottom")
        self.assertEqual(graph_check.widget.name, "ApplyJobActive")
        self.assertEqual(child_check.widget.name, "ApplyJobActive")

    async def test_unavailable_result_uses_neutral_unknown_controls_and_one_reason(self):
        """Unavailable exact handlers disable every result action with the same explicit explanation."""
        # Complete a real applicable job, then unregister its exact handler and refresh external conditions.
        processing = _WidgetJob(
            name="Texture optimization",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("processed")),
        )
        graph = self._submit_graph("Material workflow", processing)
        self._complete(processing)
        self._apply_registry.unregister_plugins([_TestApplyHandler])
        self._widget.model.refresh_schedule_conditions()
        await ui_test.human_delay()

        # Expand the graph and verify child, graph, and footer all show the same neutral unavailable state.
        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)
        await branch.click()
        await ui_test.human_delay()
        expected_reason = "The feature needed to update this job's result is unavailable."
        checks = (
            self._find(f"Image[*].identifier=='apply_graph_{graph.graph_id}'"),
            self._find(f"Image[*].identifier=='apply_job_{processing.job_id}'"),
            self._find("Image[*].identifier=='apply_filtered_jobs'"),
        )
        declines = (
            self._find(f"Image[*].identifier=='decline_graph_{graph.graph_id}'"),
            self._find(f"Image[*].identifier=='decline_job_{processing.job_id}'"),
            self._find("Image[*].identifier=='decline_filtered_jobs'"),
        )
        self.assertTrue(all(control is not None for control in (*checks, *declines)))
        for control in checks[:2]:
            self.assertEqual(control.widget.name, "ApplyJobUnknown")
            self.assertEqual(control.widget.tooltip, expected_reason)
        for control in declines[:2]:
            self.assertEqual(control.widget.name, "DeclineJobUnknown")
            self.assertEqual(control.widget.tooltip, expected_reason)
        self.assertEqual(checks[-1].widget.name, "ApplyJob")
        self.assertEqual(declines[-1].widget.name, "DeclineJob")
        for control in (*checks[:2], *declines[:2]):
            self.assertFalse(control.widget.enabled)
        self.assertTrue(checks[-1].widget.enabled)
        self.assertTrue(declines[-1].widget.enabled)

    async def test_graph_apply_controls_show_and_repeat_the_stable_disposition(self):
        """Applied and Declined graph controls stay vivid while Check can Reapply results."""
        generation = _WidgetJob(name="ComfyUI generation")
        processing = _WidgetJob(
            name="Asset processing",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("processed")),
        )
        graph = self._submit_graph("Material workflow", generation, processing)
        self._complete(generation)
        self._complete(processing)
        await ui_test.human_delay()

        # Apply through the child, then verify the graph and child show the same active disposition.
        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)
        await branch.click()
        await ui_test.human_delay()
        child_check = self._find(f"Image[*].identifier=='apply_job_{processing.job_id}'")
        graph_check = self._find(f"Image[*].identifier=='apply_graph_{graph.graph_id}'")
        graph_decline = self._find(f"Image[*].identifier=='decline_graph_{graph.graph_id}'")
        self.assertTrue(all(control is not None for control in (child_check, graph_check, graph_decline)))
        self.assertEqual(graph_check.widget.name, "ApplyJob")
        self.assertEqual(graph_decline.widget.name, "DeclineJob")
        self.assertEqual(child_check.widget.name, "ApplyJob")
        await child_check.click()
        await self._wait_for_disposition(processing.job_id, ApplyDisposition.APPLIED)
        await self._widget.model.wait_for_background_tasks()
        await ui_test.human_delay()

        graph_check = self._find(f"Image[*].identifier=='apply_graph_{graph.graph_id}'")
        child_check = self._find(f"Image[*].identifier=='apply_job_{processing.job_id}'")
        graph_status = self._find(f"Label[*].identifier=='queue_graph_status_{graph.graph_id}_label'")
        self.assertEqual(graph_check.widget.name, "ApplyJobActive")
        self.assertEqual(child_check.widget.name, "ApplyJobActive")
        self.assertTrue(graph_check.widget.enabled)
        self.assertIn("Applied", graph_status.widget.text)

        # Check remains an action: clicking the applied graph performs one real Reapply.
        await graph_check.click()
        await ui_test.human_delay()
        await self._widget.model.wait_for_background_tasks()
        await ui_test.human_delay()

        self.assertEqual(_TestApplyHandler.applied_targets, ["processed", "processed"])
        self.assertIs(
            self._interface.get_job_snapshot(processing.job_id).apply_disposition,
            ApplyDisposition.APPLIED,
        )

        # Graph details count each stage once using its final user-facing state.
        graph_label = next(
            label for label in self._find_all("Label[*].name=='CellLabel'") if label.widget.text == "Material workflow"
        )
        await graph_label.click()
        await ui_test.human_delay()
        status_frame = self._find("Frame[*].identifier=='graph_details_status'")
        widgets = [status_frame.widget]
        status_keys = []
        while widgets:
            widget = widgets.pop()
            if isinstance(widget, ui.Label) and widget.name == "QueueDetailKey":
                status_keys.append(widget.text)
            widgets.extend(ui.Inspector.get_children(widget))
        self.assertCountEqual(status_keys, ["Done", "Applied"])

        # X reverts the applied result, after which the red X is the stable active disposition.
        graph_decline = self._find(f"Image[*].identifier=='decline_graph_{graph.graph_id}'")
        await graph_decline.click()
        await ui_test.human_delay()
        confirm_button = ui_test.find("Revert Applied Results//Frame/**/Button[*].name=='confirm_button'")
        self.assertIsNotNone(confirm_button)
        await confirm_button.click()
        await self._wait_for_disposition(processing.job_id, ApplyDisposition.DECLINED)
        await self._widget.model.wait_for_background_tasks()
        await ui_test.human_delay()

        graph_decline = self._find(f"Image[*].identifier=='decline_graph_{graph.graph_id}'")
        child_decline = self._find(f"Image[*].identifier=='decline_job_{processing.job_id}'")
        graph_check = self._find(f"Image[*].identifier=='apply_graph_{graph.graph_id}'")
        graph_status = self._find(f"Label[*].identifier=='queue_graph_status_{graph.graph_id}_label'")
        self.assertEqual(graph_decline.widget.name, "DeclineJobActive")
        self.assertEqual(child_decline.widget.name, "DeclineJobActive")
        self.assertFalse(graph_decline.widget.enabled)
        self.assertFalse(child_decline.widget.enabled)
        self.assertTrue(graph_check.widget.enabled)
        self.assertEqual(graph_check.widget.name, "ApplyJob")
        self.assertIn("Declined", graph_status.widget.text)

    async def test_active_status_pills_have_equal_outer_padding_and_fit_adapter_text(self):
        """Active graph and child pills align to visible columns and retain text padding."""
        # Start a graph, expand it, and inspect the status widgets rendered by the real adapter.
        generation = _WidgetJob(name="ComfyUI generation")
        graph = self._submit_graph("Material workflow", generation)
        claimed = self._interface.claim_runnable_jobs()
        self.assertEqual(claimed, [generation.job_id])
        self.assertTrue(self._interface.start_job(generation.job_id))
        await ui_test.human_delay()
        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)

        await branch.click()
        await ui_test.human_delay()

        status_frame = self._find(f"Frame[*].identifier=='queue_graph_{graph.graph_id}_status'")
        status_pills = sorted(
            self._find_all("Rectangle[*].name=='StatusProcessing'"),
            key=lambda pill: pill.center.y,
        )
        status_labels = self._find_all("Label[*].name=='StatusLabel'")
        self.assertIsNotNone(status_frame)
        self.assertEqual(len(status_pills), 2)
        self.assertEqual(len(status_labels), 2)
        self.assertEqual(
            {label.widget.text for label in status_labels},
            {"Generating textures · 0/1 job", "Generating textures"},
        )

        left_boundary = status_frame.center.x - (status_frame.widget.computed_width / 2)
        right_boundary = status_frame.center.x + (status_frame.widget.computed_width / 2)
        for pill, label in zip(status_pills, sorted(status_labels, key=lambda status: status.center.y)):
            pill_left = pill.center.x - (pill.widget.computed_width / 2)
            pill_right = pill.center.x + (pill.widget.computed_width / 2)
            left_padding = pill_left - left_boundary
            right_padding = right_boundary - pill_right
            self.assertAlmostEqual(left_padding, right_padding, delta=0.1)
            self.assertGreaterEqual(left_padding, PADDING_SMALL.value)
            self.assertGreaterEqual(
                pill.widget.computed_width,
                label.widget.exact_content_width + (2 * PADDING_SMALL.value),
            )

    async def test_graph_details_use_compact_padded_content_over_panel_background(self):
        """Graph details retain the panel background and intrinsic-height content geometry."""
        # Select a long-named graph and inspect its rendered summary, sections, and panel body.
        first = _WidgetJob(name="ComfyUI generation")
        second = _WidgetJob(name="Asset processing")
        graph_name = "Material details with a deliberately long workflow and preset name that must remain readable"
        graph = self._submit_graph(graph_name, first, second)
        await ui_test.human_delay()
        root_label = self._find(f"Label[*].text=='{graph_name}'")
        self.assertIsNotNone(root_label)

        await root_label.click()
        await ui_test.human_delay()
        background = self._find("Rectangle[*].name=='QueueDetailBackground'")
        scroller = self._find("ScrollingFrame[*].identifier=='graph_details_scroll'")
        title = self._find("Label[*].identifier=='graph_details_title'")
        identity = self._find("Label[*].text=='JOB GRAPH · 2 stages'")
        summary = self._find("Label[*].identifier=='graph_details_summary'")
        keys = self._find_all("Label[*].name=='QueueDetailKey'")
        values = self._find_all("Label[*].name=='QueueDetailValue'")
        section_titles = self._find_all("Label[*].name=='PropertiesPaneSectionTitle'")
        collapsable_frames = self._find_all("CollapsableFrame[*].identifier=='PropertyCollapsableFrame'")
        collapsable_arrows = self._find_all("Image[*].identifier=='PropertyCollapsableFrameArrow'")
        child_buttons = self._find_all("Button[*].name=='QueueDetailChild'")
        header_background = self._find("Rectangle[*].name=='QueueDetailHeaderBackground'")
        graph_action = self._find(
            f"Image[*].identifier=='details_open_test_workflow_graph_{graph.graph_id}_job_{first.job_id}'"
        )
        technical = self._find("Frame[*].identifier=='graph_details_technical'")
        technical_frame = max(
            self._find_all("CollapsableFrame[*].identifier=='PropertyCollapsableFrame'"),
            key=lambda frame: frame.center.y,
        )
        copy_technical = self._find("Image[*].identifier=='graph_details_copy_technical'")

        self.assertIsNotNone(background)
        self.assertIsNotNone(scroller)
        self.assertEqual(scroller.widget.name, "PropertiesPaneSection")
        self.assertIsNotNone(title)
        self.assertEqual(title.widget.text, graph_name)
        self.assertEqual(title.widget.tooltip, graph_name)
        self.assertTrue(title.widget.elided_text)
        self.assertIsNotNone(identity)
        self.assertIsNotNone(summary)
        self.assertLess(title.center.y, identity.center.y)
        self.assertLess(identity.center.y, summary.center.y)
        content_left = background.center.x - (background.widget.computed_width / 2) + PADDING_MEDIUM.value
        self.assertGreaterEqual(title.center.x - (title.widget.computed_width / 2), content_left - 1)
        self.assertLessEqual(title.widget.computed_height, ROW_HEIGHT.value)
        self.assertTrue(keys)
        self.assertTrue(values)
        self.assertTrue(section_titles)
        self.assertEqual(len(collapsable_frames), len(section_titles))
        self.assertEqual(len(collapsable_arrows), len(section_titles))
        self.assertTrue(child_buttons)
        self.assertTrue(all(field.widget.computed_height <= ROW_HEIGHT.value for field in keys))
        self.assertTrue(all(field.widget.computed_height > 0 for field in values))
        self.assertTrue(all(title.widget.computed_height <= ROW_HEIGHT.value for title in section_titles))
        self.assertTrue(all(button.widget.computed_height == ROW_HEIGHT.value for button in child_buttons))
        self.assertIsNotNone(graph_action)
        self.assertIsNotNone(header_background)
        self.assertAlmostEqual(graph_action.center.y, title.center.y, delta=1)
        self.assertLessEqual(
            title.center.x + (title.widget.computed_width / 2) + PADDING_SMALL.value,
            graph_action.center.x - (graph_action.widget.computed_width / 2) + 0.1,
        )
        self.assertGreaterEqual(
            graph_action.center.y - (graph_action.widget.computed_height / 2),
            header_background.center.y - (header_background.widget.computed_height / 2) + PADDING_SMALL.value,
        )
        self.assertIsNotNone(technical)
        self.assertIsNotNone(technical_frame)
        self.assertIsNotNone(copy_technical)
        self.assertGreater(copy_technical.center.y, technical.center.y - (technical.widget.computed_height / 2))

    async def test_graph_details_topology_uses_relationship_text_without_unsupported_marker(self):
        """Topology direction stays readable without relying on a font-specific arrow glyph."""
        # Submit a dependent graph, select it, and read the topology shown in graph details.
        first = _WidgetJob(name="ComfyUI generation")
        second = _WidgetJob(name="Asset processing")
        graph = JobGraph(name="Material topology", jobs=[first, second])
        graph.bind(first, REQUEST, first.request)
        graph.bind(second, REQUEST, second.request)
        graph.depends_on(second, first)
        self._interface.submit(graph)
        await ui_test.human_delay()

        root_label = self._find("Label[*].text=='Material topology'")
        self.assertIsNotNone(root_label)
        await root_label.click()
        await ui_test.human_delay()

        relationship = self._find("Label[*].text=='Runs before'")
        topology_marker = self._find("Label[*].name=='QueueDetailTopologyArrow'")
        self.assertIsNotNone(relationship)
        self.assertIsNone(topology_marker)

    async def test_job_stage_filter_popup_filters_custom_adapter_rows(self):
        """The centralized native popup filters graph and custom-adapter stage labels together."""
        # Submit distinct graphs, choose visible graph and stage labels, and inspect the filtered tree.
        first = self._submit_graph("First Material", _WidgetJob(name="Generation"), _WidgetJob(name="Asset processing"))
        second = self._submit_graph("Second Material", _WidgetJob(name="Generation"))
        await ui_test.human_delay()
        await self._open_filter_popup()

        second_graph_label = self._find_popup("queue_filter_graph_1_label")
        asset_stage = self._find_popup("queue_filter_stage_1")
        self.assertIsNotNone(second_graph_label)
        self.assertIsNotNone(asset_stage)
        await self._click_popup(second_graph_label)
        await self._click_popup(asset_stage)

        self.assertIsNotNone(self._find(f"Label[*].text=='{first.name}'"))
        self.assertIsNone(self._find(f"Label[*].text=='{second.name}'"))
        self.assertEqual(self._find("Image[*].identifier=='queue_filters'").widget.name, "FilterActive")
        roots = self._widget.model.get_item_children(None)
        self.assertEqual([item.row.name for item in self._widget.model.get_item_children(roots[0])], ["Generation"])

    async def test_graph_filter_groups_every_graph_with_the_same_name(self):
        """One graph-name choice filters every matching graph instead of listing each submission."""
        # Submit repeated graph names and use the real popup to filter the grouped choice.
        shared_name = "PBRify - Custom Settings"
        self._submit_graph(shared_name, _WidgetJob(name="First generation"))
        self._submit_graph(shared_name, _WidgetJob(name="Second generation"))
        self._submit_graph("Upscale - Cinematic", _WidgetJob(name="Other generation"))
        await ui_test.human_delay()

        await self._open_filter_popup()

        widgets = [self._widget._filter_menu]
        shared_labels = []
        while widgets:
            widget = widgets.pop()
            if isinstance(widget, ui.Label) and widget.text == f"Job: {shared_name}":
                shared_labels.append(widget)
            widgets.extend(ui.Inspector.get_children(widget))
        self.assertEqual(len(shared_labels), 1)
        await self._click_popup(shared_labels[0])
        roots = self._widget.model.get_item_children(None)
        self.assertEqual([root.name for root in roots], ["Upscale - Cinematic"])

    async def test_status_and_apply_filters_share_one_popup_for_custom_adapter_rows(self):
        """Status and every explicit Apply disposition filter the same custom-adapter hierarchy."""
        # Complete applicable work and exercise status and Apply choices in the shared popup.
        pending = _WidgetJob(
            name="Generated result",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("pending")),
        )
        graph = self._submit_graph("Filtered Material", pending)
        self._complete(pending)
        await ui_test.human_delay()

        await self._open_filter_popup()
        status_deselect = self._find_popup("queue_filter_status_deselect_all")
        self.assertIsNotNone(status_deselect)
        await self._click_popup(status_deselect)
        ready = self._find_popup("queue_filter_status_ready_to_apply")
        self.assertIsNotNone(ready)
        await self._click_popup(ready)
        self.assertIsNotNone(self._find(f"Label[*].text=='{graph.name}'"))

        await self._open_filter_popup()
        await self._scroll_filter_popup_to_bottom()
        apply_ids = tuple(disposition.value for disposition in ApplyDisposition)
        self.assertTrue(all(self._find_popup(f"queue_filter_apply_{value}") is not None for value in apply_ids))
        apply_deselect = self._find_popup("queue_filter_apply_deselect_all")
        self.assertIsNotNone(apply_deselect)
        await self._click_popup(apply_deselect)
        pending_filter = self._find_popup("queue_filter_apply_pending")
        self.assertIsNotNone(pending_filter)
        await self._click_popup(pending_filter)
        self.assertIsNotNone(
            self._find(f"Label[*].text=='{graph.name}'"),
            msg=(
                f"states={self._widget.model.visible_states}; "
                f"apply={self._widget.model.visible_apply_dispositions}; "
                f"rows={[item.row.apply_disposition for item in self._widget.model.visible_job_items]}"
            ),
        )

    async def test_scheduler_controls_default_to_running_when_preference_is_unset(self):
        """The persistent default keeps scheduler controls left and bulk actions in the footer."""
        # Open a fresh queue and inspect scheduler state and toolbar/footer controls.
        status = self._find("Label[*].identifier=='scheduler_status'")
        start_button = self._find("Image[*].identifier=='start_scheduler'")
        stop_button = self._find("Image[*].identifier=='stop_scheduler'")
        filter_button = self._find("Image[*].identifier=='queue_filters'")
        apply_button = self._find("Image[*].identifier=='apply_filtered_jobs'")
        decline_button = self._find("Image[*].identifier=='decline_filtered_jobs'")

        self.assertIsNone(self._settings.get(SCHEDULER_ENABLED_SETTING_PATH))
        self.assertTrue(JobQueueSettings().scheduler_enabled)
        self.assertIsNotNone(status)
        self.assertIsNotNone(start_button)
        self.assertIsNotNone(stop_button)
        self.assertIsNotNone(filter_button)
        self.assertIsNotNone(apply_button)
        self.assertIsNotNone(decline_button)
        self.assertEqual(decline_button.widget.name, "DeclineJob")
        self.assertEqual(self._find_all("Label[*].name=='QueueToolbarTitle'"), [])
        self.assertEqual(start_button.widget.name, "Start")
        self.assertEqual(stop_button.widget.name, "Stop")
        self.assertEqual(status.widget.text, "Running")
        self.assertTrue(status.widget.visible)
        self.assertTrue(start_button.widget.visible)
        self.assertTrue(stop_button.widget.visible)
        self.assertFalse(start_button.widget.enabled)
        self.assertTrue(stop_button.widget.enabled)
        self.assertLess(start_button.center.x, stop_button.center.x)
        self.assertLess(stop_button.center.x, status.center.x)
        self.assertEqual(filter_button.widget.name, "Filter")
        self.assertLess(status.center.x, filter_button.center.x)
        self.assertGreater(apply_button.center.y, start_button.center.y)
        self.assertEqual(apply_button.center.y, decline_button.center.y)
        self.assertLess(apply_button.center.x, decline_button.center.x)

    async def test_apply_mode_badge_toggles_persistent_preference(self):
        """The toolbar badge switches between explicit automatic and manual modes."""
        # Click the rendered Apply-mode badge in each state and verify the saved preference follows.
        settings = JobQueueSettings()
        original = settings.auto_apply
        settings.set_auto_apply(False)
        await ui_test.human_delay()
        badge = self._find("ZStack[*].identifier=='apply_mode_badge'")
        badge_label = self._find("Label[*].name=='QueueApplyModeBadge'")
        manual_background = self._find("Rectangle[*].name=='QueueManualApplyBadge'")
        self.assertIsNotNone(badge)
        self.assertIsNotNone(badge_label)
        self.assertIsNotNone(manual_background)
        self.assertEqual(badge_label.widget.text, "MANUAL")

        try:
            await badge.click()
            await ui_test.human_delay()

            self.assertTrue(settings.auto_apply)
            self.assertEqual(badge_label.widget.text, "AUTO")
            self.assertIsNotNone(self._find("Rectangle[*].name=='QueueAutoApplyBadge'"))

            await badge.click()
            await ui_test.human_delay()

            self.assertFalse(settings.auto_apply)
            self.assertEqual(badge_label.widget.text, "MANUAL")
            self.assertIsNotNone(self._find("Rectangle[*].name=='QueueManualApplyBadge'"))
        finally:
            settings.set_auto_apply(original)
            await ui_test.human_delay()

    async def test_auto_apply_defaults_to_enabled_when_preference_is_unset(self):
        """A new user sees automatic Apply enabled before choosing a preference."""
        # Open the queue without a saved preference and inspect its visible default mode.
        badge_label = self._find("Label[*].name=='QueueApplyModeBadge'")
        auto_background = self._find("Rectangle[*].name=='QueueAutoApplyBadge'")

        auto_apply = JobQueueSettings().auto_apply

        self.assertIsNone(self._settings.get(AUTO_APPLY_SETTING_PATH))
        self.assertTrue(auto_apply)
        self.assertIsNotNone(badge_label)
        self.assertEqual(badge_label.widget.text, "AUTO")
        self.assertIsNotNone(auto_background)

    async def test_scheduler_controls_follow_setting_and_persist_button_changes(self):
        """External and toolbar preference changes keep scheduler controls synchronized."""
        # Change scheduler state through settings and visible controls, then read both representations.
        status = self._find("Label[*].identifier=='scheduler_status'")
        start_button = self._find("Image[*].identifier=='start_scheduler'")
        stop_button = self._find("Image[*].identifier=='stop_scheduler'")
        self.assertIsNotNone(status)
        self.assertIsNotNone(start_button)
        self.assertIsNotNone(stop_button)

        JobQueueSettings().set_scheduler_enabled(False)
        await ui_test.human_delay()

        self.assertEqual(status.widget.text, "Stopped")
        self.assertTrue(start_button.widget.enabled)
        self.assertFalse(stop_button.widget.enabled)
        self.assertEqual(stop_button.widget.tooltip, "The job queue is stopped")

        await start_button.click()
        await ui_test.human_delay()

        self.assertTrue(self._settings.get(SCHEDULER_ENABLED_SETTING_PATH))
        self.assertEqual(status.widget.text, "Running")
        self.assertFalse(start_button.widget.enabled)
        self.assertTrue(stop_button.widget.enabled)
        self.assertEqual(stop_button.widget.tooltip, "Stop dispatching new jobs")

        await stop_button.click()
        await ui_test.human_delay()

        self.assertFalse(self._settings.get(SCHEDULER_ENABLED_SETTING_PATH))
        self.assertEqual(status.widget.text, "Stopped")
        self.assertTrue(start_button.widget.enabled)
        self.assertFalse(stop_button.widget.enabled)
        self.assertEqual(stop_button.widget.tooltip, "The job queue is stopped")

    async def test_scheduler_controls_show_stopping_graph_until_active_job_finishes(self):
        """Stopping names the graph still finishing without cancelling its active job."""
        # Run a real queued job, stop dispatch while it is active, then let the owned work finish.
        graph = self._submit_graph("Material texture generation", _WidgetJob(name="Generation"))
        _WidgetJob.execution_started = asyncio.Event()
        _WidgetJob.execution_release = asyncio.Event()
        scheduler = JobScheduler(self._interface)
        scheduler.start()
        await asyncio.wait_for(_WidgetJob.execution_started.wait(), 2)
        stop_button = self._find("Image[*].identifier=='stop_scheduler'")
        status = self._find("Label[*].identifier=='scheduler_status'")
        self.assertIsNotNone(stop_button)
        self.assertIsNotNone(status)

        try:
            await stop_button.click()
            stop_task = asyncio.create_task(scheduler.stop())
            await ui_test.human_delay()

            self.assertEqual(status.widget.text, "Stopping")
            self.assertEqual(
                status.widget.tooltip,
                f'Waiting for graph "{graph.name}" to finish before stopping.',
            )
            self.assertFalse(stop_task.done())
            self.assertEqual(self._interface.get_job_snapshot(graph.jobs[0].job_id).state, JobState.IN_PROGRESS)

            _WidgetJob.execution_release.set()
            await asyncio.wait_for(stop_task, 2)
            await ui_test.human_delay()

            self.assertEqual(status.widget.text, "Stopped")
            self.assertEqual(status.widget.tooltip, "The job queue is stopped")
            self.assertEqual(self._interface.get_job_snapshot(graph.jobs[0].job_id).state, JobState.DONE)
        finally:
            _WidgetJob.execution_release.set()
            await scheduler.stop()

    async def test_footer_actions_remain_interactive_when_no_visible_job_is_eligible(self):
        """Check and X remain stable while their guarded callbacks have no eligible work."""
        # Submit unfinished work and inspect the always-present footer controls.
        pending = _WidgetJob(
            name="Pending result",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("pending")),
        )
        self._submit_graph("Toolbar State", pending)
        await ui_test.human_delay()
        apply_button = self._find("Image[*].identifier=='apply_filtered_jobs'")
        decline_button = self._find("Image[*].identifier=='decline_filtered_jobs'")
        self.assertIsNotNone(apply_button)
        self.assertIsNotNone(decline_button)
        self.assertTrue(apply_button.widget.enabled)
        self.assertTrue(decline_button.widget.enabled)

        # Clicking either control is a safe no-op until the result becomes eligible.
        await apply_button.click()
        await decline_button.click()
        await ui_test.human_delay()
        self.assertEqual(self._widget.model.visible_job_items[0].row.apply_disposition, ApplyDisposition.NOT_READY)

        self._complete(pending)
        await ui_test.human_delay()

        self.assertTrue(apply_button.widget.enabled)
        self.assertTrue(decline_button.widget.enabled)

    async def test_bulk_check_reserves_every_visible_job_before_execution_reaches_it(self):
        """A blocked first Apply immediately disables later captured jobs in the real widget."""
        # Start a bulk Apply over two visible jobs and inspect reservation before the first releases.
        graph_id = uuid.uuid4()
        first = _WidgetJob(
            name="First result",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("first")),
        )
        second = _WidgetJob(
            name="Second result",
            value=2,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("second")),
        )
        graph = JobGraph(graph_id=graph_id, name="Bulk Reservation", jobs=[first, second])
        graph.bind(first, REQUEST, first.request)
        graph.bind(second, REQUEST, second.request)
        self._interface.submit(graph)
        self._complete(first)
        self._complete(second)
        _TestApplyHandler.apply_started = asyncio.Event()
        _TestApplyHandler.apply_release = asyncio.Event()
        await ui_test.human_delay()
        apply_button = self._find("Image[*].identifier=='apply_filtered_jobs'")
        self.assertIsNotNone(apply_button)

        await apply_button.click()

        await asyncio.wait_for(_TestApplyHandler.apply_started.wait(), 2)
        items = tuple(self._widget.model.visible_job_items)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(self._widget.model.is_busy(item) for item in items))
        self.assertTrue(all(not self._widget.model.can_check_item(item, allow_reapply=True) for item in items))
        self.assertTrue(apply_button.widget.enabled)
        _TestApplyHandler.apply_release.set()
        await self._widget.model.wait_for_background_tasks()

    async def test_second_bulk_check_gesture_does_not_schedule_duplicate_work(self):
        """A rapid second footer callback cannot enqueue Apply or Reapply for reserved jobs."""
        # Trigger the visible bulk action twice while its first job remains active.
        first = _WidgetJob(
            name="First result",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("first")),
        )
        second = _WidgetJob(
            name="Second result",
            value=2,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("second")),
        )
        self._submit_graph("Double Check", first, second)
        self._complete(first)
        self._complete(second)
        _TestApplyHandler.apply_started = asyncio.Event()
        _TestApplyHandler.apply_release = asyncio.Event()
        await ui_test.human_delay()
        self._widget._apply_filtered()
        await asyncio.wait_for(_TestApplyHandler.apply_started.wait(), 2)

        self._widget._apply_filtered()

        await asyncio.sleep(0)
        self.assertEqual(_TestApplyHandler.applied_targets, ["first"])
        _TestApplyHandler.apply_release.set()
        await self._widget.model.wait_for_background_tasks()
        self.assertEqual(_TestApplyHandler.applied_targets, ["first", "second"])

    async def test_bulk_x_confirmation_preserves_prompt_time_actions(self):
        """A formerly skipped job cannot become a surprise Revert while confirmation is open."""
        first = _WidgetJob(
            name="First result",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("first")),
        )
        second = _WidgetJob(
            name="Second result",
            value=2,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("second")),
        )
        self._submit_graph("Confirm Exact Actions", first, second)
        self._complete(first)
        self._complete(second)
        await self._apply_executor.apply(first.job_id)
        _TestApplyHandler.apply_started = asyncio.Event()
        _TestApplyHandler.apply_release = asyncio.Event()
        second_apply = asyncio.create_task(self._apply_executor.apply(second.job_id))
        await asyncio.wait_for(_TestApplyHandler.apply_started.wait(), 2)
        await ui_test.human_delay()

        # The first result is reversible; the still-applying second result is explicitly skipped.
        decline_button = self._find("Image[*].identifier=='decline_filtered_jobs'")
        self.assertIsNotNone(decline_button)
        await decline_button.click()
        await ui_test.human_delay()
        prompt_labels = ui_test.find_all("Revert Applied Results//Frame/**/Label[*]")
        prompt_text = " ".join(label.widget.text for label in prompt_labels)
        self.assertIn("Revert 1 applied job", prompt_text)
        self.assertIn("skip 1 unavailable job", prompt_text)

        # Completion while the prompt is open must not reclassify the skipped result as a Revert.
        _TestApplyHandler.apply_release.set()
        await second_apply
        await ui_test.human_delay()
        confirm_button = ui_test.find("Revert Applied Results//Frame/**/Button[*].name=='confirm_button'")
        self.assertIsNotNone(confirm_button)
        await confirm_button.click()
        await ui_test.human_delay()
        await self._widget.model.wait_for_background_tasks()
        await ui_test.human_delay()

        self.assertIs(self._interface.get_job_snapshot(first.job_id).apply_disposition, ApplyDisposition.DECLINED)
        self.assertIs(self._interface.get_job_snapshot(second.job_id).apply_disposition, ApplyDisposition.APPLIED)
        self.assertEqual(_TestApplyHandler.reverted_targets, ["first"])
        notification_text = [notification.info.text for notification in get_all_notifications()]
        self.assertTrue(
            any("reverted 1" in text and "skipped 1" in text for text in notification_text), notification_text
        )

    async def test_graph_expansion_survives_real_structural_queue_event(self):
        """A root remains expanded by graph identity after another graph is submitted."""
        # Expand one graph, submit another through the queue, and inspect the preserved hierarchy.
        first = _WidgetJob(name="Generation")
        second = _WidgetJob(name="Asset processing")
        self._submit_graph("Material Build", first, second)
        await ui_test.human_delay()
        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)

        await branch.click()
        await ui_test.human_delay()
        first_child = self._find(f"Label[*].identifier=='job_name_{first.job_id}'")
        second_child = self._find(f"Label[*].identifier=='job_name_{second.job_id}'")
        self.assertIsNotNone(first_child)
        self.assertIsNotNone(second_child)

        self._submit_graph("Second Material", _WidgetJob(name="Other generation"))
        await ui_test.human_delay()

        self.assertIsNotNone(self._find(f"Label[*].identifier=='job_name_{first.job_id}'"))
        self.assertIsNotNone(self._find(f"Label[*].identifier=='job_name_{second.job_id}'"))

    async def test_coalesced_job_and_mutation_events_rebuild_retained_visible_row(self):
        """A queued job update remains visible when its row and structural events share one UI dispatch."""
        # Show a real queued child before updating its durable payload through the queue interface.
        job = _WidgetJob(name="Original stage name")
        self._submit_graph("Updated Material", job)
        await ui_test.human_delay()
        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)
        await branch.click()
        await ui_test.human_delay()
        self.assertIsNotNone(self._find(f"Label[*].identifier=='job_name_{job.job_id}'"))

        # The queue emits job-changed and mutation together for this one committed update.
        self.assertTrue(self._interface.try_update_queued_job(dataclasses.replace(job, name="Updated stage name")))
        await ui_test.human_delay()

        # The retained row rebuilds even though its visible membership did not change.
        updated_label = self._find(f"Label[*].identifier=='job_name_{job.job_id}'")
        self.assertIsNotNone(updated_label)
        self.assertEqual(updated_label.widget.text, "Updated stage name")

    async def test_delete_graph_removes_real_row_and_all_queue_owned_job_directories(self):
        """Confirming root Delete commits the graph and removes both child folders."""
        # Create queue-owned artifacts, confirm Delete through the row, and inspect disk and UI state.
        first = _WidgetJob(name="Generation")
        second = _WidgetJob(name="Asset processing")
        self._submit_graph("Delete Material", first, second)
        directories = [
            self._interface.get_job_directory(first.job_id),
            self._interface.get_job_directory(second.job_id),
        ]
        for directory in directories:
            directory.mkdir(parents=True)
            (directory / "result.bin").write_bytes(b"result")
        await ui_test.human_delay()

        graph_snapshot = self._interface.get_graph_snapshots()[0]
        delete_button = self._find(f"Image[*].identifier=='delete_graph_{graph_snapshot.graph_id}'")
        self.assertIsNotNone(delete_button)
        await delete_button.click()
        await ui_test.human_delay()
        prompt_labels = ui_test.find_all("Delete Job Graph//Frame/**/Label[*]")
        self.assertTrue(any("2 output files" in label.widget.text for label in prompt_labels))
        self.assertTrue(any("changes already applied" in label.widget.text for label in prompt_labels))
        confirm_button = ui_test.find("Delete Job Graph//Frame/**/Button[*].name=='confirm_button'")
        self.assertIsNotNone(confirm_button)
        await confirm_button.click()
        await ui_test.human_delay()
        await self._widget.model.wait_for_background_tasks()
        await ui_test.human_delay()

        self.assertEqual(self._interface.get_graph_snapshots(), [])
        self.assertEqual(self._find_all("Label[*].text=='Delete Material'"), [])
        self.assertTrue(all(not directory.exists() for directory in directories))

    async def test_delete_selected_graphs_uses_one_confirmation_and_removes_every_root(self):
        """Deleting a selected root applies one exact confirmation to every selected graph."""
        # Select two rendered roots, invoke one Delete action, and verify both graphs and folders disappear.
        first = _WidgetJob(name="Generation")
        second = _WidgetJob(name="Generation")
        self._submit_graph("First Material", first)
        self._submit_graph("Second Material", second)
        directories = tuple(self._interface.get_job_directory(job.job_id) for job in (first, second))
        for directory in directories:
            directory.mkdir(parents=True)
            (directory / "result.bin").write_bytes(b"result")
        await ui_test.human_delay()

        roots = tuple(self._widget.model.all_graphs)
        self._widget._tree_widget.selection = list(roots)
        # A programmatic tree selection notifies nobody, so drive the model channel like a real click does.
        self._widget.model.set_items_selected(list(roots))
        await ui_test.human_delay()
        self.assertEqual(tuple(self._widget.model.selected_items), roots)
        delete_button = self._find(f"Image[*].identifier=='delete_graph_{roots[0].graph_id}'")
        self.assertIsNotNone(delete_button)
        await delete_button.click()
        await ui_test.human_delay()

        prompt_labels = ui_test.find_all("Delete Job Graphs//Frame/**/Label[*]")
        self.assertTrue(any("2 selected graphs" in label.widget.text for label in prompt_labels))
        self.assertTrue(any("2 jobs" in label.widget.text for label in prompt_labels))
        self.assertTrue(any("2 output files" in label.widget.text for label in prompt_labels))
        confirm_button = ui_test.find("Delete Job Graphs//Frame/**/Button[*].name=='confirm_button'")
        self.assertIsNotNone(confirm_button)
        await confirm_button.click()
        self.assertEqual(self._widget.model.selected_items, [])
        await self._widget.model.wait_for_background_tasks()
        await ui_test.human_delay()

        self.assertEqual(self._interface.get_graph_snapshots(), [])
        self.assertTrue(all(not directory.exists() for directory in directories))

    async def test_delete_key_deletes_selected_graphs(self):
        """Releasing Delete over selected roots opens one confirmation and removes every graph."""
        # Select two rendered roots, then drive the tree key handler like the native Delete key.
        first = _WidgetJob(name="Generation")
        second = _WidgetJob(name="Generation")
        self._submit_graph("First Material", first)
        self._submit_graph("Second Material", second)
        await ui_test.human_delay()

        roots = tuple(self._widget.model.all_graphs)
        self._widget._tree_widget.selection = list(roots)
        # A programmatic tree selection notifies nobody, so drive the model channel like a real click does.
        self._widget.model.set_items_selected(list(roots))
        await ui_test.human_delay()
        self.assertEqual(tuple(self._widget.model.selected_items), roots)

        # A non-Delete key and a Delete key press (not release) leave the selection and queue untouched.
        self._widget._on_queue_tree_key_pressed(int(carb.input.KeyboardInput.A), 0, False)
        self._widget._on_queue_tree_key_pressed(int(carb.input.KeyboardInput.DEL), 0, True)
        await ui_test.human_delay()
        self.assertEqual(ui_test.find_all("Delete Job Graphs//Frame/**/Label[*]"), [])
        self.assertEqual(len(self._interface.get_graph_snapshots()), 2)

        # Releasing Delete opens the same confirmation the row Delete button uses for the full selection.
        self._widget._on_queue_tree_key_pressed(int(carb.input.KeyboardInput.DEL), 0, False)
        await ui_test.human_delay()
        prompt_labels = ui_test.find_all("Delete Job Graphs//Frame/**/Label[*]")
        self.assertTrue(any("2 selected graphs" in label.widget.text for label in prompt_labels))
        self.assertTrue(any("2 jobs" in label.widget.text for label in prompt_labels))
        confirm_button = ui_test.find("Delete Job Graphs//Frame/**/Button[*].name=='confirm_button'")
        self.assertIsNotNone(confirm_button)
        await confirm_button.click()
        await self._widget.model.wait_for_background_tasks()
        await ui_test.human_delay()

        self.assertEqual(self._interface.get_graph_snapshots(), [])

    async def test_graph_details_link_reveals_child_in_tree(self):
        """Selecting a root then its details link expands and selects the child."""
        # Select a graph and use its rendered stage link to navigate back into the queue tree.
        first = _WidgetJob(name="Generation")
        second = _WidgetJob(name="Asset processing")
        self._submit_graph("Material Details", first, second)
        await ui_test.human_delay()
        root_label = self._find("Label[*].text=='Material Details'")
        self.assertIsNotNone(root_label)

        await root_label.click()
        await ui_test.human_delay()
        detail_keys = [label.widget.text for label in self._find_all("Label[*].name=='QueueDetailKey'")]
        detail_values = [label.widget.text for label in self._find_all("Label[*].name=='QueueDetailValue'")]
        self.assertEqual(detail_keys.count("Queued"), 1)
        self.assertNotIn("No Apply Needed", detail_keys)
        self.assertIn("2", detail_values)
        details_link = self._find(f"Button[*].identifier=='details_job_{second.job_id}'")
        self.assertIsNotNone(details_link)

        await details_link.click()
        await ui_test.human_delay()

        child_label = self._find(f"Label[*].identifier=='job_name_{second.job_id}'")
        child_details = self._find("Label[*].identifier=='job_details_title'")
        self.assertIsNotNone(child_label)
        self.assertIsNotNone(child_details)
        self.assertEqual(child_details.widget.text, "Asset processing")

    async def test_successful_execution_log_is_visible_in_job_details_at_completion(self):
        """Real execution publishes a readable success log before its terminal notification."""
        # Execute a queued job, open its visible details, and read the completed log stream.
        job = _WidgetJob(name="Logged generation", value=7)
        self._submit_graph("Logged Material", job)
        self.assertIn(job.job_id, self._interface.claim_runnable_jobs())
        stdout_path = self._interface.get_job_directory(job.job_id) / "logs" / "stdout.log"
        terminal_logs: list[str] = []

        def on_changed(changed_id: uuid.UUID) -> None:
            """Capture the log synchronously when the terminal state is published.

            Args:
                changed_id: Durable identifier reported by the queue.
            """
            if changed_id == job.job_id and self._interface.get_job_snapshot(job.job_id).state is JobState.DONE:
                terminal_logs.append(stdout_path.read_text(encoding="utf-8"))

        subscription = self._interface.subscribe_job_changed(on_changed)

        try:
            await JobExecutor(self._interface).execute(job.job_id)
        finally:
            del subscription
        await ui_test.human_delay()
        root_label = self._find("Label[*].text=='Logged Material'")
        self.assertIsNotNone(root_label)
        await root_label.click()
        await ui_test.human_delay()
        details_link = self._find(f"Button[*].identifier=='details_job_{job.job_id}'")
        self.assertIsNotNone(details_link)
        await details_link.click()
        await ui_test.human_delay()
        rendered_logs = [label.widget.text for label in self._find_all("Label[*].name=='QueueLogStdout'")]
        timestamps = [label.widget.text for label in self._find_all("Label[*].name=='QueueLogTimestamp'")]

        self.assertEqual(len(terminal_logs), 1)
        self.assertIn("Completed successfully", terminal_logs[0])
        self.assertEqual(len(rendered_logs), 2)
        self.assertEqual(len(timestamps), 2)
        self.assertTrue(all(re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}$", timestamp) for timestamp in timestamps))
        self.assertIn(f"Starting {job.name}", rendered_logs[0])
        self.assertIn("Completed successfully", rendered_logs[1])

    async def test_job_details_prioritize_summary_and_render_structured_values_and_logs(self):
        """Job details fold unbranched data, inline scalar sequences, and retain real branches."""
        # Execute a structured job, select its row, and inspect the rendered details hierarchy and logs.
        self._window.height = 1600
        await ui_test.human_delay()
        job = _WidgetJob(name="Detailed generation", value=7)
        graph = self._submit_graph("Detailed Material", job)
        self.assertIn(job.job_id, self._interface.claim_runnable_jobs())
        await JobExecutor(self._interface).execute(job.job_id)
        log_directory = self._interface.get_job_directory(job.job_id) / "logs"
        with (log_directory / "stdout.log").open("a", encoding="utf-8") as output_stream:
            output_stream.write("[2026-07-21T01:02:03.123456] WARNING: Using fallback texture\n")
        (log_directory / "stderr.log").write_text(
            "[2026-07-21T01:02:04.123456] ERROR: Texture processing failed\n",
            encoding="utf-8",
        )
        await ui_test.human_delay()

        await self._find("Label[*].text=='Detailed Material'").click()
        await ui_test.human_delay()
        await self._find(f"Button[*].identifier=='details_job_{job.job_id}'").click()
        await ui_test.human_delay()

        title = self._find("Label[*].identifier=='job_details_title'")
        summary = self._find("Label[*].identifier=='job_details_summary'")
        header_background = self._find("Rectangle[*].name=='QueueDetailHeaderBackground'")
        overview = self._find("Frame[*].identifier=='job_details_overview'")
        inputs = self._find("Frame[*].identifier=='job_details_inputs'")
        outputs = self._find("Frame[*].identifier=='job_details_outputs'")
        inputs_tree = self._find("DetailValueTree[*].identifier=='job_details_inputs_tree'")
        outputs_tree = self._find("DetailValueTree[*].identifier=='job_details_outputs_tree'")
        output_branches = self._find_all("Image[*].identifier=='job_details_outputs_tree_branch'")
        scroller = self._find("ScrollingFrame[*].identifier=='job_details_scroll'")
        logs = self._find("Frame[*].identifier=='job_details_logs'")
        technical = self._find("Frame[*].identifier=='job_details_technical'")
        log_background = self._find("Rectangle[*].name=='QueueLogBackground'")
        keys = [label.widget.text for label in self._find_all("Label[*].name=='QueueDetailKey'")]
        tree_key_widgets = [
            *self._find_all("Label[*].identifier=='job_details_inputs_tree_key'"),
            *self._find_all("Label[*].identifier=='job_details_outputs_tree_key'"),
        ]
        output_key_widgets = self._find_all("Label[*].identifier=='job_details_outputs_tree_key'")
        tree_keys = [label.widget.text for label in tree_key_widgets]
        tree_values = [
            label.widget.text
            for label in (
                *self._find_all("Label[*].identifier=='job_details_inputs_tree_value'"),
                *self._find_all("Label[*].identifier=='job_details_outputs_tree_value'"),
            )
        ]
        timestamps = self._find_all("Label[*].name=='QueueLogTimestamp'")
        warnings = self._find_all("Label[*].name=='QueueLogWarning'")
        errors = self._find_all("Label[*].name=='QueueLogError'")
        input_value = self._find("Label[*].text=='textures/input.png'")
        output_value = self._find("Label[*].text=='7'")
        aligned_value = self._find("Label[*].text=='Aligned value'")
        long_key = self._find("Label[*].text=='an_excessively_long_nested_key_that_must_ellipsize'")
        collapsable_arrows = self._find_all("Image[*].identifier=='PropertyCollapsableFrameArrow'")
        copy_logs = self._find(f"Image[*].identifier=='details_copy_logs_{job.job_id}'")
        copy_technical = self._find(f"Image[*].identifier=='job_details_copy_technical_{job.job_id}'")
        collapsable_frames = sorted(
            self._find_all("CollapsableFrame[*].identifier=='PropertyCollapsableFrame'"),
            key=lambda frame: frame.center.y,
        )
        section_titles = sorted(
            self._find_all("Label[*].name=='PropertiesPaneSectionTitle'"),
            key=lambda label: label.center.y,
        )
        section_frames = {title.widget.text: frame for title, frame in zip(section_titles, collapsable_frames)}
        logs_frame = section_frames["Logs"]
        technical_frame = section_frames["Technical details"]
        job_header_actions = self._find_all("Frame[*].identifier=='job_details_primary_actions'")

        self.assertIsNotNone(title)
        self.assertEqual(title.widget.text, "Detailed generation")
        self.assertIsNotNone(summary)
        self.assertIn("Done", summary.widget.text)
        self.assertTrue(all(section is not None for section in (overview, inputs, outputs, logs, technical)))
        self.assertIsNotNone(inputs_tree)
        self.assertIsNotNone(outputs_tree)
        self.assertIsNotNone(scroller)
        self.assertGreaterEqual(len(output_branches), 1)
        self.assertIsNotNone(header_background)
        self.assertEqual(job_header_actions, [])
        self.assertIsNotNone(copy_logs)
        self.assertIsNotNone(copy_technical)
        self.assertIsNotNone(logs_frame)
        self.assertIsNotNone(technical_frame)
        self.assertTrue(copy_logs.widget.enabled)
        self.assertEqual(copy_logs.widget.computed_width, ICON_SIZE_MEDIUM.value)
        self.assertEqual(copy_logs.widget.computed_height, ICON_SIZE_MEDIUM.value)
        self.assertGreater(copy_logs.center.y, logs.center.y - (logs.widget.computed_height / 2))
        self.assertGreater(copy_technical.center.y, technical.center.y - (technical.widget.computed_height / 2))
        self.assertLess(overview.center.y, logs.center.y)
        self.assertLess(logs.center.y, inputs.center.y)
        self.assertLess(inputs.center.y, outputs.center.y)
        self.assertLess(outputs.center.y, technical.center.y)
        self.assertIn("Status", keys)
        self.assertIn("Completed", keys)
        self.assertIn("request > source", tree_keys)
        self.assertIn("details > request", tree_keys)
        self.assertIn("texture", tree_keys)
        self.assertIn("textures/source.png", tree_values)
        self.assertIn("textures/input.png", tree_values)
        self.assertNotIn("{'request':", " ".join(tree_values))
        self.assertFalse(any(re.search(r"\b\d+ fields?\b", value) for value in tree_values))
        self.assertFalse(any(re.search(r"\b\d+ items?\b", value) for value in tree_values))
        self.assertIsNotNone(log_background)
        self.assertGreaterEqual(len(timestamps), 4)
        self.assertEqual([label.widget.text for label in warnings], ["WARNING: Using fallback texture"])
        self.assertEqual([label.widget.text for label in errors], ["ERROR: Texture processing failed"])
        self.assertIsNotNone(input_value)
        self.assertIsNotNone(output_value)
        self.assertIsNotNone(aligned_value)
        self.assertIsNotNone(long_key)

        logs_collapsed = logs_frame.widget.collapsed
        omni.kit.clipboard.copy("")
        await copy_logs.click()
        await ui_test.human_delay()
        self.assertEqual(logs_frame.widget.collapsed, logs_collapsed)
        self.assertIn("ERROR: Texture processing failed", omni.kit.clipboard.paste())

        overview_height = overview.widget.computed_height
        for arrow in collapsable_arrows[:2]:
            await arrow.click()
            await ui_test.human_delay()
        self.assertLess(overview.widget.computed_height, overview_height)

        output_branches = self._find_all("Image[*].identifier=='job_details_outputs_tree_branch'")
        output_key_widgets = self._find_all("Label[*].identifier=='job_details_outputs_tree_key'")
        input_value = self._find("Label[*].text=='textures/input.png'")
        output_value = self._find("Label[*].text=='7'")
        aligned_value = self._find("Label[*].text=='Aligned value'")
        long_key = self._find("Label[*].text=='an_excessively_long_nested_key_that_must_ellipsize'")
        details_key = next(label for label in output_key_widgets if label.widget.text == "details > request")
        compact_key = next(
            label for label in output_key_widgets if "second_intermediate_container" in label.widget.tooltip
        )
        compact_value = min(
            self._find_all("Label[*].identifier=='job_details_outputs_tree_value'"),
            key=lambda label: abs(label.center.y - compact_key.center.y),
        )
        metadata_key = next(label for label in output_key_widgets if label.widget.text == "metadata > title")
        self.assertAlmostEqual(output_branches[0].center.y, details_key.center.y, delta=0.1)
        self.assertEqual(compact_key.widget.text, compact_key.widget.tooltip)
        self.assertTrue(compact_key.widget.elided_text)
        self.assertEqual(metadata_key.widget.tooltip, "metadata > title")
        self.assertIn("[Albedo, Normal]", tree_values)
        self.assertEqual(output_value.widget.tooltip, "Declared type: int\nValue: 7")
        self.assertEqual(compact_value.widget.tooltip, "[Albedo, Normal]")
        self.assertEqual(long_key.widget.style["font"], MONOSPACE_FONT_PATH)
        self.assertEqual(input_value.widget.style["font"], MONOSPACE_FONT_PATH)
        self.assertEqual(output_value.widget.style["font"], MONOSPACE_FONT_PATH)
        value_left_edges = [
            value.center.x - (value.widget.computed_width / 2) for value in (input_value, output_value, aligned_value)
        ]
        self.assertAlmostEqual(min(value_left_edges), max(value_left_edges), delta=0.1)
        self.assertTrue(long_key.widget.elided_text)
        self.assertIn(long_key.widget.text, long_key.widget.tooltip)
        self.assertLessEqual(
            long_key.center.x + (long_key.widget.computed_width / 2) + PADDING_MEDIUM.value,
            aligned_value.center.x - (aligned_value.widget.computed_width / 2) + 0.1,
        )
        self.assertIn("Job ID", keys)
        self.assertIn("Graph ID", keys)

        await output_branches[0].click()
        await ui_test.human_delay()
        self.assertEqual(self._find_all("Label[*].text=='textures/input.png'"), [])
        output_branches = self._find_all("Image[*].identifier=='job_details_outputs_tree_branch'")
        self.assertGreaterEqual(len(output_branches), 1)
        await output_branches[0].click()
        await ui_test.human_delay()
        self.assertIsNotNone(self._find("Label[*].text=='textures/input.png'"))

        copy_technical = self._find(f"Image[*].identifier=='job_details_copy_technical_{job.job_id}'")
        self.assertIsNotNone(copy_technical)
        technical_collapsed = technical_frame.widget.collapsed
        omni.kit.clipboard.copy("")
        await copy_technical.click()
        await ui_test.human_delay()
        self.assertEqual(technical_frame.widget.collapsed, technical_collapsed)
        copied_technical = omni.kit.clipboard.paste()
        self.assertIn(str(job.job_id), copied_technical)
        self.assertIn(str(graph.graph_id), copied_technical)

    async def test_job_details_missing_port_value_retains_declared_type_tooltip(self):
        """A queued job identifies the declared output type before a value exists."""
        # Submit a real queued job, open its child details, and inspect the missing output row.
        job = _WidgetJob(name="Queued details")
        self._submit_graph("Queued detail values", job)
        await ui_test.human_delay()
        await self._find("Label[*].text=='Queued detail values'").click()
        await ui_test.human_delay()
        await self._find(f"Button[*].identifier=='details_job_{job.job_id}'").click()
        await ui_test.human_delay()
        missing_values = self._find_all("Label[*].text=='Not available'")

        # Both missing output ports retain their declared type instead of repeating the display placeholder.
        tooltips = {value.widget.tooltip for value in missing_values}
        self.assertIn("Declared type: int\nValue: Not available", tooltips)
        self.assertIn("Declared type: dict\nValue: Not available", tooltips)

    async def test_job_details_compacted_port_retains_declared_type_tooltip(self):
        """An unbranched output tree keeps the top-level port's declared type."""
        job = _WidgetJob(name="Compacted details", details={"first": {"second": ["Albedo", "Normal"]}})
        self._submit_graph("Compacted detail values", job)
        await ui_test.human_delay()
        self._complete(job)
        await ui_test.human_delay()

        # Open the completed child and inspect the single compacted output row.
        await self._find("Label[*].text=='Compacted detail values'").click()
        await ui_test.human_delay()
        await self._find(f"Button[*].identifier=='details_job_{job.job_id}'").click()
        await ui_test.human_delay()
        compact_value = self._find("Label[*].text=='[Albedo, Normal]'")

        # Compaction changes presentation only; the port's declared type remains available for diagnostics.
        self.assertEqual(compact_value.widget.tooltip, "Declared type: dict\nValue: [Albedo, Normal]")

    async def test_job_details_put_folder_actions_and_product_fields_in_their_sections(self):
        """Input and processed-output folders stay with their ordered owning sections."""
        # Select a completed job with real folders and inspect each section's own visible action.
        input_directory = pathlib.Path(self._temporary_directory.name) / "generated"
        output_directory = pathlib.Path(self._temporary_directory.name) / "processed"
        input_directory.mkdir()
        output_directory.mkdir()
        job = _WidgetJob(
            name="Asset processing",
            details={
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
                "processed_output": str(output_directory / "albedo.dds"),
            },
        )
        self._submit_graph("Folder actions", job)
        self.assertIn(job.job_id, self._interface.claim_runnable_jobs())
        await JobExecutor(self._interface).execute(job.job_id)
        await ui_test.human_delay()

        await self._find("Label[*].text=='Folder actions'").click()
        await ui_test.human_delay()
        await self._find(f"Button[*].identifier=='details_job_{job.job_id}'").click()
        await ui_test.human_delay()

        input_folder = self._find("Image[*].identifier=='job_details_open_input_directory'")
        output_folder = self._find("Image[*].identifier=='job_details_open_output_directory'")
        overview = self._find("Frame[*].identifier=='job_details_overview'")
        inputs = self._find("Frame[*].identifier=='job_details_inputs'")
        outputs = self._find("Frame[*].identifier=='job_details_outputs'")
        processed_outputs = self._find("Frame[*].identifier=='job_details_product_processed_outputs'")
        processed_folder = self._find("Image[*].identifier=='job_details_open_product_processed_outputs_directory'")
        logs = self._find("Frame[*].identifier=='job_details_logs'")
        technical = self._find("Frame[*].identifier=='job_details_technical'")

        self.assertIsNotNone(input_folder)
        self.assertIsNone(output_folder)
        self.assertIsNotNone(overview)
        self.assertIsNotNone(inputs)
        self.assertIsNotNone(outputs)
        self.assertIsNotNone(processed_outputs)
        self.assertIsNotNone(processed_folder)
        self.assertIsNotNone(logs)
        self.assertIsNotNone(technical)
        self.assertLess(overview.center.y, logs.center.y)
        self.assertLess(logs.center.y, inputs.center.y)
        self.assertLess(inputs.center.y, outputs.center.y)
        self.assertLess(outputs.center.y, processed_outputs.center.y)
        self.assertLess(processed_outputs.center.y, technical.center.y)
        self.assertEqual(input_folder.widget.tooltip, "Open the folder containing this job's inputs")
        self.assertEqual(
            processed_folder.widget.tooltip,
            "Open the folder containing this job's processed outputs",
        )

    async def test_apply_filter_scopes_footer_action_and_reports_exact_counts(self):
        """A filtered footer X changes only matching jobs and reports the completed scope."""
        # Filter a mixed graph, invoke the visible bulk X, and inspect changed jobs and notification counts.
        pending = _WidgetJob(
            name="Pending result",
            value=1,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("pending")),
        )
        applied = _WidgetJob(
            name="Applied result",
            value=2,
            apply_binding=ApplyBinding(RESULT, _TestApplyHandler, _ApplyTarget("applied")),
        )
        self._submit_graph("Apply Scope", pending, applied)
        self._complete(pending)
        self._complete(applied)
        await self._apply_executor.apply(applied.job_id)
        await ui_test.human_delay()
        destroy_all_notifications()
        await ui_test.human_delay()

        await self._open_filter_popup()
        await self._scroll_filter_popup_to_bottom()
        applied_filter = self._find_popup("queue_filter_apply_applied")
        self.assertIsNotNone(applied_filter)
        await self._click_popup(applied_filter)

        decline_button = self._find("Image[*].identifier=='decline_filtered_jobs'")
        self.assertIsNotNone(decline_button)
        self.assertTrue(decline_button.widget.enabled)
        self.assertEqual([item.row.name for item in self._widget.model.visible_job_items], ["Pending result"])
        await decline_button.click()
        await self._wait_for_disposition(pending.job_id, ApplyDisposition.DECLINED)
        await self._widget.model.wait_for_background_tasks()
        await ui_test.human_delay()

        pending_snapshot = self._interface.get_job_snapshot(pending.job_id)
        applied_snapshot = self._interface.get_job_snapshot(applied.job_id)
        notifications = get_all_notifications()
        notification_text = [notification.info.text for notification in notifications]
        self.assertIs(pending_snapshot.apply_disposition, ApplyDisposition.DECLINED)
        self.assertIs(applied_snapshot.apply_disposition, ApplyDisposition.APPLIED)
        self.assertTrue(
            any("declined 1" in text and "skipped 0" in text for text in notification_text), notification_text
        )

    async def test_status_filter_without_matches_shows_no_match_overlay(self):
        """A user-selected status filter preserves the tree under a no-match overlay."""
        # Toggle the queued-status choice and inspect the real tree and empty-result overlay.
        self._submit_graph("Queued Material", _WidgetJob(name="Queued job"))
        await ui_test.human_delay()
        await self._open_filter_popup()
        queued_filter = self._find_popup("queue_filter_status_queued")
        self.assertIsNotNone(queued_filter)
        await self._click_popup(queued_filter)

        tree = self._find("TreeWidget[*].identifier=='job_queue_tree'")
        title = self._find("Label[*].identifier=='queue_empty_title'")
        self.assertIsNotNone(tree)
        self.assertIsNotNone(title)
        self.assertEqual(title.widget.text, "No jobs match the current filters")

    async def test_filter_popup_reserves_scrollbar_space_for_right_edge_controls(self):
        """A long filter popup keeps every checkbox and icon clear of its vertical scrollbar."""
        # Open a populated filter popup and inspect controls at its scrollable right edge.
        self._submit_graph("Filtered Material", _WidgetJob(name="Generation"), _WidgetJob(name="Asset processing"))
        await ui_test.human_delay()

        await self._open_filter_popup()

        scrolling_frame = self._find_popup("queue_filters_popup")
        filter_icon = self._find_popup("queue_filter_icon")
        self.assertIsNotNone(scrolling_frame)
        self.assertIsNotNone(filter_icon)
        self.assertGreater(scrolling_frame.scroll_y_max, 0)
        widgets = [self._widget._filter_menu]
        checkboxes = []
        section_actions = []
        while widgets:
            widget = widgets.pop()
            if isinstance(widget, ui.CheckBox) and widget.identifier.startswith("queue_filter_"):
                checkboxes.append(widget)
            if isinstance(widget, ui.Label) and widget.identifier.endswith(("_select_all", "_deselect_all")):
                section_actions.append(widget)
            widgets.extend(ui.Inspector.get_children(widget))
        self.assertGreater(len(checkboxes), 0)
        self.assertGreater(len(section_actions), 0)
        content_right = scrolling_frame.screen_position_x + scrolling_frame.computed_width - SCROLLBAR_SPACING.value
        for widget in (*checkboxes, *section_actions, filter_icon):
            self.assertLessEqual(widget.screen_position_x + widget.computed_width, content_right)

    async def test_hidden_widget_resynchronizes_event_changes_when_shown(self):
        """Visibility detaches listeners and the next show synchronizes durable state."""
        # Hide the real widget, mutate the queue, and reopen it to inspect synchronized rows.
        self._widget.show(False)
        hidden_job = _WidgetJob(name="Submitted while hidden")

        self._submit_graph("Submitted while hidden", hidden_job)
        await ui_test.human_delay()
        hidden_labels = self._find_all(f"Label[*].identifier=='job_name_{hidden_job.job_id}'")
        self.assertEqual(hidden_labels, [])

        self._widget.show(True)
        await ui_test.human_delay()
        branch = self._find("Image[*].identifier=='queue_graph_branch'")
        self.assertIsNotNone(branch)
        await branch.click()
        await ui_test.human_delay()

        self.assertIsNotNone(self._find(f"Label[*].identifier=='job_name_{hidden_job.job_id}'"))

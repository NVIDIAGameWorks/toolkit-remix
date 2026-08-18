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

import contextlib
import datetime
import pathlib
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from functools import partial
from typing import Any

import carb
import omni.kit.clipboard
from omni import ui
from omni.flux.job_queue.core.models import QueueJobDetailsSnapshot
from omni.flux.utils.common import EventSubscription
from omni.flux.utils.common.path_utils import open_file_using_os_default
from omni.flux.utils.widget.collapsable_frame import PropertyCollapsableFrame

from . import adapter_interaction
from .constants import (
    ABSOLUTE_TIMESTAMP_FORMAT,
    EMPTY_STATE_ICON_SIZE,
    ICON_SIZE_MEDIUM,
    JOB_LOAD_ERRORS,
    LOG_TIMESTAMP_PATTERN,
    MONOSPACE_FONT_PATH,
    PADDING_LARGE,
    PADDING_MEDIUM,
    PADDING_SMALL,
    PROBLEM_DISPLAY_STATES,
    ROW_HEIGHT,
    TERMINAL_JOB_STATES,
)
from .display_adapter_base import JobAction, JobDetailDirectories, JobDetailSection
from .detail_value_tree.model import MISSING_VALUE
from .detail_value_tree.widget import DetailValueTree
from .enums import DisplayState, JobDetailSectionPlacement, LogStream
from .model import QueueModel
from .queue_item import QueueGraphItem, QueueItem

__all__ = ("JobDetailsPanel",)


class JobDetailsPanel(ui.Frame):
    """Show typed graph and job details while the containing window is visible."""

    _HEADER_HEIGHT = ui.Pixel(76)
    _KEY_WIDTH = ui.Percent(34)
    _LOG_VIEWER_HEIGHT = ui.Pixel(180)
    _LOG_TIMESTAMP_WIDTH = ui.Pixel(96)

    def __init__(self, model: QueueModel | None = None, **kwargs) -> None:
        """Initialize a hidden details panel without retaining model subscriptions.

        Args:
            model: Queue model to observe after the panel becomes visible.
            **kwargs: Native ui.Frame construction arguments.
        """
        super().__init__(**kwargs)
        self._model = model
        self._selection_sub: EventSubscription | None = None
        self._item_changed_sub = None
        self._progress_changed_sub: EventSubscription | None = None
        self._selected_item: QueueGraphItem | QueueItem | None = None
        self._visible = False
        self._destroyed = False
        self._log_text = ""
        self._collapsed_sections: dict[str, bool] = {}
        self._sections: list[PropertyCollapsableFrame] = []
        self._value_trees: list[DetailValueTree] = []
        self._header_summary_label: ui.Label | None = None
        self._overview_status_label: ui.Label | None = None
        self._overview_progress_label: ui.Label | None = None
        with self:
            self._content = ui.Frame(build_fn=self._build_content)

    def show(self, visible: bool) -> None:
        """Activate subscriptions before synchronizing, or release them while hidden.

        Args:
            visible: Whether the owning details window is visible.
        """
        if self._destroyed or visible == self._visible:
            return
        self._visible = visible
        if visible:
            self._subscribe()
            self._sync_selection_from_model()
        else:
            self._unsubscribe()

    def set_model(self, model: QueueModel | None) -> None:
        """Replace the observed model without activating a hidden panel.

        Args:
            model: Queue model to observe, or None to detach.
        """
        self._unsubscribe()
        self._model = model
        self._selected_item = None
        if self._visible:
            self._subscribe()
            self._sync_selection_from_model()
        else:
            self._content.rebuild()

    def _subscribe(self) -> None:
        """Subscribe to selection and row invalidation before the first model read."""
        model = self._model
        if model is None or self._selection_sub is not None:
            return
        self._selection_sub = model.subscribe_selection_changed(self._selection_changed)
        self._item_changed_sub = model.subscribe_item_changed_fn(self._item_changed)
        self._progress_changed_sub = model.subscribe_progress_changed(self._progress_changed)

    def _unsubscribe(self) -> None:
        """Release process-local subscriptions."""
        self._selection_sub = None
        self._item_changed_sub = None
        self._progress_changed_sub = None

    def _sync_selection_from_model(self) -> None:
        """Read selection after subscriptions are active so no update is missed."""
        selected = self._model.selected_items if self._model is not None else []
        self._selection_changed(selected)

    def _selection_changed(self, items: list[QueueGraphItem | QueueItem]) -> None:
        """Render exactly one selected graph or job.

        Args:
            items: Current model-owned selection.
        """
        self._selected_item = items[0] if len(items) == 1 else None
        self._content.rebuild()

    def _item_changed(self, _model: QueueModel, item) -> None:
        """Refresh details for a selected row, its parent, or a structural change.

        Args:
            _model: Model that emitted the change.
            item: Changed tree item, or None for a structural invalidation.
        """
        selected_parent = self._selected_item.parent if isinstance(self._selected_item, QueueItem) else None
        changed_parent = item.parent if isinstance(item, QueueItem) else None
        if (
            item is None
            or item is self._selected_item
            or selected_parent is item
            or changed_parent is self._selected_item
        ):
            self._content.rebuild()

    def _progress_changed(self, items: tuple[QueueItem, ...]) -> None:
        """Update selected progress labels once for a UI-frame batch.

        Args:
            items: Existing child items whose progress changed.
        """
        if self._model is None:
            return
        if isinstance(self._selected_item, QueueGraphItem) and any(
            item.parent is self._selected_item for item in items
        ):
            graph = self._selected_item
            status = self._model.get_graph_status_label(graph)
            tooltip = self._model.get_graph_state_tooltip(graph)
            if self._header_summary_label is not None:
                self._header_summary_label.text = status
                self._header_summary_label.tooltip = tooltip
            if self._overview_status_label is not None:
                self._overview_status_label.text = status
                self._overview_status_label.tooltip = tooltip
            if self._overview_progress_label is not None:
                progress_rows = [
                    child.row.progress
                    for child in graph.children
                    if child.row.progress is not None
                    and child.row.progress.completed is not None
                    and child.row.progress.total is not None
                ]
                progress_completed = sum(progress.completed or 0 for progress in progress_rows)
                progress_total = sum(progress.total or 0 for progress in progress_rows)
                self._overview_progress_label.text = (
                    f"{progress_completed} of {progress_total}" if progress_total else "In progress"
                )
            return
        if not isinstance(self._selected_item, QueueItem) or self._selected_item not in items:
            return
        row = self._selected_item.row
        state = self._model.resolve_display_state(row)
        status = self._model.get_status_label(row, state)
        tooltip = self._model.get_state_tooltip(row, state)
        if self._header_summary_label is not None:
            self._header_summary_label.text = status
            self._header_summary_label.tooltip = status
        if self._overview_status_label is not None:
            self._overview_status_label.text = status
            self._overview_status_label.tooltip = tooltip
        if self._overview_progress_label is not None:
            progress = row.progress
            active_label = self._model.get_active_progress_label(row)
            count = (
                f"{progress.completed} of {progress.total}"
                if progress is not None and progress.completed is not None and progress.total is not None
                else None
            )
            self._overview_progress_label.text = active_label or count or "In progress"

    def _build_content(self) -> None:
        """Build the current empty, graph, or job state."""
        self._destroy_sections()
        self._log_text = ""
        self._header_summary_label = None
        self._overview_status_label = None
        self._overview_progress_label = None
        with ui.ZStack():
            ui.Rectangle(name="QueueDetailBackground")
            if self._selected_item is None:
                self._build_empty()
            elif isinstance(self._selected_item, QueueGraphItem):
                self._build_graph_details(self._selected_item)
            else:
                self._build_job_details(self._selected_item)

    @staticmethod
    def _build_empty() -> None:
        """Build the no-selection guidance."""
        with ui.HStack(spacing=PADDING_MEDIUM):
            ui.Spacer(width=0)
            with ui.VStack():
                ui.Spacer()
                with ui.HStack(height=EMPTY_STATE_ICON_SIZE):
                    ui.Spacer()
                    ui.Image(
                        "",
                        name="QueueDetailEmpty",
                        identifier="queue_detail_empty_icon",
                        width=EMPTY_STATE_ICON_SIZE,
                        height=EMPTY_STATE_ICON_SIZE,
                    )
                    ui.Spacer()
                ui.Spacer(height=PADDING_MEDIUM)
                ui.Label(
                    "Select a graph or job to view details",
                    name="QueueDetailEmptyLabel",
                    identifier="queue_detail_empty_title",
                    alignment=ui.Alignment.CENTER,
                    height=0,
                    word_wrap=True,
                )
                ui.Spacer(height=PADDING_SMALL)
                ui.Label(
                    "Progress, topology, values, logs, and actions will appear here",
                    name="QueueDetailEmptySubLabel",
                    identifier="queue_detail_empty_subtitle",
                    alignment=ui.Alignment.CENTER,
                    height=0,
                    word_wrap=True,
                )
                ui.Spacer()
            ui.Spacer(width=0)

    def _build_graph_details(self, graph: QueueGraphItem) -> None:
        """Build aggregate state, topology, failures, and child navigation.

        Args:
            graph: Selected graph root.
        """
        assert self._model is not None
        model = self._model
        child_states = [(child, model.resolve_display_state(child.row)) for child in graph.children]
        counts: dict[DisplayState, int] = {}
        for _child, state in child_states:
            counts[state] = counts.get(state, 0) + 1
        finished = sum(child.row.state in TERMINAL_JOB_STATES for child in graph.children)
        progress_rows = [
            child.row.progress
            for child in graph.children
            if child.row.progress is not None
            and child.row.progress.completed is not None
            and child.row.progress.total is not None
        ]
        progress_completed = sum(progress.completed or 0 for progress in progress_rows)
        progress_total = sum(progress.total or 0 for progress in progress_rows)
        started_values = [child.row.started_at for child in graph.children if child.row.started_at is not None]
        completed_values = [child.row.completed_at for child in graph.children if child.row.completed_at is not None]
        with self._details_scroller("graph_details_scroll"):
            self._build_graph_header(graph, finished)
            with self._section("Overview", "graph_details_overview"):
                self._overview_status_label = self._field(
                    "Status", model.get_graph_status_label(graph), model.get_graph_state_tooltip(graph)
                )
                self._field("Jobs", f"{finished} of {len(graph.children)} finished")
                if progress_total or any(state is DisplayState.IN_PROGRESS for _child, state in child_states):
                    self._overview_progress_label = self._field(
                        "Progress",
                        f"{progress_completed} of {progress_total}" if progress_total else "In progress",
                        identifier="graph_details_progress",
                    )
                self._field(
                    "Submitted",
                    self._format_timestamp(min((child.row.submitted_at for child in graph.children), default=None)),
                )
                if started_values:
                    self._field("Started", self._format_timestamp(min(started_values)))
                if completed_values and len(completed_values) == len(graph.children):
                    self._field("Completed", self._format_timestamp(max(completed_values)))

            with self._section("Jobs", "graph_details_jobs"):
                visible_children = set(model.get_item_children(graph))
                for child, state in child_states:
                    if child not in visible_children:
                        continue
                    button = ui.Button(
                        f"{child.row.name}  -  {model.get_status_label(child.row, state)}",
                        name="QueueDetailChild",
                        identifier=f"details_job_{child.row.job_id}",
                        alignment=ui.Alignment.LEFT_CENTER,
                        height=ROW_HEIGHT,
                    )
                    button.set_clicked_fn(lambda _job_id=child.row.job_id: self._navigate_to_child(_job_id))

            with self._section("Status breakdown", "graph_details_status"):
                for label, count in self._format_state_counts(counts):
                    self._field(label, str(count))

            problems = [
                (child.row.name, model.get_state_tooltip(child.row, state))
                for child, state in child_states
                if state in PROBLEM_DISPLAY_STATES
            ]
            if problems:
                with self._section("Problems", "graph_details_problems"):
                    for name, problem in problems:
                        self._field(name, problem)

            self._build_graph_topology(graph)
            graph_id = str(graph.graph_id)
            with self._section(
                "Technical details",
                "graph_details_technical",
                header_actions_fn=partial(
                    self._build_copy_section_action,
                    "graph_details_copy_technical",
                    "Copy graph technical details to the clipboard",
                    f"Graph ID: {graph_id}",
                ),
            ):
                self._field("Graph ID", graph_id)

    def _build_graph_topology(self, graph: QueueGraphItem) -> None:
        """Render unique data and control edges exposed by targeted detail reads.

        Args:
            graph: Graph whose child details provide the edges.
        """
        assert self._model is not None
        names = {child.row.job_id: child.row.name for child in graph.children}
        data_edges: set[tuple[uuid.UUID, str, uuid.UUID, str]] = set()
        control_edges: set[tuple[uuid.UUID, uuid.UUID]] = set()
        for child in graph.children:
            details = self._load_details(child.row.job_id, include_values=False)
            if details is None:
                continue
            data_edges.update(
                (edge.source_job_id, edge.source_port.name, edge.target_job_id, edge.target_port.name)
                for edge in details.connections
            )
            control_edges.update((edge.prerequisite_job_id, edge.target_job_id) for edge in details.control_edges)
        if not data_edges and not control_edges:
            return
        with self._section("Topology", "graph_details_topology"):
            for source, source_port, target, target_port in sorted(data_edges, key=lambda edge: tuple(map(str, edge))):
                self._topology_row(
                    f"{names.get(source, str(source))} · {source_port}",
                    f"{names.get(target, str(target))} · {target_port}",
                )
            for source, target in sorted(control_edges, key=lambda edge: tuple(map(str, edge))):
                self._topology_row(names.get(source, str(source)), names.get(target, str(target)), "Runs before")

    def _build_job_details(self, item: QueueItem) -> None:
        """Build one selected job from a targeted typed details snapshot.

        Args:
            item: Selected child item.
        """
        assert self._model is not None
        model = self._model
        row = item.row
        state = model.resolve_display_state(row)
        details = self._load_details(row.job_id, include_values=True)
        product_sections = (
            adapter_interaction.get_detail_sections(row, details, model.context_name) if details is not None else ()
        )
        logs = self._get_combined_logs(row.job_id)
        self._log_text = "\n".join(
            message if timestamp is None else f"[{timestamp.strftime('%Y-%m-%dT%H:%M:%S.%f')}] {message}"
            for timestamp, message, _stream in logs
        )
        with self._details_scroller("job_details_scroll"):
            self._build_job_header(item, state)
            with self._section("Overview", "job_details_overview"):
                self._overview_status_label = self._field(
                    "Status", model.get_status_label(row, state), model.get_state_tooltip(row, state)
                )
                if row.progress is not None or state is DisplayState.IN_PROGRESS:
                    active_label = model.get_active_progress_label(row)
                    count = (
                        f"{row.progress.completed} of {row.progress.total}"
                        if row.progress is not None
                        and row.progress.completed is not None
                        and row.progress.total is not None
                        else None
                    )
                    self._overview_progress_label = self._field(
                        "Progress", active_label or count or "In progress", identifier="job_details_progress"
                    )
                self._field("Source", row.source)
                self._field("Submitted", self._format_timestamp(row.submitted_at))
                if row.started_at is not None:
                    self._field("Started", self._format_timestamp(row.started_at))
                if row.completed_at is not None:
                    self._field("Completed", self._format_timestamp(row.completed_at))

            self._build_logs(row.job_id, logs)

            status_explanation = model.get_state_tooltip(row, state)
            if state in PROBLEM_DISPLAY_STATES and status_explanation:
                with self._section("Status details", "job_details_status_details"):
                    ui.Label(status_explanation, name="QueueDetailValue", height=0, word_wrap=True)

            self._build_product_sections(product_sections, JobDetailSectionPlacement.BEFORE_INPUTS)
            if details is not None:
                directories = adapter_interaction.get_detail_directories(row, details, model.context_name)
                self._build_ports_and_values(details, directories)
                self._build_product_sections(product_sections, JobDetailSectionPlacement.AFTER_OUTPUTS)
                self._build_job_topology(details, item.parent)
            self._build_technical_details(item)

    def _build_product_sections(
        self,
        sections: Sequence[JobDetailSection],
        placement: JobDetailSectionPlacement,
    ) -> None:
        """Build product-owned sections at their declared generic-layout boundary.

        Args:
            sections: Safe product sections returned by the exact job adapter.
            placement: Relative generic-port boundary rendered by this pass.
        """
        for section in sections:
            if section.placement is not placement:
                continue
            with self._section(
                section.title,
                f"job_details_product_{section.section_id}",
                directory=section.directory,
                directory_identifier=f"job_details_open_product_{section.section_id}_directory",
            ):
                for field in section.fields:
                    self._field(field.label, field.value, field.tooltip)

    def _build_ports_and_values(
        self,
        details: QueueJobDetailsSnapshot,
        directories: JobDetailDirectories,
    ) -> None:
        """Build declared ports and optional typed input/output values.

        Args:
            details: Typed job details snapshot.
            directories: Explicit local directories represented by the typed values.
        """
        literal_values = {literal.port: literal.value for literal in details.literal_inputs}
        input_values: Mapping[Any, Any] = details.inputs or {}
        output_values: Mapping[Any, Any] = details.outputs or {}
        with self._section(
            "Inputs",
            "job_details_inputs",
            directory=directories.input_directory,
            directory_identifier="job_details_open_input_directory",
        ):
            if not details.input_ports:
                ui.Label("No inputs", name="QueueDetailMessage", height=0, word_wrap=True)
            else:
                self._build_detail_value_tree(
                    "job_details_inputs_tree",
                    [
                        (
                            port.name,
                            port.value_type.__name__,
                            input_values.get(port, literal_values.get(port, MISSING_VALUE)),
                        )
                        for port in details.input_ports
                    ],
                )
        with self._section(
            "Outputs",
            "job_details_outputs",
            directory=directories.output_directory,
            directory_identifier="job_details_open_output_directory",
        ):
            if not details.output_ports:
                ui.Label("No outputs", name="QueueDetailMessage", height=0, word_wrap=True)
            else:
                self._build_detail_value_tree(
                    "job_details_outputs_tree",
                    [
                        (port.name, port.value_type.__name__, output_values.get(port, MISSING_VALUE))
                        for port in details.output_ports
                    ],
                )

    def _build_detail_value_tree(self, identifier: str, values: Sequence[tuple[str, str, Any]]) -> None:
        """Build one responsive native tree for typed input or output values.

        Args:
            identifier: Stable E2E identifier for the tree and its cells.
            values: Port name, declared type name, and persisted value tuples.
        """
        # The tree owns its model and delegate, so the panel must outlive the native widget it mounts.
        self._value_trees.append(DetailValueTree(values, identifier, self._KEY_WIDTH))

    def _build_job_topology(self, details: QueueJobDetailsSnapshot, graph: QueueGraphItem | None) -> None:
        """Build incoming/outgoing data edges and control prerequisites.

        Args:
            details: Typed job details snapshot.
            graph: Owning graph used to resolve readable child names.
        """
        if not details.connections and not details.control_edges:
            return
        names = {child.row.job_id: child.row.name for child in graph.children} if graph is not None else {}
        with self._section("Topology", "job_details_topology"):
            for edge in details.connections:
                self._topology_row(
                    f"{names.get(edge.source_job_id, str(edge.source_job_id))} · {edge.source_port.name}",
                    f"{names.get(edge.target_job_id, str(edge.target_job_id))} · {edge.target_port.name}",
                )
            for edge in details.control_edges:
                self._topology_row(
                    names.get(edge.prerequisite_job_id, str(edge.prerequisite_job_id)),
                    names.get(edge.target_job_id, str(edge.target_job_id)),
                    "Runs before",
                )

    def _build_logs(
        self,
        job_id: uuid.UUID,
        logs: list[tuple[datetime.datetime | None, str, LogStream]],
    ) -> None:
        """Build a compact severity-aware viewer for queue-owned logs.

        Args:
            job_id: Stable job identifier used by the section action.
            logs: Chronological timestamps, messages, and source streams.
        """
        with self._section(
            "Logs",
            "job_details_logs",
            header_actions_fn=partial(
                self._build_copy_section_action,
                f"details_copy_logs_{job_id}",
                "Copy logs to the clipboard" if logs else "No logs are available to copy.",
                self._log_text,
            ),
        ):
            if not logs:
                ui.Label("No logs available", name="QueueDetailMessage", height=0, word_wrap=True)
                return
            with ui.ZStack(height=self._LOG_VIEWER_HEIGHT):
                ui.Rectangle(name="QueueLogBackground")
                with ui.ScrollingFrame(
                    name="QueueLogViewer",
                    identifier="job_details_log_viewer",
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                ):
                    with ui.HStack(height=0, spacing=PADDING_MEDIUM):
                        ui.Spacer(width=0)
                        with ui.VStack(height=0, spacing=PADDING_SMALL):
                            ui.Spacer(height=0)
                            for timestamp, message, stream in logs:
                                with ui.HStack(height=0, spacing=PADDING_MEDIUM):
                                    ui.Label(
                                        timestamp.strftime("%H:%M:%S.%f")[:-3] if timestamp is not None else "—",
                                        name="QueueLogTimestamp",
                                        width=self._LOG_TIMESTAMP_WIDTH,
                                        height=0,
                                        style={"font": MONOSPACE_FONT_PATH},
                                        tooltip=self._format_timestamp(timestamp),
                                    )
                                    ui.Label(
                                        message,
                                        name=self._log_style_name(message, stream),
                                        height=0,
                                        style={"font": MONOSPACE_FONT_PATH},
                                        word_wrap=True,
                                    )
                            ui.Spacer(height=0)
                        ui.Spacer(width=0)

    def _build_graph_header(self, graph: QueueGraphItem, finished: int) -> None:
        """Build graph identity, aggregate state, and graph-owned actions.

        Args:
            graph: Selected graph root.
            finished: Number of terminal child jobs.
        """
        assert self._model is not None
        actions = [
            (child, action)
            for child in graph.children
            for action in adapter_interaction.get_graph_actions(child.row, self._model.context_name)
        ]
        self._header(
            "JOB GRAPH",
            graph.name,
            f"{len(graph.children)} stages",
            f"{self._model.get_graph_status_label(graph)} · {finished} of {len(graph.children)} finished",
            "graph_details_title",
            "graph_details_summary",
            "graph_details_primary_actions",
            partial(self._build_graph_header_actions, graph, actions) if actions else None,
            len(actions),
        )

    def _build_graph_header_actions(
        self,
        graph: QueueGraphItem,
        actions: Sequence[tuple[QueueItem, JobAction]],
    ) -> None:
        """Build graph-owned actions beside the ellipsized graph title.

        Args:
            graph: Graph whose stable ID identifies the action widgets.
            actions: Ordered contributing child/action pairs.
        """
        assert self._model is not None
        for child, action in actions:
            self._action_icon(
                action.style_name,
                f"details_{action.action_id}_graph_{graph.graph_id}_job_{child.row.job_id}",
                action.tooltip,
                action.enabled,
                lambda _row=child.row, _action_id=action.action_id: adapter_interaction.execute_action(
                    _row, _action_id, self._model.context_name
                ),
            )

    def _build_job_header(self, item: QueueItem, state: DisplayState) -> None:
        """Build job identity, current state, progress, and common actions.

        Args:
            item: Selected child job.
            state: Resolved user-facing state.
        """
        assert self._model is not None
        row = item.row
        child_count = len(item.parent.children) if item.parent is not None else 1
        summary = self._model.get_status_label(row, state)
        self._header(
            "JOB STAGE",
            row.name,
            f"{row.graph_name} · Stage {row.position + 1} of {child_count}",
            summary,
            "job_details_title",
            "job_details_summary",
            "job_details_primary_actions",
            None,
            0,
        )

    @staticmethod
    def _action_icon(
        style_name: str,
        identifier: str,
        tooltip: str,
        enabled: bool,
        callback: Callable[[], None],
    ) -> None:
        """Build one compact native icon action.

        Args:
            style_name: Registered image style that supplies the icon and state colors.
            identifier: Stable UI-test identifier.
            tooltip: User-facing explanation of the action or disabled state.
            enabled: Whether the action accepts input.
            callback: Action invoked by a primary-button press.
        """
        image = ui.Image(
            "",
            name=style_name,
            identifier=identifier,
            width=ICON_SIZE_MEDIUM,
            height=ICON_SIZE_MEDIUM,
            enabled=enabled,
            tooltip=tooltip,
        )
        if enabled:
            image.set_mouse_pressed_fn(lambda _x, _y, button, _modifiers: callback() if button == 0 else None)

    def _build_technical_details(self, item: QueueItem) -> None:
        """Build identifiers, concrete type, and durable diagnostics last.

        Args:
            item: Selected child item.
        """
        diagnostics = (("Execution", item.row.error), ("Apply", item.row.apply_error))
        diagnostics = tuple((label, error) for label, error in diagnostics if error is not None)
        job_id = str(item.row.job_id)
        graph_id = str(item.row.graph_id)
        technical_lines = [f"Job type: {item.row.job_type}", f"Job ID: {job_id}", f"Graph ID: {graph_id}"]
        for label, error in diagnostics:
            technical_lines.extend(
                (f"{label} error: {error.message}", f"{label} error type: {error.exception_type}", error.traceback)
            )
        with self._section(
            "Technical details",
            "job_details_technical",
            header_actions_fn=partial(
                self._build_copy_section_action,
                f"job_details_copy_technical_{item.row.job_id}",
                "Copy job technical details to the clipboard",
                "\n".join(technical_lines),
            ),
        ):
            self._field("Job type", item.row.job_type)
            self._field("Job ID", job_id.replace("-", "-\u200b"), job_id)
            self._field("Graph ID", graph_id.replace("-", "-\u200b"), graph_id)
            for label, error in diagnostics:
                self._field(f"{label} error", error.message)
                self._field(f"{label} error type", error.exception_type)
                with ui.ZStack(height=0):
                    ui.Rectangle(name="QueueLogBackground")
                    with ui.HStack(height=0, spacing=PADDING_MEDIUM):
                        ui.Spacer(width=0)
                        ui.Label(
                            error.traceback,
                            name="QueueDetailTechnical",
                            height=0,
                            style={"font": MONOSPACE_FONT_PATH},
                            word_wrap=True,
                        )
                        ui.Spacer(width=0)

    def _load_details(self, job_id: uuid.UUID, include_values: bool) -> QueueJobDetailsSnapshot | None:
        """Load the public typed details snapshot with a resilient empty fallback.

        Args:
            job_id: Job to load.
            include_values: Whether available persisted typed values are requested.

        Returns:
            Typed details, or None when the job cannot be loaded.
        """
        if self._model is None:
            return None
        try:
            return self._model.interface.get_job_details(job_id, include_values=include_values)
        except JOB_LOAD_ERRORS as error:
            carb.log_warn(f"Could not load details for queue job {job_id}: {error}")
            return None

    def _get_combined_logs(self, job_id: uuid.UUID) -> list[tuple[datetime.datetime | None, str, LogStream]]:
        """Merge queue-owned stdout and stderr log lines chronologically.

        Args:
            job_id: Job whose logs should be read.

        Returns:
            Chronological line and stream pairs.
        """
        assert self._model is not None
        lines: list[tuple[datetime.datetime | None, str, LogStream]] = []
        for filename, stream in (("stdout.log", LogStream.STDOUT), ("stderr.log", LogStream.STDERR)):
            path = self._model.interface.get_job_directory(job_id) / "logs" / filename
            if not path.exists():
                continue
            try:
                file_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError as error:
                carb.log_warn(f"Could not read queue job log {path}: {error}")
                continue
            for line in file_lines:
                if line.strip():
                    lines.append((*self._parse_log_line(line), stream))
        lines.sort(key=lambda entry: (entry[0] is None, entry[0] or datetime.datetime.min))
        return lines

    @staticmethod
    def _parse_log_line(line: str) -> tuple[datetime.datetime | None, str]:
        """Parse an optional persisted log timestamp.

        Args:
            line: Raw persisted log line.

        Returns:
            Parsed timestamp, when present, and message without its timestamp prefix.
        """
        match = LOG_TIMESTAMP_PATTERN.match(line)
        if match is None:
            return None, line.rstrip()
        try:
            timestamp = datetime.datetime.strptime(match.group("ts"), "%Y-%m-%dT%H:%M:%S.%f")
            return timestamp, line[match.end() :].lstrip().rstrip()
        except ValueError:
            return None, line.rstrip()

    @staticmethod
    def _open_directory(path: pathlib.Path) -> None:
        """Open an existing local directory in the operating-system file browser.

        Args:
            path: Directory to open.
        """
        if path.is_dir():
            open_file_using_os_default(str(path), highlight=False)

    def _navigate_to_child(self, job_id: uuid.UUID) -> None:
        """Reveal one child through the model-owned navigation event.

        Args:
            job_id: Child job to reveal when it matches current filters.
        """
        if self._model is not None:
            self._model.reveal_item(job_id)

    @staticmethod
    def _format_state_counts(counts: Mapping[DisplayState, int]) -> tuple[tuple[str, int], ...]:
        """Merge state counts that share the same user-facing label.

        Args:
            counts: Resolved display-state counts in presentation order.

        Returns:
            Nonzero label-count pairs in first-seen order.
        """
        label_counts: dict[str, int] = {}
        for state, count in counts.items():
            if count:
                label_counts[state.label] = label_counts.get(state.label, 0) + count
        return tuple(label_counts.items())

    @contextlib.contextmanager
    def _details_scroller(self, identifier: str) -> Iterator[None]:
        """Build one padded intrinsic-height details document.

        Args:
            identifier: Stable UI-test identifier for the scrolling frame.

        Yields:
            Context in which the ordered detail sections are built.
        """
        with ui.ScrollingFrame(
            name="PropertiesPaneSection",
            identifier=identifier,
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
        ):
            with ui.HStack(height=0, spacing=PADDING_LARGE):
                ui.Spacer(width=0)
                with ui.VStack(height=0, spacing=PADDING_LARGE):
                    ui.Spacer(height=0)
                    yield
                    ui.Spacer(height=0)
                ui.Spacer(width=0)

    def _header(
        self,
        eyebrow: str,
        title: str,
        metadata: str,
        summary: str,
        title_identifier: str,
        summary_identifier: str,
        actions_identifier: str,
        actions_fn: Callable[[], None] | None,
        action_count: int,
    ) -> None:
        """Build a fixed-height identity header with optional title-row actions.

        Args:
            eyebrow: Short uppercase content category.
            title: Primary graph or job identity.
            metadata: Owning graph and position context.
            summary: Current status and progress summary.
            title_identifier: Stable title lookup identifier.
            summary_identifier: Stable summary lookup identifier.
            actions_identifier: Stable actions lookup identifier.
            actions_fn: Optional graph-owned action builder beside the title.
            action_count: Number of compact actions built beside the title.
        """
        with ui.ZStack(height=self._HEADER_HEIGHT):
            ui.Rectangle(name="QueueDetailHeaderBackground")
            with ui.HStack(height=0, spacing=PADDING_LARGE):
                ui.Spacer(width=0)
                with ui.VStack(height=0, spacing=PADDING_SMALL):
                    ui.Spacer(height=PADDING_SMALL)
                    with ui.HStack(height=ICON_SIZE_MEDIUM, spacing=PADDING_SMALL):
                        ui.Label(
                            title,
                            name="QueueDetailTitle",
                            identifier=title_identifier,
                            height=ICON_SIZE_MEDIUM,
                            elided_text=True,
                            tooltip=title,
                        )
                        if actions_fn is not None:
                            actions_width = (action_count * ICON_SIZE_MEDIUM.value) + (
                                max(0, action_count - 1) * PADDING_SMALL.value
                            )
                            with ui.Frame(
                                width=ui.Pixel(actions_width),
                                height=ICON_SIZE_MEDIUM,
                                identifier=actions_identifier,
                            ):
                                with ui.HStack(height=ICON_SIZE_MEDIUM, spacing=PADDING_SMALL):
                                    actions_fn()
                    identity = f"{eyebrow} · {metadata}"
                    ui.Label(identity, name="QueueDetailMeta", height=0, elided_text=True, tooltip=identity)
                    self._header_summary_label = ui.Label(
                        summary,
                        name="QueueDetailSummary",
                        identifier=summary_identifier,
                        height=0,
                        elided_text=True,
                        tooltip=summary,
                    )
                    ui.Spacer(height=0)
                ui.Spacer(width=0)

    @contextlib.contextmanager
    def _section(
        self,
        title: str,
        identifier: str | None = None,
        directory: pathlib.Path | None = None,
        directory_identifier: str | None = None,
        header_actions_fn: Callable[[], None] | None = None,
    ) -> Iterator[None]:
        """Build one native collapsible details section.

        Args:
            title: User-facing section heading.
            identifier: Optional stable UI-test identifier for the section frame.
            directory: Optional local directory represented by this section.
            directory_identifier: Stable identifier for the directory action.
            header_actions_fn: Optional builder for a non-directory section action.

        Yields:
            Context in which the section content is built.
        """
        section_key = identifier or title
        frame_args = {"identifier": identifier} if identifier is not None else {}
        with ui.Frame(height=0, **frame_args):
            if directory is not None and directory_identifier is not None:
                if header_actions_fn is not None:
                    raise ValueError("A detail section cannot define multiple header action builders")
                header_actions_fn = partial(
                    self._build_section_directory_action, title, directory, directory_identifier
                )
            section = PropertyCollapsableFrame(
                title,
                collapsed=self._collapsed_sections.get(section_key, False),
                header_actions_fn=header_actions_fn,
            )
            section.root.set_collapsed_changed_fn(
                lambda collapsed, _section_key=section_key: self._set_section_collapsed(_section_key, collapsed)
            )
            self._sections.append(section)
            with section:
                with ui.ZStack(height=0):
                    ui.Rectangle(name="QueueDetailSectionBackground")
                    with ui.HStack(height=0, spacing=PADDING_MEDIUM):
                        ui.Spacer(width=0)
                        with ui.VStack(height=0, spacing=PADDING_SMALL):
                            ui.Spacer(height=PADDING_MEDIUM)
                            yield
                            ui.Spacer(height=PADDING_MEDIUM)
                        ui.Spacer(width=0)

    def _build_section_directory_action(
        self,
        title: str,
        directory: pathlib.Path,
        identifier: str,
    ) -> None:
        """Build one folder action in the native section header.

        Args:
            title: User-facing section name used by the tooltip.
            directory: Local directory represented by the section.
            identifier: Stable UI-test identifier for the action.
        """
        available = directory.is_dir()
        self._build_section_action(
            "OpenFolder",
            identifier,
            f"Open the folder containing this job's {title.lower()}"
            if available
            else f"This job's {title.lower()} folder is not available.",
            available,
            lambda: self._open_directory(directory),
        )

    def _build_copy_section_action(self, identifier: str, tooltip: str, text: str) -> None:
        """Build a section-owned clipboard action.

        Args:
            identifier: Stable UI-test identifier for the action.
            tooltip: User-facing description or disabled explanation.
            text: Complete section text copied when non-empty.
        """
        self._build_section_action(
            "CopyToClipboard",
            identifier,
            tooltip,
            bool(text),
            lambda: omni.kit.clipboard.copy(text),
        )

    def _build_section_action(
        self,
        style_name: str,
        identifier: str,
        tooltip: str,
        enabled: bool,
        callback: Callable[[], None],
    ) -> None:
        """Align one compact action inside a native collapsible-section header.

        Args:
            style_name: Registered icon style.
            identifier: Stable UI-test identifier for the action.
            tooltip: User-facing description or disabled explanation.
            enabled: Whether the action accepts input.
            callback: Action invoked by a primary-button press.
        """
        ui.Spacer()
        with ui.VStack(width=ICON_SIZE_MEDIUM, content_clipping=True):
            ui.Spacer()
            self._action_icon(style_name, identifier, tooltip, enabled, callback)
            ui.Spacer()
        ui.Spacer(width=PADDING_SMALL)

    def _set_section_collapsed(self, section_key: str, collapsed: bool) -> None:
        """Retain a section's native collapse state across live detail refreshes.

        Args:
            section_key: Stable section identifier or title.
            collapsed: Current native frame state.
        """
        self._collapsed_sections[section_key] = collapsed

    def _destroy_sections(self) -> None:
        """Release native collapsible-frame callbacks before rebuilding details."""
        for section in self._sections:
            section.root.set_collapsed_changed_fn(None)
            section.destroy()
        self._sections.clear()
        self._value_trees.clear()

    def _field(
        self,
        label: str,
        value: str,
        tooltip: str = "",
        identifier: str = "",
    ) -> ui.Label:
        """Build one aligned key/value table row.

        Args:
            label: User-facing field name.
            value: Readable field value.
            tooltip: Optional explanation shared by the field name and value.
            identifier: Optional stable identifier for the mutable value label.

        Returns:
            Mutable value label for targeted live updates.
        """
        with ui.HStack(height=0, spacing=PADDING_MEDIUM):
            ui.Label(
                label,
                name="QueueDetailKey",
                width=JobDetailsPanel._KEY_WIDTH,
                height=0,
                elided_text=True,
                tooltip=f"{label}\n{tooltip}" if tooltip else label,
            )
            return ui.Label(
                value,
                name="QueueDetailValue",
                height=0,
                tooltip=tooltip,
                word_wrap=True,
                identifier=identifier,
            )

    @staticmethod
    def _topology_row(source: str, target: str, relationship: str = "Provides data to") -> None:
        """Build one readable directed graph relationship.

        Args:
            source: Readable producer or prerequisite name.
            target: Readable consumer or dependent name.
            relationship: User-facing description of the directed edge.
        """
        with ui.VStack(height=0, spacing=PADDING_SMALL):
            ui.Label(source, name="QueueDetailTopologyJob", height=0, word_wrap=True)
            ui.Label(relationship, name="QueueDetailMeta", height=0)
            ui.Label(target, name="QueueDetailTopologyJob", height=0, word_wrap=True)

    @staticmethod
    def _format_timestamp(value: datetime.datetime | None) -> str:
        """Format an optional absolute queue timestamp.

        Args:
            value: Timestamp to format.

        Returns:
            Absolute timestamp or an unavailable label.
        """
        return value.strftime(ABSOLUTE_TIMESTAMP_FORMAT) if value is not None else "Not available"

    @staticmethod
    def _log_style_name(message: str, stream: LogStream) -> str:
        """Resolve severity styling from explicit log text and stream.

        Args:
            message: Log message without its timestamp prefix.
            stream: Persisted source stream.

        Returns:
            Registered label style for the resolved severity.
        """
        severity = message.lstrip().lower()
        if severity.startswith(("warning", "warn:", "[warning]", "[warn]")):
            return "QueueLogWarning"
        if stream is LogStream.STDERR or severity.startswith(("error", "fatal", "[error]", "[fatal]")):
            return "QueueLogError"
        return "QueueLogStdout"

    def destroy(self) -> None:
        """Release subscriptions and references before destroying the UI frame."""
        if self._destroyed:
            return
        self._destroyed = True
        self._visible = False
        self._unsubscribe()
        self._destroy_sections()
        self._model = None
        self._selected_item = None
        super().destroy()

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

import datetime
import uuid
from collections.abc import Callable

from omni import ui
from omni.flux.job_queue.core.enums import ApplyDisposition, TimestampMode
from omni.flux.job_queue.core.settings import JobQueueSettings
from omni.flux.utils.widget.tree_widget.delegate import TreeDelegateBase

from . import adapter_interaction
from .constants import (
    ABSOLUTE_TIMESTAMP_FORMAT,
    BRANCH_COLUMN_WIDTH,
    BRANCH_ICON_SIZE,
    ICON_SIZE_MEDIUM,
    ICON_SIZE_SMALL,
    PADDING_MEDIUM,
    PADDING_SMALL,
    RELATIVE_TIME_THRESHOLDS,
    ROW_HEIGHT,
    STATUS_PILL_HEIGHT,
)
from .enums import ColumnKey, DisplayState
from .model import QueueModel
from .queue_item import QueueGraphItem, QueueItem
from .row import Row

__all__ = ("QueueItemDelegate",)


class QueueItemDelegate(TreeDelegateBase):
    """Render graph roots and typed job children in five compact columns."""

    _BRANCH_RAIL_WIDTH = ui.Pixel(44)

    def __init__(
        self,
        model: QueueModel,
        settings: JobQueueSettings,
        on_delete_graph: Callable[[QueueGraphItem], None] | None = None,
        on_revert_item: Callable[[QueueItem], None] | None = None,
        on_bulk_x: Callable[[tuple[QueueItem, ...], str], None] | None = None,
    ) -> None:
        """Initialize the queue delegate and destructive-action callbacks.

        Args:
            model: Queue tree model.
            settings: Shared queue display preferences.
            on_delete_graph: Optional graph deletion confirmation callback.
            on_revert_item: Optional single Revert confirmation callback.
            on_bulk_x: Optional bulk X confirmation callback.
        """
        super().__init__()
        self.model = model
        self._settings = settings
        self._on_delete_graph = on_delete_graph
        self._on_revert_item = on_revert_item
        self._on_bulk_x = on_bulk_x
        self._job_status_labels: dict[uuid.UUID, ui.Label] = {}
        self._graph_status_labels: dict[uuid.UUID, ui.Label] = {}
        self._progress_subscription = model.subscribe_progress_changed(self._on_progress_changed)

    @property
    def default_attr(self) -> dict[str, None]:
        """Return attributes released by the delegate lifecycle.

        Returns:
            Default lifecycle attribute mapping.
        """
        return {
            **super().default_attr,
            "model": None,
            "_settings": None,
            "_on_delete_graph": None,
            "_on_revert_item": None,
            "_on_bulk_x": None,
            "_job_status_labels": None,
            "_graph_status_labels": None,
            "_progress_subscription": None,
        }

    def build_branch(self, model, item, column_id: int, _level: int, expanded: bool) -> None:
        """Build the graph drag handle before its expansion affordance.

        Args:
            model: Native tree model.
            item: Graph or child tree item.
            column_id: Visible column index.
            _level: Unused tree depth.
            expanded: Whether the graph is expanded.
        """
        if column_id != 0:
            return
        with ui.HStack(width=self._BRANCH_RAIL_WIDTH, height=ROW_HEIGHT, spacing=0):
            ui.Spacer(width=PADDING_MEDIUM)
            if isinstance(item, QueueGraphItem):
                with ui.VStack(width=ICON_SIZE_SMALL):
                    ui.Spacer()
                    drag_handle = ui.Image(
                        "",
                        name="DragHandle",
                        width=ICON_SIZE_SMALL,
                        height=ICON_SIZE_SMALL,
                        tooltip="Drag graph",
                        identifier=f"queue_graph_drag_handle_{item.graph_id}",
                    )
                    drag_handle.set_drag_fn(lambda: model.get_drag_mime_data(item))
                    ui.Spacer()
            else:
                ui.Spacer(width=ICON_SIZE_SMALL)
            ui.Spacer(width=PADDING_SMALL)
            if isinstance(item, QueueGraphItem) and model.can_item_have_children(item):
                with ui.Frame(
                    width=BRANCH_COLUMN_WIDTH,
                    mouse_released_fn=lambda _x, _y, button, _modifiers: self._item_expanded(
                        button, item, not expanded
                    ),
                ):
                    self._build_branch(model, item, column_id, _level, expanded)
            else:
                ui.Spacer(width=BRANCH_COLUMN_WIDTH)

    def _build_branch(self, _model, _item, _column_id: int, _level: int, expanded: bool) -> None:
        """Build the centered native TreeView expansion glyph.

        Args:
            _model: Unused native tree model.
            _item: Unused native tree item.
            _column_id: Unused branch column index.
            _level: Unused tree depth.
            expanded: Whether the graph is expanded.
        """
        style_name = "TreeView.Item.Minus" if expanded else "TreeView.Item.Plus"
        with ui.VStack(width=BRANCH_COLUMN_WIDTH, height=ROW_HEIGHT):
            ui.Spacer()
            ui.Image(
                "",
                width=BRANCH_ICON_SIZE,
                height=BRANCH_ICON_SIZE,
                style_type_name_override=style_name,
                identifier="queue_graph_branch",
            )
            ui.Spacer()

    def _build_widget(
        self,
        model: QueueModel,
        item: QueueGraphItem | QueueItem | None = None,
        column_id: int = 0,
        _level: int = 0,
        _expanded: bool = False,
    ) -> None:
        """Build one graph or child cell at a fixed row height.

        Args:
            model: Queue tree model.
            item: Graph or job item to render.
            column_id: Visible column index.
            _level: Unused native tree depth.
            _expanded: Unused native expansion state.
        """
        if item is None:
            return
        key = Row.keys()[column_id]
        item_kind = "graph" if isinstance(item, QueueGraphItem) else "job"
        item_id = item.graph_id if isinstance(item, QueueGraphItem) else item.row.job_id
        horizontal_padding = PADDING_SMALL if key is ColumnKey.JOB_STAGE else PADDING_MEDIUM
        with ui.Frame(height=ROW_HEIGHT, identifier=f"queue_{item_kind}_{item_id}_{key.value}"):
            with ui.HStack(height=ROW_HEIGHT, spacing=0):
                ui.Spacer(width=horizontal_padding)
                with ui.Frame(width=ui.Fraction(1)):
                    if isinstance(item, QueueGraphItem):
                        self._build_graph_cell(model, item, key)
                    else:
                        self._build_job_cell(model, item, key)
                ui.Spacer(width=horizontal_padding)

    def _build_graph_cell(self, model: QueueModel, graph: QueueGraphItem, key: ColumnKey) -> None:
        """Build one aggregate graph cell.

        Args:
            model: Queue tree model.
            graph: Graph root to render.
            key: Visible column key.
        """
        children = list(graph.children)
        visible = model.get_item_children(graph)
        if key is ColumnKey.JOB_STAGE:
            ui.Label(
                graph.name,
                name="CellLabel",
                height=ROW_HEIGHT,
                alignment=ui.Alignment.LEFT_CENTER,
                elided_text=True,
                tooltip=graph.name,
            )
        elif key is ColumnKey.STATUS:
            state = model.resolve_graph_display_state(graph)
            self._graph_status_labels[graph.graph_id] = self._build_status(
                model.get_graph_status_label(graph),
                state.status_style_name,
                model.get_graph_state_tooltip(graph),
                f"queue_graph_status_{graph.graph_id}",
            )
        elif key is ColumnKey.COMPLETED:
            completed_values = [child.row.completed_at for child in children if child.row.completed_at is not None]
            completed_at = max(completed_values) if children and len(completed_values) == len(children) else None
            self._build_completed(completed_at, f"queue_graph_completed_{graph.graph_id}")
        elif key is ColumnKey.APPLY:
            self._build_graph_apply(model, graph, visible)
        elif key is ColumnKey.ACTIONS:
            self._build_graph_actions(model, graph)

    def _build_job_cell(self, model: QueueModel, item: QueueItem, key: ColumnKey) -> None:
        """Build one typed child cell.

        Args:
            model: Queue tree model.
            item: Job child to render.
            key: Visible column key.
        """
        row = item.row
        if key is ColumnKey.JOB_STAGE:
            ui.Label(
                row.name,
                name="CellLabel",
                height=ROW_HEIGHT,
                alignment=ui.Alignment.LEFT_CENTER,
                elided_text=True,
                tooltip=model.get_name_tooltip(row),
                identifier=f"job_name_{row.job_id}",
            )
        elif key is ColumnKey.STATUS:
            state = model.resolve_display_state(row)
            self._job_status_labels[row.job_id] = self._build_status(
                model.get_status_label(row, state),
                state.status_style_name,
                model.get_state_tooltip(row, state),
                f"queue_job_status_{row.job_id}",
            )
        elif key is ColumnKey.COMPLETED:
            self._build_completed(row.completed_at, f"queue_job_completed_{row.job_id}")
        elif key is ColumnKey.APPLY:
            self._build_job_apply(model, item)
        elif key is ColumnKey.ACTIONS:
            self._build_job_actions(model, item)

    @staticmethod
    def _build_status(label: str, style_name: str, tooltip: str, identifier: str) -> ui.Label:
        """Build a centered status pill.

        Args:
            label: User-facing status text.
            style_name: Named status style.
            tooltip: Safe status explanation.
            identifier: Stable UI lookup identifier.

        Returns:
            Mutable label retained for progress-only text updates.
        """
        with ui.VStack():
            ui.Spacer()
            with ui.ZStack(height=STATUS_PILL_HEIGHT):
                ui.Rectangle(name=style_name, identifier=identifier)
                status_label = ui.Label(
                    label,
                    name="StatusLabel",
                    alignment=ui.Alignment.CENTER,
                    tooltip=tooltip,
                    identifier=f"{identifier}_label",
                )
            ui.Spacer()
        return status_label

    def _on_progress_changed(self, items: tuple[QueueItem, ...]) -> None:
        """Update existing status labels for one UI-frame progress batch.

        Args:
            items: Existing child items whose progress changed.
        """
        changed_parents: set[QueueGraphItem] = set()
        for item in items:
            row = item.row
            state = self.model.resolve_display_state(row)
            job_label = self._job_status_labels.get(row.job_id)
            if job_label is not None:
                job_label.text = self.model.get_status_label(row, state)
                job_label.tooltip = self.model.get_state_tooltip(row, state)
            if item.parent is not None:
                changed_parents.add(item.parent)

        for parent in changed_parents:
            graph_label = self._graph_status_labels.get(parent.graph_id)
            if graph_label is not None:
                graph_label.text = self.model.get_graph_status_label(parent)
                graph_label.tooltip = self.model.get_graph_state_tooltip(parent)

    def prune_status_widgets(self) -> None:
        """Release retained labels for rows removed by a structural synchronization."""
        job_ids = {item.row.job_id for item in self.model.all_items}
        graph_ids = {graph.graph_id for graph in self.model.all_graphs}
        self._job_status_labels = {
            job_id: label for job_id, label in self._job_status_labels.items() if job_id in job_ids
        }
        self._graph_status_labels = {
            graph_id: label for graph_id, label in self._graph_status_labels.items() if graph_id in graph_ids
        }

    @staticmethod
    def _format_relative_time(value: datetime.datetime) -> str:
        """Format one UTC SQLite timestamp as compact elapsed time.

        Args:
            value: Naive UTC completion timestamp from SQLite.

        Returns:
            Human-readable elapsed time.
        """
        delta = datetime.datetime.now(tz=datetime.UTC) - value.replace(tzinfo=datetime.UTC)
        total_minutes = int(delta.total_seconds() / 60)
        if total_minutes < 1:
            return "Just now"
        for maximum_minutes, divisor, unit in RELATIVE_TIME_THRESHOLDS:
            if maximum_minutes == 0 or total_minutes < maximum_minutes:
                count = total_minutes // divisor
                return f"{count} {unit}{'s' if count != 1 else ''} ago"
        return "Just now"

    def _build_completed(self, value: datetime.datetime | None, identifier: str) -> None:
        """Build one completion timestamp using the persistent display mode.

        Args:
            value: Execution completion timestamp, or None while unfinished.
            identifier: Stable UI-test identifier.
        """
        mode = self._settings.timestamp_mode
        text = ""
        tooltip = "Job has not completed."
        if value is not None:
            text = (
                self._format_relative_time(value)
                if mode is TimestampMode.RELATIVE
                else value.strftime(ABSOLUTE_TIMESTAMP_FORMAT)
            )
            next_mode = "absolute" if mode is TimestampMode.RELATIVE else "relative"
            tooltip = f"Completed {value.strftime(ABSOLUTE_TIMESTAMP_FORMAT)}. Click to show {next_mode} times."
        label = ui.Label(
            text,
            name="CellLabel",
            height=ROW_HEIGHT,
            alignment=ui.Alignment.LEFT_CENTER,
            elided_text=True,
            tooltip=tooltip,
            identifier=identifier,
        )
        if value is not None:
            label.set_mouse_pressed_fn(lambda _x, _y, button, _modifiers: self._toggle_timestamp_mode(button))

    def _toggle_timestamp_mode(self, button: int) -> None:
        """Toggle completion times after a left-click.

        Args:
            button: Native mouse button index.
        """
        if button != 0:
            return
        mode = self._settings.timestamp_mode
        self._settings.set_timestamp_mode(
            TimestampMode.ABSOLUTE if mode is TimestampMode.RELATIVE else TimestampMode.RELATIVE
        )

    def _build_graph_apply(self, model: QueueModel, graph: QueueGraphItem, visible: list[QueueItem]) -> None:
        """Build filter-scoped graph Apply and X controls.

        Args:
            model: Queue tree model.
            graph: Owning graph root.
            visible: Currently matching children captured by actions.
        """
        disposition = model.resolve_graph_apply_disposition(graph)
        graph_state = model.resolve_graph_display_state(graph)
        unavailable = graph_state in (DisplayState.CORRUPTED, DisplayState.HANDLER_UNAVAILABLE)
        check_block_reasons = tuple(
            (child, model.get_check_block_reason(child, allow_reapply=True)) for child in visible
        )
        x_block_reasons = tuple((child, model.get_x_block_reason(child)) for child in visible)
        can_check = not unavailable and any(reason is None for _child, reason in check_block_reasons)
        can_x = not unavailable and any(reason is None for _child, reason in x_block_reasons)
        scope = f'graph "{graph.name}" under current filters'
        check_tooltip = (
            "Reapply matching results" if disposition is ApplyDisposition.APPLIED else "Apply matching results"
        )
        if not can_check:
            check_tooltip = self._get_relevant_block_reason(
                check_block_reasons,
                (ApplyDisposition.PENDING, ApplyDisposition.DECLINED, ApplyDisposition.APPLIED),
                "No matching results are ready to apply.",
            )
        x_tooltip = (
            "Results are declined" if disposition is ApplyDisposition.DECLINED else "Decline or revert matching results"
        )
        if not can_x:
            x_tooltip = self._get_relevant_block_reason(
                x_block_reasons,
                (ApplyDisposition.PENDING, ApplyDisposition.APPLIED, ApplyDisposition.DECLINED),
                "No matching results can be declined or reverted.",
            )
        check_style = (
            "ApplyJobUnknown"
            if unavailable
            else ("ApplyJobActive" if disposition is ApplyDisposition.APPLIED else "ApplyJob")
        )
        x_style = (
            "DeclineJobUnknown"
            if unavailable
            else ("DeclineJobActive" if disposition is ApplyDisposition.DECLINED else "DeclineJob")
        )
        with ui.VStack():
            ui.Spacer()
            with ui.HStack(height=ICON_SIZE_MEDIUM, spacing=PADDING_SMALL):
                ui.Spacer()
                self._build_icon(
                    check_style,
                    f"apply_graph_{graph.graph_id}",
                    check_tooltip,
                    can_check,
                    lambda: model.apply_items(tuple(visible), scope),
                )
                self._build_icon(
                    x_style,
                    f"decline_graph_{graph.graph_id}",
                    x_tooltip,
                    can_x,
                    lambda: self._request_bulk_x(model, tuple(visible), scope),
                )
                ui.Spacer()
            ui.Spacer()

    def _request_bulk_x(self, model: QueueModel, items: tuple[QueueItem, ...], scope: str) -> None:
        """Route captured bulk X work through confirmation when available.

        Args:
            model: Queue tree model.
            items: Captured matching children.
            scope: User-facing filter scope.
        """
        if self._on_bulk_x is not None:
            self._on_bulk_x(items, scope)
        else:
            declines, reverts, skipped = model.group_decline_or_revert_items(items)
            model.decline_or_revert_items(declines, reverts, skipped, scope)

    def _build_job_apply(self, model: QueueModel, item: QueueItem) -> None:
        """Build desired-state Check/X controls for one child.

        Args:
            model: Queue tree model.
            item: Job child to render.
        """
        disposition = item.row.apply_disposition
        display_state = model.resolve_display_state(item.row)
        unavailable = display_state in (DisplayState.CORRUPTED, DisplayState.HANDLER_UNAVAILABLE)
        check_block_reason = model.get_check_block_reason(item, allow_reapply=True)
        x_block_reason = model.get_x_block_reason(item)
        can_check = check_block_reason is None
        can_x = x_block_reason is None
        if unavailable:
            unavailable_reason = model.get_unavailable_reason(item) or "This job's result is unavailable."
            check_tooltip = unavailable_reason
            x_tooltip = unavailable_reason
        elif disposition is ApplyDisposition.NOT_APPLICABLE:
            check_tooltip = "This job has no result to apply"
            x_tooltip = "This job has no result to discard"
        elif disposition is ApplyDisposition.NOT_READY:
            check_tooltip = "Results are not ready to apply"
            x_tooltip = "Results are not ready to decline"
        else:
            check_tooltip = check_block_reason or (
                "Reapply results" if disposition is ApplyDisposition.APPLIED else "Apply results"
            )
            x_tooltip = x_block_reason or (
                "Revert applied results" if disposition is ApplyDisposition.APPLIED else "Decline results"
            )
        check_style = (
            "ApplyJobUnknown"
            if unavailable
            else ("ApplyJobActive" if disposition is ApplyDisposition.APPLIED else "ApplyJob")
        )
        x_style = (
            "DeclineJobUnknown"
            if unavailable
            else ("DeclineJobActive" if disposition is ApplyDisposition.DECLINED else "DeclineJob")
        )
        with ui.VStack():
            ui.Spacer()
            with ui.HStack(height=ICON_SIZE_MEDIUM, spacing=PADDING_SMALL):
                ui.Spacer()
                self._build_icon(
                    check_style,
                    f"apply_job_{item.row.job_id}",
                    check_tooltip,
                    can_check,
                    lambda: model.apply_item(item),
                )
                self._build_icon(
                    x_style,
                    f"decline_job_{item.row.job_id}",
                    x_tooltip,
                    can_x,
                    lambda: self._request_x(model, item),
                )
                ui.Spacer()
            ui.Spacer()

    @staticmethod
    def _get_relevant_block_reason(
        item_reasons: tuple[tuple[QueueItem, str | None], ...],
        relevant_dispositions: tuple[ApplyDisposition, ...],
        fallback: str,
    ) -> str:
        """Prefer the reason from a result-bearing child over an unrelated graph stage.

        Args:
            item_reasons: Visible children paired with their current action block reason.
            relevant_dispositions: Stable dispositions to which the action applies.
            fallback: Explanation used when no child has a more specific reason.

        Returns:
            Most relevant user-facing block reason.
        """
        relevant_reason = next(
            (
                reason
                for item, reason in item_reasons
                if item.row.apply_disposition in relevant_dispositions and reason is not None
            ),
            None,
        )
        if relevant_reason is not None:
            return relevant_reason
        return next((reason for _item, reason in item_reasons if reason is not None), fallback)

    def _request_x(self, model: QueueModel, item: QueueItem) -> None:
        """Confirm Revert or immediately schedule Decline.

        Args:
            model: Queue tree model.
            item: Job child targeted by X.
        """
        if item.row.apply_disposition is ApplyDisposition.APPLIED and self._on_revert_item is not None:
            self._on_revert_item(item)
        else:
            model.decline_item(item)

    def _build_graph_actions(self, model: QueueModel, graph: QueueGraphItem) -> None:
        """Build Delete followed by adapter-declared graph actions.

        Args:
            model: Queue tree model.
            graph: Graph whose children explicitly contribute actions.
        """
        delete_graphs = model.get_delete_action_graphs(graph)
        delete_jobs = sum(len(selected.children) for selected in delete_graphs)
        delete_tooltip = (
            f"Delete {len(delete_graphs)} selected graphs and their {delete_jobs} jobs"
            if len(delete_graphs) > 1
            else f"Delete graph and its {delete_jobs} jobs"
        )
        with ui.VStack():
            ui.Spacer()
            with ui.HStack(height=ICON_SIZE_MEDIUM, spacing=PADDING_SMALL):
                self._build_icon(
                    "TrashCan",
                    f"delete_graph_{graph.graph_id}",
                    delete_tooltip,
                    model.can_delete_graphs(delete_graphs),
                    lambda: self._on_delete_graph(graph) if self._on_delete_graph else None,
                )
                for child in graph.children:
                    for action in adapter_interaction.get_graph_actions(child.row, model.context_name):
                        self._build_icon(
                            action.style_name,
                            f"{action.action_id}_graph_{graph.graph_id}_job_{child.row.job_id}",
                            action.tooltip,
                            action.enabled,
                            lambda _row=child.row, _action_id=action.action_id: adapter_interaction.execute_action(
                                _row, _action_id, model.context_name
                            ),
                        )
            ui.Spacer()

    def _build_job_actions(self, model: QueueModel, item: QueueItem) -> None:
        """Build only actions explicitly owned by a child job.

        Args:
            model: Queue tree model.
            item: Job child whose adapter owns actions.
        """
        row = item.row
        with ui.VStack():
            ui.Spacer()
            with ui.HStack(height=ICON_SIZE_MEDIUM, spacing=PADDING_SMALL):
                for action in adapter_interaction.get_job_actions(row, model.context_name):
                    self._build_icon(
                        action.style_name,
                        f"{action.action_id}_job_{item.row.job_id}",
                        action.tooltip,
                        action.enabled,
                        lambda _action_id=action.action_id: adapter_interaction.execute_action(
                            row, _action_id, model.context_name
                        ),
                    )
            ui.Spacer()

    @staticmethod
    def _build_icon(
        style_name: str,
        identifier: str,
        tooltip: str,
        enabled: bool,
        callback: Callable[[], None] | None,
    ) -> None:
        """Build one icon and attach its callback only while enabled.

        Args:
            style_name: Named icon style.
            identifier: Stable UI lookup identifier.
            tooltip: Safe user-facing help.
            enabled: Whether the action accepts interaction.
            callback: Zero-argument action callback while enabled.
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
        if enabled and callback is not None:
            image.set_mouse_pressed_fn(lambda _x, _y, button, _modifiers: callback() if button == 0 else None)

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
import threading
import uuid

import carb.input
import carb.settings
from omni import ui
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.enums import JobState, TimestampMode
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import Job, JobProgress
from omni.flux.job_queue.core.settings import (
    AUTO_APPLY_SETTING_PATH,
    SCHEDULER_ENABLED_SETTING_PATH,
    TIMESTAMP_MODE_SETTING_PATH,
    JobQueueSettings,
)
from omni.flux.utils.common import EventSubscription
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget
from omni.kit.app import SettingChangeSubscription
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager

from .constants import (
    ADAPTER_ERRORS,
    APPLY_MODE_BADGE_HEIGHT,
    APPLY_MODE_BADGE_WIDTH,
    COLUMN_SEPARATOR_HALF_WIDTH,
    EMPTY_STATE_ICON_SIZE,
    ICON_SIZE_LARGE,
    ICON_SIZE_MEDIUM,
    PADDING_EXTRA_LARGE,
    PADDING_LARGE,
    PADDING_MEDIUM,
    PADDING_SMALL,
    ROW_HEIGHT,
    SCROLLBAR_SPACING,
    TOOLBAR_HEIGHT,
)
from .delegate import QueueItemDelegate
from .enums import ColumnKey
from .filter_popup import QueueFiltersPopup
from .model import QueueModel
from .queue_item import QueueGraphItem, QueueItem
from .row import Row

__all__ = ("QueueWidget",)


class QueueWidget:
    """Own the event-driven hierarchical queue tree and generic controls."""

    def __init__(self, interface: QueueInterface, apply_executor: ApplyExecutor, context_name: str) -> None:
        """Initialize a collapsed queue tree without starting a scheduler.

        Args:
            interface: Typed durable queue interface.
            apply_executor: Shared apply lifecycle executor.
            context_name: USD context passed to exact-type display adapters.
        """
        self._queue_interface = interface
        self._main_loop = asyncio.get_running_loop()
        self._destroyed = False
        self._visible = False
        self._settings = JobQueueSettings()
        self._auto_apply_subscription: SettingChangeSubscription | None = None
        self._scheduler_enabled_subscription: SettingChangeSubscription | None = None
        self._timestamp_mode_subscription: SettingChangeSubscription | None = None
        self._job_changed_subscription: EventSubscription | None = None
        self._job_progress_changed_subscription: EventSubscription | None = None
        self._mutation_subscription: EventSubscription | None = None
        self._external_conditions_subscription: EventSubscription | None = None
        self._adapter_action_subscriptions: dict[type[Job], EventSubscription] = {}
        self._event_lock = threading.Lock()
        self._pending_job_changes: set[uuid.UUID] = set()
        self._pending_progress: dict[uuid.UUID, JobProgress] = {}
        self._pending_structure_refresh = False
        self._pending_external_refresh = False
        self._change_dispatch_scheduled = False
        self._model_changed_subscription = None
        self._tree_selection_subscription: EventSubscription | None = None
        self._reveal_subscription: EventSubscription | None = None
        self._filter_menu: QueueFiltersPopup | None = None
        self._footer_label: ui.Label | None = None
        self._footer_apply_button: ui.Image | None = None
        self._footer_decline_button: ui.Image | None = None
        self._footer_label_text = ""

        self.model = QueueModel(interface, apply_executor, context_name)
        self.delegate = QueueItemDelegate(
            self.model,
            self._settings,
            on_delete_graph=self._confirm_delete_graph,
            on_revert_item=self._confirm_revert_item,
            on_bulk_x=self._confirm_bulk_x,
        )
        self._column_widths = Row.get_column_widths()

        with ui.ZStack():
            ui.Rectangle(name="WorkspaceBackground")
            with ui.VStack(spacing=0):
                self._build_toolbar()
                self._build_header()
                with ui.ZStack():
                    self._tree_widget = ScrollingTreeWidget(
                        model=self.model,
                        delegate=self.delegate,
                        alternating_rows=True,
                        expansion_caching=True,
                        frame_selection=True,
                        select_all_children=False,
                        row_height=int(ROW_HEIGHT.value),
                        header_visible=False,
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        root_visible=False,
                        columns_resizable=False,
                        column_widths=self._column_widths,
                        drop_between_items=True,
                        identifier="job_queue_tree",
                        key_pressed_fn=self._on_queue_tree_key_pressed,
                    )
                    with ui.VStack():
                        self._empty_frame = ui.Frame(
                            visible=True,
                            separate_window=True,
                        )
                        with self._empty_frame:
                            with ui.ZStack():
                                ui.Rectangle(
                                    name="TreePanelBackground",
                                    identifier="queue_empty_overlay",
                                )
                                with ui.VStack():
                                    ui.Spacer()
                                    with ui.HStack(height=EMPTY_STATE_ICON_SIZE):
                                        ui.Spacer()
                                        ui.Image(
                                            "",
                                            name="QueueEmpty",
                                            identifier="queue_empty_icon",
                                            width=EMPTY_STATE_ICON_SIZE,
                                            height=EMPTY_STATE_ICON_SIZE,
                                        )
                                        ui.Spacer()
                                    ui.Spacer(height=PADDING_MEDIUM)
                                    self._empty_title = ui.Label(
                                        "No jobs in queue",
                                        name="QueueEmptyLabel",
                                        identifier="queue_empty_title",
                                        alignment=ui.Alignment.CENTER,
                                        height=0,
                                    )
                                    ui.Spacer(height=PADDING_SMALL)
                                    self._empty_subtitle = ui.Label(
                                        "Submit jobs to get started",
                                        name="QueueEmptySubLabel",
                                        identifier="queue_empty_subtitle",
                                        alignment=ui.Alignment.CENTER,
                                        height=0,
                                    )
                                    ui.Spacer()
                    with ui.Frame(separate_window=True):
                        self._build_column_separators()
                self._footer_frame = ui.Frame(width=ui.Fraction(1), height=ROW_HEIGHT, identifier="job_queue_footer")
                with self._footer_frame:
                    self._build_footer()

        self._tree_selection_subscription = self._tree_widget.subscribe_selection_changed(
            self._on_tree_selection_changed
        )
        self._model_changed_subscription = self.model.subscribe_item_changed_fn(self._on_model_item_changed)
        self._reveal_subscription = self.model.subscribe_reveal_item(self._reveal_item)
        self._scheduler_enabled_subscription = SettingChangeSubscription(
            SCHEDULER_ENABLED_SETTING_PATH, self._on_scheduler_enabled_changed
        )
        self._auto_apply_subscription = SettingChangeSubscription(AUTO_APPLY_SETTING_PATH, self._on_auto_apply_changed)
        self._timestamp_mode_subscription = SettingChangeSubscription(
            TIMESTAMP_MODE_SETTING_PATH, self._on_timestamp_mode_changed
        )
        self._refresh_scheduler_state()
        self._refresh_auto_apply_state()
        self._refresh_queue_state()

    def _build_toolbar(self) -> None:
        """Build the established left-aligned scheduler controls and options menu."""
        with ui.ZStack(height=TOOLBAR_HEIGHT):
            self._toolbar_background = ui.Rectangle(name="QueueToolbarBackground")
            with ui.HStack():
                ui.Spacer(width=PADDING_MEDIUM)
                with ui.VStack(width=ICON_SIZE_LARGE):
                    ui.Spacer()
                    self._start_scheduler_button = ui.Image(
                        "",
                        name="Start",
                        identifier="start_scheduler",
                        width=ICON_SIZE_LARGE,
                        height=ICON_SIZE_LARGE,
                        tooltip="Start dispatching queued jobs",
                    )
                    ui.Spacer()
                self._start_scheduler_button.set_mouse_pressed_fn(
                    lambda _x, _y, button, _modifiers: self._set_scheduler_enabled(True) if button == 0 else None
                )
                ui.Spacer(width=PADDING_SMALL)
                with ui.VStack(width=ICON_SIZE_LARGE):
                    ui.Spacer()
                    self._stop_scheduler_button = ui.Image(
                        "",
                        name="Stop",
                        identifier="stop_scheduler",
                        width=ICON_SIZE_LARGE,
                        height=ICON_SIZE_LARGE,
                        tooltip="Stop dispatching new jobs",
                    )
                    ui.Spacer()
                self._stop_scheduler_button.set_mouse_pressed_fn(
                    lambda _x, _y, button, _modifiers: self._set_scheduler_enabled(False) if button == 0 else None
                )
                ui.Spacer(width=PADDING_LARGE)
                self._scheduler_status = ui.Label(
                    "",
                    name="QueueRunnerState",
                    identifier="scheduler_status",
                    width=0,
                    tooltip="Job queue status",
                )
                ui.Spacer(width=PADDING_EXTRA_LARGE)
                with ui.VStack(width=APPLY_MODE_BADGE_WIDTH):
                    ui.Spacer()
                    self._apply_mode_badge = ui.ZStack(
                        width=APPLY_MODE_BADGE_WIDTH,
                        height=APPLY_MODE_BADGE_HEIGHT,
                        identifier="apply_mode_badge",
                    )
                    with self._apply_mode_badge:
                        self._apply_mode_badge_background = ui.Rectangle()
                        self._apply_mode_badge_label = ui.Label(
                            "", name="QueueApplyModeBadge", alignment=ui.Alignment.CENTER
                        )
                    ui.Spacer()
                self._apply_mode_badge.set_mouse_pressed_fn(
                    lambda _x, _y, button, _modifiers: self._toggle_auto_apply() if button == 0 else None
                )
                ui.Spacer()
                with ui.VStack(width=ICON_SIZE_LARGE):
                    ui.Spacer()
                    self._filter_button = ui.Image(
                        "",
                        name="Filter",
                        identifier="queue_filters",
                        width=ICON_SIZE_LARGE,
                        height=ICON_SIZE_LARGE,
                        tooltip="Filter jobs and stages",
                    )
                    ui.Spacer()
                self._filter_button.set_mouse_pressed_fn(
                    lambda _x, _y, button, _modifiers: self._show_filter_popup() if button == 0 else None
                )
                ui.Spacer(width=PADDING_MEDIUM)

    def _build_footer(self) -> None:
        """Build the fixed summary row with the same columns as the queue body."""
        job_stage_width, status_width, completed_width, apply_width, actions_width = Row.get_column_widths()
        with ui.ZStack(width=ui.Fraction(1), height=ROW_HEIGHT):
            ui.Rectangle(name="TabBackground")
            self._build_column_separators()
            with ui.HStack(width=ui.Fraction(1), spacing=0):
                with ui.Frame(width=job_stage_width):
                    self._build_footer_cell(ColumnKey.JOB_STAGE)
                ui.Spacer(width=status_width)
                ui.Spacer(width=completed_width)
                with ui.Frame(width=apply_width):
                    self._build_footer_cell(ColumnKey.APPLY)
                ui.Spacer(width=actions_width)
                ui.Spacer(width=SCROLLBAR_SPACING)

    def _build_header(self) -> None:
        """Build a stable queue header outside the native TreeView rebuild surface."""
        with ui.ZStack(width=ui.Fraction(1), height=ROW_HEIGHT):
            ui.Rectangle(name="TabBackground")
            self._build_column_separators()
            with ui.HStack(width=ui.Fraction(1), spacing=0):
                for key, header, width in zip(Row.keys(), Row.get_column_headers(), Row.get_column_widths()):
                    with ui.HStack(
                        width=width,
                        height=ROW_HEIGHT,
                        spacing=0,
                        identifier=f"queue_header_cell_{key.value}",
                    ):
                        ui.Spacer(width=PADDING_MEDIUM)
                        label = ui.Label(
                            header,
                            name="ColumnHeader",
                            height=ROW_HEIGHT,
                            alignment=ui.Alignment.LEFT_CENTER,
                            identifier=f"queue_header_{key.value}",
                            tooltip=(
                                "Click to switch between relative and absolute completion times."
                                if key is ColumnKey.COMPLETED
                                else ""
                            ),
                        )
                        ui.Spacer(width=PADDING_MEDIUM)
                    if key is ColumnKey.COMPLETED:
                        label.set_mouse_pressed_fn(
                            lambda _x, _y, button, _modifiers: self._toggle_timestamp_mode(button)
                        )
                ui.Spacer(width=SCROLLBAR_SPACING)

    def _build_column_separators(self) -> None:
        """Draw the canonical queue column separators over a complete row or body."""
        column_widths = Row.get_column_widths()
        with ui.HStack(spacing=0):
            for index, width in enumerate(column_widths):
                with ui.ZStack(width=width):
                    if index > 0:
                        with ui.HStack(spacing=0):
                            ui.Rectangle(
                                width=COLUMN_SEPARATOR_HALF_WIDTH,
                                name="ColumnSeparator",
                                identifier=f"queue_column_separator_{index}_left",
                            )
                            ui.Spacer()
                    if index < len(column_widths) - 1:
                        with ui.HStack(spacing=0):
                            ui.Spacer()
                            ui.Rectangle(
                                width=COLUMN_SEPARATOR_HALF_WIDTH,
                                name="ColumnSeparator",
                                identifier=f"queue_column_separator_{index}_right",
                            )
            ui.Spacer(width=SCROLLBAR_SPACING, height=0)

    def _build_footer_cell(self, key: ColumnKey) -> None:
        """Build summary content inside one queue column.

        Args:
            key: Shared queue column rendered by the footer row.
        """
        with ui.Frame(height=ROW_HEIGHT, identifier=f"queue_footer_{key.value}"):
            if key is ColumnKey.JOB_STAGE:
                with ui.HStack(height=ROW_HEIGHT, spacing=0):
                    ui.Spacer(width=PADDING_MEDIUM)
                    self._footer_label = ui.Label(self._footer_label_text, name="QueueFooterLabel")
                    ui.Spacer(width=PADDING_MEDIUM)
            elif key is ColumnKey.APPLY:
                with ui.VStack():
                    ui.Spacer()
                    with ui.HStack(height=ICON_SIZE_MEDIUM, spacing=PADDING_SMALL):
                        ui.Spacer()
                        self._footer_apply_button = ui.Image(
                            "",
                            name="ApplyJob",
                            identifier="apply_filtered_jobs",
                            width=ICON_SIZE_MEDIUM,
                            height=ICON_SIZE_MEDIUM,
                            tooltip="Apply or reapply matching results from top to bottom",
                        )
                        self._footer_apply_button.set_mouse_pressed_fn(
                            lambda _x, _y, button, _modifiers: self._apply_filtered() if button == 0 else None
                        )
                        self._footer_decline_button = ui.Image(
                            "",
                            name="DeclineJob",
                            identifier="decline_filtered_jobs",
                            width=ICON_SIZE_MEDIUM,
                            height=ICON_SIZE_MEDIUM,
                            tooltip="Decline or revert matching results from top to bottom",
                        )
                        self._footer_decline_button.set_mouse_pressed_fn(
                            lambda _x, _y, button, _modifiers: self._decline_filtered() if button == 0 else None
                        )
                        ui.Spacer()
                    ui.Spacer()

    def _set_scheduler_enabled(self, enabled: bool) -> None:
        """Persist whether core-owned scheduling should dispatch new jobs.

        Args:
            enabled: Whether core should dispatch queued jobs.
        """
        if not self._destroyed:
            self._settings.set_scheduler_enabled(enabled)

    def _on_scheduler_enabled_changed(self, _item, _event_type: carb.settings.ChangeEventType) -> None:
        """Marshal a persistent scheduler preference change onto the UI loop.

        Args:
            _item: Changed settings item.
            _event_type: Carbonite settings change type.
        """
        if not self._destroyed:
            self._main_loop.call_soon_threadsafe(self._refresh_scheduler_state)

    def _refresh_scheduler_state(self) -> None:
        """Synchronize toolbar state with the scheduler preference and active work."""
        if self._destroyed:
            return
        enabled = self._settings.scheduler_enabled
        stopping_graphs = (
            ()
            if enabled
            else tuple(
                dict.fromkeys(
                    item.row.graph_name
                    for item in self.model.all_items
                    if item.row.state in (JobState.SCHEDULED, JobState.IN_PROGRESS)
                )
            )
        )
        if enabled:
            status_text = "Running"
            status_tooltip = "The job queue is running"
            start_tooltip = status_tooltip
        elif stopping_graphs:
            status_text = "Stopping"
            start_tooltip = "Resume dispatching after active work finishes"
            if len(stopping_graphs) == 1:
                status_tooltip = f'Waiting for graph "{stopping_graphs[0]}" to finish before stopping.'
            else:
                graph_list = ", ".join(f'"{name}"' for name in stopping_graphs)
                status_tooltip = f"Waiting for these graphs to finish before stopping: {graph_list}."
        else:
            status_text = "Stopped"
            status_tooltip = "The job queue is stopped"
            start_tooltip = "Start dispatching queued jobs"
        self._scheduler_status.text = status_text
        self._scheduler_status.tooltip = status_tooltip
        scheduler_status_name = "QueueRunnerState" if enabled else "QueueRunnerStateStopped"
        if self._scheduler_status.name != scheduler_status_name:
            self._scheduler_status.name = scheduler_status_name
        toolbar_background_name = "QueueToolbarBackground" if enabled else "QueueToolbarBackgroundStopped"
        if self._toolbar_background.name != toolbar_background_name:
            self._toolbar_background.name = toolbar_background_name
        self._start_scheduler_button.enabled = not enabled
        self._start_scheduler_button.tooltip = start_tooltip
        self._stop_scheduler_button.enabled = enabled
        self._stop_scheduler_button.tooltip = "Stop dispatching new jobs" if enabled else status_tooltip

    def _on_auto_apply_changed(self, _item, _event_type: carb.settings.ChangeEventType) -> None:
        """Marshal a persistent automatic-Apply preference change onto the UI loop.

        Args:
            _item: Changed settings item.
            _event_type: Carbonite settings change type.
        """
        if not self._destroyed:
            self._main_loop.call_soon_threadsafe(self._refresh_auto_apply_state)

    def _refresh_auto_apply_state(self) -> None:
        """Synchronize the toolbar badge with the persistent Apply preference."""
        if self._destroyed:
            return
        auto_apply = self._settings.auto_apply
        badge_background_name = "QueueAutoApplyBadge" if auto_apply else "QueueManualApplyBadge"
        if self._apply_mode_badge_background.name != badge_background_name:
            self._apply_mode_badge_background.name = badge_background_name
        self._apply_mode_badge_label.text = "AUTO" if auto_apply else "MANUAL"
        self._apply_mode_badge.tooltip = (
            "Completed jobs are applied automatically. Click to use manual Apply."
            if auto_apply
            else "Completed jobs wait for manual Apply. Click to apply automatically."
        )

    def _toggle_auto_apply(self) -> None:
        """Toggle the persistent Apply mode from the toolbar badge."""
        if not self._destroyed:
            self._settings.set_auto_apply(not self._settings.auto_apply)

    def _toggle_timestamp_mode(self, button: int) -> None:
        """Toggle completion times after a primary-button press.

        Args:
            button: Native mouse button index.
        """
        if button != 0:
            return
        mode = self._settings.timestamp_mode
        self._settings.set_timestamp_mode(
            TimestampMode.ABSOLUTE if mode is TimestampMode.RELATIVE else TimestampMode.RELATIVE
        )

    def _on_timestamp_mode_changed(self, _item, _event_type: carb.settings.ChangeEventType) -> None:
        """Rebuild visible timestamps after the persistent mode changes.

        Args:
            _item: Changed settings item.
            _event_type: Carbonite settings change type.
        """
        if not self._destroyed and self._visible:
            self._main_loop.call_soon_threadsafe(self.model.invalidate_visible_items)

    @property
    def destroyed(self) -> bool:
        """Whether the widget released its event ownership and native tree.

        Returns:
            True after destroy(), which tells an owning workspace window to rebuild its content.
        """
        return self._destroyed

    def show(self, visible: bool) -> None:
        """Subscribe before synchronization while the owning workspace is visible.

        Args:
            visible: Whether queue events should currently drive this tree.
        """
        if self._destroyed or visible == self._visible:
            return
        self._visible = visible
        if visible:
            self._subscribe_queue_events()
            self.model.refresh(force=True)
            self._sync_adapter_action_subscriptions()
            self._refresh_scheduler_state()
        else:
            self._unsubscribe_queue_events()

    def _subscribe_queue_events(self) -> None:
        """Subscribe to queue events before reading the durable snapshot."""
        self._job_changed_subscription = self._queue_interface.subscribe_job_changed(self._on_job_changed)
        self._job_progress_changed_subscription = self._queue_interface.subscribe_job_progress_changed(
            self._on_job_progress_changed
        )
        self._mutation_subscription = self._queue_interface.subscribe_mutation(self._on_mutation)
        self._external_conditions_subscription = self._queue_interface.subscribe_external_conditions_changed(
            self._on_external_conditions_changed
        )

    def _unsubscribe_queue_events(self) -> None:
        """Release process-local queue subscriptions while hidden."""
        self._job_changed_subscription = None
        self._job_progress_changed_subscription = None
        self._mutation_subscription = None
        self._external_conditions_subscription = None
        self._adapter_action_subscriptions.clear()
        with self._event_lock:
            self._pending_job_changes.clear()
            self._pending_progress.clear()
            self._pending_structure_refresh = False
            self._pending_external_refresh = False
            self._change_dispatch_scheduled = False

    def _sync_adapter_action_subscriptions(self) -> None:
        """Own one product action subscription per exact visible adapter type."""
        adapters = {
            item.row.adapter.job_type: item.row.adapter for item in self.model.all_items if item.row.adapter is not None
        }
        for job_type in set(self._adapter_action_subscriptions) - set(adapters):
            self._adapter_action_subscriptions.pop(job_type)
        for job_type, adapter in adapters.items():
            if job_type in self._adapter_action_subscriptions:
                continue
            try:
                subscription = adapter.subscribe_action_events(self.model)
            except ADAPTER_ERRORS as error:
                carb.log_warn(f"Could not subscribe to {adapter.name} queue action changes: {error}")
                continue
            if subscription is not None:
                self._adapter_action_subscriptions[job_type] = subscription

    def _on_job_changed(self, job_id: uuid.UUID) -> None:
        """Marshal a worker-thread job event onto the UI loop.

        Args:
            job_id: Changed durable job identifier.
        """
        if not self._visible or self._destroyed:
            return
        with self._event_lock:
            self._pending_job_changes.add(job_id)
        self._request_change_dispatch()

    def _on_job_progress_changed(self, job_id: uuid.UUID, progress: JobProgress) -> None:
        """Coalesce committed progress onto the UI loop without rebuilding tree rows.

        Args:
            job_id: Changed durable job identifier.
            progress: Committed structured progress.
        """
        if not self._visible or self._destroyed:
            return
        with self._event_lock:
            self._pending_progress[job_id] = progress
        self._request_change_dispatch()

    def _on_mutation(self) -> None:
        """Marshal a structural queue event onto the UI loop."""
        if not self._visible or self._destroyed:
            return
        with self._event_lock:
            self._pending_structure_refresh = True
        self._request_change_dispatch()

    def _on_external_conditions_changed(self) -> None:
        """Marshal an external readiness event onto the UI loop."""
        if not self._visible or self._destroyed:
            return
        with self._event_lock:
            self._pending_external_refresh = True
        self._request_change_dispatch()

    def _request_change_dispatch(self) -> None:
        """Schedule at most one UI-loop drain for the current worker-event burst."""
        with self._event_lock:
            if self._change_dispatch_scheduled:
                return
            self._change_dispatch_scheduled = True
        self._main_loop.call_soon_threadsafe(self._dispatch_queue_changes)

    def _dispatch_queue_changes(self) -> None:
        """Apply one coalesced worker-event burst at the narrowest valid scope."""
        with self._event_lock:
            job_ids = self._pending_job_changes
            progress_updates = self._pending_progress
            refresh_structure = self._pending_structure_refresh
            refresh_external = self._pending_external_refresh
            self._pending_job_changes = set()
            self._pending_progress = {}
            self._pending_structure_refresh = False
            self._pending_external_refresh = False
            self._change_dispatch_scheduled = False

        if not self._visible:
            return
        if refresh_structure:
            self.model.refresh(force=bool(job_ids or progress_updates or refresh_external))
            self._sync_adapter_action_subscriptions()
            self.delegate.prune_status_widgets()
            self._refresh_scheduler_state()
            return

        if any(not self.model.has_item(job_id) for job_id in job_ids):
            self.model.refresh()
            self._sync_adapter_action_subscriptions()
            self.delegate.prune_status_widgets()
            self._refresh_scheduler_state()
            return
        for job_id in job_ids:
            self.model.update_item(job_id)
        progress_updates = {job_id: progress for job_id, progress in progress_updates.items() if job_id not in job_ids}
        if progress_updates and self.model.update_progress_batch(progress_updates):
            self.model.refresh()
            self.delegate.prune_status_widgets()
            return
        if refresh_external:
            self.model.refresh_schedule_conditions()
        if job_ids:
            self._refresh_scheduler_state()

    def _on_tree_selection_changed(self, selected_items: list[QueueGraphItem | QueueItem]) -> None:
        """Forward native TreeView selection to the model-owned selection channel.

        Args:
            selected_items: Current native tree selection.
        """
        self.model.set_items_selected(selected_items)

    def _reveal_item(self, item: QueueItem) -> None:
        """Expand, select, and frame one currently visible child.

        Args:
            item: Visible child requested by details navigation.
        """
        if item.parent is not None:
            self._tree_widget.set_expanded(item.parent, True, False)
        self._tree_widget.selection = [item]
        # A programmatic selection never notifies subscribers, so drive the model channel directly.
        self.model.set_items_selected([item])

    def _on_model_item_changed(self, _model: QueueModel, item: QueueGraphItem | QueueItem | None) -> None:
        """Refresh empty/footer/toolbar state after any visible model change.

        Args:
            _model: Model that emitted the invalidation.
            item: Specific invalidated item, when available.
        """
        if item is None:
            self._refresh_queue_state()

    def _refresh_queue_state(self) -> None:
        """Synchronize the empty overlay, filter state, and visible counts."""
        self._refresh_filter_button_state()
        visible_items = self.model.visible_job_items
        total_jobs = len(self.model.all_items)
        visible_jobs = len(visible_items)
        self._empty_frame.visible = total_jobs == 0 or visible_jobs == 0
        if total_jobs == 0:
            self._empty_title.text = "No jobs in queue"
            self._empty_subtitle.text = "Submit jobs to get started"
        elif visible_jobs == 0:
            self._empty_title.text = "No jobs match the current filters"
            self._empty_subtitle.text = "Change or clear filters to see queued jobs"
        visible_graphs = len(self.model.get_item_children(None))
        footer_label = (
            f"{visible_graphs} graph{'s' if visible_graphs != 1 else ''}"
            f" - {visible_jobs}/{total_jobs} job{'s' if total_jobs != 1 else ''}"
        )
        self._footer_label_text = footer_label
        if self._footer_label is not None:
            self._footer_label.text = footer_label

    def _refresh_filter_button_state(self) -> None:
        """Show whether the centralized popup currently limits visible jobs."""
        filters_active = self.model.filters_active
        filter_name = "FilterActive" if filters_active else "Filter"
        if self._filter_button.name != filter_name:
            self._filter_button.name = filter_name
        self._filter_button.tooltip = "Filters are active" if filters_active else "Filter jobs and stages"

    def _apply_filtered(self) -> None:
        """Apply or Reapply matching results in visible tree order."""
        self.model.apply_items(tuple(self.model.visible_job_items), "current filters")

    def _decline_filtered(self) -> None:
        """Decline or Revert matching results in visible tree order."""
        self._confirm_bulk_x(tuple(self.model.visible_job_items), "current filters")

    def _on_queue_tree_key_pressed(self, key: int, _modifiers: int, pressed: bool) -> None:
        """Delete the selected job graphs when Delete is released over the queue tree.

        Args:
            key: Released carb keyboard key code.
            _modifiers: Active keyboard modifier flags; unused.
            pressed: True on key press, False on release. The delete workflow runs on
                release to match the Delete-key behavior of the other Remix trees.
        """
        if pressed or key not in (int(carb.input.KeyboardInput.DEL), int(carb.input.KeyboardInput.NUMPAD_DEL)):
            return
        selected_graphs = [item for item in self._tree_widget.selection if isinstance(item, QueueGraphItem)]
        if not selected_graphs:
            return
        self._confirm_delete_graph(selected_graphs[0])

    def _confirm_delete_graph(self, graph: QueueGraphItem) -> None:
        """Request core-owned file inventory for the anchored root selection.

        Args:
            graph: Graph whose row contains the invoked Delete action.
        """
        graphs = self.model.get_delete_action_graphs(graph)
        if self.model.can_delete_graphs(graphs):
            self.model.get_graphs_artifact_file_count(
                graphs, lambda count: self._show_delete_graphs_prompt(graphs, count)
            )

    def _show_delete_graphs_prompt(self, graphs: tuple[QueueGraphItem, ...], file_count: int) -> None:
        """Show one exact-count confirmation after asynchronous inventory.

        Args:
            graphs: Idle roots selected for deletion.
            file_count: Exact recursive queue-owned file count.
        """
        if self._destroyed or not self.model.can_delete_graphs(graphs):
            return
        graph_count = len(graphs)
        job_count = sum(len(graph.children) for graph in graphs)
        job_suffix = "s" if job_count != 1 else ""
        title = "Delete Job Graph" if graph_count == 1 else "Delete Job Graphs"
        prompt = (
            f'Delete graph "{graphs[0].name}", all {job_count} job{job_suffix}, '
            if graph_count == 1
            else f"Delete {graph_count} selected graphs, all {job_count} jobs, "
        )
        PromptManager.post_simple_prompt(
            title,
            prompt + f"and {file_count} output file{'s' if file_count != 1 else ''}?\n\n"
            "Any changes already applied to the project will remain.",
            ok_button_info=PromptButtonInfo(
                "Delete Graph" if graph_count == 1 else "Delete Graphs",
                lambda: self._delete_graphs_if_available(graphs),
            ),
            cancel_button_info=PromptButtonInfo("Cancel", None),
            modal=True,
        )

    def _delete_graphs_if_available(self, graphs: tuple[QueueGraphItem, ...]) -> None:
        """Delete a still-current root selection from a live widget.

        Args:
            graphs: Graphs captured by the confirmation prompt.
        """
        if self._destroyed or not self.model.can_delete_graphs(graphs):
            return
        self.model.delete_graphs(graphs)

    def _confirm_revert_item(self, item: QueueItem) -> None:
        """Request confirmation before reverting one applied result.

        Args:
            item: Applied child selected for Revert.
        """
        PromptManager.post_simple_prompt(
            "Revert Applied Results",
            f'Restore the project values from before "{item.row.name}" was applied?',
            ok_button_info=PromptButtonInfo("Revert", lambda: self._revert_item_if_available(item)),
            cancel_button_info=PromptButtonInfo("Cancel", None),
            modal=True,
        )

    def _revert_item_if_available(self, item: QueueItem) -> None:
        """Run the exact Revert shown by a live confirmation prompt.

        Args:
            item: Item captured by the confirmation prompt.
        """
        if self._destroyed or item not in self.model.all_items:
            return
        self.model.revert_item(item)

    def _confirm_bulk_x(self, items: tuple[QueueItem, ...], scope: str) -> None:
        """Confirm exact Revert/Decline/skip counts when any Revert is present.

        Args:
            items: Captured filtered children.
            scope: User-facing capture scope for completion notifications.
        """
        declines, reverts, skipped = self.model.group_decline_or_revert_items(items)
        if not reverts:
            self.model.decline_or_revert_items(declines, reverts, skipped, scope)
            return
        PromptManager.post_simple_prompt(
            "Revert Applied Results",
            f"Revert {len(reverts)} applied job{'s' if len(reverts) != 1 else ''}"
            f", decline {len(declines)} pending job{'s' if len(declines) != 1 else ''},"
            f" and skip {skipped} unavailable job{'s' if skipped != 1 else ''}?",
            ok_button_info=PromptButtonInfo(
                "Continue", lambda: self._run_confirmed_bulk_x(declines, reverts, skipped, scope)
            ),
            cancel_button_info=PromptButtonInfo("Cancel", None),
            modal=True,
        )

    def _run_confirmed_bulk_x(
        self,
        declines: tuple[QueueItem, ...],
        reverts: tuple[QueueItem, ...],
        skipped: int,
        scope: str,
    ) -> None:
        """Run the exact action groups shown by a live confirmation prompt.

        Args:
            declines: Items shown as Decline actions.
            reverts: Items shown as Revert actions.
            skipped: Items shown as unavailable.
            scope: User-facing capture scope for completion notifications.
        """
        if self._destroyed:
            return
        self.model.decline_or_revert_items(declines, reverts, skipped, scope)

    def _show_filter_popup(self) -> None:
        """Show the complete centralized filter popup from the toolbar."""
        if self._filter_menu is not None:
            self._filter_menu.hide()
            self._filter_menu.destroy()
        self._filter_menu = QueueFiltersPopup(self.model, self._main_loop, self._refresh_filter_button_state)
        self._filter_menu.show_below_right(self._filter_button)

    def destroy(self) -> None:
        """Release event ownership and native tree resources."""
        if self._destroyed:
            return
        self._destroyed = True
        self._visible = False
        self._auto_apply_subscription = None
        self._scheduler_enabled_subscription = None
        self._timestamp_mode_subscription = None
        self._unsubscribe_queue_events()
        self._model_changed_subscription = None
        self._tree_selection_subscription = None
        self._reveal_subscription = None
        if self._filter_menu is not None:
            self._filter_menu.hide()
            self._filter_menu.destroy()
        self._filter_menu = None
        self._footer_label = None
        self._footer_apply_button = None
        self._footer_decline_button = None
        self._tree_widget.destroy()
        self.delegate.destroy()
        self.model.destroy()

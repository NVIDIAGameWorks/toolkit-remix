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
from collections.abc import Callable

from omni import ui
from omni.flux.job_queue.core.enums import ApplyDisposition
from omni.flux.utils.common import EventSubscription
from omni.kit import app
from omni.kit.widget.options_menu.popup_menu import AbstractPopupMenu, PopupMenuDelegate

from .constants import (
    ALL_APPLY_FILTERS,
    ALL_STATUS_FILTERS,
    APPLY_FILTER_OPTIONS,
    SCROLLBAR_SPACING,
    STATUS_FILTER_OPTIONS,
)
from .enums import ColumnKey, DisplayState
from .model import QueueModel

__all__ = ("QueueFiltersPopup",)

_POPUP_WIDTH = ui.Pixel(340)
_POPUP_MAX_BODY_HEIGHT = ui.Pixel(500)
_POPUP_EDGE_MARGIN = ui.Pixel(8)
_ROW_HEIGHT = ui.Pixel(24)
_SEARCH_LABEL_WIDTH = ui.Pixel(56)
_TITLE_MINIMUM_WIDTH = ui.Pixel(45)
_ICON_SIZE = ui.Pixel(24)
_PADDING_SMALL = ui.Pixel(4)
_PADDING_MEDIUM = ui.Pixel(8)
_PADDING_LARGE = ui.Pixel(12)


class _QueueFiltersPopupDelegate(PopupMenuDelegate):
    """Provide the native Additional Filters title and Reset All action."""

    def __init__(self, model: QueueModel, reset_fn: Callable[[], None]) -> None:
        """Initialize the title delegate.

        Args:
            model: Central queue model containing all filter state.
            reset_fn: Callback that clears filters and refreshes the popup body.
        """
        super().__init__()
        self._model = model
        self._reset_fn = reset_fn

    def build_title(self, item: ui.Menu) -> None:
        """Build the shared popup title and synchronize Reset All.

        Args:
            item: Popup menu whose title is being built.
        """
        with ui.ZStack(height=_ROW_HEIGHT, content_clipping=True, identifier="queue_filters_header"):
            ui.Rectangle(style_type_name_override="Title.Background")
            with ui.HStack(style_type_name_override="Title.Header"):
                ui.Label(self.get_title(item), width=0, style_type_name_override="Title.Label")
                ui.Spacer(width=_TITLE_MINIMUM_WIDTH)
                ui.Spacer()
                self._reset_all = ui.Button(
                    "Reset All",
                    width=0,
                    height=_ROW_HEIGHT,
                    style_type_name_override="ResetButton",
                    clicked_fn=self.on_reset_all,
                    identifier="queue_filter_reset_all",
                )
        self.refresh_reset_enabled()

    def on_reset_all(self) -> None:
        """Clear all queue filters and rebuild their controls."""
        self._reset_fn()

    def refresh_reset_enabled(self) -> None:
        """Enable Reset All only while at least one filter is active."""
        self.enable_reset_all(self._model.filters_active)


class QueueFiltersPopup(AbstractPopupMenu):
    """Render all generic queue filters in one Stage Manager-style popup."""

    def __init__(
        self,
        model: QueueModel,
        main_loop: asyncio.AbstractEventLoop,
        filter_changed_fn: Callable[[], None],
    ) -> None:
        """Initialize the centralized queue filter popup.

        Args:
            model: Queue model providing generic graph, stage, status, and Apply values.
            main_loop: Owning Kit event loop used to defer UI rebuilds after input callbacks.
            filter_changed_fn: Callback that refreshes the owning toolbar indicator.
        """
        self._model = model
        self._main_loop = main_loop
        self._filter_changed_fn = filter_changed_fn
        self._subscriptions: list[EventSubscription] = []
        self._scrolling_frame: ui.ScrollingFrame | None = None
        self._body_frame: ui.Frame | None = None
        self._body_stack: ui.VStack | None = None
        self._filter_icon: ui.Image | None = None
        self._search_field: ui.StringField | None = None
        self._section_frames: dict[ColumnKey, ui.Frame] = {}
        self._requested_focus: ColumnKey | None = None
        self._rebuild_handle: asyncio.Handle | None = None
        self._focus_task: asyncio.Task[None] | None = None
        self._popup_delegate = _QueueFiltersPopupDelegate(model, self._reset_all)
        super().__init__("Additional Filters", self._popup_delegate)

    def build_menu_items(self) -> None:
        """Build one scrollable popup containing every queue filter control."""
        self._subscriptions.clear()
        self._scrolling_frame = ui.ScrollingFrame(
            width=_POPUP_WIDTH,
            height=_POPUP_MAX_BODY_HEIGHT,
            identifier="queue_filters_popup",
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            computed_content_size_changed_fn=self._update_body_height,
        )
        with self._scrolling_frame:
            self._body_frame = ui.Frame(build_fn=self._build_body)

    def show_below_right(self, widget: ui.Widget) -> None:
        """Show the popup below a widget with their right edges aligned.

        Args:
            widget: Toolbar widget used as the popup anchor.
        """
        self._requested_focus = None
        x = max(
            _POPUP_EDGE_MARGIN.value,
            widget.screen_position_x + widget.computed_width - _POPUP_WIDTH.value,
        )
        self.show_at(x, widget.screen_position_y + widget.computed_height)
        self._schedule_requested_focus()

    def _update_body_height(self) -> None:
        """Shrink short popups while retaining scrolling for long filter lists."""
        if self._scrolling_frame is None:
            return
        if self._scrolling_frame.scroll_y_max:
            self._scrolling_frame.height = _POPUP_MAX_BODY_HEIGHT
            self._schedule_requested_focus()
            return
        content_height = (
            self._body_stack.computed_height if self._body_stack else self._scrolling_frame.computed_content_height
        )
        if content_height:
            self._scrolling_frame.height = ui.Pixel(max(1, min(_POPUP_MAX_BODY_HEIGHT.value, content_height)))
        self._schedule_requested_focus()

    def _schedule_requested_focus(self) -> None:
        """Defer section scrolling until the popup has completed its layout pass."""
        if self._requested_focus is None:
            return
        if self._focus_task is not None:
            return
        self._focus_task = self._main_loop.create_task(self._focus_requested_section_after_layout())

    async def _focus_requested_section_after_layout(self) -> None:
        """Focus the requested section after native UI geometry is current."""
        try:
            for _attempt in range(3):
                await app.get_app().next_update_async()
                if self._focus_requested_section():
                    return
        finally:
            self._focus_task = None

    def _build_body(self) -> None:
        """Build search and direct filter controls using the shared visual pattern."""
        self._subscriptions.clear()
        self._section_frames.clear()
        with ui.HStack(width=_POPUP_WIDTH, height=0, spacing=_PADDING_MEDIUM):
            ui.Spacer(width=0)
            self._body_stack = ui.VStack(height=0)
            with self._body_stack:
                ui.Spacer(height=_PADDING_MEDIUM)
                self._build_search()
                ui.Spacer(height=_PADDING_LARGE)
                self._section_frames[ColumnKey.JOB_STAGE] = ui.Frame(
                    identifier="queue_filter_job_stage_section",
                )
                with self._section_frames[ColumnKey.JOB_STAGE]:
                    with ui.VStack(height=0):
                        self._build_job_stage_filters()
                ui.Spacer(height=_PADDING_LARGE)
                self._section_frames[ColumnKey.STATUS] = ui.Frame(
                    identifier="queue_filter_status_section",
                )
                with self._section_frames[ColumnKey.STATUS]:
                    with ui.VStack(height=0):
                        self._build_status_filters()
                ui.Spacer(height=_PADDING_LARGE)
                self._section_frames[ColumnKey.APPLY] = ui.Frame(
                    identifier="queue_filter_apply_section",
                )
                with self._section_frames[ColumnKey.APPLY]:
                    with ui.VStack(height=0):
                        self._build_apply_filters()
                ui.Spacer(height=_PADDING_MEDIUM)
            ui.Spacer(width=SCROLLBAR_SPACING)

    def _build_search(self) -> None:
        """Build the native search field and filter-state icon."""
        with ui.HStack(height=_ROW_HEIGHT, spacing=_PADDING_MEDIUM):
            ui.Label("Search:", width=_SEARCH_LABEL_WIDTH)
            self._search_field = ui.StringField(identifier="queue_filter_search")
            self._search_field.model.set_value(self._model.search_text)
            self._subscriptions.append(self._search_field.model.subscribe_end_edit_fn(self._on_search_edited))
            self._filter_icon = ui.Image(
                "",
                name="FilterActive" if self._model.filters_active else "Filter",
                identifier="queue_filter_icon",
                width=_ICON_SIZE,
                height=_ICON_SIZE,
                tooltip="Queue filters",
            )

    def _build_job_stage_filters(self) -> None:
        """Build direct graph and stage choices from all current queue rows."""
        graph_options = self._model.get_graph_filter_options()
        stage_options = self._model.get_stage_filter_options()
        graph_names = set(graph_options)
        stage_names = set(stage_options)
        selected_graph_names = (
            graph_names if self._model.visible_graph_names is None else self._model.visible_graph_names
        )
        selected_stage_names = (
            stage_names if self._model.visible_job_stage_names is None else self._model.visible_job_stage_names
        )
        self._build_section_header(
            "Jobs and Stages",
            "job_stage",
            select_enabled=selected_graph_names != graph_names or selected_stage_names != stage_names,
            deselect_enabled=bool(selected_graph_names or selected_stage_names),
            set_all_fn=self._set_all_job_stage_filters,
        )
        if not graph_options and not stage_options:
            self._build_empty_group_label("No jobs available")
            return
        for index, graph_name in enumerate(graph_options):
            self._build_checkbox(
                f"Job: {graph_name}",
                f"queue_filter_graph_{index}",
                graph_name in selected_graph_names,
                lambda selected, value=graph_name: self._set_graph_selected(value, selected),
            )
        for index, stage_name in enumerate(stage_options):
            self._build_checkbox(
                f"Stage: {stage_name}",
                f"queue_filter_stage_{index}",
                stage_name in selected_stage_names,
                lambda selected, value=stage_name: self._set_stage_selected(value, selected),
            )

    def _build_status_filters(self) -> None:
        """Build every explicit display-status choice."""
        selected_states = ALL_STATUS_FILTERS if self._model.visible_states is None else self._model.visible_states
        self._build_section_header(
            "Status",
            "status",
            select_enabled=selected_states != ALL_STATUS_FILTERS,
            deselect_enabled=bool(selected_states),
            set_all_fn=self._set_all_status_filters,
        )
        for state, label in STATUS_FILTER_OPTIONS:
            self._build_checkbox(
                label,
                f"queue_filter_status_{state.value}",
                state in selected_states,
                lambda selected, value=state: self._set_status_selected(value, selected),
            )

    def _build_apply_filters(self) -> None:
        """Build all five explicit persisted Apply dispositions."""
        selected_dispositions = self._model.visible_apply_dispositions
        self._build_section_header(
            "Apply",
            "apply",
            select_enabled=selected_dispositions != ALL_APPLY_FILTERS,
            deselect_enabled=bool(selected_dispositions),
            set_all_fn=self._set_all_apply_filters,
        )
        for disposition, label in APPLY_FILTER_OPTIONS:
            self._build_checkbox(
                label,
                f"queue_filter_apply_{disposition.value}",
                disposition in selected_dispositions,
                lambda selected, value=disposition: self._set_apply_selected(value, selected),
            )

    def _build_section_header(
        self,
        title: str,
        identifier: str,
        *,
        select_enabled: bool,
        deselect_enabled: bool,
        set_all_fn: Callable[[bool], None],
    ) -> None:
        """Build a Stage Manager-style category header with bulk actions.

        Args:
            title: User-facing category title.
            identifier: Stable identifier segment for UI automation.
            select_enabled: Whether Select All changes the filter.
            deselect_enabled: Whether Deselect All changes the filter.
            set_all_fn: Callback receiving the requested selected state.
        """
        with ui.HStack(height=_ROW_HEIGHT, spacing=_PADDING_MEDIUM):
            ui.Label(title, name="PropertiesPaneSectionTitle", width=0)
            ui.Spacer()
            self._build_section_action("Select All", f"{identifier}_select_all", select_enabled, set_all_fn, True)
            self._build_section_action(
                "Deselect All", f"{identifier}_deselect_all", deselect_enabled, set_all_fn, False
            )
        ui.Spacer(height=_PADDING_SMALL)

    @staticmethod
    def _build_section_action(
        text: str,
        identifier: str,
        enabled: bool,
        callback: Callable[[bool], None],
        selected: bool,
    ) -> None:
        """Build one native category action label.

        Args:
            text: User-facing action label.
            identifier: Stable UI automation identifier.
            enabled: Whether the action currently changes the filter.
            callback: Callback receiving the requested selected state.
            selected: State requested when activated.
        """
        ui.Label(
            text,
            width=0,
            name="FilterSectionAction",
            identifier=f"queue_filter_{identifier}",
            enabled=enabled,
            mouse_pressed_fn=lambda _x, _y, button, _modifiers: callback(selected) if button == 0 else None,
        )

    def _build_checkbox(
        self,
        label: str,
        identifier: str,
        selected: bool,
        changed_fn: Callable[[bool], None],
    ) -> None:
        """Build one direct labeled checkbox.

        Args:
            label: User-facing filter value.
            identifier: Stable UI automation identifier.
            selected: Current selected state.
            changed_fn: Callback receiving the new selected state.
        """
        with ui.HStack(height=_ROW_HEIGHT, spacing=_PADDING_MEDIUM):
            label_widget = ui.Label(label, name="FilterCheckboxLabel", identifier=f"{identifier}_label")
            checkbox = ui.CheckBox(width=_ICON_SIZE, identifier=identifier)
        checkbox.model.set_value(selected)
        label_widget.set_mouse_pressed_fn(
            lambda _x, _y, button, _modifiers: (
                checkbox.model.set_value(not checkbox.model.get_value_as_bool()) if button == 0 else None
            )
        )
        self._subscriptions.append(
            checkbox.model.subscribe_value_changed_fn(lambda value_model: changed_fn(value_model.as_bool))
        )

    @staticmethod
    def _build_empty_group_label(text: str) -> None:
        """Build muted text for an empty dynamic filter group.

        Args:
            text: User-facing empty group text.
        """
        ui.Label(text, name="FilterCheckboxLabel", enabled=False, height=_ROW_HEIGHT)

    def _on_search_edited(self, value_model: ui.AbstractValueModel) -> None:
        """Apply the literal graph/stage search after editing ends.

        Args:
            value_model: Native string field model.
        """
        self._model.set_search_filter(value_model.get_value_as_string())
        self._refresh_filter_state()

    def _focus_requested_section(self) -> bool:
        """Scroll to the requested section once its native geometry is available.

        Returns:
            Whether the request was handled or no request remains.
        """
        if self._requested_focus is None:
            return True
        if self._scrolling_frame is None or self._body_frame is None:
            return False
        if self._requested_focus is ColumnKey.JOB_STAGE and self._search_field is not None:
            self._scrolling_frame.scroll_y = 0
            self._search_field.focus_keyboard()
        else:
            section = self._section_frames.get(self._requested_focus)
            if section is None or not section.computed_height:
                return False
            self._scrolling_frame.scroll_y = max(0, section.screen_position_y - self._body_frame.screen_position_y)
        self._requested_focus = None
        return True

    def _set_graph_selected(self, graph_name: str, selected: bool) -> None:
        """Set one graph-name filter choice.

        Args:
            graph_name: Graph group represented by the checkbox.
            selected: Whether the graph should remain visible.
        """
        all_graph_names = set(self._model.get_graph_filter_options())
        selected_graph_names = set(
            all_graph_names if self._model.visible_graph_names is None else self._model.visible_graph_names
        )
        if selected:
            selected_graph_names.add(graph_name)
        else:
            selected_graph_names.discard(graph_name)
        self._model.set_job_stage_filter(
            None if selected_graph_names == all_graph_names else selected_graph_names,
            self._model.visible_job_stage_names,
        )
        self._refresh_filter_state()

    def _set_stage_selected(self, stage_name: str, selected: bool) -> None:
        """Set one child-stage filter choice.

        Args:
            stage_name: Adapter-rendered stage name represented by the checkbox.
            selected: Whether the stage should remain visible.
        """
        all_stage_names = set(self._model.get_stage_filter_options())
        selected_stage_names = set(
            all_stage_names if self._model.visible_job_stage_names is None else self._model.visible_job_stage_names
        )
        if selected:
            selected_stage_names.add(stage_name)
        else:
            selected_stage_names.discard(stage_name)
        self._model.set_job_stage_filter(
            self._model.visible_graph_names,
            None if selected_stage_names == all_stage_names else selected_stage_names,
        )
        self._refresh_filter_state()

    def _set_status_selected(self, state: DisplayState, selected: bool) -> None:
        """Set one explicit display-status choice.

        Args:
            state: Generic display status represented by the checkbox.
            selected: Whether the status should remain visible.
        """
        selected_states = set(ALL_STATUS_FILTERS if self._model.visible_states is None else self._model.visible_states)
        if selected:
            selected_states.add(state)
        else:
            selected_states.discard(state)
        self._model.set_status_filter(None if selected_states == ALL_STATUS_FILTERS else selected_states)
        self._refresh_filter_state()

    def _set_apply_selected(self, disposition: ApplyDisposition, selected: bool) -> None:
        """Set one persisted Apply-disposition choice.

        Args:
            disposition: Apply disposition represented by the checkbox.
            selected: Whether the disposition should remain visible.
        """
        selected_dispositions = set(self._model.visible_apply_dispositions)
        if selected:
            selected_dispositions.add(disposition)
        else:
            selected_dispositions.discard(disposition)
        self._model.set_apply_filter(selected_dispositions)
        self._refresh_filter_state()

    def _set_all_job_stage_filters(self, selected: bool) -> None:
        """Select or deselect every dynamic graph and stage choice.

        Args:
            selected: Whether every graph and stage should remain visible.
        """
        self._model.set_job_stage_filter(None if selected else set(), None if selected else set())
        self._requested_focus = ColumnKey.JOB_STAGE
        self._refresh_filter_state(rebuild=True)

    def _set_all_status_filters(self, selected: bool) -> None:
        """Select or deselect every explicit display-status choice.

        Args:
            selected: Whether every display status should remain visible.
        """
        self._model.set_status_filter(None if selected else set())
        self._requested_focus = ColumnKey.STATUS
        self._refresh_filter_state(rebuild=True)

    def _set_all_apply_filters(self, selected: bool) -> None:
        """Select or deselect every explicit Apply-disposition choice.

        Args:
            selected: Whether every Apply disposition should remain visible.
        """
        self._model.set_apply_filter(set(ALL_APPLY_FILTERS) if selected else set())
        self._requested_focus = ColumnKey.APPLY
        self._refresh_filter_state(rebuild=True)

    def _reset_all(self) -> None:
        """Clear every queue filter and synchronize the popup controls."""
        self._model.clear_filters()
        self._refresh_filter_state(rebuild=True)

    def _refresh_filter_state(self, *, rebuild: bool = False) -> None:
        """Synchronize the filter icon, Reset All, and optional direct controls.

        Args:
            rebuild: Whether all controls must reflect a bulk state change.
        """
        if self._filter_icon is not None:
            self._filter_icon.name = "FilterActive" if self._model.filters_active else "Filter"
        self._filter_changed_fn()
        self._popup_delegate.refresh_reset_enabled()
        if rebuild and self._body_frame is not None:
            if self._rebuild_handle is not None:
                self._rebuild_handle.cancel()
            self._rebuild_handle = self._main_loop.call_soon(self._rebuild_body)

    def _rebuild_body(self) -> None:
        """Rebuild direct controls after the active UI event has completed."""
        self._rebuild_handle = None
        if self._body_frame is not None:
            self._body_frame.rebuild()
            self._schedule_requested_focus()

    def destroy(self) -> None:
        """Release native value-model subscriptions and popup resources."""
        if self._rebuild_handle is not None:
            self._rebuild_handle.cancel()
            self._rebuild_handle = None
        if self._focus_task is not None:
            self._focus_task.cancel()
            self._focus_task = None
        self._subscriptions.clear()
        self._body_frame = None
        self._body_stack = None
        self._filter_icon = None
        self._search_field = None
        self._section_frames.clear()
        self._requested_focus = None
        self._scrolling_frame = None
        super().destroy()

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


__all__ = ("AbstractDragFieldGroup", "AbstractField", "DragFieldGroupCoordinator")

import abc
import asyncio
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar, cast, overload

import carb
import omni.kit.app
import omni.kit.undo
import omni.ui as ui
from omni.flux.utils.common.types import RealNumber, ScalarValue
from omni.flux.utils.widget.resources import get_icons as _get_icons


if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item
    from omni.flux.property_widget_builder.widget.tree.item_model import ItemModelBase


ItemT = TypeVar("ItemT", bound="Item")


_PRIMARY_FRAME_HEIGHT = 24
_PER_ELEMENT_SPACER_WIDTH = 8
_VSTACK_SPACER_HEIGHT = 2
_LINK_SIZE = ui.Pixel(16)
_LINK_PADDING = ui.Pixel(2)
_LINK_GAP_WIDTH = ui.Pixel(20)
_LINK_OFF_TOOLTIP = "Multi-channel edit is off. Click to copy the first value to every field and link them."
_LINK_ON_TOOLTIP = "Multi-channel edit is on. Click to unlink the fields."
_LINKED_EDITOR_IDENTIFIER = "linked_drag_field_inline_editor"


class _LinkedEditWidget(Protocol):
    """Provide the value model and presentation state used by linked editing."""

    model: ui.AbstractValueModel
    style_type_name_override: str


class _LinkedEditController:
    """Manage a numeric inline editor without changing the native drag hierarchy."""

    def __init__(
        self,
        widget: _LinkedEditWidget,
        editor_model_type: Callable[[RealNumber], ui.AbstractValueModel],
        editor_field_type: Callable[..., ui.Widget],
        get_value: Callable[[ui.AbstractValueModel], RealNumber],
    ) -> None:
        """Initialize the controller with numeric UI construction hooks."""
        self._widget = widget
        self._editor_model_type = editor_model_type
        self._editor_field_type = editor_field_type
        self._get_value = get_value
        self._text_editor: ui.Widget | None = None
        self._text_editor_model: ui.AbstractValueModel | None = None
        self._text_editor_begin_sub = None
        self._text_editor_end_sub = None
        self._text_editor_active = False
        self._underlying_edit_active = False
        self._unsubscribe_property_edit_cancel = self._widget.model.subscribe_property_edit_cancel_fn(
            self.cancel_text_edit
        )

    def build_text_editor(self, *, read_only: bool, identifier: str) -> None:
        """Build the temporary editor inside the native drag's field bounds."""
        if self._text_editor is not None:
            return

        self._text_editor_model = self._editor_model_type(self._get_value(self._widget.model))
        self._text_editor_begin_sub = self._text_editor_model.subscribe_begin_edit_fn(self._on_text_editor_begin)
        self._text_editor_end_sub = self._text_editor_model.subscribe_end_edit_fn(self._on_text_editor_end)
        self._text_editor = self._editor_field_type(
            model=self._text_editor_model,
            read_only=read_only,
            visible=False,
            identifier=identifier,
            style_type_name_override=self._widget.style_type_name_override,
        )

    def _on_text_editor_begin(self, _model: ui.AbstractValueModel) -> None:
        """Forward text-edit lifecycle to the validated value model."""
        if self._text_editor_active and not self._underlying_edit_active:
            self._widget.model.begin_edit()
            self._underlying_edit_active = True

    def _on_text_editor_end(self, model: ui.AbstractValueModel) -> None:
        """Commit the parsed value once through the existing value-model path."""
        if not self._text_editor_active and not self._underlying_edit_active:
            return
        self._finish_text_edit(model=model, commit=True)

    def _finish_text_edit(self, *, model: ui.AbstractValueModel | None, commit: bool) -> None:
        """Close the editor and balance the forwarded edit lifecycle exactly once."""
        was_active = self._text_editor_active
        self._text_editor_active = False
        try:
            if commit and was_active and self._underlying_edit_active and model is not None:
                value = self._get_value(model)
                if value != self._get_value(self._widget.model):
                    self._widget.model.set_value(value)
        finally:
            try:
                if self._underlying_edit_active:
                    self._underlying_edit_active = False
                    self._widget.model.end_edit()
            finally:
                if self._text_editor is not None:
                    self._text_editor.visible = False

    def cancel_text_edit(self) -> None:
        """Close the editor without committing stale text after an external cancel."""
        self._finish_text_edit(model=None, commit=False)

    async def focus_text_edit(self) -> None:
        """Show the inline editor with keyboard focus and selected text."""
        if self._text_editor is None or self._text_editor_model is None:
            return

        self._text_editor_model.set_value(self._get_value(self._widget.model))
        self._text_editor.style_type_name_override = self._widget.style_type_name_override
        self._text_editor.visible = True
        self._text_editor_active = True
        await omni.kit.app.get_app().next_update_async()
        if self._text_editor_active and self._text_editor is not None:
            self._text_editor.focus_keyboard()

    def hide_text_edit(self) -> None:
        """Hide the temporary editor without committing its displayed value."""
        self._finish_text_edit(model=None, commit=False)

    def destroy(self) -> None:
        """Destroy the temporary editor with the owning row."""
        self.cancel_text_edit()
        if self._unsubscribe_property_edit_cancel is not None:
            self._unsubscribe_property_edit_cancel()
            self._unsubscribe_property_edit_cancel = None
        self._text_editor_begin_sub = None
        self._text_editor_end_sub = None
        self._text_editor = None
        self._text_editor_model = None


class DragFieldGroupCoordinator:
    """Coordinate linked-row focus and preemption without consumer-specific widget access."""

    def __init__(self) -> None:
        self._states: dict[int, _DragFieldBuildState] = {}
        self._active_item_key: int | None = None
        self._focus_task: asyncio.Task | None = None

    def register(self, state: _DragFieldBuildState) -> None:
        """Register the newest visual build for one linked item."""
        if state.item_key is None:
            return
        previous_state = self._states.get(state.item_key)
        if previous_state is not None and previous_state is not state:
            previous_state.destroy()
        self._states[state.item_key] = state
        if state.link_enabled and self._active_item_key is None:
            self._active_item_key = state.item_key

    def unregister(self, state: _DragFieldBuildState) -> None:
        """Forget a visual build only when it is still the current one."""
        if state.item_key is None:
            return
        if self._states.get(state.item_key) is state:
            self._states.pop(state.item_key, None)

    def link_changed(self, state: _DragFieldBuildState, enabled: bool) -> None:
        """Preempt the active row and drive the current row's editor lifecycle."""
        if state.item_key is None:
            return
        item_key = state.item_key
        if enabled:
            if self._active_item_key != item_key:
                active_state = self._states.get(self._active_item_key) if self._active_item_key is not None else None
                if active_state is not None and active_state.item is not None:
                    if active_state.linked_edit_controller is not None:
                        active_state.linked_edit_controller.hide_text_edit()
                    self._active_item_key = None
                    self._cancel_focus()
                    active_state.item.set_linked_edit_enabled(False)
            self._active_item_key = item_key
            self._schedule_focus(item_key)
            return

        if self._active_item_key != item_key:
            return
        current_state = self._states.get(item_key)
        if current_state is not None and current_state.linked_edit_controller is not None:
            current_state.linked_edit_controller.hide_text_edit()
        self._active_item_key = None
        self._cancel_focus()

    def _schedule_focus(self, item_key: int) -> None:
        """Focus the newest visual build after tree selection/rebuild settles."""
        self._cancel_focus()

        async def focus() -> None:
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            state = self._states.get(item_key)
            if state is not None and state.link_enabled and state.linked_edit_controller is not None:
                await state.linked_edit_controller.focus_text_edit()

        self._focus_task = asyncio.ensure_future(focus())

    def _cancel_focus(self) -> None:
        """Cancel any pending linked-editor focus operation."""
        if self._focus_task is not None:
            self._focus_task.cancel()
            self._focus_task = None

    def cancel_active_text_edit(self) -> None:
        """Cancel dirty linked text before a link press can move keyboard focus."""
        active_state = self._states.get(self._active_item_key) if self._active_item_key is not None else None
        if active_state is not None and active_state.linked_edit_controller is not None:
            active_state.linked_edit_controller.cancel_text_edit()

    def reset(self) -> None:
        """Cancel deferred work and forget all rows."""
        self._cancel_focus()
        self._states.clear()
        self._active_item_key = None


class _DragFieldBuildState:
    """Track linked-edit resources for one built drag-field row."""

    def __init__(
        self,
        item: Item | None,
        identifier: str | None,
        coordinator: DragFieldGroupCoordinator,
    ) -> None:
        """Initialize one row's linked-edit state."""
        self.subs: list[object] = []
        self.item = item
        self.item_key = id(item) if item is not None else None
        self.identifier = identifier
        self.coordinator = coordinator
        self.link_widgets: list[ui.Image] = []
        self.linked_edit_controller: _LinkedEditController | None = None
        self.link_enabled = item.linked_edit_enabled if item is not None else False
        self.routing_value = False

    def destroy(self) -> None:
        """Release subscriptions, widgets, tasks, and controller resources."""
        self.coordinator.unregister(self)
        if self.linked_edit_controller is not None:
            self.linked_edit_controller.destroy()
            self.linked_edit_controller = None
        self.subs.clear()
        self.link_widgets.clear()
        self.item = None
        self.item_key = None
        self.identifier = None


class AbstractField(Generic[ItemT]):
    """
    AbstractField that stores a style_name attribute to be used within `build_ui` for styling widgets.
    """

    def __init__(self, style_name: str = "PropertiesWidgetField", identifier: None | str = None) -> None:
        self.style_name = style_name
        self.identifier = identifier

    def __call__(self, item: ItemT, **kwargs) -> ui.Widget | list[ui.Widget] | None:
        return self.build_ui(item, **kwargs)

    @abc.abstractmethod
    def build_ui(self, item: ItemT, **kwargs) -> ui.Widget | list[ui.Widget] | None:
        raise NotImplementedError

    @staticmethod
    def set_dynamic_tooltip_fn(widget: ui.Widget, item_value_model: ItemModelBase) -> None:
        """Helper method to set dynamic tooltip function on a built widget."""

        def update_tooltip(_hovered: bool):
            tool_tip = item_value_model.get_tool_tip()

            if tool_tip is not None:
                widget.tooltip = tool_tip

        widget.set_mouse_hovered_fn(update_tooltip)

    @staticmethod
    def set_style_state(widget: ui.Widget, selected: bool | None = None, mixed: bool | None = None) -> None:
        """Update selected and mixed suffixes on a field's style override."""
        style_override = widget.style_type_name_override

        def strip_suffix(style: str, suffix: str, enabled: bool | None) -> tuple[str, bool | None]:
            """Strip one existing suffix while preserving its state when unspecified."""
            if style.endswith(suffix):
                return style[: -len(suffix)], True if enabled is None else enabled
            return style, enabled

        selected_suffix = "Selected"
        mixed_suffix = "Mixed"
        style_override, mixed = strip_suffix(style_override, mixed_suffix, mixed)
        style_override, selected = strip_suffix(style_override, selected_suffix, selected)
        if selected:
            style_override = f"{style_override}{selected_suffix}"
        if mixed:
            style_override = f"{style_override}{mixed_suffix}"
        if widget.style_type_name_override != style_override:
            widget.style_type_name_override = style_override


class AbstractDragFieldGroup(AbstractField):
    """Abstract base for drag-style delegates with optional min/max bounds and step.

    Subclasses must implement :meth:`build_drag_widget` to create the actual
    drag widget instance. Edit events are grouped for undo via
    :meth:`begin_edit` and :meth:`end_edit`.

    Hard bounds (``hard_min_value`` / ``hard_max_value``) are forwarded to the
    widget, which is responsible for value clamping behavior. Soft bounds are
    drag-range hints only and are not promoted to typed-value clamps. Bounded
    drag widgets also use a matching hard bound as the drag bound when that
    soft side is omitted.

    API note:
        This class was renamed from ``AbstractDragField`` to
        ``AbstractDragFieldGroup`` to make it explicit that it orchestrates one
        or more drag widgets (for scalar/vector channels) rather than being a
        single concrete drag widget itself.
    """

    def __init__(
        self,
        min_value: ScalarValue | None = None,
        max_value: ScalarValue | None = None,
        hard_min_value: ScalarValue | None = None,
        hard_max_value: ScalarValue | None = None,
        step: ScalarValue | None = None,
        linkable: bool = False,
        **kwargs,
    ):
        """Initialize the drag field.

        Args:
            min_value: Soft minimum for the drag range. May be scalar or
                sequence-like for per-channel resolution. ``None`` = unbounded.
            max_value: Soft maximum for the drag range. May be scalar or
                sequence-like for per-channel resolution. ``None`` = unbounded.
            hard_min_value: Hard minimum bound forwarded to drag widgets for
                typed-value clamping via widget pre-set callbacks. May be scalar
                or sequence-like for per-channel resolution.
            hard_max_value: Hard maximum bound forwarded to drag widgets for
                typed-value clamping via widget pre-set callbacks. May be scalar
                or sequence-like for per-channel resolution.
            step: Optional step size; scalar or sequence-like values are
                resolved per channel in ``build_ui``.
            linkable: Whether multi-value items expose native linked editing.
            **kwargs: Passed to AbstractField (e.g. style_name, identifier).
        """
        super().__init__(**kwargs)
        self._build_states: list[_DragFieldBuildState] = []
        self._link_coordinator = DragFieldGroupCoordinator()
        self.linkable = linkable

        if isinstance(min_value, RealNumber) and isinstance(max_value, RealNumber) and min_value >= max_value:
            raise ValueError(f"min_value ({min_value}) must be less than max_value ({max_value})")

        self.min_value = min_value
        self.max_value = max_value

        self.hard_min_value = hard_min_value
        self.hard_max_value = hard_max_value

        self.step = step

    def begin_edit(self, model: ItemModelBase) -> None:
        """Start an undo group for non-batched edits.

        Typed edits use this begin/end pair directly. Drag edits on batch-capable
        models open and close their undo group from the widget mouse callbacks.
        """
        if model.supports_batch_edit:
            return
        omni.kit.undo.begin_group()

    def end_edit(self, model: ItemModelBase) -> None:
        """End the current edit.

        For batch-edit models, this closes any active drag batch if needed.
        For non-batch models, this closes the regular undo group.
        """
        if model.supports_batch_edit:
            if model.is_batch_editing:
                model.end_batch_edit()
            return
        omni.kit.undo.end_group()

    @abc.abstractmethod
    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: RealNumber | None,
        max_val: RealNumber | None,
        hard_min_val: RealNumber | None,
        hard_max_val: RealNumber | None,
        step: RealNumber | None,
    ) -> ui.Widget:
        """Build the drag widget for one value model.

        Args:
            model: Value model to bind to the widget.
            style_type_name_override: Style name for the widget (e.g. read-only variant).
            read_only: Whether the widget should be read-only.
            min_val: Minimum value for the widget, or ``None`` for unbounded.
            max_val: Maximum value for the widget, or ``None`` for unbounded.
            hard_min_val: Hard minimum value for typed-value clamping, or
                ``None`` for no lower hard bound.
            hard_max_val: Hard maximum value for typed-value clamping, or
                ``None`` for no upper hard bound.
            step: Step size for the widget, or ``None`` to omit.

        Returns:
            The built drag widget (typically ``FloatBoundedDrag``/``IntBoundedDrag`` wrappers
            or other ``ui.Widget``-compatible drag controls).
        """
        raise NotImplementedError

    @staticmethod
    @overload
    def _resolve_scalar_component(value: ScalarValue | None, scalar_index: None) -> ScalarValue | None: ...

    @staticmethod
    @overload
    def _resolve_scalar_component(value: ScalarValue | None, scalar_index: int) -> RealNumber | None: ...

    @staticmethod
    def _resolve_scalar_component(value: ScalarValue | None, scalar_index: int | None) -> ScalarValue | None:
        """Resolve a channel scalar from bounds/step, or return input when index is None."""
        if scalar_index is None:
            return value
        if isinstance(value, (int, float)):
            return value

        if value is None:
            return None

        try:
            # Keep panel rendering resilient: if one attribute provides malformed
            # bounds metadata, fail this component gracefully instead of crashing
            # the whole properties panel build.
            return cast(ScalarValue, value[scalar_index])
        except (IndexError, KeyError, TypeError):
            carb.log_error(f"Failed to resolve bounds component at index {scalar_index} from value {value!r}")
            return None

    def destroy(self) -> None:
        """Release resources retained for every built drag-field row."""
        for state in tuple(self._build_states):
            state.destroy()
        self._build_states.clear()
        self._link_coordinator.reset()

    def _create_build_state(
        self,
        register_cleanup: Callable[[Callable[[], None]], None] | None,
        item: Item | None,
        identifier: str | None,
        coordinator: DragFieldGroupCoordinator,
    ) -> _DragFieldBuildState:
        """Create linked-edit state and register its row cleanup callback."""
        if register_cleanup is None:
            self.destroy()
        state = _DragFieldBuildState(item, identifier, coordinator)
        self._build_states.append(state)
        coordinator.register(state)

        def cleanup() -> None:
            state.destroy()
            with suppress(ValueError):
                self._build_states.remove(state)

        if register_cleanup is not None:
            register_cleanup(cleanup)
        return state

    def _get_linked_edit(self, item: Item) -> Item | None:
        """Return an item when it is eligible for shared linked editing."""
        if not self.linkable or item.element_count < 2 or item.read_only:
            return None
        return item

    @staticmethod
    def _on_model_value_changed(state: _DragFieldBuildState, element_index: int, model: ItemModelBase) -> None:
        """Route a channel change through the consumer's linked-value callback."""
        item = state.item
        if item is None or not state.link_enabled or state.routing_value:
            return
        state.routing_value = True
        try:
            item.synchronize_linked_edit_value(element_index, model.get_value())
        finally:
            state.routing_value = False

    def _build_linked_edit_controller(
        self, widget: ui.Widget, read_only: bool, identifier: str
    ) -> _LinkedEditController | None:
        """Build the shared inline editor when a numeric group supplies its UI hooks."""
        model_type = self._get_linked_edit_model_type()
        field_type = self._get_linked_edit_field_type()
        if model_type is None or field_type is None:
            return None
        controller = _LinkedEditController(
            cast(_LinkedEditWidget, widget),
            model_type,
            field_type,
            self._get_linked_edit_value,
        )
        controller.build_text_editor(read_only=read_only, identifier=identifier)
        return controller

    @staticmethod
    def _get_linked_edit_model_type() -> Callable[[RealNumber], ui.AbstractValueModel] | None:
        """Return the numeric model factory used by the linked inline editor."""
        return None

    @staticmethod
    def _get_linked_edit_field_type() -> Callable[..., ui.Widget] | None:
        """Return the numeric field type used by the linked inline editor."""
        return None

    @staticmethod
    def _get_linked_edit_value(_model: ui.AbstractValueModel) -> RealNumber:
        """Return the numeric value used by the linked inline editor."""
        raise NotImplementedError

    @staticmethod
    def _set_link_style(link_widget: ui.Image, selected: bool) -> None:
        """Synchronize a link icon and tooltip with linked-edit state."""
        link_widget.name = "Link" if selected else "LinkOff"
        link_widget.source_url = _get_icons("link" if selected else "link-off") or ""
        link_widget.tooltip = _LINK_ON_TOOLTIP if selected else _LINK_OFF_TOOLTIP

    @staticmethod
    def _on_link_released(item: Item | None, button: int) -> None:
        """Toggle linked editing after a primary-button link click."""
        if button == 0 and item is not None:
            item.toggle_linked_edit()

    def _on_linked_edit_changed(
        self,
        state: _DragFieldBuildState,
        widgets: list[ui.Widget],
        selected: bool,
    ) -> None:
        """Update linked presentation and the first-field editor lifecycle."""
        state.link_enabled = selected
        for widget in widgets:
            self.set_style_state(widget, selected=False)
        if state.item is not None:
            for link_widget in state.link_widgets:
                self._set_link_style(link_widget, selected)
        state.coordinator.link_changed(state, selected)

    def _build_element_separator(self, _item, element_index: int, state: _DragFieldBuildState) -> None:
        """Build normal spacing or a linked-edit control before one element."""
        linked_item = state.item
        if linked_item is None or element_index == 0:
            ui.Spacer(width=ui.Pixel(_PER_ELEMENT_SPACER_WIDTH))
            return

        with ui.VStack(width=_LINK_GAP_WIDTH):
            ui.Spacer()
            with ui.HStack(height=_LINK_GAP_WIDTH, spacing=_LINK_PADDING):
                ui.Spacer(width=0, height=0)
                with ui.VStack(spacing=_LINK_PADDING):
                    ui.Spacer(width=0, height=0)
                    link_widget = ui.Image(
                        _get_icons("link" if state.link_enabled else "link-off") or "",
                        name="Link" if state.link_enabled else "LinkOff",
                        width=_LINK_SIZE,
                        height=_LINK_SIZE,
                        tooltip=_LINK_ON_TOOLTIP if state.link_enabled else _LINK_OFF_TOOLTIP,
                        opaque_for_mouse_events=True,
                        identifier=state.identifier,
                        mouse_pressed_fn=lambda _x, _y, button, _modifier: (
                            state.coordinator.cancel_active_text_edit() if button == 0 else None
                        ),
                        mouse_released_fn=lambda _x, _y, button, _modifier: self._on_link_released(linked_item, button),
                    )
                    ui.Spacer(width=0, height=0)
                ui.Spacer(width=0, height=0)
            ui.Spacer()
        state.link_widgets.append(link_widget)

    def build_ui(self, item, **kwargs) -> list[ui.Widget]:  # PLW0221
        """Build drag widgets for each element of the item, with undo grouping and tooltips."""
        register_cleanup = kwargs.pop("register_cleanup", None)
        coordinator = kwargs.pop("linked_edit_coordinator", None) or self._link_coordinator
        linked_item = self._get_linked_edit(item)
        identifier = None
        if linked_item is not None:
            row_name = "".join(model.get_value_as_string() for model in item.name_models)
            identifier = f"linked_drag_field_link_{row_name}"
        state = self._create_build_state(register_cleanup, linked_item, identifier, coordinator)
        widgets: list[ui.Widget] = []
        with ui.HStack(height=ui.Pixel(_PRIMARY_FRAME_HEIGHT)):
            for i in range(item.element_count):
                value_model = item.value_models[i]
                state.subs.append(value_model.subscribe_begin_edit_fn(self.begin_edit))
                state.subs.append(value_model.subscribe_end_edit_fn(self.end_edit))
                if linked_item is not None:
                    state.subs.append(
                        value_model.subscribe_value_changed_fn(
                            lambda model, index=i: self._on_model_value_changed(state, index, model)
                        )
                    )

                min_value = self._resolve_scalar_component(self.min_value, i)
                max_value = self._resolve_scalar_component(self.max_value, i)
                hard_min_value = self._resolve_scalar_component(self.hard_min_value, i)
                hard_max_value = self._resolve_scalar_component(self.hard_max_value, i)
                step_value = self._resolve_scalar_component(self.step, i)

                if min_value is not None and max_value is not None and min_value >= max_value:
                    carb.log_warn(
                        f"Drag bounds ignored for channel {i}: min ({min_value}) must be less than max ({max_value})."
                    )
                    min_value = None
                    max_value = None

                if step_value is not None:
                    step_value = abs(step_value)

                effective_hard_min = hard_min_value
                effective_hard_max = hard_max_value
                if (
                    effective_hard_min is not None
                    and effective_hard_max is not None
                    and effective_hard_min >= effective_hard_max
                ):
                    carb.log_warn(
                        f"Hard bounds ignored for channel {i}: hard_min ({effective_hard_min}) "
                        f"must be less than hard_max ({effective_hard_max})."
                    )
                    effective_hard_min = None
                    effective_hard_max = None

                self._build_element_separator(item, i, state)
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(_VSTACK_SPACER_HEIGHT))
                    style_type_name_override = f"{self.style_name}Read" if value_model.read_only else self.style_name
                    if linked_item is not None and i == 0:
                        with ui.ZStack():
                            widget = self.build_drag_widget(
                                value_model,
                                style_type_name_override,
                                value_model.read_only,
                                min_value,
                                max_value,
                                effective_hard_min,
                                effective_hard_max,
                                step_value,
                            )
                            state.linked_edit_controller = self._build_linked_edit_controller(
                                widget, value_model.read_only, _LINKED_EDITOR_IDENTIFIER
                            )
                    else:
                        widget = self.build_drag_widget(
                            value_model,
                            style_type_name_override,
                            value_model.read_only,
                            min_value,
                            max_value,
                            effective_hard_min,
                            effective_hard_max,
                            step_value,
                        )
                    self.set_dynamic_tooltip_fn(widget, value_model)
                    widgets.append(widget)
                    state.subs.append(
                        value_model.subscribe_begin_edit_fn(
                            lambda _model, current_widget=widget: self.set_style_state(
                                current_widget, selected=not state.link_enabled
                            )
                        )
                    )
                    state.subs.append(
                        value_model.subscribe_end_edit_fn(
                            lambda _model, current_widget=widget: self.set_style_state(current_widget, selected=False)
                        )
                    )
                    ui.Spacer(height=ui.Pixel(_VSTACK_SPACER_HEIGHT))
        if linked_item is not None:
            state.subs.append(
                linked_item.subscribe_linked_edit_changed(
                    lambda selected: self._on_linked_edit_changed(state, widgets, selected)
                )
            )
            for link_widget in state.link_widgets:
                self._set_link_style(link_widget, state.link_enabled)
        return widgets

    def __del__(self):
        self.destroy()

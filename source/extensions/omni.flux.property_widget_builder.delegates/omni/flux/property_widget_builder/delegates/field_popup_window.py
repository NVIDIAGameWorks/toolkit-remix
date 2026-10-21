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

import weakref
from collections.abc import Callable
from traceback import format_exc

from carb import log_error
from carb.eventdispatcher import get_eventdispatcher
from carb.input import (
    KEYBOARD_MODIFIER_FLAG_ALT,
    KEYBOARD_MODIFIER_FLAG_CONTROL,
    KEYBOARD_MODIFIER_FLAG_SHIFT,
    KEYBOARD_MODIFIER_FLAG_SUPER,
    DeviceType,
    InputEvent,
    KeyboardEventType,
    KeyboardInput,
    MouseInput,
    acquire_input_interface,
)
from omni import ui
from omni.appwindow import get_default_app_window
from omni.flux.utils.common.mouse import get_mouse_position
from omni.kit.app import GLOBAL_EVENT_UPDATE
from omni.usd import StageEventType, get_context

__all__ = ["FieldPopupWindow"]

_WINDOW_MARGIN = 8.0
_WINDOW_FLAGS = ui.WINDOW_FLAGS_NO_DOCKING | ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_SCROLLBAR
_WINDOW_IDENTITY = "###PropertyPanelFloatingEditor"
_SHORTCUT_MODIFIERS = (
    KEYBOARD_MODIFIER_FLAG_CONTROL
    | KEYBOARD_MODIFIER_FLAG_SHIFT
    | KEYBOARD_MODIFIER_FLAG_ALT
    | KEYBOARD_MODIFIER_FLAG_SUPER
)
_MOUSE_BUTTONS = (
    MouseInput.LEFT_BUTTON,
    MouseInput.RIGHT_BUTTON,
    MouseInput.MIDDLE_BUTTON,
    MouseInput.FORWARD_BUTTON,
    MouseInput.BACK_BUTTON,
)
_ACTIVE_WINDOW: FieldPopupWindow | None = None
_PENDING_WINDOW: tuple[FieldPopupWindow, tuple[float, float], tuple[float, float, float, float] | None] | None = None


class FieldPopupWindow(ui.Window):
    """Host one disposable property popup, with at most one active window application-wide."""

    def __init__(
        self,
        *,
        title: str,
        context_name: str | None,
        pre_open_fn: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        """Construct a hidden native window without preparing data or building content.

        Args:
            title: Visible native-window title supplied by the concrete popup.
            context_name: Owning USD context, or None for a field without scene-selection tracking.
            pre_open_fn: Optional preparation callback receiving a guarded continuation before activation.
        """
        self.__context_name = context_name
        self.__pre_open_fn = pre_open_fn
        self.__selection_subscription = None
        self.__selection_snapshot = None
        self.__pre_open_token = None
        self.__opened = False
        self._closing = False
        self.__destroyed = False
        self.__cleanup_subscription = None
        self.__update_subscription = None
        self.__keyboard_subscription = None
        self.__input_interface = None
        self.__mouse = None
        self.__mouse_buttons_down: set[MouseInput] = set()
        super().__init__(
            f"{title}{_WINDOW_IDENTITY}_{id(self):x}",
            visible=False,
            flags=_WINDOW_FLAGS,
            padding_x=0,
            padding_y=0,
            exclusive_keyboard=False,
        )
        # Native drag capture can consume input before the application-level subscription.
        self.set_key_pressed_fn(self._on_key_pressed)
        self.set_visibility_changed_fn(self.__on_visibility_changed)

    @property
    def is_open(self) -> bool:
        """Whether this window has visible active content rather than pending or closing content."""
        return not self._closing and self.visible

    def open(
        self,
        *,
        preferred_size: tuple[float, float],
        anchor_rect: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Prepare this window once, or focus it when already visible.

        Geometry is captured before preparation can refresh the row. Continuations are one-shot and invalidated by
        close or destruction. Only the latest activation-ready request builds after outgoing content detaches and
        its window is destroyed. Opening a closed window does nothing.

        Ordinary closure defers detachment and cleanup by one update. Build failure finalizes never-displayed content
        immediately. Direct errors propagate; deferred errors are logged with their traceback.

        Args:
            preferred_size: Initial width and height in logical pixels, clamped to the workspace.
            anchor_rect: Launcher left, top, width, and height in logical application coordinates, or None to center.
        """
        if self._closing:
            return
        if self.is_open:
            self.focus()
            return
        if self.__opened:
            return
        self.__opened = True
        preferred_size = tuple(preferred_size)
        anchor_rect = tuple(anchor_rect) if anchor_rect is not None else None
        token = self.__pre_open_token = object()
        activate_ref = weakref.WeakMethod(self.__request_open)

        def activate_if_current() -> None:
            """Ignore continuations whose requesting row no longer owns the opening."""
            activate = activate_ref()
            if activate is not None:
                activate(token, preferred_size, anchor_rect)

        try:
            self.__watch_selection()
            if self.__pre_open_fn is None:
                activate_if_current()
            else:
                self.__pre_open_fn(activate_if_current)
        except Exception:
            try:
                self.__finalize()
            except Exception:  # noqa: BLE001 - Carb logs the full exception traceback.
                log_error(f"Failed to clean up a failed property-panel floating editor opening\n{format_exc()}")
            raise

    def close(self) -> None:
        """Close this window permanently, deferring cleanup only for activated content."""
        global _PENDING_WINDOW
        if self._closing:
            return
        self._closing = True
        self.__pre_open_token = None
        self.__stop_selection_watch()
        if _PENDING_WINDOW is not None and _PENDING_WINDOW[0] is self:
            _PENDING_WINDOW = None
        if _ACTIVE_WINDOW is not self:
            self.__finalize()
            return
        self.__begin_close()

    def destroy(self) -> None:
        """Close this window permanently through the ordered cleanup path."""
        self.close()

    def _on_outside_click(self) -> None:
        """Dismiss this window when a click falls outside its bounds."""
        self.close()

    def _build_content(self) -> None:
        """Build this opening's content after preparation."""
        raise NotImplementedError

    def _release_content(self) -> None:
        """Release this opening's resources, tolerating absent or partially constructed content."""
        return

    def _on_key_pressed(self, key: int, modifiers: int, is_down: bool) -> None:
        """Close on unmodified Escape delivered to this focused native window."""
        if key == int(KeyboardInput.ESCAPE) and is_down and not modifiers & _SHORTCUT_MODIFIERS:
            self.close()

    def __request_open(self, token, preferred_size, anchor_rect) -> None:
        global _PENDING_WINDOW
        if self.__pre_open_token is not token:
            return
        self.__pre_open_token = None
        pending, _PENDING_WINDOW = _PENDING_WINDOW, (self, preferred_size, anchor_rect)
        if pending is not None and pending[0] is not self:
            pending[0].close()
        if _PENDING_WINDOW is None or _PENDING_WINDOW[0] is not self:
            return
        if _ACTIVE_WINDOW is not None:
            _ACTIVE_WINDOW.close()
        else:
            _PENDING_WINDOW = None
            self.__activate(preferred_size, anchor_rect)

    def __activate(self, preferred_size, anchor_rect) -> None:
        global _ACTIVE_WINDOW
        # Selection events may dispatch after the update that finalizes the outgoing editor.
        if self.__selection_snapshot is not None:
            selection, selected_paths = self.__selection_snapshot
            if selection.get_selected_prim_paths() != selected_paths:
                self.close()
                return
        _ACTIVE_WINDOW = self
        try:
            self.__apply_geometry(preferred_size, anchor_rect)
            if self._closing:
                return
            with self.frame:
                self._build_content()
            if not self._closing:
                self.visible = True
                self.__start_input_watch()
                self.focus()
        except Exception:
            try:
                self.__finalize()
            except Exception:  # noqa: BLE001 - Carb logs the full exception traceback.
                log_error(f"Failed to clean up a failed property-panel floating editor build\n{format_exc()}")
            raise

    def __apply_geometry(self, preferred_size, anchor_rect) -> None:
        workspace_width = float(ui.Workspace.get_main_window_width())
        workspace_height = float(ui.Workspace.get_main_window_height())
        width = min(max(0.0, float(preferred_size[0])), max(0.0, workspace_width - 2 * _WINDOW_MARGIN))
        height = min(max(0.0, float(preferred_size[1])), max(0.0, workspace_height - 2 * _WINDOW_MARGIN))
        self.width = width
        self.height = height
        position_x = (workspace_width - width) / 2
        position_y = (workspace_height - height) / 2
        if anchor_rect is not None and anchor_rect[2] > 0 and anchor_rect[3] > 0:
            anchor_x, anchor_y, anchor_width, anchor_height = anchor_rect
            right_x = anchor_x + anchor_width + _WINDOW_MARGIN
            left_space = anchor_x - 2 * _WINDOW_MARGIN
            right_space = workspace_width - _WINDOW_MARGIN - right_x
            if right_space >= width or (left_space < width and right_space >= left_space):
                position_x = right_x
            else:
                position_x = anchor_x - _WINDOW_MARGIN - width
            position_y = anchor_y + (anchor_height - height) / 2
        self.position_x = max(_WINDOW_MARGIN, min(position_x, workspace_width - _WINDOW_MARGIN - width))
        self.position_y = max(_WINDOW_MARGIN, min(position_y, workspace_height - _WINDOW_MARGIN - height))

    def __begin_close(self) -> None:
        self.__stop_input_watch()
        self.visible = False
        self.__cleanup_subscription = get_eventdispatcher().observe_event(
            order=0,
            event_name=GLOBAL_EVENT_UPDATE,
            on_event=self.__on_cleanup_update,
            observer_name="PropertyPanelFloatingEditorCleanup",
        )

    def __on_cleanup_update(self, _event) -> None:
        try:
            self.__finalize()
        except Exception:  # noqa: BLE001 - Carb logs the full exception traceback.
            log_error(f"Failed to clean up property-panel floating editor content\n{format_exc()}")

    def __finalize(self) -> None:
        global _ACTIVE_WINDOW, _PENDING_WINDOW
        if self.__destroyed:
            return
        self._closing = True
        self.__pre_open_token = None
        if _PENDING_WINDOW is not None and _PENDING_WINDOW[0] is self:
            _PENDING_WINDOW = None
        try:
            # Protect content and native release even if sequential observer bookkeeping fails.
            try:
                try:
                    self.visible = False
                    if self.__cleanup_subscription is not None:
                        self.__cleanup_subscription.reset()
                    self.__stop_input_watch()
                    self.__stop_selection_watch()
                finally:
                    self.frame.clear()
            finally:
                self._release_content()
        finally:
            try:
                super().destroy()
            finally:
                self.__destroyed = True
                self.__pre_open_fn = None
                self.__cleanup_subscription = None
                if _ACTIVE_WINDOW is self:
                    _ACTIVE_WINDOW = None
                    pending, _PENDING_WINDOW = _PENDING_WINDOW, None
                    if pending is not None:
                        try:
                            FieldPopupWindow.__activate(pending[0], pending[1], pending[2])
                        except Exception:  # noqa: BLE001 - Carb logs the full exception traceback.
                            log_error(f"Failed to build deferred property-panel floating editor\n{format_exc()}")

    def __watch_selection(self) -> None:
        if self.__context_name is None:
            return
        context = get_context(self.__context_name)
        if context is None:
            raise RuntimeError(f"USD context is not registered: {self.__context_name!r}")
        selection = context.get_selection()
        self.__selection_snapshot = (selection, selection.get_selected_prim_paths())
        self.__selection_subscription = get_eventdispatcher().observe_event(
            event_name=context.stage_event_name(StageEventType.SELECTION_CHANGED),
            on_event=lambda _event: self.close(),
            observer_name="PropertyPanelFloatingEditorSelection",
        )

    def __stop_selection_watch(self) -> None:
        self.__selection_snapshot = None
        if self.__selection_subscription is not None:
            self.__selection_subscription.reset()
            self.__selection_subscription = None

    def __start_input_watch(self) -> None:
        app_window = get_default_app_window()
        self.__input_interface = acquire_input_interface()
        # Insert before existing UI/hotkey subscribers, including when a child picker has focus.
        self.__keyboard_subscription = self.__input_interface.subscribe_to_input_events(self.__on_input, order=0)
        self.__mouse = app_window.get_mouse() if app_window else None
        self.__mouse_buttons_down = {
            button
            for button in _MOUSE_BUTTONS
            if self.__mouse and self.__input_interface.get_mouse_value(self.__mouse, button)
        }
        self.__update_subscription = get_eventdispatcher().observe_event(
            order=0,
            event_name=GLOBAL_EVENT_UPDATE,
            on_event=self.__check_outside_click,
            observer_name="PropertyPanelFloatingEditorOutsideClick",
        )

    def __stop_input_watch(self) -> None:
        if self.__keyboard_subscription is not None:
            self.__input_interface.unsubscribe_to_input_events(self.__keyboard_subscription)
            self.__keyboard_subscription = None
        if self.__update_subscription is not None:
            self.__update_subscription.reset()
        self.__update_subscription = None
        self.__input_interface = None
        self.__mouse = None
        self.__mouse_buttons_down.clear()

    def __check_outside_click(self, _event) -> None:
        if not self.is_open or self.__input_interface is None or self.__mouse is None:
            return
        buttons_down = {
            button for button in _MOUSE_BUTTONS if self.__input_interface.get_mouse_value(self.__mouse, button)
        }
        just_pressed = buttons_down - self.__mouse_buttons_down
        self.__mouse_buttons_down = buttons_down
        if not just_pressed:
            return
        mouse_position = get_mouse_position()
        if mouse_position is None:
            return
        mouse_x, mouse_y = mouse_position
        if not (
            self.position_x <= mouse_x <= self.position_x + self.width
            and self.position_y <= mouse_y <= self.position_y + self.height
        ):
            self._on_outside_click()

    def __on_input(self, event: InputEvent) -> bool:
        if not self.is_open or event.deviceType != DeviceType.KEYBOARD:
            return True
        keyboard = event.event
        if (
            keyboard.type != KeyboardEventType.KEY_PRESS
            or keyboard.input != KeyboardInput.ESCAPE
            or keyboard.modifiers & _SHORTCUT_MODIFIERS
        ):
            return True
        self.close()
        return False

    def __on_visibility_changed(self, visible: bool) -> None:
        if not visible:
            self.close()

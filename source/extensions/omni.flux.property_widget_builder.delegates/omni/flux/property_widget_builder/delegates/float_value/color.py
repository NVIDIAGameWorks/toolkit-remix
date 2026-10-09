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

__all__ = ("ColorField",)

from functools import partial

import carb.input
import omni.ui as ui
from omni.kit.app import get_app
from omni.kit.commands import POST_DO_CALLBACK, register_callback, unregister_callback
from pxr import Gf

from ..base import AbstractField


class ColorValueModel(ui.AbstractValueModel):
    """
    Wrapper value model that allows for tweaking how the value is displayed as a string.
    """

    def __init__(self, parent: ui.AbstractValueModel, display_precision: int = 2):
        super().__init__()
        self._parent = parent
        self.display_precision = display_precision
        # Echo any value changes to ensure the widget updates
        self._sub = parent.subscribe_value_changed_fn(lambda _: self._value_changed())

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)
        return getattr(self._parent, attr)

    def get_value_as_string(self):
        return f"{self._parent.get_value_as_float():.{self.display_precision}f}"


class ColorField(AbstractField):
    """Delegate of the tree"""

    _WRITE_COLOR = 1
    _CHECKPOINT_COLOR = 2
    _DISMISS_PICKER = 3

    def __init__(self, display_precision: int = 2, style_name: str = "ColorsWidgetFieldRead"):
        super().__init__(style_name=style_name)

        self.display_precision = display_precision

        # The color widget is a bit unique as the provided item's model is not used directly within the widget. We
        # instead connect change events between the two models to ensure that updates properly flow both ways.
        self._color_widget_begin_edit_subscription = None
        self._color_widget_changed_sub = None
        self._color_widget_item_changed_subscription = None
        self._update_subscription = None
        self._pending_action = None
        self._value_model_value_changed_sub = None
        self._unsubscribe_property_edit_cancel = None
        self._value_model = None
        self._picker_window = None
        self._undo_callback_id = None
        self._mouse_input_subscription_id = None

        # Both change callbacks ignore updates echoed from the other model.
        self._ignore_value_change_events = False
        self._picker_edit_cancelled = False
        self._batch_editing = False
        self._value_model_editing = False

    def build_ui(self, item, *, register_cleanup=None) -> list[ui.Widget]:
        """Build the color field and connect its cleanup to the owning property row.

        Args:
            item: Property row whose value model stores the color vector.
            register_cleanup: Optional callback that registers field cleanup with the owning delegate.
        """
        if len(item.value_models) != 1:
            raise ValueError("Expected 1 value_model that holds the vector values")

        self.cleanup()
        value_model = item.value_models[0]
        self._value_model = value_model
        self._picker_edit_cancelled = False
        vec = value_model.get_attributes_raw_value(0)
        if vec is None:
            vec = Gf.Vec3f(0, 0, 0)

        widgets = []

        with ui.HStack(height=ui.Pixel(24)):
            ui.Spacer(width=ui.Pixel(8))
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(2))
                color_widget = ui.ColorWidget(*vec, name=self.style_name, enabled=not value_model.read_only)
                widgets.append(color_widget)
                ui.Spacer(height=ui.Pixel(2))

            ui.Spacer(width=ui.Pixel(4))

            component_models = tuple(
                color_widget.model.get_item_value_model(child) for child in color_widget.model.get_item_children()
            )
            for index, child_model in enumerate(component_models):
                ui.Spacer(width=ui.Pixel(4))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
                    widgets.append(
                        ui.StringField(
                            model=ColorValueModel(child_model, display_precision=self.display_precision),
                            style_type_name_override=self.style_name,
                            read_only=True,
                        )
                    )
                    ui.Spacer(height=ui.Pixel(2))
                if index < len(vec) - 1:
                    ui.Spacer(width=ui.Pixel(4))
                    with ui.VStack(width=ui.Pixel(1)):
                        ui.Spacer(height=ui.Pixel(4))
                        ui.Rectangle(name="ColorsWidgetSeparator")
                        ui.Spacer(height=ui.Pixel(4))

            # The picker changes RGB components separately; author the completed color once per frame.
            self._color_widget_item_changed_subscription = color_widget.model.subscribe_item_changed_fn(
                partial(self._color_widget_item_changed, type(vec), value_model, component_models)
            )
            self._color_widget_begin_edit_subscription = color_widget.model.subscribe_begin_edit_fn(
                partial(self._color_widget_begin_edit, type(vec), value_model, component_models)
            )
            # Closing the picker commits the final value and ends its backing model edit session.
            self._color_widget_changed_sub = color_widget.model.subscribe_end_edit_fn(
                partial(self._color_widget_changed, type(vec), value_model, component_models)
            )

        self._value_model_value_changed_sub = value_model.subscribe_value_changed_fn(
            partial(self._value_model_changed, component_models)
        )
        self._unsubscribe_property_edit_cancel = value_model.subscribe_property_edit_cancel_fn(self._cancel_edit)
        if register_cleanup is not None:
            # Delegate reset can release the row while its backing model remains alive.
            register_cleanup(self.cleanup)

        return widgets

    def cleanup(self) -> None:
        """Release field subscriptions and close any active picker edit sessions."""
        self._stop_watching_popup()
        if self._unsubscribe_property_edit_cancel is not None:
            self._unsubscribe_property_edit_cancel()
            self._unsubscribe_property_edit_cancel = None
        self._color_widget_item_changed_subscription = None
        self._color_widget_begin_edit_subscription = None
        self._color_widget_changed_sub = None
        self._value_model_value_changed_sub = None
        self._cancel_edit()
        self._value_model = None

    def _cancel_edit(self) -> None:
        """Discard a cancelled popup's buffered input while keeping the row reusable."""
        self._picker_edit_cancelled = True
        self._stop_watching_mouse()
        if self._pending_action != self._DISMISS_PICKER:
            self._clear_pending_update()
        self._end_edit()

    def _color_widget_begin_edit(self, vec_type, value_model, component_models, _model, _item):
        """Accept new picker input when the native popup opens again."""
        if value_model is not self._value_model:
            return
        self._picker_edit_cancelled = False
        self._picker_window = next(
            (
                window
                for window in reversed(ui.Workspace.get_windows())
                if isinstance(window, ui.Window) and window.focused
            ),
            None,
        )
        if self._picker_window is not None and self._undo_callback_id is None:
            self._undo_callback_id = register_callback(
                "Undo", POST_DO_CALLBACK, partial(self._on_undo, vec_type, value_model, component_models)
            )
        if self._picker_window is not None and value_model.supports_batch_edit:
            self._mouse_input_subscription_id = carb.input.acquire_input_interface().subscribe_to_input_events(
                partial(self._on_picker_mouse_input, vec_type, value_model, component_models),
                device=self._picker_window.app_window.get_mouse(),
                order=0,
            )

    def _on_picker_mouse_input(self, vec_type, value_model, component_models, event):
        """Checkpoint completed mouse edits without consuming native picker input."""
        if event.event.type == carb.input.MouseEventType.LEFT_BUTTON_UP and not self._picker_edit_cancelled:
            # Native popup controls expose no per-drag edit callbacks. Wait for their final RGB update.
            self._schedule_update(self._CHECKPOINT_COLOR, vec_type, value_model, component_models)
        return True

    def _schedule_update(self, action, vec_type, value_model, component_models):
        """Queue the highest-priority picker action for the next application update."""
        if value_model is not self._value_model or (
            self._pending_action is not None and action <= self._pending_action
        ):
            return
        self._pending_action = action
        if self._update_subscription is None:
            self._update_subscription = (
                get_app()
                .get_update_event_stream()
                .create_subscription_to_pop(
                    partial(self._drain_update, vec_type, value_model, component_models),
                    name="ColorField pending update",
                )
            )

    def _drain_update(self, vec_type, value_model, component_models, _event):
        """Apply queued input or dismiss the popup before any color can be authored."""
        if value_model is not self._value_model:
            return
        action = self._pending_action
        self._clear_pending_update()
        if action is None:
            return
        if action == self._DISMISS_PICKER:
            self._cancel_edit()
            if self._picker_window is not None:
                self._picker_window.focus()
            return
        if self._picker_edit_cancelled:
            return
        self._apply_color(vec_type, value_model, component_models)
        if action == self._CHECKPOINT_COLOR and self._batch_editing and not self._picker_edit_cancelled:
            self._batch_editing = False
            value_model.end_batch_edit()
            if value_model is self._value_model and not self._picker_edit_cancelled:
                # Keep observing external edits between drags; an empty live batch creates no undo entry.
                value_model.begin_batch_edit(live=True)
                self._batch_editing = True

    def _clear_pending_update(self):
        """Discard the queued action and release its application update subscription."""
        self._pending_action = None
        self._update_subscription = None

    def _stop_watching_mouse(self):
        """Release popup-only mouse input observation."""
        if self._mouse_input_subscription_id is not None:
            carb.input.acquire_input_interface().unsubscribe_to_input_events(self._mouse_input_subscription_id)
            self._mouse_input_subscription_id = None

    def _on_undo(self, vec_type, value_model, component_models, _info):
        """Schedule dismissal after the Undo command restores its values."""
        if self._picker_window is None:
            return
        # SDK command callbacks iterate a mutable list; close the popup after dispatch.
        self._schedule_update(self._DISMISS_PICKER, vec_type, value_model, component_models)

    def _stop_watching_popup(self):
        """Release popup observers and discard any pending picker action."""
        self._clear_pending_update()
        self._stop_watching_mouse()
        self._picker_window = None
        if self._undo_callback_id is not None:
            unregister_callback(self._undo_callback_id)
            self._undo_callback_id = None

    def _value_model_changed(self, component_models, value_model):
        """Synchronize the picker components with the backing property value."""
        if self._ignore_value_change_events or value_model is not self._value_model:
            return
        if self._pending_action == self._WRITE_COLOR:
            self._clear_pending_update()
        if value_model.supports_batch_edit and not value_model.is_batch_editing:
            self._batch_editing = False
        vec = value_model.get_attributes_raw_value(0)
        if vec is None:
            vec = Gf.Vec3f(0, 0, 0)
        assert len(component_models) == len(vec), f"{vec} does not match expected length for ColorWidget"
        self._ignore_value_change_events = True
        try:
            for child_value_model, value in zip(component_models, vec):
                child_value_model.set_value(value)
        finally:
            self._ignore_value_change_events = False

    def _color_widget_item_changed(self, vec_type, value_model, component_models, _model, item):
        """Queue the latest picker color for the next application update."""
        if item is None:
            return
        if self._ignore_value_change_events or value_model.read_only or value_model is not self._value_model:
            return
        if self._picker_edit_cancelled:
            self._value_model_changed(component_models, value_model)
            return
        if value_model.supports_batch_edit and not self._batch_editing:
            # Observe competing scene edits before the queued first color can be authored.
            value_model.begin_batch_edit(live=True)
            self._batch_editing = True
        self._schedule_update(self._WRITE_COLOR, vec_type, value_model, component_models)

    def _color_widget_changed(self, vec_type, value_model, component_models, _model, _item):
        """Commit any queued color when the picker closes and close its edit sessions."""
        if value_model is not self._value_model:
            return
        action = self._pending_action
        if action == self._DISMISS_PICKER:
            self._cancel_edit()
        self._stop_watching_popup()
        try:
            if action in (self._WRITE_COLOR, self._CHECKPOINT_COLOR) and not self._picker_edit_cancelled:
                self._apply_color(vec_type, value_model, component_models)
        finally:
            self._end_edit()
            if self._picker_edit_cancelled:
                self._value_model_changed(component_models, value_model)

    def _end_edit(self) -> None:
        """End the picker batch and property edit sessions at most once."""
        try:
            if self._batch_editing:
                self._batch_editing = False
                self._value_model.end_batch_edit()
        finally:
            if self._value_model_editing:
                self._value_model_editing = False
                self._value_model.end_edit()

    def _apply_color(self, vec_type, value_model, component_models):
        """Write the picker color to the backing value model without echoing the update.

        Args:
            vec_type: Vector constructor matching the backing color value.
            value_model: Destination property value model that receives the color.
            component_models: Retained native value models that provide the color components.
        """
        if (
            value_model is not self._value_model
            or value_model.read_only
            or self._picker_edit_cancelled
            or self._pending_action == self._DISMISS_PICKER
        ):
            return
        new_value = vec_type(*(component_model.get_value_as_float() for component_model in component_models))
        if not value_model.is_mixed and new_value == value_model.get_attributes_raw_value(0):
            return
        self._ignore_value_change_events = True
        try:
            if value_model.supports_batch_edit and not self._batch_editing:
                value_model.begin_batch_edit(live=True)
                self._batch_editing = True
            if not self._value_model_editing:
                try:
                    value_model.begin_edit()
                    self._value_model_editing = True
                finally:
                    if not self._value_model_editing:
                        self._end_edit()
            value_model.set_value(new_value)
        finally:
            self._ignore_value_change_events = False
            if value_model.supports_batch_edit and not value_model.is_batch_editing:
                self._batch_editing = False
                self._value_model_changed(component_models, value_model)

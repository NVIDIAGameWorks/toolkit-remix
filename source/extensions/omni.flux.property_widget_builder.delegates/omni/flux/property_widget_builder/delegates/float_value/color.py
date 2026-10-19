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

import omni.ui as ui
from pxr import Gf

from ..base import AbstractField
from .color_picker import ColorPicker


class _ColorItemModel(ui.AbstractItemModel):
    """Own the color components independently of the native picker widget."""

    def __init__(self, values):
        """Create the root and component models for an RGB or RGBA color."""
        super().__init__()
        self._root_model = ui.SimpleIntModel()
        self._components = {ui.AbstractItem(): ui.SimpleFloatModel(float(value)) for value in values}
        self._updating_values = False
        self._subscriptions = [self._root_model.subscribe_value_changed_fn(lambda _: self._item_changed(None))]
        self._subscriptions.extend(
            model.subscribe_value_changed_fn(lambda _, item=item: self._item_changed(item))
            for item, model in self._components.items()
        )

    def get_item_children(self, parent_item=None):
        """Return the component items belonging to the root."""
        return list(self._components) if parent_item is None else []

    def get_item_value_model(self, item=None, column_id=0):
        """Return the root or requested color component value model."""
        return self._root_model if item is None else self._components[item]

    def get_item_value_model_count(self, item=None):
        """Return the single value column for each item."""
        return 1

    def begin_edit(self, item):
        """Accept the native popup's begin-edit dispatch."""

    def end_edit(self, item):
        """Accept the native popup's end-edit dispatch."""

    def set_values(self, values):
        """Notify item listeners only after the complete external color is restored."""
        components = tuple(self._components.values())
        if all(model.get_value_as_float() == value for model, value in zip(components, values)):
            return
        self._updating_values = True
        try:
            for model, value in zip(components, values):
                model.set_value(value)
        finally:
            self._updating_values = False
        self._item_changed(None)

    def destroy(self):
        """Release notifications from the owned component value models."""
        self._subscriptions.clear()

    def _item_changed(self, item):
        """Keep intermediate component values out of complete-color notifications."""
        if not self._updating_values:
            super()._item_changed(item)


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

    def __init__(
        self,
        display_precision: int = 2,
        style_name: str = "ColorsWidgetFieldRead",
        *,
        context_name: str | None = None,
    ):
        """Create a color field with optional scene-selection tracking for its editor.

        Args:
            display_precision: Decimal places shown by the inline component labels.
            style_name: Theme style used for the inline color field.
            context_name: Owning USD context, or None for a generic color field.
        """
        super().__init__(style_name=style_name)

        self.display_precision = display_precision
        self._context_name = context_name

        # The color widget is a bit unique as the provided item's model is not used directly within the widget. We
        # instead connect change events between the two models to ensure that updates properly flow both ways.
        self._picker_subscriptions = []
        self._value_model_value_changed_sub = None
        self._unsubscribe_property_edit_cancel = None
        self._property_edit_finish_subscription = None
        self._value_model = None
        self._color_widget_model = None
        self._picker = None

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
        vec = value_model.get_value() if value_model.is_batch_editing else value_model.get_attributes_raw_value(0)
        if vec is None:
            vec = Gf.Vec3f(0, 0, 0)
        color_model = _ColorItemModel(vec)
        self._color_widget_model = color_model
        component_models = tuple(color_model.get_item_value_model(child) for child in color_model.get_item_children())
        property_name = "".join(model.get_value_as_string() for model in item.name_models)

        widgets = []

        with ui.HStack(height=ui.Pixel(24)):
            ui.Spacer(width=ui.Pixel(8))
            with ui.VStack():
                ui.Spacer()
                self._picker = ColorPicker(
                    color_model,
                    context_name=self._context_name,
                    title=f"{property_name} - Color Editor" if property_name else "Color Editor",
                    name=self.style_name,
                    identifier="color_swatch",
                    enabled=not value_model.read_only,
                    height=0,
                )
                widgets.append(self._picker)
                ui.Spacer()

            ui.Spacer(width=ui.Pixel(4))

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

            self._picker_subscriptions = [
                self._picker.subscribe_edit_started(partial(self._begin_edit, value_model)),
                self._picker.subscribe_color_changed(partial(self._preview_color, type(vec), value_model)),
                self._picker.subscribe_edit_finished(partial(self._finish_edit, value_model)),
            ]

        self._value_model_value_changed_sub = value_model.subscribe_value_changed_fn(self._value_model_changed)
        self._unsubscribe_property_edit_cancel = value_model.subscribe_property_edit_cancel_fn(self._cancel_edit)
        self._property_edit_finish_subscription = value_model.subscribe_property_edit_finish_fn(self._end_edit)
        if register_cleanup is not None:
            # Delegate reset can release the row while its backing model remains alive.
            register_cleanup(self.cleanup)

        return widgets

    def cleanup(self) -> None:
        """Release field subscriptions and close any active picker edit sessions."""
        if self._unsubscribe_property_edit_cancel is not None:
            self._unsubscribe_property_edit_cancel()
            self._unsubscribe_property_edit_cancel = None
        self._property_edit_finish_subscription = None
        self._picker_subscriptions.clear()
        self._value_model_value_changed_sub = None
        picker = self._picker
        self._picker = None
        color_model = self._color_widget_model
        self._color_widget_model = None
        try:
            try:
                self._end_edit()
            finally:
                try:
                    if picker is not None:
                        picker.destroy()
                finally:
                    if color_model is not None:
                        color_model.destroy()
        finally:
            self._value_model = None

    def _cancel_edit(self) -> None:
        """Discard interrupted input before dismissing an active picker edit."""
        self._picker_edit_cancelled = True
        try:
            self._end_edit()
        finally:
            if self._picker is not None:
                self._picker.cancel()
            if self._color_widget_model is not None:
                self._value_model_changed(self._value_model)

    def _begin_edit(self, value_model):
        """Start a deferred property preview before a gesture changes its first component."""
        if value_model is not self._value_model or value_model.read_only:
            return
        self._picker_edit_cancelled = False
        self._ignore_value_change_events = True
        try:
            if value_model.supports_batch_edit and not self._batch_editing:
                value_model.begin_batch_edit()
                self._batch_editing = True
            if not self._value_model_editing:
                try:
                    value_model.begin_edit()
                    if value_model is not self._value_model or self._picker_edit_cancelled:
                        value_model.end_edit()
                        return
                    self._value_model_editing = True
                finally:
                    if value_model is self._value_model and not self._value_model_editing:
                        self._end_edit()
        finally:
            self._ignore_value_change_events = False

    def _value_model_changed(self, value_model):
        """Synchronize the picker components with the backing property value."""
        if self._ignore_value_change_events or value_model is not self._value_model:
            return
        if value_model.supports_batch_edit and not value_model.is_batch_editing:
            self._batch_editing = False
        vec = value_model.get_value() if value_model.is_batch_editing else value_model.get_attributes_raw_value(0)
        if vec is None:
            vec = Gf.Vec3f(0, 0, 0)
        self._ignore_value_change_events = True
        try:
            self._color_widget_model.set_values(vec)
        finally:
            self._ignore_value_change_events = False

    def _finish_edit(self, value_model):
        """Commit the final preview when a gesture ends."""
        if value_model is not self._value_model:
            return
        try:
            self._end_edit()
        finally:
            if self._picker_edit_cancelled:
                self._value_model_changed(value_model)

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

    def _preview_color(self, vec_type, value_model, values):
        """Preview one complete picker color without echoing the update.

        Args:
            vec_type: Vector constructor matching the backing color value.
            value_model: Destination property value model that receives the color.
            values: Complete normalized color emitted by the owned picker.
        """
        if value_model is not self._value_model or value_model.read_only or self._picker_edit_cancelled:
            return
        self._ignore_value_change_events = True
        try:
            value_model.set_value(vec_type(*values))
        finally:
            self._ignore_value_change_events = False
            if value_model.supports_batch_edit and not value_model.is_batch_editing:
                self._batch_editing = False
                self._end_edit()
                self._value_model_changed(value_model)

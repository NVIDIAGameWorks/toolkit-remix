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

import weakref
from math import isfinite

import omni.ui as ui
from omni.flux.utils.common import Event
from pxr import Gf

from ..base import AbstractField
from .color_picker import ColorPickerWindow, _display_color_to_hex, _weak_callback


class _ChannelModel(ui.AbstractValueModel):
    """Clamp picker input while preserving authored values during synchronization."""

    def __init__(self, value: float):
        """Initialize one RGB or alpha channel."""
        super().__init__()
        self._value = float(value)
        self.input_changed = Event(copy=True)

    def get_value_as_float(self):
        """Return the unquantized channel value."""
        return self._value

    def get_value_as_string(self):
        """Return the channel text used by native drag controls."""
        return str(self._value)

    def set_value(self, value):
        """Clamp user input to the normalized picker range."""
        value = float(value)
        if not isfinite(value):
            return
        self.mirror(min(1.0, max(0.0, value)))
        # Row observers may cancel native input before its complete color is published.
        self.input_changed(self)

    def mirror(self, value):
        """Reflect authored HDR and negative values without clamping."""
        if value != self._value:
            self._value = float(value)
            self._value_changed()


class _ColorSwatch(ui.Rectangle):
    """Preserve named swatch styles when the property row changes state."""

    @property
    def style_type_name_override(self):
        """Return the shared field's selected and mixed style state."""
        name = self.name.removesuffix("Mixed")
        return name + ("Selected" if self.selected else "") + ("Mixed" if self.name.endswith("Mixed") else "")

    @style_type_name_override.setter
    def style_type_name_override(self, value):
        """Apply selected and mixed styles to the native rectangle."""
        self.name = value.replace("Selected", "")
        self.selected = "Selected" in value


class ColorField(AbstractField):
    """Own color channels and property transactions for a floating picker."""

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

        self._value_model_value_changed_sub = None
        self._unsubscribe_property_edit_cancel = None
        self._property_edit_finish_subscription = None
        self._value_model = None
        self._components = []
        self._readouts = []
        self._swatch = None
        self._title = ""
        self._vector_type = None
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
        self._vector_type = type(vec)
        self._components = [_ChannelModel(value) for value in vec]
        property_name = "".join(model.get_value_as_string() for model in item.name_models)

        self._title = f"{property_name} - Color Editor" if property_name else "Color Editor"
        widgets = []

        with ui.HStack(height=ui.Pixel(24)):
            ui.Spacer(width=ui.Pixel(8))
            with ui.VStack():
                ui.Spacer()
                swatch = _ColorSwatch(
                    width=ui.Pixel(48),
                    height=ui.Pixel(20),
                    name=self.style_name,
                    identifier="color_swatch",
                    enabled=not value_model.read_only,
                    mouse_released_fn=self._on_swatch_released,
                )
                self._swatch = weakref.ref(swatch)
                widgets.append(swatch)
                ui.Spacer()

            ui.Spacer(width=ui.Pixel(4))

            for index in range(len(self._components)):
                ui.Spacer(width=ui.Pixel(4))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
                    readout = ui.SimpleStringModel()
                    self._readouts.append(readout)
                    widgets.append(
                        ui.StringField(
                            model=readout,
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

        self._value_model_value_changed_sub = value_model.subscribe_value_changed_fn(
            _weak_callback(self._value_model_changed)
        )
        self._unsubscribe_property_edit_cancel = value_model.subscribe_property_edit_cancel_fn(
            _weak_callback(self._cancel_edit)
        )
        self._property_edit_finish_subscription = value_model.subscribe_property_edit_finish_fn(
            _weak_callback(self._end_edit)
        )
        if register_cleanup is not None:
            # Delegate reset can release the row while its backing model remains alive.
            register_cleanup(self.cleanup)

        self._update_swatch()
        return widgets

    def cleanup(self) -> None:
        """End the property edit and retire its controls even when a subscriber fails."""
        if self._unsubscribe_property_edit_cancel is not None:
            self._unsubscribe_property_edit_cancel()
            self._unsubscribe_property_edit_cancel = None
        self._property_edit_finish_subscription = None
        self._value_model_value_changed_sub = None
        try:
            self._end_edit()
        finally:
            try:
                if self._picker is not None:
                    self._picker.cancel()
            finally:
                self._picker = None
                self._components = []
                self._readouts = []
                self._swatch = None
                self._value_model = None

    def _on_swatch_released(self, _x, _y, button, _modifier):
        """Open the color editor from an editable inline swatch."""
        swatch = self._swatch() if self._swatch is not None else None
        if button != 0 or swatch is None or self._value_model.read_only:
            return
        self._picker_edit_cancelled = False
        self._picker = ColorPickerWindow(self._components, title=self._title, context_name=self._context_name)
        self._picker.edit_started.add(_weak_callback(self._begin_picker_edit))
        self._picker.color_changed.add(_weak_callback(self._preview_picker_color))
        self._picker.edit_finished.add(_weak_callback(self._finish_picker_edit))
        self._picker.open(
            preferred_size=(ColorPickerWindow.WINDOW_WIDTH, ColorPickerWindow.WINDOW_HEIGHT),
            anchor_rect=(
                swatch.screen_position_x,
                swatch.screen_position_y,
                swatch.computed_width,
                swatch.computed_height,
            ),
        )

    def _begin_picker_edit(self):
        """Start a property transaction before the picker changes channels."""
        self._begin_edit(self._value_model)

    def _preview_picker_color(self, values):
        """Apply one complete picker color through the backing model."""
        if self._ignore_value_change_events:
            return
        self._preview_color(self._vector_type, self._value_model, values)
        self._update_swatch()

    def _finish_picker_edit(self):
        """Commit the completed picker gesture."""
        self._finish_edit(self._value_model)

    def _update_swatch(self):
        """Refresh the inline preview from the authored channel values."""
        for readout, model in zip(self._readouts, self._components):
            readout.set_value(f"{model.get_value_as_float():.{self.display_precision}f}")
        swatch = self._swatch() if self._swatch is not None else None
        if swatch is not None:
            values = tuple(model.get_value_as_float() for model in self._components)
            swatch.set_style({"background_color": _display_color_to_hex(values)})

    def _cancel_edit(self) -> None:
        """Discard interrupted input before dismissing an active picker edit."""
        self._picker_edit_cancelled = True
        try:
            self._end_edit()
        finally:
            if self._picker is not None:
                self._picker.cancel()
            if self._components:
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
            if self._picker is not None and self._picker.is_open:
                self._picker.sync_color(vec)
            else:
                for model, value in zip(self._components, vec):
                    model.mirror(value)
        finally:
            self._ignore_value_change_events = False
        self._update_swatch()

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

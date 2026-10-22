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
from omni.flux.utils.common import weak_callback
from pxr import Gf

from ..base import AbstractField
from .color_picker import ColorPickerWindow, _display_color_to_hex


class _ChannelModel(ui.AbstractValueModel):
    """Clamp picker input while preserving authored values during synchronization."""

    def __init__(self, value: float):
        """Initialize one RGB or alpha channel."""
        super().__init__()
        self._value = float(value)

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

    def mirror(self, value, *, notify=True):
        """Reflect authored HDR and negative values without clamping."""
        if value != self._value:
            self._value = float(value)
            if notify:
                self._value_changed()

    @classmethod
    def mirror_values(cls, models, values):
        """Update every channel before notifying observers of the complete color."""
        changed = []
        for model, value in zip(models, values):
            if value != model.get_value_as_float():
                model.mirror(value, notify=False)
                changed.append(model)
        for model in changed:
            cls._value_changed(model)


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

    _SWATCH_WIDTH = ui.Pixel(48)
    _SWATCH_HEIGHT = ui.Pixel(20)

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

        self._subscriptions = []
        self._value_model = None
        self._components = []
        self._readouts = []
        self._swatch = None
        self._title = ""
        self._vector_type = None
        self._picker = None

        # Both change callbacks ignore updates echoed from the other model.
        self._ignore_value_change_events = False
        self._editing = False

    def build_ui(self, item) -> list[ui.Widget]:
        """Build the color field and subscribe weakly to its backing value model."""
        if len(item.value_models) != 1:
            raise ValueError("Expected 1 value_model that holds the vector values")

        value_model = item.value_models[0]
        self._value_model = value_model
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
                    width=self._SWATCH_WIDTH,
                    height=self._SWATCH_HEIGHT,
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

        self._subscriptions = [
            model.subscribe_value_changed_fn(weak_callback(self._color_widget_changed)) for model in self._components
        ]
        self._subscriptions.append(value_model.subscribe_value_changed_fn(weak_callback(self._value_model_changed)))
        unsubscribe_cancel = value_model.subscribe_property_edit_cancel_fn(weak_callback(self._cancel_edit))
        weakref.finalize(self, unsubscribe_cancel).atexit = False
        self._update_swatch()
        return widgets

    def _on_swatch_released(self, _x, _y, button, _modifier):
        """Open the color editor from an editable inline swatch."""
        swatch = self._swatch() if self._swatch is not None else None
        if button != 0 or swatch is None or self._value_model.read_only:
            return
        self._picker = ColorPickerWindow(self._components, title=self._title, context_name=self._context_name)
        self._picker.edit_started.add(self._begin_edit)
        self._picker.edit_finished.add(self._end_edit)
        self._picker.open(
            preferred_size=(ColorPickerWindow.WINDOW_WIDTH, ColorPickerWindow.WINDOW_HEIGHT),
            anchor_rect=(
                swatch.screen_position_x,
                swatch.screen_position_y,
                swatch.computed_width,
                swatch.computed_height,
            ),
        )

    def _update_swatch(self):
        """Refresh the inline preview from the authored channel values."""
        for readout, model in zip(self._readouts, self._components):
            readout.set_value(f"{model.get_value_as_float():.{self.display_precision}f}")
        swatch = self._swatch() if self._swatch is not None else None
        if swatch is not None:
            values = tuple(model.get_value_as_float() for model in self._components)
            swatch.set_style({"background_color": _display_color_to_hex(values)})

    def _cancel_edit(self) -> None:
        """Balance the edit and discard native input after the backing preview is cancelled."""
        try:
            self._end_edit()
        finally:
            if self._picker is not None:
                self._picker.cancel()
            self._value_model_changed(self._value_model)

    def _begin_edit(self):
        """Open one property batch for the native gesture."""
        if self._editing or self._value_model.read_only:
            return
        self._editing = True
        try:
            self._value_model.begin_edit()
            if self._editing:
                self._value_model.begin_batch_edit()
            else:
                self._value_model.end_edit()
        except Exception:
            self._end_edit()
            raise

    def _value_model_changed(self, value_model):
        """Mirror authoritative values through the same channel models used by the picker."""
        if self._ignore_value_change_events:
            return
        vec = value_model.get_value() if value_model.is_batch_editing else value_model.get_attributes_raw_value(0)
        if vec is None:
            vec = Gf.Vec3f(0, 0, 0)
        if (
            self._editing
            and self._picker is not None
            and tuple(vec) != tuple(model.get_value_as_float() for model in self._components)
        ):
            # USD may notify while rollback is still restoring its batch.
            self._picker.cancel()
        self._ignore_value_change_events = True
        try:
            _ChannelModel.mirror_values(self._components, vec)
        finally:
            self._ignore_value_change_events = False
        self._update_swatch()

    def _end_edit(self) -> None:
        """Let the backing value model close its batch and balance the gesture once."""
        if self._editing:
            self._editing = False
            self._value_model.end_edit()

    def _color_widget_changed(self, _model):
        """Preview the complete shared color without echoing it back into the controls."""
        if self._ignore_value_change_events or not self._editing or self._value_model.read_only:
            return
        values = self._vector_type(*(min(1.0, max(0.0, model.get_value_as_float())) for model in self._components))
        if not self._value_model.is_mixed and values == self._value_model.get_value():
            return
        self._ignore_value_change_events = True
        try:
            self._value_model.set_value(values)
        finally:
            self._ignore_value_change_events = False
            if self._value_model.supports_batch_edit and not self._value_model.is_batch_editing:
                self._end_edit()
                self._value_model_changed(self._value_model)
        self._update_swatch()

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

__all__ = ("ColorPickerWindow",)

import colorsys
import weakref
from collections.abc import Callable
from ctypes import c_float
from functools import partial
from math import isfinite
from string import hexdigits
from typing import TYPE_CHECKING

import omni.ui as ui
from omni.flux.utils.common import Event, EventSubscription
from omni.flux.utils.widget.gradient import create_checkerboard
from omni.flux.utils.widget.resources import get_icons

from ..field_popup_window import FieldPopupWindow

if TYPE_CHECKING:
    from .color import _ChannelModel


_COLOR_BYTE_MAX = 255
_HUE_TEXTURE_HEIGHT = 256


def _weak_callback(method: Callable) -> Callable:
    """Forward a bound method without keeping its owner alive.

    Calls return None after the owner is released.

    Args:
        method: Bound method of a weak-referenceable Python object.

    Returns:
        A callable with the same arguments that holds the owner weakly.
    """
    reference = weakref.WeakMethod(method)

    def callback(*args, **kwargs):
        bound = reference()
        if bound is not None:
            return bound(*args, **kwargs)
        return None

    return callback


def _display_byte(value: float) -> int:
    """Round a clipped display channel with Kit's float32 color arithmetic."""
    scaled = c_float(min(1.0, max(0.0, value)) * _COLOR_BYTE_MAX).value
    return int(c_float(scaled + 0.5).value)


def _display_color_to_hex(values: tuple[float, ...]) -> int:
    """Pack rounded RGB or RGBA display channels in omni.ui's AABBGGRR format."""
    channels = (*values, 1.0) if len(values) == 3 else values
    return sum(_display_byte(value) << (8 * index) for index, value in enumerate(channels))


def _parse_color_text(text: str, component_count: int) -> list[float] | None:
    """Parse complete hexadecimal colors or finite normalized tuples matching the channel count."""
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        components = text[1:-1].split(",", component_count)
        if len(components) != component_count:
            return None
        try:
            values = [float(component) for component in components]
        except ValueError:
            return None
        if not all(isfinite(value) and 0 <= value <= 1 for value in values):
            return None
        return [_display_byte(value) / _COLOR_BYTE_MAX for value in values]
    text = text.removeprefix("#")
    if len(text) != component_count * 2 or not all(character in hexdigits for character in text):
        return None
    return [int(text[index : index + 2], 16) / _COLOR_BYTE_MAX for index in range(0, len(text), 2)]


class ColorPickerWindow(FieldPopupWindow):
    """Edit borrowed RGB or RGBA channels with complete-color notifications and gesture boundaries."""

    WINDOW_WIDTH = 384
    WINDOW_HEIGHT = 384
    _CONTROL_SIZE = ui.Pixel(20)
    _CHANNEL_LABEL_WIDTH = ui.Pixel(24)
    _HEX_LABEL_WIDTH = ui.Pixel(32)
    _CURRENT_WIDTH = ui.Pixel(64)
    _CURRENT_HEIGHT = ui.Pixel(44)
    _SPACING_MD = ui.Pixel(8)
    _PADDING_MD = ui.Pixel(8)
    _HANDLE_SIZE_MD = ui.Pixel(12)
    _NUMERIC_STEP = 0.001
    _SV_TEXTURE_SIZE = 64
    _HUE_BYTES = [
        channel
        for index in range(_HUE_TEXTURE_HEIGHT)
        for channel in (
            *(round(value * _COLOR_BYTE_MAX) for value in colorsys.hsv_to_rgb(index / (_HUE_TEXTURE_HEIGHT - 1), 1, 1)),
            _COLOR_BYTE_MAX,
        )
    ]

    def __init__(self, component_models: list["_ChannelModel"], *, title: str, context_name: str | None):
        """Borrow caller-owned component models and construct a hidden floating editor.

        Args:
            component_models: RGB or RGBA channel models preserving externally authored values.
            title: Friendly property name displayed by the floating editor.
            context_name: USD context whose selection changes close the editor, or None.
        """
        self._components = component_models
        self.edit_started = Event(copy=True)
        self.color_changed = Event(copy=True)
        self.edit_finished = Event(copy=True)
        self._gesture_depth = 0
        self._syncing = False
        self._input_enabled = False
        self._dragging = None
        self._hsv = [0.0, 0.0, 0.0]
        self._hsv_models = [ui.SimpleFloatModel() for _ in self._hsv]
        self._hex_model = ui.SimpleStringModel()
        self._hex_dirty = False
        self._subscriptions = []
        self._last_color = tuple(model.get_value_as_float() for model in self._components)
        self._preview_hue = None
        self._current_opaque = self._current_alpha = None
        self._sv_image = self._hue_image = self._sv_marker = self._hue_marker = None
        self._sv_provider = ui.ByteImageProvider()
        self._hue_provider = ui.ByteImageProvider()
        self._hue_provider.set_bytes_data(self._HUE_BYTES, [1, _HUE_TEXTURE_HEIGHT])
        self._checker_provider = None
        super().__init__(title=title, context_name=context_name)
        self.flags |= ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def cancel(self) -> None:
        """Disable abandoned input and close without committing buffered text."""
        self._input_enabled = False
        self._gesture_depth = 0
        self._dragging = None
        self._hex_dirty = False
        super().close()

    def sync_color(self, values) -> None:
        """Mirror an authoritative color without emitting edits or retaining interrupted native input."""
        if self._gesture_depth or self._hex_dirty:
            self.cancel()
        syncing = self._syncing
        self._syncing = True
        try:
            for model, value in zip(self._components, values):
                model.mirror(value)
        finally:
            self._syncing = syncing
        self._last_color = tuple(model.get_value_as_float() for model in self._components)
        if self._components:
            self._read_hsv()
            self._refresh()

    def _build_content(self) -> None:
        """Build this opening's controls after the shared floating host activates."""
        self._input_enabled = True
        self._read_hsv()
        if len(self._components) == 4:
            self._checker_provider = ui.ByteImageProvider()
            checker_width = int(float(self._CURRENT_WIDTH) / 2)
            checker_height = int(float(self._CURRENT_HEIGHT))
            checker = create_checkerboard(checker_width, checker_height)
            self._checker_provider.set_bytes_data(checker.ravel().tolist(), [checker_width, checker_height])
        with ui.ZStack():
            ui.Rectangle(name="WorkspaceBackground", opaque_for_mouse_events=False)
            with ui.HStack(spacing=self._SPACING_MD):
                ui.Spacer(width=0, height=0)
                self._build_main_column()
                self._build_current_column()
                ui.Spacer(width=0, height=0)
        for model in self._components:
            self._subscriptions.append(
                EventSubscription(model.input_changed, _weak_callback(self._on_component_changed))
            )
        for model in self._hsv_models:
            self._subscriptions.append(model.subscribe_value_changed_fn(_weak_callback(self._on_hsv_changed)))
        for model in (*self._components, *self._hsv_models):
            self._subscriptions.append(model.subscribe_begin_edit_fn(_weak_callback(self._begin_gesture)))
            self._subscriptions.append(model.subscribe_end_edit_fn(_weak_callback(self._end_gesture)))
        self._subscriptions.extend(
            (
                self._hex_model.subscribe_value_changed_fn(_weak_callback(self._on_hex_changed)),
                self._hex_model.subscribe_begin_edit_fn(_weak_callback(self._begin_gesture)),
                self._hex_model.subscribe_end_edit_fn(_weak_callback(self._on_hex_committed)),
            )
        )
        self._sv_image.set_computed_content_size_changed_fn(self._update_markers)
        self._hue_image.set_computed_content_size_changed_fn(self._update_markers)
        self._refresh()

    def _build_main_column(self) -> None:
        """Build the flexible color plane and its aligned numeric editors."""
        with ui.VStack(spacing=self._SPACING_MD):
            ui.Spacer(width=0, height=0)
            with ui.HStack(spacing=self._SPACING_MD):
                self._build_sv_control()
                self._build_hue_control()
            self._build_numeric_row(list(zip("RGBA", self._components, ("red", "green", "blue", "alpha"))))
            hsv_fields = list(zip("HSV", self._hsv_models, ("hue_value", "saturation", "value")))
            if len(self._components) == 4:
                hsv_fields.append(("A", self._components[3], "alpha_hsv"))
            self._build_numeric_row(hsv_fields)
            with ui.HStack(height=self._CONTROL_SIZE):
                ui.Label("Hex", width=self._HEX_LABEL_WIDTH)
                ui.StringField(model=self._hex_model, identifier="color_picker_hex")
            ui.Spacer(height=self._PADDING_MD)

    def _build_sv_control(self) -> None:
        """Build the stretched saturation/value plane and hollow selection handle."""
        with ui.ZStack():
            self._sv_image = ui.ImageWithProvider(
                self._sv_provider,
                fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                identifier="color_picker_sv",
                mouse_pressed_fn=partial(self._on_plane_pressed, "sv"),
                mouse_moved_fn=partial(self._on_plane_moved, "sv"),
                mouse_released_fn=partial(self._on_plane_released, "sv"),
            )
            self._sv_marker = ui.Placer(stable_size=True)
            with self._sv_marker:
                # Placer stretches a direct Image child, so a fixed frame preserves the SVG's handle size.
                with ui.Frame(width=self._HANDLE_SIZE_MD, height=self._HANDLE_SIZE_MD):
                    ui.Image(
                        get_icons("ColorPickerHandle", ext_name="omni.flux.resources"),
                        width=self._HANDLE_SIZE_MD,
                        height=self._HANDLE_SIZE_MD,
                        name="ColorPickerHandle",
                        opaque_for_mouse_events=False,
                    )

    def _build_hue_control(self) -> None:
        """Build the fixed-width hue bar and contrasting side handles."""
        with ui.ZStack(width=self._CONTROL_SIZE):
            self._hue_image = ui.ImageWithProvider(
                self._hue_provider,
                fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                identifier="color_picker_hue",
                mouse_pressed_fn=partial(self._on_plane_pressed, "hue"),
                mouse_moved_fn=partial(self._on_plane_moved, "hue"),
                mouse_released_fn=partial(self._on_plane_released, "hue"),
            )
            self._hue_marker = ui.Placer(stable_size=True)
            with self._hue_marker:
                with ui.Frame(width=self._CONTROL_SIZE, height=self._HANDLE_SIZE_MD):
                    ui.Image(
                        get_icons("ColorPickerHueHandle", ext_name="omni.flux.resources"),
                        width=self._CONTROL_SIZE,
                        height=self._HANDLE_SIZE_MD,
                        name="ColorPickerHueHandle",
                        opaque_for_mouse_events=False,
                    )

    def _build_current_column(self) -> None:
        """Build the top-aligned Current preview and optional alpha checkerboard."""
        with ui.VStack(width=self._CURRENT_WIDTH, spacing=self._SPACING_MD):
            ui.Spacer(width=0, height=0)
            ui.Label("Current", height=self._CONTROL_SIZE, alignment=ui.Alignment.LEFT_TOP)
            with ui.ZStack(height=self._CURRENT_HEIGHT):
                if len(self._components) == 4:
                    with ui.HStack():
                        self._current_opaque = ui.Rectangle(opaque_for_mouse_events=False)
                        with ui.ZStack():
                            ui.ImageWithProvider(self._checker_provider, fill_policy=ui.IwpFillPolicy.IWP_STRETCH)
                            self._current_alpha = ui.Rectangle(opaque_for_mouse_events=False)
                else:
                    self._current_opaque = ui.Rectangle(opaque_for_mouse_events=False)
                ui.Rectangle(name="ColorPickerCurrentBorder", opaque_for_mouse_events=False)
            ui.Spacer()

    def _build_numeric_row(self, fields) -> None:
        """Build labeled native component drags with the shared color-editor spacing."""
        with ui.HStack(height=self._CONTROL_SIZE):
            for index, (label, model, identifier) in enumerate(fields):
                if index:
                    ui.Spacer(width=self._SPACING_MD)
                ui.Label(label, width=self._CHANNEL_LABEL_WIDTH, alignment=ui.Alignment.LEFT_CENTER)
                ui.FloatDrag(
                    model=model,
                    min=0.0,
                    max=1.0,
                    step=self._NUMERIC_STEP,
                    precision=4,
                    style_type_name_override="DragField",
                    identifier=f"color_picker_{identifier}",
                )

    def _release_content(self) -> None:
        """Finish surviving gestures and release this opening's native subscriptions and previews."""
        try:
            try:
                self._commit_hex()
            finally:
                if self._gesture_depth:
                    self._gesture_depth = 0
                    self.edit_finished()
        finally:
            self._input_enabled = False
            self._subscriptions.clear()
            self._components = ()
            self._dragging = None
            self._current_opaque = self._current_alpha = None
            self._sv_image = self._hue_image = self._sv_marker = self._hue_marker = None
            self._sv_provider = self._hue_provider = self._checker_provider = None

    def _begin_gesture(self, _model=None) -> None:
        """Report only the outermost overlapping native edit gesture."""
        if self._input_enabled:
            self._gesture_depth += 1
            if self._gesture_depth == 1:
                self.edit_started()

    def _end_gesture(self, _model=None) -> None:
        """Finish an edit once its last overlapping control releases."""
        if self._input_enabled and self._gesture_depth:
            self._gesture_depth -= 1
            if not self._gesture_depth:
                self.edit_finished()

    def _on_plane_pressed(self, control, x, y, button, _modifier) -> None:
        """Begin a left-button gesture on the owned color plane."""
        if self._input_enabled and button == 0:
            self._dragging = control
            self._begin_gesture()
            self._pick_color(control, x, y)

    def _on_plane_moved(self, control, x, y, _modifier, _pressed) -> None:
        """Apply continuous color changes from the active plane drag."""
        if self._input_enabled and self._dragging == control:
            self._pick_color(control, x, y)

    def _on_plane_released(self, control, _x, _y, button, _modifier) -> None:
        """Finish a plane gesture when its initiating button releases."""
        if self._input_enabled and button == 0 and self._dragging == control:
            self._dragging = None
            self._end_gesture()

    def _pick_color(self, control, x, y) -> None:
        """Convert pointer coordinates into normalized saturation/value or hue."""
        image = self._sv_image if control == "sv" else self._hue_image
        if not self._input_enabled or image is None or image.computed_width <= 0 or image.computed_height <= 0:
            return
        horizontal = min(1.0, max(0.0, (x - image.screen_position_x) / image.computed_width))
        vertical = min(1.0, max(0.0, (y - image.screen_position_y) / image.computed_height))
        if control == "sv":
            self._hsv[1:] = [horizontal, 1.0 - vertical]
        else:
            self._hsv[0] = vertical
            self._hsv[2] = min(1.0, max(0.0, self._hsv[2]))
        self._apply_hsv()

    def _on_component_changed(self, _model) -> None:
        """Publish native input only after ordinary component notifications finish."""
        if self._syncing or not self._input_enabled:
            return
        if self._gesture_depth:
            self._set_components([model.get_value_as_float() for model in self._components], read_hsv=True)
        else:
            self._read_hsv()
            self._refresh()

    def _on_hsv_changed(self, _model) -> None:
        """Apply a finite normalized HSV edit through the complete-color path."""
        if self._syncing or not self._input_enabled:
            return
        values = [model.get_value_as_float() for model in self._hsv_models]
        if self._gesture_depth and all(isfinite(value) for value in values):
            self._hsv = [min(1.0, max(0.0, value)) for value in values]
            self._apply_hsv()
        else:
            self._refresh()

    def _on_hex_changed(self, _model) -> None:
        """Keep native hexadecimal input buffered until end-edit or dismissal."""
        if not self._syncing and self._input_enabled:
            self._hex_dirty = True

    def _on_hex_committed(self, _model) -> None:
        """Commit buffered hexadecimal input before ending its native gesture."""
        try:
            self._commit_hex()
        finally:
            self._end_gesture()

    def _commit_hex(self) -> None:
        """Apply valid text once and restore canonical text for invalid input."""
        if not self._input_enabled or not self._hex_dirty:
            return
        self._hex_dirty = False
        values = _parse_color_text(self._hex_model.get_value_as_string(), len(self._components))
        if values is not None:
            own_gesture = not self._gesture_depth
            if own_gesture:
                self._begin_gesture()
            try:
                self._set_components(values, read_hsv=True)
            finally:
                if own_gesture:
                    self._end_gesture()
        else:
            self._refresh()

    def _apply_hsv(self) -> None:
        """Convert the selected HSV color while retaining the optional alpha channel."""
        self._set_components(
            [*colorsys.hsv_to_rgb(*self._hsv), *(model.get_value_as_float() for model in self._components[3:])]
        )

    def _set_components(self, values, *, read_hsv=False) -> None:
        """Write normalized channels and emit one complete color unless the gesture was cancelled."""
        if self._syncing or not self._input_enabled or not all(isfinite(value) for value in values):
            return
        values = tuple(min(1.0, max(0.0, value)) for value in values)
        if values != self._last_color:
            self._syncing = True
            try:
                for model, value in zip(self._components, values):
                    if not self._input_enabled:
                        return
                    model.set_value(value)
                if not self._input_enabled:
                    return
                self.color_changed(values)
            finally:
                self._syncing = False
        if not self._input_enabled:
            return
        if read_hsv:
            self._read_hsv()
        self._refresh()

    def _read_hsv(self) -> None:
        """Read authored colors without rewriting HDR values or losing achromatic selectors."""
        hue, saturation, value = colorsys.rgb_to_hsv(
            *(max(0.0, model.get_value_as_float()) for model in self._components[:3])
        )
        if saturation > 0 and value > 0:
            self._hsv[0] = hue
        if value > 0:
            self._hsv[1] = saturation
        self._hsv[2] = value

    def _refresh(self) -> None:
        """Refresh canonical text, split alpha previews, texture, and selectors without authoring values."""
        if not self._input_enabled:
            return
        values = tuple(model.get_value_as_float() for model in self._components)
        self._last_color = values
        self._syncing = True
        try:
            for model, value in zip(self._hsv_models, self._hsv):
                model.set_value(value)
            if not self._hex_dirty:
                self._hex_model.set_value("#" + "".join(f"{_display_byte(value):02X}" for value in values))
        finally:
            self._syncing = False
        if self._current_opaque is not None:
            self._current_opaque.set_style({"background_color": _display_color_to_hex((*values[:3], 1.0))})
        if self._current_alpha is not None:
            self._current_alpha.set_style({"background_color": _display_color_to_hex(values)})
        if self._sv_image is not None and self._preview_hue != self._hsv[0]:
            self._preview_hue = self._hsv[0]
            hue_rgb = colorsys.hsv_to_rgb(self._hsv[0], 1, 1)
            pixels = []
            for row in range(self._SV_TEXTURE_SIZE):
                value = 1 - row / (self._SV_TEXTURE_SIZE - 1)
                for column in range(self._SV_TEXTURE_SIZE):
                    saturation = column / (self._SV_TEXTURE_SIZE - 1)
                    pixels.extend(
                        round((1 - saturation + saturation * channel) * value * _COLOR_BYTE_MAX) for channel in hue_rgb
                    )
                    pixels.append(_COLOR_BYTE_MAX)
            self._sv_provider.set_bytes_data(pixels, [self._SV_TEXTURE_SIZE, self._SV_TEXTURE_SIZE])
        self._update_markers()

    def _update_markers(self) -> None:
        """Position both SVG selectors after a color or measured layout change."""
        if self._sv_image is not None and self._sv_image.computed_width > 0 and self._sv_image.computed_height > 0:
            self._sv_marker.offset_x = ui.Pixel(
                min(1.0, max(0.0, self._hsv[1])) * self._sv_image.computed_width - float(self._HANDLE_SIZE_MD) / 2
            )
            self._sv_marker.offset_y = ui.Pixel(
                (1 - min(1.0, max(0.0, self._hsv[2]))) * self._sv_image.computed_height
                - float(self._HANDLE_SIZE_MD) / 2
            )
        if self._hue_image is not None and self._hue_image.computed_height > 0:
            self._hue_marker.offset_y = ui.Pixel(
                self._hsv[0] * self._hue_image.computed_height - float(self._HANDLE_SIZE_MD) / 2
            )

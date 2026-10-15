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

__all__ = ("ColorPicker",)

import asyncio
import colorsys
from collections.abc import Callable
from ctypes import c_float
from functools import partial
from string import hexdigits

import omni.ui as ui
from omni.flux.utils.widget.color import color_to_hex
from omni.flux.utils.widget.gradient import create_checkerboard
from omni.kit.app import get_app
from omni.ui import color as cl

from .color_picker_popup import ColorPickerPopup


class _PickerValueModel(ui.AbstractValueModel):
    """Route a popup input through its retained display model and owner."""

    def __init__(self, parent: ui.AbstractValueModel, write_fn: Callable[[float | str], None]):
        """Borrow a display model and connect its public value notifications.

        Args:
            parent: Display model retained for native value getters.
            write_fn: Callback that authors or buffers input while the popup accepts edits.
        """
        super().__init__()
        self._parent = parent
        self._write_fn = write_fn
        self._subscription = parent.subscribe_value_changed_fn(lambda _: self._value_changed())

    def get_value_as_float(self):
        """Return the authoritative component value without limiting its range."""
        return self._parent.get_value_as_float()

    def get_value_as_string(self):
        """Return the display model text used by the editor."""
        return self._parent.get_value_as_string()

    def set_value(self, value):
        """Forward an edit while the popup accepts input."""
        if self._write_fn is not None:
            self._write_fn(value)

    def destroy(self):
        """Release the borrowed component subscription and input callback."""
        self._write_fn = None
        self._subscription = None


class ColorPicker(ui.Frame):
    """Display a color swatch with an owned picker and explicit gesture boundaries."""

    _PLANE_SIZE = ui.Pixel(240)
    _HUE_WIDTH = ui.Pixel(20)
    _SWATCH_WIDTH = ui.Pixel(48)
    _SWATCH_HEIGHT = ui.Pixel(20)
    _CHANNEL_ROW_HEIGHT = ui.Pixel(20)
    _CHANNEL_LABEL_WIDTH = ui.Pixel(24)
    _HEX_LABEL_WIDTH = ui.Pixel(32)
    _CURRENT_WIDTH = ui.Pixel(64)
    _CURRENT_HEIGHT = ui.Pixel(44)
    _SPACING = ui.Pixel(8)
    _PADDING = ui.Pixel(8)
    _RIGHT_PADDING = ui.Pixel(16)
    _BOTTOM_PADDING = ui.Pixel(56)
    _MARKER_SIZE = ui.Pixel(12)
    _MARKER_INNER_SIZE = ui.Pixel(8)
    _HUE_MARKER_WIDTH = ui.Pixel(8)
    _HUE_MARKER_HEIGHT = ui.Pixel(12)
    _NUMERIC_STEP = 0.001
    _SV_TEXTURE_SIZE = 64
    _HUE_TEXTURE_HEIGHT = 256
    _CHANNEL_NAMES = ("red", "green", "blue", "alpha")
    _HSV_NAMES = ("hue_value", "saturation", "value")
    _FALLBACK_STYLE = {
        "Circle::ColorPickerHandleOutline": {
            "background_color": cl.transparent,
            "border_color": cl.black,
            "border_width": 2,
        },
        "Circle::ColorPickerHandle": {
            "background_color": cl.transparent,
            "border_color": cl.white,
            "border_width": 1,
        },
        "Triangle::ColorPickerHueHandle": {
            "background_color": cl.white,
            "border_color": cl.black,
            "border_width": 1,
        },
        "Rectangle::ColorPickerCurrentBorder": {
            "background_color": cl.transparent,
            "border_color": cl.black,
            "border_width": 1,
        },
    }
    _HUE_BYTES = [
        channel
        for index in range(_HUE_TEXTURE_HEIGHT)
        for channel in (*(round(value * 255) for value in colorsys.hsv_to_rgb(index / 255, 1, 1)), 255)
    ]

    def __init__(
        self,
        model: ui.AbstractItemModel,
        *,
        begin_edit_fn: Callable[[], None],
        end_edit_fn: Callable[[], None],
        context_name: str | None = None,
        title: str = "Color Editor",
        **kwargs,
    ):
        """Borrow a color model and callbacks for the first change and final gesture value.

        Args:
            model: Caller-owned item model containing RGB or RGBA component values.
            begin_edit_fn: Callback invoked before the first actual change of a gesture.
            end_edit_fn: Callback that flushes and commits the gesture's final value.
            context_name: USD context whose selection changes dismiss this editor, or None for generic fields.
            title: Friendly property name and editor title for the native window.
            **kwargs: Built-in Frame constructor options for the swatch.
        """
        super().__init__(**kwargs)
        self._model = model
        self._components = tuple(model.get_item_value_model(item) for item in model.get_item_children())
        self._begin_edit_fn = begin_edit_fn
        self._end_edit_fn = end_edit_fn
        self._context_name = context_name
        self._title = title
        self._style_name = kwargs.get("style_type_name_override", kwargs.get("name", "ColorsWidgetFieldRead"))
        self._window = None
        self._window_title = ""
        self._close_task = None
        self._input_enabled = False
        self._gesture_active = False
        self._pointer_control = None
        self._numeric_editing = None
        self._writing = False
        self._writing_color = False
        self._hsv_models = []
        self._hex_model = None
        self._hex_dirty = False
        self._current_opaque = None
        self._current_alpha = None
        self._checker_provider = None
        self._numeric_models = []
        self._numeric_subscriptions = []
        self._hue = 0.0
        self._preview_hue = None
        self._saturation = 0.0
        self._value = 0.0
        self._value_scale = 1.0
        self._sv_image = None
        self._hue_image = None
        self._sv_marker = None
        self._hue_marker = None
        self._sv_provider = None
        self._hue_provider = None
        with self:
            self._swatch = ui.Rectangle(
                width=self._SWATCH_WIDTH,
                height=self._SWATCH_HEIGHT,
                name=self._style_name,
                style_type_name_override="ColorWidget",
                mouse_released_fn=self._on_swatch_released,
            )
        self._model_subscription = model.subscribe_item_changed_fn(self._on_model_changed)
        self._refresh()

    @property
    def model(self):
        """Return the borrowed item model used by the swatch and picker."""
        return self._model

    @property
    def window_title(self):
        """Return the owned popup's unique title for UI queries."""
        return self._window_title

    @property
    def style_type_name_override(self):
        """Return the delegate style applied to the actual swatch."""
        return self._style_name

    @style_type_name_override.setter
    def style_type_name_override(self, value):
        """Forward mixed and selected styling to the actual swatch."""
        self._style_name = value
        self._swatch.name = value.replace("Selected", "")
        self._swatch.selected = "Selected" in value

    def open(self):
        """Request the shared floating editor without starting a property edit."""
        if not self.enabled or self._window is not None or self._model is None:
            return
        popup_width = (
            float(self._PLANE_SIZE)
            + float(self._HUE_WIDTH)
            + float(self._SPACING)
            + float(self._CURRENT_WIDTH)
            + float(self._SPACING)
            + float(self._PADDING)
            + float(self._RIGHT_PADDING)
        )
        popup_height = (
            float(self._PLANE_SIZE)
            + 3 * (float(self._CHANNEL_ROW_HEIGHT) + float(self._SPACING))
            + float(self._PADDING)
            + float(self._BOTTOM_PADDING)
        )
        self._window = ColorPickerPopup(
            title=self._title,
            context_name=self._context_name,
            build_fn=partial(self._build_content, (popup_width, popup_height)),
            close_fn=self.close,
            cancel_fn=self.cancel,
        )
        self._window_title = self._window.title
        self._window.open(
            preferred_size=(popup_width, popup_height),
            anchor_rect=(
                self.screen_position_x,
                self.screen_position_y,
                self.computed_width,
                self.computed_height,
            ),
        )

    def _build_content(self, preferred_size, window):
        """Create this opening's controls only after its shared floating host activates."""
        if window is not self._window or self._model is None:
            return
        self._input_enabled = True
        self._refresh()
        self._value_scale = max(1.0, self._value)
        if self._hue_provider is None:
            self._sv_provider = ui.ByteImageProvider()
            self._hue_provider = ui.ByteImageProvider()
            self._hue_provider.set_bytes_data(self._HUE_BYTES, [1, self._HUE_TEXTURE_HEIGHT])
        if len(self._components) == 4 and self._checker_provider is None:
            self._checker_provider = ui.ByteImageProvider()
            checker_width = int(float(self._CURRENT_WIDTH) / 2)
            checker_height = int(float(self._CURRENT_HEIGHT))
            checker = create_checkerboard(checker_width, checker_height)
            self._checker_provider.set_bytes_data(checker.ravel().tolist(), [checker_width, checker_height])
        main_width = ui.Pixel(float(self._PLANE_SIZE) + float(self._HUE_WIDTH) + float(self._SPACING))
        self._hsv_models = [ui.SimpleFloatModel(value) for value in (self._hue, self._saturation, self._value)]
        self._hex_model = ui.SimpleStringModel(self._format_hex())
        self._hex_dirty = False
        default_style = ui.Style.get_instance().default
        fallback_style = {name: style for name, style in self._FALLBACK_STYLE.items() if name not in default_style}
        if fallback_style:
            self._window.frame.set_style(fallback_style)
        with ui.Frame():
            with ui.ZStack(width=ui.Pixel(preferred_size[0]), height=ui.Pixel(preferred_size[1])):
                ui.Rectangle(name="WorkspaceBackground", opaque_for_mouse_events=False)
                with ui.HStack():
                    ui.Spacer(width=self._PADDING)
                    with ui.VStack():
                        ui.Spacer(height=self._PADDING)
                        with ui.HStack(spacing=self._SPACING):
                            with ui.VStack(width=main_width, spacing=self._SPACING):
                                with ui.HStack(spacing=self._SPACING, height=self._PLANE_SIZE):
                                    with ui.ZStack(width=self._PLANE_SIZE):
                                        self._sv_image = ui.ImageWithProvider(
                                            self._sv_provider,
                                            fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                                            identifier="color_picker_sv",
                                            mouse_pressed_fn=partial(self._on_plane_pressed, "sv", self._window),
                                            mouse_moved_fn=partial(self._on_plane_moved, "sv", self._window),
                                            mouse_released_fn=partial(self._on_plane_released, self._window),
                                        )
                                        self._sv_marker = ui.Placer(stable_size=True)
                                        with self._sv_marker:
                                            with ui.ZStack(width=self._MARKER_SIZE, height=self._MARKER_SIZE):
                                                ui.Circle(
                                                    width=self._MARKER_SIZE,
                                                    height=self._MARKER_SIZE,
                                                    name="ColorPickerHandleOutline",
                                                    opaque_for_mouse_events=False,
                                                )
                                                ui.Circle(
                                                    width=self._MARKER_SIZE,
                                                    height=self._MARKER_SIZE,
                                                    radius=float(self._MARKER_INNER_SIZE) / 2,
                                                    size_policy=ui.CircleSizePolicy.FIXED,
                                                    alignment=ui.Alignment.CENTER,
                                                    name="ColorPickerHandle",
                                                    opaque_for_mouse_events=False,
                                                )
                                    with ui.ZStack(width=self._HUE_WIDTH):
                                        self._hue_image = ui.ImageWithProvider(
                                            self._hue_provider,
                                            fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                                            identifier="color_picker_hue",
                                            mouse_pressed_fn=partial(self._on_plane_pressed, "hue", self._window),
                                            mouse_moved_fn=partial(self._on_plane_moved, "hue", self._window),
                                            mouse_released_fn=partial(self._on_plane_released, self._window),
                                        )
                                        self._hue_marker = ui.Placer(stable_size=True)
                                        with self._hue_marker:
                                            with ui.HStack(width=self._HUE_WIDTH, height=self._HUE_MARKER_HEIGHT):
                                                ui.Triangle(
                                                    width=self._HUE_MARKER_WIDTH,
                                                    height=self._HUE_MARKER_HEIGHT,
                                                    alignment=ui.Alignment.RIGHT_CENTER,
                                                    name="ColorPickerHueHandle",
                                                    opaque_for_mouse_events=False,
                                                )
                                                ui.Spacer()
                                                ui.Triangle(
                                                    width=self._HUE_MARKER_WIDTH,
                                                    height=self._HUE_MARKER_HEIGHT,
                                                    alignment=ui.Alignment.LEFT_CENTER,
                                                    name="ColorPickerHueHandle",
                                                    opaque_for_mouse_events=False,
                                                )
                                self._build_numeric_row(
                                    [
                                        (name[0].upper(), parent, partial(self._write_component, index), name)
                                        for index, (name, parent) in enumerate(
                                            zip(self._CHANNEL_NAMES, self._components)
                                        )
                                    ]
                                )
                                hsv_fields = [
                                    (label, parent, partial(self._write_hsv, index), name)
                                    for index, (label, parent, name) in enumerate(
                                        zip("HSV", self._hsv_models, self._HSV_NAMES)
                                    )
                                ]
                                if len(self._components) == 4:
                                    hsv_fields.append(
                                        ("A", self._components[3], partial(self._write_component, 3), "alpha_hsv")
                                    )
                                self._build_numeric_row(hsv_fields)
                                with ui.HStack(height=self._CHANNEL_ROW_HEIGHT):
                                    ui.Label("Hex", width=self._HEX_LABEL_WIDTH)
                                    ui.StringField(
                                        model=self._create_input_model(
                                            self._hex_model, self._write_hex_text, commit_fn=self._commit_hex
                                        ),
                                        identifier="color_picker_hex",
                                    )
                            with ui.VStack(width=self._CURRENT_WIDTH, spacing=self._SPACING):
                                ui.Label("Current", height=self._CHANNEL_ROW_HEIGHT)
                                with ui.ZStack(height=self._CURRENT_HEIGHT):
                                    if len(self._components) == 4:
                                        with ui.HStack():
                                            self._current_opaque = ui.Rectangle(opaque_for_mouse_events=False)
                                            with ui.ZStack():
                                                ui.ImageWithProvider(
                                                    self._checker_provider,
                                                    fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                                                )
                                                self._current_alpha = ui.Rectangle(opaque_for_mouse_events=False)
                                    else:
                                        self._current_opaque = ui.Rectangle(opaque_for_mouse_events=False)
                                    ui.Rectangle(name="ColorPickerCurrentBorder", opaque_for_mouse_events=False)
                                ui.Spacer()
                        ui.Spacer(height=self._BOTTOM_PADDING)
                    ui.Spacer(width=self._RIGHT_PADDING)
        self._sv_image.set_computed_content_size_changed_fn(partial(self._update_markers, self._window))
        self._hue_image.set_computed_content_size_changed_fn(partial(self._update_markers, self._window))
        self._refresh()

    def _create_input_model(self, parent, write_fn, *, commit_fn=None):
        """Connect one popup editor to the shared gesture and cleanup lifecycle."""
        proxy = _PickerValueModel(parent, write_fn)
        index = len(self._numeric_models)
        self._numeric_models.append(proxy)
        self._numeric_subscriptions.extend(
            (
                proxy.subscribe_begin_edit_fn(partial(self._on_numeric_begin, index)),
                proxy.subscribe_end_edit_fn(partial(self._on_numeric_end, index, commit_fn=commit_fn)),
            )
        )
        return proxy

    def _build_numeric_row(self, fields):
        """Build a compact row of labeled component editors."""
        with ui.HStack(height=self._CHANNEL_ROW_HEIGHT, spacing=self._SPACING):
            for label, parent, write_fn, identifier in fields:
                with ui.HStack():
                    ui.Label(label, width=self._CHANNEL_LABEL_WIDTH, alignment=ui.Alignment.CENTER)
                    ui.FloatDrag(
                        model=self._create_input_model(parent, write_fn),
                        step=self._NUMERIC_STEP,
                        precision=4,
                        identifier=f"color_picker_{identifier}",
                    )

    def close(self):
        """Finish complete color updates and focused numeric input before closing."""
        if self._window is None or self._close_task is not None:
            return
        if (self._numeric_editing is not None and not self._writing) or self._writing_color:
            self._close_task = asyncio.ensure_future(self._close_after_update(self._window))
        else:
            window = self._window
            try:
                self._commit_hex()
                if self._window is window:
                    self._finish_gesture()
            finally:
                if self._window is window:
                    self._input_enabled = False
                    self._release_window()

    def cancel(self):
        """Close the popup without committing buffered numeric input."""
        self._input_enabled = False
        self._gesture_active = False
        self._pointer_control = None
        self._numeric_editing = None
        self._release_window()

    def destroy(self):
        """Release owned UI and callbacks without destroying the borrowed model."""
        self._model_subscription = None
        self.cancel()
        self._begin_edit_fn = None
        self._end_edit_fn = None
        self._model = None
        self._components = ()
        self._sv_provider = self._hue_provider = self._checker_provider = None
        super().destroy()

    async def _close_after_update(self, window):
        """Let native input dispatch finish before closing its gesture and controls."""
        await get_app().next_update_async()
        self._close_task = None
        if self._window is window:
            try:
                self._commit_hex()
                if self._window is window:
                    self._finish_gesture()
            finally:
                if self._window is window:
                    self._input_enabled = False
                    self._release_window()

    def _release_window(self):
        """Disable popup input and transfer retired controls to their window owner."""
        if self._close_task is not None:
            self._close_task.cancel()
            self._close_task = None
        window, self._window = self._window, None
        if window is None:
            return
        self._pointer_control = None
        self._numeric_editing = None
        for proxy in self._numeric_models:
            proxy.destroy()
        window.retire(self._numeric_models, self._numeric_subscriptions)
        self._numeric_models = []
        self._numeric_subscriptions = []
        self._hsv_models = []
        self._hex_model = None
        self._hex_dirty = False
        self._current_opaque = self._current_alpha = None
        self._sv_image = self._hue_image = None
        self._sv_marker = self._hue_marker = None

    def _on_swatch_released(self, _x, _y, button, _modifier):
        """Open the picker on a left click of its swatch."""
        if button == 0:
            self.open()

    def _start_gesture(self):
        """Begin a property transaction on its first actual value change."""
        if not self._gesture_active:
            self._gesture_active = True
            self._begin_edit_fn()

    def _finish_gesture(self):
        """Commit a completed gesture once."""
        if self._gesture_active:
            self._gesture_active = False
            self._end_edit_fn()

    def _on_numeric_begin(self, index, model):
        """Track focused numeric input before its first value change."""
        if self._input_enabled and index < len(self._numeric_models) and self._numeric_models[index] is model:
            self._numeric_editing = index

    def _on_numeric_end(self, index, model, *, commit_fn=None):
        """Finish numeric dragging or a committed text edit."""
        if (
            self._input_enabled
            and self._numeric_editing == index
            and index < len(self._numeric_models)
            and self._numeric_models[index] is model
        ):
            self._numeric_editing = None
            window = self._window
            if commit_fn is not None:
                commit_fn()
            if self._window is window:
                self._finish_gesture()

    def _write_component(self, index, value):
        """Author one unrestricted RGB or alpha component."""
        values = [model.get_value_as_float() for model in self._components]
        values[index] = float(value)
        self._write_color(values)

    def _write_hsv(self, index, value):
        """Update normalized hue/saturation or nonnegative HDR value."""
        hsv = [self._hue, self._saturation, self._value]
        value = max(0.0, float(value))
        hsv[index] = min(1.0, value) if index < 2 else value
        self._hue, self._saturation, self._value = hsv
        values = [*colorsys.hsv_to_rgb(*hsv), *(model.get_value_as_float() for model in self._components[3:])]
        self._write_color(values, read_hsv=False)

    def _write_color(self, values, *, read_hsv=True):
        """Apply a complete color while rejecting cancelled or replaced input."""
        if not self._input_enabled:
            return
        changes = [
            (model, value) for model, value in zip(self._components, values) if value != model.get_value_as_float()
        ]
        if changes:
            window = self._window
            self._start_gesture()
            if not self._input_enabled or self._window is not window:
                return
            self._writing = True
            self._writing_color = len(changes) > 1
            try:
                for model, value in changes:
                    if not self._input_enabled or self._window is not window:
                        return
                    model.set_value(value)
            finally:
                self._writing = False
                self._writing_color = False
            if not self._input_enabled or self._window is not window:
                return
        self._refresh(read_hsv=read_hsv)

    def _format_hex(self):
        """Format clipped display bytes without changing authoritative HDR values."""
        return "#" + "".join(f"{self._display_byte(model.get_value_as_float()):02X}" for model in self._components)

    @staticmethod
    def _display_byte(value: float) -> int:
        """Round a clipped display channel with Kit's float32 color arithmetic."""
        scaled = c_float(min(1.0, max(0.0, value)) * 255).value
        rounded = c_float(scaled + 0.5).value
        return int(rounded)

    def _write_hex_text(self, value):
        """Buffer color text until the hexadecimal editor commits."""
        if self._input_enabled and self._hex_model is not None:
            self._hex_dirty = True
            self._hex_model.set_value(str(value))

    def _commit_hex(self):
        """Commit hexadecimal or normalized tuple input, or restore the canonical display."""
        if not self._input_enabled or not self._hex_dirty or self._hex_model is None:
            return
        window, model = self._window, self._hex_model
        text = model.get_value_as_string().strip()
        self._hex_dirty = False
        if text.startswith("(") and text.endswith(")"):
            components = text[1:-1].split(",", len(self._components))
            if len(components) == len(self._components):
                try:
                    values = [float(component) for component in components]
                except ValueError:
                    text = ""
                else:
                    if all(0 <= value <= 1 for value in values):
                        text = "".join(f"{self._display_byte(value):02X}" for value in values)
        text = text.removeprefix("#")
        if len(text) == len(self._components) * 2 and all(character in hexdigits for character in text):
            self._write_color([int(text[index : index + 2], 16) / 255 for index in range(0, len(text), 2)])
        if self._window is window and self._hex_model is model:
            model.set_value(self._format_hex())

    def _on_plane_pressed(self, control, window, x, y, button, _modifier):
        """Start tracking input belonging to an owned color plane."""
        if window is self._window and button == 0 and self._input_enabled:
            self._pointer_control = control
            self._value_scale = max(1.0, self._value)
            self._pick_color(control, x, y)

    def _on_plane_moved(self, control, window, x, y, _modifier, _pressed):
        """Apply continuous color changes from an owned drag."""
        if window is self._window and self._pointer_control == control and self._input_enabled:
            self._pick_color(control, x, y)

    def _on_plane_released(self, window, _x, _y, button, _modifier):
        """Finish the gesture when its initiating mouse button is released."""
        if window is self._window and button == 0:
            self._pointer_control = None
            self._finish_gesture()

    def _pick_color(self, control, x, y):
        """Convert an owned control's pointer coordinates into a floating color."""
        image = self._sv_image if control == "sv" else self._hue_image
        if image is None or image.computed_width <= 0 or image.computed_height <= 0:
            return
        horizontal = min(1.0, max(0.0, (x - image.screen_position_x) / image.computed_width))
        vertical = min(1.0, max(0.0, (y - image.screen_position_y) / image.computed_height))
        if control == "sv":
            self._saturation = horizontal
            self._value = (1.0 - vertical) * self._value_scale
        else:
            self._hue = vertical
        values = [
            *colorsys.hsv_to_rgb(self._hue, self._saturation, self._value),
            *(model.get_value_as_float() for model in self._components[3:]),
        ]
        self._write_color(values, read_hsv=False)

    def _on_model_changed(self, _model, _item):
        """Reflect authoritative colors and cancel uncommitted numeric text."""
        if self._writing:
            return
        if self._numeric_editing is not None:
            self.cancel()
        self._refresh()

    def _refresh(self, *, read_hsv=True):
        """Update previews without quantizing the component values."""
        values = [component.get_value_as_float() for component in self._components]
        if read_hsv:
            # HSV controls represent nonnegative colors; numeric authoring keeps the original channels.
            hue, saturation, value = colorsys.rgb_to_hsv(*(max(0.0, channel) for channel in values[:3]))
            if saturation > 0 and value > 0:
                self._hue = hue
            if value > 0:
                self._saturation = saturation
            self._value = value
        rgba = values if len(values) == 4 else [*values, 1.0]
        self._swatch.set_style({"background_color": color_to_hex(tuple(rgba))})
        for model, value in zip(self._hsv_models, (self._hue, self._saturation, self._value)):
            model.set_value(value)
        if self._hex_model is not None and not self._hex_dirty:
            self._hex_model.set_value(self._format_hex())
        if self._current_opaque is not None:
            self._current_opaque.set_style({"background_color": color_to_hex((*values[:3], 1.0))})
        if self._current_alpha is not None:
            self._current_alpha.set_style({"background_color": color_to_hex(tuple(rgba))})
        if self._sv_image is not None and self._preview_hue != self._hue:
            self._preview_hue = self._hue
            hue_rgb = colorsys.hsv_to_rgb(self._hue, 1, 1)
            pixels = []
            for row in range(self._SV_TEXTURE_SIZE):
                value = 1 - row / (self._SV_TEXTURE_SIZE - 1)
                for column in range(self._SV_TEXTURE_SIZE):
                    saturation = column / (self._SV_TEXTURE_SIZE - 1)
                    pixels.extend(round((1 - saturation + saturation * channel) * value * 255) for channel in hue_rgb)
                    pixels.append(255)
            self._sv_provider.set_bytes_data(pixels, [self._SV_TEXTURE_SIZE, self._SV_TEXTURE_SIZE])
        self._update_markers(self._window)

    def _update_markers(self, window):
        """Position the current popup's selectors after its color or measured layout changes."""
        if window is not self._window:
            return
        if self._sv_image is not None and self._sv_image.computed_width > 0 and self._sv_image.computed_height > 0:
            self._sv_marker.offset_x = ui.Pixel(
                min(1.0, max(0.0, self._saturation)) * self._sv_image.computed_width - float(self._MARKER_SIZE) / 2
            )
            self._sv_marker.offset_y = ui.Pixel(
                (1 - min(1.0, max(0.0, self._value / self._value_scale))) * self._sv_image.computed_height
                - float(self._MARKER_SIZE) / 2
            )
        if self._hue_image is not None and self._hue_image.computed_height > 0:
            self._hue_marker.offset_y = ui.Pixel(
                self._hue * self._hue_image.computed_height - float(self._HUE_MARKER_HEIGHT) / 2
            )

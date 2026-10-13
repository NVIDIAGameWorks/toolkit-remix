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
from functools import partial

import carb
import omni.ui as ui
from omni.flux.utils.widget.color import color_to_hex
from omni.kit.app import get_app
from omni.ui import color as cl


class _ComponentValueModel(ui.AbstractValueModel):
    """Start an edit before forwarding a numeric color change to its owner."""

    def __init__(self, parent: ui.AbstractValueModel, write_fn: Callable[[float], None]):
        """Borrow a component and connect its public value notifications.

        Args:
            parent: Authoritative component model retained for native value getters.
            write_fn: Callback that begins the gesture before updating the component.
        """
        super().__init__()
        self._parent = parent
        self._write_fn = write_fn
        self._subscription = parent.subscribe_value_changed_fn(lambda _: self._value_changed())

    def get_value_as_float(self):
        """Return the authoritative component value without limiting its range."""
        return self._parent.get_value_as_float()

    def get_value_as_string(self):
        """Return the component text used by the numeric editor."""
        return str(self.get_value_as_float())

    def set_value(self, value):
        """Forward a numeric edit while the popup accepts input."""
        if self._write_fn is not None:
            self._write_fn(float(value))

    def destroy(self):
        """Release the borrowed component subscription and input callback."""
        self._write_fn = None
        self._subscription = None


class ColorPicker(ui.Frame):
    """Display a color swatch with an owned picker and explicit gesture boundaries."""

    _PLANE_SIZE = ui.Pixel(180)
    _HUE_WIDTH = ui.Pixel(20)
    _SWATCH_WIDTH = ui.Pixel(24)
    _SWATCH_HEIGHT = ui.Pixel(20)
    _WINDOW_WIDTH = ui.Pixel(260)
    _WINDOW_HEIGHT = ui.Pixel(360)
    _CHANNEL_ROW_HEIGHT = ui.Pixel(20)
    _CHANNEL_LABEL_WIDTH = ui.Pixel(45)
    _SPACING = ui.Pixel(6)
    _PADDING = ui.Pixel(8)
    _CLOSE_HEIGHT = ui.Pixel(24)
    _MARKER_SIZE = ui.Pixel(12)
    _MARKER_INNER_SIZE = ui.Pixel(10)
    _HUE_MARKER_WIDTH = ui.Pixel(6)
    _HUE_MARKER_HEIGHT = ui.Pixel(10)
    _NUMERIC_STEP = 0.001
    _SV_TEXTURE_SIZE = 64
    _HUE_TEXTURE_HEIGHT = 256
    _CHANNEL_NAMES = ("red", "green", "blue", "alpha")
    _HANDLE_FALLBACK_STYLE = {
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
        **kwargs,
    ):
        """Borrow a color model and callbacks for the first change and final gesture value.

        Args:
            model: Caller-owned item model containing RGB or RGBA component values.
            begin_edit_fn: Callback invoked before the first actual change of a gesture.
            end_edit_fn: Callback that flushes and commits the gesture's final value.
            **kwargs: Built-in Frame constructor options for the swatch.
        """
        super().__init__(**kwargs)
        self._model = model
        self._components = tuple(model.get_item_value_model(item) for item in model.get_item_children())
        self._begin_edit_fn = begin_edit_fn
        self._end_edit_fn = end_edit_fn
        self._style_name = kwargs.get("style_type_name_override", kwargs.get("name", "ColorsWidgetFieldRead"))
        self._window = None
        self._close_task = None
        self._window_focused = False
        self._input_enabled = False
        self._gesture_active = False
        self._pointer_control = None
        self._numeric_editing = None
        self._writing = False
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
        return f"ColorPicker_{id(self)}"

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
        """Open the owned popup without starting a property edit."""
        if not self.enabled or self._window is not None or self._model is None:
            return
        self._input_enabled = True
        self._window_focused = False
        self._refresh()
        self._value_scale = max(1.0, self._value)
        if self._hue_provider is None:
            self._sv_provider = ui.ByteImageProvider()
            self._hue_provider = ui.ByteImageProvider()
            self._hue_provider.set_bytes_data(self._HUE_BYTES, [1, self._HUE_TEXTURE_HEIGHT])
        popup_height = float(self._WINDOW_HEIGHT) + (
            float(self._CHANNEL_ROW_HEIGHT) + float(self._SPACING) if len(self._components) == 4 else 0
        )
        position_y = self.screen_position_y + self.computed_height
        if position_y + popup_height > ui.Workspace.get_main_window_height():
            position_y = max(0.0, self.screen_position_y - popup_height)
        self._window = ui.Window(
            self.window_title,
            width=float(self._WINDOW_WIDTH),
            height=popup_height,
            position_x=self.screen_position_x,
            position_y=position_y,
            flags=ui.WINDOW_FLAGS_POPUP
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_DOCKING
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_TITLE_BAR
            | ui.WINDOW_FLAGS_NO_MOVE,
        )
        default_style = ui.Style.get_instance().default
        fallback_style = {
            name: style for name, style in self._HANDLE_FALLBACK_STYLE.items() if name not in default_style
        }
        if fallback_style:
            self._window.frame.set_style(fallback_style)
        with self._window.frame:
            with ui.ZStack():
                ui.Rectangle(name="WorkspaceBackground", opaque_for_mouse_events=False)
                with ui.HStack():
                    ui.Spacer(width=self._PADDING)
                    with ui.VStack(spacing=self._SPACING):
                        ui.Spacer(height=self._PADDING)
                        with ui.HStack(spacing=self._SPACING, height=self._PLANE_SIZE):
                            with ui.ZStack(width=self._PLANE_SIZE):
                                self._sv_image = ui.ImageWithProvider(
                                    self._sv_provider,
                                    fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                                    identifier="color_picker_sv",
                                    mouse_pressed_fn=partial(self._on_plane_pressed, "sv"),
                                    mouse_moved_fn=partial(self._on_plane_moved, "sv"),
                                    mouse_released_fn=self._on_plane_released,
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
                                    mouse_pressed_fn=partial(self._on_plane_pressed, "hue"),
                                    mouse_moved_fn=partial(self._on_plane_moved, "hue"),
                                    mouse_released_fn=self._on_plane_released,
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
                        for index, component in enumerate(self._components):
                            proxy = _ComponentValueModel(component, partial(self._write_component, index))
                            self._numeric_models.append(proxy)
                            self._numeric_subscriptions.extend(
                                (
                                    proxy.subscribe_begin_edit_fn(partial(self._on_numeric_begin, index)),
                                    proxy.subscribe_end_edit_fn(partial(self._on_numeric_end, index)),
                                )
                            )
                            with ui.HStack(height=self._CHANNEL_ROW_HEIGHT):
                                ui.Label(self._CHANNEL_NAMES[index].capitalize(), width=self._CHANNEL_LABEL_WIDTH)
                                ui.FloatDrag(
                                    model=proxy,
                                    step=self._NUMERIC_STEP,
                                    precision=4,
                                    identifier=f"color_picker_{self._CHANNEL_NAMES[index]}",
                                )
                        ui.Spacer()
                        ui.Button(
                            "Close",
                            height=self._CLOSE_HEIGHT,
                            identifier="color_picker_close",
                            clicked_fn=self.close,
                        )
                        ui.Spacer(height=self._PADDING)
                    ui.Spacer(width=self._PADDING)
        self._window.set_key_pressed_fn(self._on_key_pressed)
        self._window.set_focused_changed_fn(self._on_focus_changed)
        self._window.set_visibility_changed_fn(self._on_visibility_changed)
        self._refresh()

    def close(self):
        """Commit focused numeric input and finish its gesture before closing."""
        if self._window is None or self._close_task is not None:
            return
        if self._numeric_editing is not None and not self._writing:
            self._close_task = asyncio.ensure_future(self._close_after_update(self._window))
        else:
            window = self._window
            try:
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
        super().destroy()

    async def _close_after_update(self, window):
        """Let focus-loss dispatch commit before disposing of numeric controls."""
        await get_app().next_update_async()
        self._close_task = None
        if self._window is window:
            try:
                self._finish_gesture()
            finally:
                if self._window is window:
                    self._input_enabled = False
                    self._release_window()

    def _release_window(self):
        """Hide the owned window and defer destruction until callbacks finish."""
        if self._close_task is not None:
            self._close_task.cancel()
            self._close_task = None
        window, self._window = self._window, None
        if window is None:
            return
        self._pointer_control = None
        self._numeric_editing = None
        self._window_focused = False
        window.set_key_pressed_fn(None)
        window.set_focused_changed_fn(None)
        window.set_visibility_changed_fn(None)
        for proxy in self._numeric_models:
            proxy.destroy()
        window.visible = False
        asyncio.ensure_future(
            self._destroy_window_after_update(window, self._numeric_models, self._numeric_subscriptions)
        )
        self._numeric_models = []
        self._numeric_subscriptions = []
        self._sv_image = self._hue_image = None
        self._sv_marker = self._hue_marker = None

    @staticmethod
    async def _destroy_window_after_update(window, models, subscriptions):
        """Destroy hidden controls after their native event dispatch completes."""
        await get_app().next_update_async()
        subscriptions.clear()
        for model in models:
            model.destroy()
        window.destroy()

    def _on_swatch_released(self, _x, _y, button, _modifier):
        """Open the picker on a left click of its swatch."""
        if button == 0:
            self.open()

    def _on_key_pressed(self, key, _modifier, down):
        """Close the owned window when Escape is pressed."""
        if down and key == int(carb.input.KeyboardInput.ESCAPE):
            self.close()

    def _on_focus_changed(self, focused):
        """Close an opened picker when its own window loses focus."""
        if focused:
            self._window_focused = True
        elif self._window_focused:
            self.close()

    def _on_visibility_changed(self, visible):
        """Finish a gesture when the window's close control hides it."""
        if not visible and self._window is not None:
            self.close()

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

    def _on_numeric_end(self, index, model):
        """Finish numeric dragging or a committed text edit."""
        if (
            self._input_enabled
            and self._numeric_editing == index
            and index < len(self._numeric_models)
            and self._numeric_models[index] is model
        ):
            self._numeric_editing = None
            self._finish_gesture()

    def _write_component(self, index, value):
        """Author unrestricted numeric input after beginning its gesture."""
        component = self._components[index]
        if not self._input_enabled or value == component.get_value_as_float():
            return
        self._start_gesture()
        if not self._input_enabled:
            return
        self._writing = True
        try:
            component.set_value(value)
        finally:
            self._writing = False
        self._refresh()

    def _on_plane_pressed(self, control, x, y, button, _modifier):
        """Start tracking input belonging to an owned color plane."""
        if button == 0 and self._input_enabled:
            self._pointer_control = control
            self._value_scale = max(1.0, self._value)
            self._pick_color(control, x, y)

    def _on_plane_moved(self, control, x, y, _modifier, _pressed):
        """Apply continuous color changes from an owned drag."""
        if self._pointer_control == control and self._input_enabled:
            self._pick_color(control, x, y)

    def _on_plane_released(self, _x, _y, button, _modifier):
        """Finish the gesture when its initiating mouse button is released."""
        if button == 0:
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
        rgb = colorsys.hsv_to_rgb(self._hue, self._saturation, self._value)
        if any(value != component.get_value_as_float() for value, component in zip(rgb, self._components)):
            self._start_gesture()
            if not self._input_enabled:
                return
            self._writing = True
            try:
                for component, value in zip(self._components, rgb):
                    component.set_value(value)
            finally:
                self._writing = False
        self._refresh(read_hsv=False)

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
            self._saturation = saturation
            self._value = value
        rgba = values if len(values) == 4 else [*values, 1.0]
        self._swatch.set_style({"background_color": color_to_hex(tuple(rgba))})
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
        if self._sv_image is not None:
            self._sv_marker.offset_x = ui.Pixel(
                min(1.0, max(0.0, self._saturation)) * self._sv_image.computed_width - float(self._MARKER_SIZE) / 2
            )
            self._sv_marker.offset_y = ui.Pixel(
                (1 - min(1.0, max(0.0, self._value / self._value_scale))) * self._sv_image.computed_height
                - float(self._MARKER_SIZE) / 2
            )
            self._hue_marker.offset_y = ui.Pixel(
                self._hue * self._hue_image.computed_height - float(self._HUE_MARKER_HEIGHT) / 2
            )

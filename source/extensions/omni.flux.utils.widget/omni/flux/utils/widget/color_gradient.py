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

__all__ = ["GRADIENT_PRESETS", "ColorGradientWidget"]

import contextlib
import itertools
import random
import weakref
from collections.abc import Callable, Sequence
from functools import partial

import carb
import carb.input
import omni.appwindow
import omni.kit.app
import omni.ui as ui

from .gradient import create_checkerboard, create_multi_stop_gradient, sample_gradient_at_time
from .resources import get_icons

# ---------------------------------------------------------------------------
# Layout constants — derived from the standard property-panel row height
# ---------------------------------------------------------------------------
_GRADIENT_IMAGE_WIDTH = 128
_GRADIENT_IMAGE_HEIGHT = 1
_CHECKER_IMAGE_WIDTH = 2048  # Large enough to avoid stretching on most displays
_CHECKER_IMAGE_HEIGHT = 16

_STANDARD_ROW_HEIGHT = 24  # matches DEFAULT_IMAGE_ICON_SIZE across the property panel

_MARKER_SIZE = 12  # marker SVG width
_HALF_MARKER = _MARKER_SIZE // 2
_MARKER_COLOR = 0xFFBBBBBB  # default marker tint
_MARKER_SELECTED_COLOR = 0xFFFFFFFF  # selected marker tint

_TOP_PAD = 2  # small gap so the gradient bar doesn't touch the row above
_GRADIENT_BAR_HEIGHT = _STANDARD_ROW_HEIGHT  # gradient image strip, matches normal field height
_EDIT_ROW_HEIGHT = _STANDARD_ROW_HEIGHT  # keyframe controls row
_KF_LABEL_WIDTH = 38  # fits "12/12" comfortably
_KF_TIME_FIELD_WIDTH = 58  # fits "0.10494" with room to spare
_EDIT_ICON_SIZE = 20  # icon button size for the edit row (trash, menu, arrows)
_EDIT_GROUP_SPACING = 12  # space between logical groups in the edit row
_GRADIENT_BORDER_RADIUS = 5  # corner radius for the gradient bar background rectangle
_TIME_DECIMAL_PLACES = 5  # decimal precision for stored keyframe times

_POPUP_MARKER_HEIGHT = 18  # total marker SVG height
_POPUP_MARKER_HEIGHT_TOTAL = _POPUP_MARKER_HEIGHT + 4  # room below markers
_POPUP_MARKER_BOTTOM_PAD = 10  # breathing room between marker row and edit row
_POPUP_MIN_WIDTH = 500  # minimum popup content width; keeps the edit row readable on narrow panels
_POPUP_BOTTOM_PAD = 4  # small gap below the edit row so the bottom isn't flush with the window edge
_POPUP_WIDGET_HEIGHT = (
    _TOP_PAD
    + _GRADIENT_BAR_HEIGHT
    + _POPUP_MARKER_HEIGHT_TOTAL
    + _POPUP_MARKER_BOTTOM_PAD
    + _EDIT_ROW_HEIGHT
    + _POPUP_BOTTOM_PAD
)

# Inline widget shows only the gradient bar (collapsed); full UI appears in the hover popup.
_GRADIENT_WIDGET_HEIGHT = _TOP_PAD + _GRADIENT_BAR_HEIGHT + _TOP_PAD

# Opaque background for the gradient region so TreeView row highlights don't bleed through.
_GRADIENT_BG_COLOR = 0xFF242424

_MAX_KEYFRAMES = 128  # gradient image is 128 px wide; more keyframes exceed 1-px-per-stop resolution

_NOOP = lambda *_: None  # noqa: E731  # no-op callback for read-only mode

_GRADIENT_KF_ICON: str | None = None
_LOCAL_STYLE: dict | None = None


def _gradient_kf_icon() -> str:
    """Lazily resolve the GradientKeyframe SVG path from omni.flux.resources."""
    global _GRADIENT_KF_ICON
    if _GRADIENT_KF_ICON is None:
        _GRADIENT_KF_ICON = get_icons("GradientKeyframe", ext_name="omni.flux.resources") or ""
    return _GRADIENT_KF_ICON


def _get_local_style() -> dict:
    """Lazily build the local style fallback, resolving icon paths at runtime."""
    global _LOCAL_STYLE
    if _LOCAL_STYLE is not None:
        return _LOCAL_STYLE

    resources_ext = "omni.flux.resources"
    w60, w80, w30 = 0x99FFFFFF, 0xCCFFFFFF, 0x4DFFFFFF

    _LOCAL_STYLE = {
        "Rectangle::ColorGradientBarOverlay": {
            "background_color": 0x00000000,
            "border_radius": _GRADIENT_BORDER_RADIUS,
            "border_width": 1,
            "border_color": 0x33FFFFFF,
        },
        "Image::ArrowLeft": {"image_url": get_icons("arrow-left", ext_name=resources_ext), "color": w60},
        "Image::ArrowLeft:disabled": {"image_url": get_icons("arrow-left", ext_name=resources_ext), "color": w30},
        "Image::ArrowLeft:hovered": {"image_url": get_icons("arrow-left", ext_name=resources_ext), "color": w80},
        "Image::ArrowRight": {"image_url": get_icons("arrow-right", ext_name=resources_ext), "color": w60},
        "Image::ArrowRight:disabled": {"image_url": get_icons("arrow-right", ext_name=resources_ext), "color": w30},
        "Image::ArrowRight:hovered": {"image_url": get_icons("arrow-right", ext_name=resources_ext), "color": w80},
        "Image::TrashCan": {"image_url": get_icons("trash-can", ext_name=resources_ext), "color": w60},
        "Image::TrashCan:disabled": {"image_url": get_icons("trash-can", ext_name=resources_ext), "color": w30},
        "Image::TrashCan:hovered": {"image_url": get_icons("trash-can", ext_name=resources_ext), "color": w80},
        "Image::MenuBurger": {"image_url": get_icons("menu-burger", ext_name=resources_ext), "color": w60},
        "Image::MenuBurger:hovered": {"image_url": get_icons("menu-burger", ext_name=resources_ext), "color": w80},
    }
    return _LOCAL_STYLE


# Gradient presets - professional/technical gradients
GRADIENT_PRESETS = {
    "Constant": [],  # No keyframes - uses the color swatch value
    "Grayscale": [
        (0.0, (0.0, 0.0, 0.0, 1.0)),  # Black
        (1.0, (1.0, 1.0, 1.0, 1.0)),  # White
    ],
    "White to Black": [
        (0.0, (1.0, 1.0, 1.0, 1.0)),  # White
        (1.0, (0.0, 0.0, 0.0, 1.0)),  # Black
    ],
    "Linear Red": [
        (0.0, (0.0, 0.0, 0.0, 1.0)),  # Black (no red)
        (1.0, (1.0, 0.0, 0.0, 1.0)),  # Pure red
    ],
    "Linear Green": [
        (0.0, (0.0, 0.0, 0.0, 1.0)),  # Black (no green)
        (1.0, (0.0, 1.0, 0.0, 1.0)),  # Pure green
    ],
    "Linear Blue": [
        (0.0, (0.0, 0.0, 0.0, 1.0)),  # Black (no blue)
        (1.0, (0.0, 0.0, 1.0, 1.0)),  # Pure blue
    ],
    "Transparent to Opaque": [
        (0.0, (1.0, 1.0, 1.0, 0.0)),  # Fully transparent white
        (1.0, (1.0, 1.0, 1.0, 1.0)),  # Fully opaque white
    ],
}

# Type alias – a keyframe is (time, (r, g, b, a)) with floats in [0, 1].
Color4 = tuple[float, float, float, float]
Keyframe = tuple[float, Color4]

_uid_counter = itertools.count(1)


class _KF:
    """Internal mutable keyframe with a stable unique id for drag tracking."""

    __slots__ = ("uid", "time", "color")

    def __init__(self, time: float, color: Color4):
        self.uid: int = next(_uid_counter)
        self.time: float = time
        self.color: Color4 = color


class ColorGradientWidget:
    """A multi-stop color gradient editor with draggable keyframe markers.

    The widget renders a horizontal gradient bar with SVG markers
    for each keyframe.  A ``ui.ColorWidget`` swatch on the left provides quick
    constant-color editing.

    Args:
        keyframes: Initial keyframes as ``(time, (r, g, b, a))`` pairs.
        default_color: Solid fill color when no keyframes are present.
        read_only: If ``True``, all mouse interactions and editing are disabled.
        on_gradient_changed_fn: Callback ``(times, values)`` fired on every edit.
        time_range: ``(min, max)`` bounds for keyframe time values.
            Defaults to ``(0.0, 1.0)``.  The gradient left edge corresponds to
            *min* and the right edge to *max*.
    """

    # Inline row height: gradient bar only (no markers/edit row).
    HEIGHT: int = _GRADIENT_WIDGET_HEIGHT

    # Class-level sentinel: at most one gradient popup is visible at a time.
    # Stored as a weakref so that a lingering class reference cannot prevent GC.
    _active_popup_widget: weakref.ref[ColorGradientWidget] | None = None

    def __init__(
        self,
        keyframes: Sequence[Keyframe] | None = None,
        default_color: Color4 = (0.2, 0.2, 0.2, 1.0),
        read_only: bool = False,
        on_gradient_changed_fn: Callable[[list[float], list[Color4]], None] | None = None,
        time_range: tuple[float, float] = (0.0, 1.0),
        title: str = "",
        **kwargs,
    ):
        self._time_min, self._time_max = time_range
        self._title = title

        self._keyframes: list[_KF] = sorted(
            [_KF(t, c) for t, c in (keyframes or [])],
            key=lambda kf: kf.time,
        )
        self._default_color: Color4 = default_color
        self._read_only: bool = read_only
        self._gradient_changed_fns: list = []
        if on_gradient_changed_fn is not None:
            self._gradient_changed_fns.append(on_gradient_changed_fn)

        # Auto-select first keyframe if available
        self._selected_uid: int | None = self._keyframes[0].uid if self._keyframes else None

        # Widget references
        self._checker_provider: ui.ByteImageProvider | None = None
        self._gradient_provider: ui.ByteImageProvider | None = None
        self._gradient_overlay: ui.Widget | None = None
        self._gradient_bar_stack: ui.ZStack | None = None
        self._color_widget: ui.ColorWidget | None = None
        self._presets_button: ui.Button | ui.Image | None = None
        self._presets_menu: ui.Menu | None = None

        # Outer container reference (used for popup positioning)
        self._outer_container: ui.VStack | None = None

        # Popup window and its frames
        self._popup_window: ui.Window | None = None
        self._popup_markers_frame: ui.Frame | None = None
        self._popup_edit_frame: ui.Frame | None = None
        # Transparent overlay on the popup gradient bar (used for click-to-add position math)
        self._popup_gradient_overlay: ui.Widget | None = None

        # Per-marker widget refs keyed by uid.
        self._marker_widgets: dict[int, ui.Image] = {}
        self._marker_placers: dict[int, ui.Placer] = {}

        # Keep subscriptions alive
        self._subs: list = []
        self._color_subs: list = []
        self._ignore_swatch_change = False
        # Ref-count: > 0 while the color picker popup is open (suppress outside-click dismiss).
        self._color_picker_active: int = 0

        self._drag_started_fns: list = []
        self._drag_ended_fns: list = []

        # Outside-click watcher: per-frame LMB poll that hides the popup when the
        # user clicks anywhere outside the popup window.
        self._carb_input = carb.input.acquire_input_interface()
        app_window = omni.appwindow.get_default_app_window()
        self._app_mouse = app_window.get_mouse() if app_window else None
        self._outside_click_lmb_was_down: bool = False
        self._update_sub = None  # Created lazily when popup is shown; see _show_popup

        self._build_ui(**kwargs)
        self._init_checkerboard()
        self._update_gradient_image()

    # ------------------------------------------------------------------
    # Time-range conversion
    # ------------------------------------------------------------------

    @property
    def time_range(self) -> tuple[float, float]:
        """The ``(min, max)`` time bounds for keyframe positioning."""
        return (self._time_min, self._time_max)

    def _time_span(self) -> float:
        return self._time_max - self._time_min or 1.0

    def _time_to_percent(self, t: float) -> float:
        """Convert a time value in ``[time_min, time_max]`` to ``[0, 100]``."""
        return (t - self._time_min) / self._time_span() * 100.0

    def _percent_to_time(self, pct: float) -> float:
        """Convert a ``[0, 100]`` percent to a time value."""
        return self._time_min + (pct / 100.0) * self._time_span()

    def _clamp_time(self, t: float) -> float:
        return max(self._time_min, min(self._time_max, t))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, **kwargs):
        self._outer_container = ui.VStack(spacing=0, **kwargs)
        if "Rectangle::ColorGradientBarOverlay" not in ui.Style.get_instance().default:
            self._outer_container.set_style(_get_local_style())
        with self._outer_container:
            ui.Spacer(height=ui.Pixel(_TOP_PAD))

            # --- Inline gradient bar — full-width, no marker inset ---
            with ui.HStack(spacing=0, height=ui.Pixel(_GRADIENT_BAR_HEIGHT)):
                self._gradient_bar_stack = ui.ZStack(
                    width=ui.Fraction(1),
                    tooltip="Click to open gradient editor" if not self._read_only else "",
                )
                with self._gradient_bar_stack:
                    ui.Rectangle(
                        style={"background_color": _GRADIENT_BG_COLOR, "border_radius": _GRADIENT_BORDER_RADIUS}
                    )
                    self._checker_provider = ui.ByteImageProvider()
                    ui.ImageWithProvider(
                        self._checker_provider,
                        fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                        name="ColorGradientBar",
                    )
                    self._gradient_provider = ui.ByteImageProvider()
                    ui.ImageWithProvider(
                        self._gradient_provider,
                        fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                        name="ColorGradientBar",
                    )
                    self._gradient_overlay = ui.Rectangle(
                        name="ColorGradientBarOverlay",
                        mouse_released_fn=self._on_inline_bar_released if not self._read_only else _NOOP,
                    )
            ui.Spacer(height=ui.Pixel(_TOP_PAD))
        # Marker row and edit row are shown only in the hover popup.

    def _init_checkerboard(self):
        checker = create_checkerboard(_CHECKER_IMAGE_WIDTH, _CHECKER_IMAGE_HEIGHT, cell_size=4)
        self._checker_provider.set_bytes_data(
            checker.ravel().tolist(),
            [_CHECKER_IMAGE_WIDTH, _CHECKER_IMAGE_HEIGHT],
        )

    # ------------------------------------------------------------------
    # Gradient image
    # ------------------------------------------------------------------

    def _keyframes_to_stops(self) -> list[tuple[float, tuple[int, int, int, int]]]:
        """Return gradient stops with times normalized to [0, 1] for image creation."""
        if not self._keyframes:
            c = tuple(int(ch * 255) for ch in self._default_color)
            return [(0.0, c), (1.0, c)]
        span = self._time_span()
        return [((kf.time - self._time_min) / span, tuple(int(ch * 255) for ch in kf.color)) for kf in self._keyframes]

    def _update_gradient_image(self):
        stops = self._keyframes_to_stops()
        gradient = create_multi_stop_gradient(_GRADIENT_IMAGE_WIDTH, _GRADIENT_IMAGE_HEIGHT, stops)
        if self._gradient_provider:
            self._gradient_provider.set_bytes_data(
                gradient.ravel().tolist(),
                [_GRADIENT_IMAGE_WIDTH, _GRADIENT_IMAGE_HEIGHT],
            )

    # ------------------------------------------------------------------
    # Popup open / close
    # ------------------------------------------------------------------

    def _on_inline_bar_released(self, x: float, y: float, button: int, modifier: int) -> None:
        """Left-click on the collapsed inline bar opens the editor popup."""
        if button == 0:
            self._show_popup()

    def _show_popup(self) -> None:
        if self._popup_window and self._popup_window.visible:
            return  # Already shown

        # Dismiss any other gradient popup that may be open.
        active_ref = ColorGradientWidget._active_popup_widget
        active = active_ref() if active_ref is not None else None
        if active is not None and active is not self:
            active._hide_popup()  # noqa: SLF001 — same class, singleton management
        ColorGradientWidget._active_popup_widget = weakref.ref(self)

        x = self._outer_container.screen_position_x
        y = self._outer_container.screen_position_y
        # The popup gradient bar is inset from the popup window's left edge by 4 * _HALF_MARKER
        # (window border + padding_x + spacer).  Add the same amount to the width so the popup
        # bar left/right edges overlay the inline bar exactly.
        w = max(self._outer_container.computed_width + 2 * _MARKER_SIZE, _POPUP_MIN_WIDTH)

        flags = (
            ui.WINDOW_FLAGS_NO_DOCKING
            | ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE
            | ui.WINDOW_FLAGS_NO_RESIZE
        )
        if not self._popup_window:
            window_name = (
                f"{self._title} - Gradient Editor##{id(self)}" if self._title else f"Gradient Editor##{id(self)}"
            )
            self._popup_window = ui.Window(
                window_name,
                width=w,
                height=_POPUP_WIDGET_HEIGHT + _STANDARD_ROW_HEIGHT,
                visible=False,
                flags=flags,
                padding_x=0,
                padding_y=0,
            )
            self._popup_window.set_visibility_changed_fn(self._on_window_close)
            with self._popup_window.frame:
                if "Rectangle::ColorGradientBarOverlay" not in ui.Style.get_instance().default:
                    self._popup_window.frame.set_style(_get_local_style())
                with ui.ZStack():
                    ui.Rectangle(style={"background_color": _GRADIENT_BG_COLOR})
                    self._build_popup_content()
        else:
            # Rebuild dynamic parts on re-show
            self._popup_markers_frame.rebuild()
            self._popup_edit_frame.rebuild()

        self._popup_window.width = w
        self._popup_window.height = _POPUP_WIDGET_HEIGHT + _STANDARD_ROW_HEIGHT
        self._popup_window.position_x = x - _MARKER_SIZE
        self._popup_window.position_y = y - _STANDARD_ROW_HEIGHT
        self._outside_click_lmb_was_down = False
        if self._update_sub is None:
            self._update_sub = (
                omni.kit.app.get_app()
                .get_update_event_stream()
                .create_subscription_to_pop(
                    self._check_outside_click,
                    name=f"gradient_outside_click_{id(self)}",
                )
            )
        self._popup_window.visible = True

    def _hide_popup(self) -> None:
        self._color_picker_active = 0
        self._update_sub = None
        active_ref = ColorGradientWidget._active_popup_widget
        if active_ref is not None and active_ref() is self:
            ColorGradientWidget._active_popup_widget = None
        if self._popup_window:
            self._popup_window.visible = False

    def _on_window_close(self, visible: bool) -> None:
        """Handle the title-bar X close button (or any external visibility change)."""
        if not visible:
            self._color_picker_active = 0
            self._update_sub = None
            active_ref = ColorGradientWidget._active_popup_widget
            if active_ref is not None and active_ref() is self:
                ColorGradientWidget._active_popup_widget = None

    def _check_outside_click(self, _event) -> None:
        """Per-frame check: dismiss the popup when LMB is pressed outside its bounds.

        Runs every frame while the widget is alive (cheap when popup is hidden).
        Detects the rising edge of LMB so dragging outside doesn't re-trigger.
        """
        if not self._popup_window or not self._popup_window.visible:
            # Reset so the next show doesn't misfire on a stale True state.
            self._outside_click_lmb_was_down = False
            return
        if not self._app_mouse or not self._carb_input:
            return
        lmb_down = bool(self._carb_input.get_mouse_value(self._app_mouse, carb.input.MouseInput.LEFT_BUTTON))
        just_pressed = lmb_down and not self._outside_click_lmb_was_down
        self._outside_click_lmb_was_down = lmb_down
        if not just_pressed:
            return
        # Don't dismiss while the user is interacting with the presets menu.
        if self._presets_menu is not None and self._presets_menu.visible:
            return
        # Get current mouse position in logical (DPI-independent) pixels.
        px, py = self._carb_input.get_mouse_coords_pixel(self._app_mouse)
        dpi = ui.Workspace.get_dpi_scale()
        mx, my = px / dpi, py / dpi
        pw_x = self._popup_window.position_x
        pw_y = self._popup_window.position_y
        pw_w = self._popup_window.width
        pw_h = self._popup_window.height
        if pw_x <= mx <= pw_x + pw_w and pw_y <= my <= pw_y + pw_h:
            # User clicked inside our popup (e.g. returning from the color picker).
            # Treat this as closing any auxiliary popup and stay open.
            self._color_picker_active = 0
            return
        # Outside our popup: don't dismiss while the color picker is active.
        if self._color_picker_active > 0:
            return
        self._hide_popup()

    def _build_popup_content(self) -> None:
        with ui.VStack(spacing=0):
            popup_container = ui.ZStack()
            popup_container.set_mouse_wheel_fn(lambda *_: None)
            with popup_container:
                with ui.HStack(spacing=0):
                    with ui.VStack(spacing=0):
                        ui.Spacer(height=ui.Pixel(_TOP_PAD))
                        # Gradient bar — same layout as inline, sharing the same providers
                        with ui.HStack(spacing=0, height=ui.Pixel(_GRADIENT_BAR_HEIGHT)):
                            ui.Spacer(width=ui.Pixel(_HALF_MARKER))
                            with ui.ZStack(width=ui.Fraction(1)):
                                ui.Rectangle(
                                    style={
                                        "background_color": _GRADIENT_BG_COLOR,
                                        "border_radius": _GRADIENT_BORDER_RADIUS,
                                    }
                                )
                                ui.ImageWithProvider(
                                    self._checker_provider,
                                    fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                                    name="ColorGradientBar",
                                )
                                ui.ImageWithProvider(
                                    self._gradient_provider,
                                    fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                                    name="ColorGradientBar",
                                )
                                self._popup_gradient_overlay = ui.Rectangle(
                                    name="ColorGradientBarOverlay",
                                    tooltip="Click to add keyframe",
                                    mouse_released_fn=self._on_popup_bar_released if not self._read_only else _NOOP,
                                )
                            ui.Spacer(width=ui.Pixel(_HALF_MARKER))
                        ui.Spacer(height=ui.Pixel(_TOP_PAD))
                        # Marker row — fraction height fills remaining VStack space.
                        with ui.HStack(spacing=0, height=ui.Fraction(1)):
                            self._popup_markers_frame = ui.Frame(width=ui.Fraction(1))
                            self._popup_markers_frame.set_build_fn(self._build_popup_markers)
                            ui.Spacer(width=ui.Pixel(_MARKER_SIZE))
                        ui.Spacer(height=ui.Pixel(_POPUP_MARKER_BOTTOM_PAD))
                        # Edit row
                        self._popup_edit_frame = ui.Frame(height=ui.Pixel(_EDIT_ROW_HEIGHT))
                        self._popup_edit_frame.set_build_fn(self._build_edit_row)
                        ui.Spacer(height=ui.Pixel(_POPUP_BOTTOM_PAD))

    def _build_popup_markers(self):
        """Build SVG keyframe markers with draggable Placers."""
        self._marker_widgets.clear()
        self._marker_placers.clear()
        if not self._keyframes:
            ui.Spacer()
            return
        with ui.ZStack(width=ui.Fraction(1), height=ui.Fraction(1)):
            for kf in self._keyframes:
                is_selected = kf.uid == self._selected_uid
                offset_percent = self._time_to_percent(kf.time)
                marker_color = _MARKER_SELECTED_COLOR if is_selected else _MARKER_COLOR
                placer = ui.Placer(
                    draggable=not self._read_only,
                    drag_axis=ui.Axis.X,
                    offset_x=ui.Percent(offset_percent),
                    stable_size=True,
                )
                with placer:
                    with ui.Frame(
                        width=ui.Pixel(_MARKER_SIZE),
                        height=ui.Pixel(_POPUP_MARKER_HEIGHT),
                        tooltip=self._format_marker_tooltip(kf.time, kf.color),
                    ):
                        marker = ui.Image(
                            _gradient_kf_icon(),
                            width=ui.Pixel(_MARKER_SIZE),
                            height=ui.Pixel(_POPUP_MARKER_HEIGHT),
                            identifier="GradientKeyframeMarker",
                            style={"color": marker_color, "Tooltip": {"color": 0xFF000000}},
                        )

                if not self._read_only:
                    placer.set_offset_x_changed_fn(lambda offset, uid=kf.uid: self._on_marker_dragged(uid, offset))
                    marker.set_mouse_pressed_fn(lambda x, y, b, m, uid=kf.uid: self._on_marker_pressed(uid, b))
                    marker.set_mouse_released_fn(lambda x, y, b, m, uid=kf.uid: self._on_marker_released(uid, b))
                self._marker_widgets[kf.uid] = marker
                self._marker_placers[kf.uid] = placer

    def _rebuild_markers(self):
        if self._popup_markers_frame and self._popup_window and self._popup_window.visible:
            self._popup_markers_frame.rebuild()

    def _update_marker_selection(self, old_uid: int | None, new_uid: int | None):
        """Update marker tint for selection change without a full rebuild."""
        for uid, style_selected in [(old_uid, False), (new_uid, True)]:
            if uid is None:
                continue
            marker_color = _MARKER_SELECTED_COLOR if style_selected else _MARKER_COLOR
            marker = self._marker_widgets.get(uid)
            if marker is None:
                self._rebuild_markers()
                return
            try:
                marker.style = {"color": marker_color}
            except (AttributeError, RuntimeError):
                self._rebuild_markers()
                return

    # ------------------------------------------------------------------
    # Inline edit row (time + delete) shown below markers
    # ------------------------------------------------------------------

    def _build_edit_row(self):
        """Built by ``_edit_frame``; shows controls for the selected keyframe (always visible)."""
        kf = self._find_kf(self._selected_uid) if self._selected_uid else None
        has_selection = kf is not None

        # Consistent row height — style overrides keep children within bounds
        h = ui.Pixel(_EDIT_ROW_HEIGHT)
        icon = ui.Pixel(_EDIT_ICON_SIZE)
        group_gap = ui.Pixel(_EDIT_GROUP_SPACING)
        row_style = {
            "FloatDrag": {"margin": 0, "padding": 2, "border_width": 0},
            "Label": {"margin": 0},
        }
        nav_enabled = has_selection and len(self._keyframes) > 1 and not self._read_only

        # Layout groups:  color | time | arrows + counter | delete + options
        with ui.HStack(height=h, spacing=0, style=row_style):
            ui.Spacer(width=ui.Pixel(_HALF_MARKER))

            # --- Group 1: Color swatch ---
            initial = kf.color if has_selection else self._default_color
            self._color_widget = ui.ColorWidget(
                *initial,
                width=ui.Percent(25),
                height=h,
                name="ColorsWidgetFieldRead",
                enabled=not self._read_only,
            )
            if not self._read_only:
                self._color_subs.clear()
                self._subscribe_color_widget()

            ui.Spacer(width=group_gap)

            # --- Group 2: Time field ---
            time_model = ui.SimpleFloatModel(kf.time if has_selection else self._time_min)
            ui.FloatDrag(
                model=time_model,
                min=self._time_min,
                max=self._time_max,
                step=0.01 * self._time_span(),
                precision=_TIME_DECIMAL_PLACES,
                width=ui.Pixel(_KF_TIME_FIELD_WIDTH),
                enabled=has_selection and not self._read_only,
            )
            if has_selection:
                self._subs.append(time_model.subscribe_value_changed_fn(partial(self._on_edit_time_changed, kf.uid)))

            ui.Spacer(width=group_gap)

            # --- Group 3: < N/M > + delete ---
            with ui.HStack(spacing=ui.Pixel(4), width=0):
                ui.Image(
                    "",
                    name="ArrowLeft",
                    width=icon,
                    height=icon,
                    enabled=nav_enabled,
                    tooltip="Select previous keyframe",
                    mouse_released_fn=lambda *_: self._select_previous_marker() if nav_enabled else None,
                )
                if has_selection:
                    kf_index = next((i for i, k in enumerate(self._keyframes) if k.uid == kf.uid), -1) + 1
                    label_text = f"{kf_index}/{len(self._keyframes)}"
                else:
                    label_text = "Constant"
                ui.Label(
                    label_text,
                    width=0,
                    alignment=ui.Alignment.CENTER,
                    tooltip="Click on gradient area to create keyframes",
                )
                ui.Image(
                    "",
                    name="ArrowRight",
                    width=icon,
                    height=icon,
                    enabled=nav_enabled,
                    tooltip="Select next keyframe",
                    mouse_released_fn=lambda *_: self._select_next_marker() if nav_enabled else None,
                )
                if not self._read_only:
                    ui.Image(
                        "",
                        name="TrashCan",
                        width=icon,
                        height=icon,
                        enabled=has_selection,
                        tooltip="Delete selected keyframe",
                        mouse_released_fn=(
                            (lambda *_, uid=kf.uid: self._delete_keyframe(uid)) if has_selection else _NOOP
                        ),
                    )

            # --- Options icon, pushed to far right ---
            if not self._read_only:
                ui.Spacer()
                self._presets_button = ui.Image(
                    "",
                    name="MenuBurger",
                    width=icon,
                    height=icon,
                    tooltip="Gradient presets and options",
                    mouse_released_fn=lambda *_: self._show_presets_menu(),
                )

            ui.Spacer(width=ui.Pixel(_HALF_MARKER))

    def _rebuild_edit_row(self):
        # Rebuilding destroys and replaces the color widget, which closes any open color picker.
        self._color_picker_active = 0
        if self._popup_edit_frame and self._popup_window and self._popup_window.visible:
            self._popup_edit_frame.rebuild()

    def _on_edit_time_changed(self, uid, model):
        kf = self._find_kf(uid)
        if kf is None:
            return
        kf.time = self._clamp_time(model.get_value_as_float())
        self._keyframes.sort(key=lambda k: k.time)
        self._update_gradient_image()
        self._rebuild_markers()
        self._fire_changed()

    # ------------------------------------------------------------------
    # Swatch interaction (edits the *selected* keyframe)
    # ------------------------------------------------------------------

    def _subscribe_color_widget(self):
        """Subscribe to per-component value changes for real-time gradient updates."""
        cw = self._color_widget
        for child in cw.model.get_item_children():
            sub_model = cw.model.get_item_value_model(child)
            self._color_subs.append(sub_model.subscribe_value_changed_fn(self._on_swatch_component_changed))
            # Try to detect picker close via sub-model end_edit (fires on slider release).
            self._color_subs.append(sub_model.subscribe_end_edit_fn(lambda *_: self._on_color_picker_end()))
        # Use mouse_pressed_fn to reliably detect when the swatch is clicked and the picker opens.
        cw.set_mouse_pressed_fn(lambda x, y, b, m: self._on_color_widget_pressed(b))
        # Also try model-level end_edit as a fallback (fires when the overall edit session ends).
        self._color_subs.append(cw.model.subscribe_end_edit_fn(lambda *_: self._on_color_picker_end()))

    def _on_color_widget_pressed(self, button: int) -> None:
        if button == 0:
            if self._color_picker_active == 0:
                self._fire_drag_started()
            self._color_picker_active += 1

    def _on_color_picker_end(self) -> None:
        self._color_picker_active = max(0, self._color_picker_active - 1)
        if self._color_picker_active == 0:
            self._fire_drag_ended()
            self._fire_changed()

    def _on_swatch_component_changed(self, model):
        """Called on every R/G/B/A change from the swatch color picker."""
        if self._ignore_swatch_change:
            return
        cw = self._color_widget
        children = cw.model.get_item_children()
        new_color: Color4 = tuple(cw.model.get_item_value_model(c).get_value_as_float() for c in children)

        # If no keyframes exist, update the default color (Constant preset behavior)
        if not self._keyframes:
            self._default_color = new_color
            self._update_gradient_image()
            self._fire_changed()
            return

        # Edit the selected keyframe
        kf = self._find_kf(self._selected_uid) if self._selected_uid else None
        if kf is None:
            kf = self._keyframes[0]
        kf.color = new_color
        self._update_gradient_image()
        self._fire_changed()

    def _update_swatch(self):
        """Sync the swatch to the selected (or first) keyframe color."""
        if not self._color_widget:
            return
        self._ignore_swatch_change = True
        kf = self._find_kf(self._selected_uid) if self._selected_uid else None
        if kf is None and self._keyframes:
            kf = self._keyframes[0]
        color = kf.color if kf else self._default_color
        children = self._color_widget.model.get_item_children()
        for child, value in zip(children, color):
            self._color_widget.model.get_item_value_model(child).set_value(value)
        self._ignore_swatch_change = False

    # ------------------------------------------------------------------
    # Bar click (release)
    # ------------------------------------------------------------------

    def _on_popup_bar_released(self, x, y, button, modifier):
        """Click-to-add handler for the popup gradient bar.

        Uses the popup bar's own overlay widget for position math so that the
        wider popup bar (when _POPUP_MIN_WIDTH is larger than the inline bar)
        maps clicks correctly to keyframe times.
        """
        if button != 0:
            return
        bar = self._popup_gradient_overlay
        if bar is None:
            return
        width = bar.computed_width
        if width <= 0:
            return
        local_x = x - bar.screen_position_x
        frac = max(0.0, min(1.0, local_x / width))
        time = round(self._percent_to_time(frac * 100.0), _TIME_DECIMAL_PLACES)
        color = self._sample_gradient_at(time)
        new_kf = _KF(time, color)
        if len(self._keyframes) >= _MAX_KEYFRAMES:
            return
        self._keyframes.append(new_kf)
        self._keyframes.sort(key=lambda kf: kf.time)
        self._selected_uid = new_kf.uid
        self._refresh_all()

    # ------------------------------------------------------------------
    # Marker interactions
    # ------------------------------------------------------------------

    def _on_marker_pressed(self, uid: int, button: int) -> None:
        """Select a marker and begin drag (left click) or delete (right click)."""
        if button == 0:
            old_uid = self._selected_uid
            self._selected_uid = uid
            self._fire_drag_started()
            self._update_marker_selection(old_uid, uid)
            self._update_swatch()
            self._rebuild_edit_row()
        elif button == 1:
            self._delete_keyframe(uid)

    def _on_marker_released(self, uid: int, button: int) -> None:
        """End marker drag on mouse release."""
        if button == 0:
            self._rebuild_edit_row()
            self._fire_drag_ended()
            self._fire_changed()

    def _on_marker_dragged(self, uid: int, offset) -> None:
        """Handle Placer offset_x change during drag."""
        kf = self._find_kf(uid)
        if kf is None:
            return
        clamped = max(0.0, min(100.0, offset.value))
        kf.time = round(self._percent_to_time(clamped), _TIME_DECIMAL_PLACES)
        placer = self._marker_placers.get(uid)
        if placer and offset.value != clamped:
            placer.offset_x = ui.Percent(clamped)
        self._keyframes.sort(key=lambda k: k.time)
        self._update_gradient_image()
        self._update_swatch()
        self._update_marker_tooltip(uid)
        self._fire_changed()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete_keyframe(self, uid):
        deleted_idx = next((i for i, kf in enumerate(self._keyframes) if kf.uid == uid), None)
        if deleted_idx is None:
            return
        deleted_kf = self._keyframes[deleted_idx]

        # Preserve color when deleting the last keyframe
        if len(self._keyframes) == 1:
            self._default_color = deleted_kf.color

        self._keyframes = [kf for kf in self._keyframes if kf.uid != uid]

        # Auto-select a neighbouring keyframe
        if self._selected_uid == uid:
            if self._keyframes:
                select_idx = min(deleted_idx, len(self._keyframes) - 1)
                self._selected_uid = self._keyframes[select_idx].uid
            else:
                self._selected_uid = None

        self._refresh_all()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _select_next_marker(self) -> None:
        """Select the next marker in the sequence."""
        if not self._keyframes:
            return

        if self._selected_uid is None:
            # Select first marker
            new_uid = self._keyframes[0].uid
        else:
            # Find current index and select next
            current_idx = next((idx for idx, kf in enumerate(self._keyframes) if kf.uid == self._selected_uid), None)
            if current_idx is None:
                new_uid = self._keyframes[0].uid
            else:
                next_idx = (current_idx + 1) % len(self._keyframes)
                new_uid = self._keyframes[next_idx].uid

        old_uid = self._selected_uid
        self._selected_uid = new_uid
        self._update_marker_selection(old_uid, new_uid)
        self._update_swatch()
        self._rebuild_edit_row()

    def _select_previous_marker(self) -> None:
        """Select the previous marker in the sequence."""
        if not self._keyframes:
            return

        if self._selected_uid is None:
            # Select last marker
            new_uid = self._keyframes[-1].uid
        else:
            # Find current index and select previous
            current_idx = next((idx for idx, kf in enumerate(self._keyframes) if kf.uid == self._selected_uid), None)
            if current_idx is None:
                new_uid = self._keyframes[-1].uid
            else:
                prev_idx = (current_idx - 1) % len(self._keyframes)
                new_uid = self._keyframes[prev_idx].uid

        old_uid = self._selected_uid
        self._selected_uid = new_uid
        self._update_marker_selection(old_uid, new_uid)
        self._update_swatch()
        self._rebuild_edit_row()

    # ------------------------------------------------------------------
    # Gradient presets and operations
    # ------------------------------------------------------------------

    def _show_presets_menu(self) -> None:
        """Show the presets and operations popup menu."""
        # Destroy existing menu if any to avoid memory leaks
        if self._presets_menu is not None:
            self._presets_menu.destroy()

        # Create new menu (stored as member to avoid garbage collection)
        self._presets_menu = ui.Menu("Presets + Operations")

        def _section_header(text: str) -> None:
            ui.Separator()
            ui.MenuItem(
                text,
                enabled=False,
                delegate=ui.MenuDelegate(
                    on_build_item=lambda _item: ui.Label(
                        f"  {text}",
                    )
                ),
            )

        with self._presets_menu:
            # Presets section
            _section_header("Presets")
            for preset_name in GRADIENT_PRESETS:
                ui.MenuItem(preset_name, triggered_fn=lambda p=preset_name: self._apply_preset(p))

            # Operations section
            _section_header("Operations")
            ui.MenuItem("Reverse", triggered_fn=self._reverse_gradient)
            ui.MenuItem("Distribute Evenly", triggered_fn=self._distribute_evenly)
            ui.MenuItem("Randomize Colors", triggered_fn=self._randomize_colors)
            ui.MenuItem("Clear All", triggered_fn=self._clear_all_keyframes)

        # Show the menu
        self._presets_menu.show()

    def _apply_preset(self, preset_name: str) -> None:
        """Apply a gradient preset."""
        if preset_name not in GRADIENT_PRESETS:
            return

        keyframes = GRADIENT_PRESETS[preset_name]
        self.set_keyframes(keyframes)
        # Auto-select first keyframe if available
        if self._keyframes:
            self._selected_uid = self._keyframes[0].uid
        else:
            self._selected_uid = None
        self._rebuild_edit_row()
        self._fire_changed()

    def _reverse_gradient(self) -> None:
        """Reverse the gradient by flipping all keyframe times."""
        if not self._keyframes:
            return

        for kf in self._keyframes:
            kf.time = self._time_max - (kf.time - self._time_min)

        self._keyframes.sort(key=lambda k: k.time)
        self._update_gradient_image()
        self._rebuild_markers()
        self._rebuild_edit_row()
        self._fire_changed()

    def _distribute_evenly(self) -> None:
        """Distribute keyframes evenly across the gradient."""
        if len(self._keyframes) < 2:
            return

        count = len(self._keyframes)
        for idx, kf in enumerate(self._keyframes):
            kf.time = self._time_min + idx / (count - 1) * self._time_span()

        self._update_gradient_image()
        self._rebuild_markers()
        self._rebuild_edit_row()
        self._fire_changed()

    def _randomize_colors(self) -> None:
        """Randomize the color of each keyframe."""
        if not self._keyframes:
            return

        for kf in self._keyframes:
            kf.color = (
                random.random(),
                random.random(),
                random.random(),
                1.0,  # Keep alpha at 1.0
            )

        self._update_gradient_image()
        self._update_swatch()
        self._rebuild_markers()
        self._fire_changed()

    def _clear_all_keyframes(self) -> None:
        """Remove all keyframes."""
        if not self._keyframes:
            return

        self._keyframes.clear()
        self._selected_uid = None
        self._refresh_all()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        """Refresh all UI components and fire the changed callback."""
        self._update_gradient_image()
        self._update_swatch()
        self._rebuild_markers()
        self._rebuild_edit_row()
        self._fire_changed()

    def _find_kf(self, uid: int) -> _KF | None:
        return next((kf for kf in self._keyframes if kf.uid == uid), None)

    def _format_marker_tooltip(self, time: float, color: Color4) -> str:
        """Format a tooltip string showing color and time information."""
        r, g, b = [int(c * 255) for c in color[:3]]
        a = color[3]  # Keep alpha as 0-1 float for consistency
        hex_color = f"#{r:02X}{g:02X}{b:02X}"
        return f"RGB: ({r}, {g}, {b}) | Alpha: {a:.2f} | Hex: {hex_color} | Time: {time:.2f}"

    def _update_marker_tooltip(self, uid: int) -> None:
        """Update the tooltip for a specific marker."""
        kf = self._find_kf(uid)
        if kf is None:
            return

        marker = self._marker_widgets.get(uid)
        if marker:
            marker.tooltip = self._format_marker_tooltip(kf.time, kf.color)

    def _sample_gradient_at(self, time: float) -> Color4:
        """Linearly interpolate the gradient at the given *time*."""
        if not self._keyframes:
            return self._default_color
        # Convert internal keyframes to the format expected by sample_gradient_at_time
        stops = [(kf.time, kf.color) for kf in self._keyframes]
        return sample_gradient_at_time(stops, time)

    def _fire_drag_started(self) -> None:
        for fn in self._drag_started_fns:
            fn()

    def _fire_drag_ended(self) -> None:
        for fn in self._drag_ended_fns:
            fn()

    def _fire_changed(self):
        times = [kf.time for kf in self._keyframes]
        values = [kf.color for kf in self._keyframes]
        for fn in self._gradient_changed_fns:
            fn(times, values)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe_gradient_changed_fn(self, fn: Callable[[list, list], None]) -> None:
        """Register an additional callback fired on every gradient edit."""
        self._gradient_changed_fns.append(fn)

    def unsubscribe_gradient_changed_fn(self, fn: Callable[[list, list], None]) -> None:
        """Remove a previously registered callback."""
        with contextlib.suppress(ValueError):
            self._gradient_changed_fns.remove(fn)

    def subscribe_drag_started_fn(self, fn: Callable[[], None]) -> None:
        """Register a callback fired when a marker drag begins."""
        self._drag_started_fns.append(fn)

    def unsubscribe_drag_started_fn(self, fn: Callable[[], None]) -> None:
        """Unregister a previously registered drag-started callback."""
        with contextlib.suppress(ValueError):
            self._drag_started_fns.remove(fn)

    def subscribe_drag_ended_fn(self, fn: Callable[[], None]) -> None:
        """Register a callback fired when a marker drag ends."""
        self._drag_ended_fns.append(fn)

    def unsubscribe_drag_ended_fn(self, fn: Callable[[], None]) -> None:
        """Unregister a previously registered drag-ended callback."""
        with contextlib.suppress(ValueError):
            self._drag_ended_fns.remove(fn)

    def set_keyframes(self, keyframes: Sequence[Keyframe]):
        """Replace all keyframes and refresh the widget."""
        if len(keyframes) > _MAX_KEYFRAMES:
            carb.log_warn(
                f"ColorGradientWidget: keyframe count {len(keyframes)} exceeds _MAX_KEYFRAMES={_MAX_KEYFRAMES}; "
                f"truncating to {_MAX_KEYFRAMES}."
            )
            keyframes = list(keyframes)[:_MAX_KEYFRAMES]
        self._keyframes = sorted(
            [_KF(t, c) for t, c in keyframes],
            key=lambda kf: kf.time,
        )
        # Auto-select first keyframe if available
        self._selected_uid = self._keyframes[0].uid if self._keyframes else None
        self._update_gradient_image()
        self._update_swatch()
        self._rebuild_markers()
        self._rebuild_edit_row()

    def get_keyframes(self) -> list[Keyframe]:
        """Return the current keyframes as ``(time, color)`` tuples."""
        return [(kf.time, kf.color) for kf in self._keyframes]

    @property
    def read_only(self) -> bool:
        """Whether the widget is in read-only mode."""
        return self._read_only

    def destroy(self):
        """Release resources."""
        if self._presets_menu is not None:
            self._presets_menu.destroy()
            self._presets_menu = None
        if self._popup_window is not None:
            self._popup_window.visible = False
            self._popup_window.destroy()
            self._popup_window = None
        self._popup_markers_frame = None
        self._popup_edit_frame = None
        self._color_subs.clear()
        self._subs.clear()
        self._marker_widgets.clear()
        self._marker_placers.clear()
        self._popup_gradient_overlay = None
        self._update_sub = None
        self._app_mouse = None
        self._carb_input = None
        self._checker_provider = None
        self._gradient_provider = None
        self._gradient_overlay = None
        self._gradient_bar_stack = None
        self._color_widget = None
        self._presets_button = None
        self._outer_container = None
        self._gradient_changed_fns.clear()
        self._drag_started_fns.clear()
        self._drag_ended_fns.clear()
        self._keyframes.clear()
        active_ref = ColorGradientWidget._active_popup_widget
        if active_ref is not None and active_ref() is self:
            ColorGradientWidget._active_popup_widget = None

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

__all__ = [
    "DEFAULT_GRADIENT_COLOR",
    "GRADIENT_BACKGROUND_COLOR",
    "GRADIENT_BAR_HEIGHT",
    "GRADIENT_BAR_PADDING",
    "GRADIENT_BORDER_RADIUS",
    "GRADIENT_MARKER_SIZE",
    "GRADIENT_PRESETS",
    "ColorGradientWidget",
    "GradientPreview",
    "get_color_gradient_style",
    "keyframes_from_payload",
    "normalize_gradient_keyframes",
]

import itertools
import random
from collections.abc import Callable, Sequence
from functools import partial

import carb
import omni.ui as ui
from carb.input import (
    KEYBOARD_MODIFIER_FLAG_ALT,
    KEYBOARD_MODIFIER_FLAG_CONTROL,
    KEYBOARD_MODIFIER_FLAG_SHIFT,
    KEYBOARD_MODIFIER_FLAG_SUPER,
    DeviceType,
    InputEvent,
    KeyboardEventType,
    KeyboardInput,
    acquire_input_interface,
)

from .gradient import create_checkerboard, create_multi_stop_gradient, sample_gradient_at_time
from .grouped_keys_model import GroupedKeysModel, GroupedKeysPayload
from .resources import get_icons

DEFAULT_GRADIENT_COLOR = (0.2, 0.2, 0.2, 1.0)

# ---------------------------------------------------------------------------
# Layout constants — derived from the standard property-panel row height
# ---------------------------------------------------------------------------
_GRADIENT_IMAGE_WIDTH = 128
_GRADIENT_IMAGE_HEIGHT = 1
_CHECKER_IMAGE_WIDTH = 2048
_CHECKER_IMAGE_HEIGHT = 16

_STANDARD_ROW_HEIGHT = 24  # matches DEFAULT_IMAGE_ICON_SIZE across the property panel

GRADIENT_MARKER_SIZE = 12  # marker SVG width
_HALF_MARKER = GRADIENT_MARKER_SIZE // 2
_MARKER_COLOR = 0xFFBBBBBB  # default marker tint
_MARKER_SELECTED_COLOR = 0xFFFFFFFF  # selected marker tint

GRADIENT_BAR_PADDING = 2  # small gap so the gradient bar doesn't touch the row above
GRADIENT_BAR_HEIGHT = _STANDARD_ROW_HEIGHT  # gradient image strip, matches normal field height
_EDIT_ROW_HEIGHT = _STANDARD_ROW_HEIGHT  # keyframe controls row
_KF_TIME_FIELD_WIDTH = 58  # fits "0.10494" with room to spare
_EDIT_ICON_SIZE = 20  # icon button size for the edit row (trash, menu, arrows)
_EDIT_GROUP_SPACING = 12  # space between logical groups in the edit row
GRADIENT_BORDER_RADIUS = 5  # corner radius for the gradient bar background rectangle
_TIME_DECIMAL_PLACES = 5  # decimal precision for stored keyframe times

_POPUP_MARKER_HEIGHT = 18  # total marker SVG height
_POPUP_MARKER_BOTTOM_PAD = 10  # breathing room between marker row and edit row
_POPUP_BOTTOM_PAD = 4  # small gap below the edit row so the bottom isn't flush with the window edge
# Opaque background for the gradient region so TreeView row highlights don't bleed through.
GRADIENT_BACKGROUND_COLOR = 0xFF242424

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


def get_color_gradient_style() -> dict:
    """Lazily build the local style fallback, resolving icon paths at runtime."""
    global _LOCAL_STYLE
    if _LOCAL_STYLE is not None:
        return _LOCAL_STYLE

    resources_ext = "omni.flux.resources"
    w60, w80, w30 = 0x99FFFFFF, 0xCCFFFFFF, 0x4DFFFFFF

    _LOCAL_STYLE = {
        "Rectangle::ColorGradientBarOverlay": {
            "background_color": 0x00000000,
            "border_radius": GRADIENT_BORDER_RADIUS,
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


def keyframes_from_payload(payload: GroupedKeysPayload | None) -> list[Keyframe]:
    """Convert a grouped-key payload into full-precision time/color pairs."""
    if payload is None:
        return []
    return [
        (float(time), tuple(float(channel) for channel in value))
        for time, value in zip(payload.get("times") or [], payload.get("values") or [])
    ]


def normalize_gradient_keyframes(keyframes: Sequence[Keyframe]) -> list[Keyframe]:
    """Cap input keys before sorting them by time, preserving duplicate-time order."""
    if len(keyframes) > _MAX_KEYFRAMES:
        carb.log_warn(
            f"ColorGradientWidget: keyframe count {len(keyframes)} exceeds _MAX_KEYFRAMES={_MAX_KEYFRAMES}; "
            f"truncating to {_MAX_KEYFRAMES}."
        )
        keyframes = list(keyframes)[:_MAX_KEYFRAMES]
    return sorted(keyframes, key=lambda keyframe: keyframe[0])


class GradientPreview:
    """Share Gradient images and its nonserialized fallback color across editor openings."""

    def __init__(
        self,
        default_color: Color4 = DEFAULT_GRADIENT_COLOR,
        time_range: tuple[float, float] = (0.0, 1.0),
        *,
        gradient_provider: ui.ByteImageProvider | None = None,
        checker_provider: ui.ByteImageProvider | None = None,
    ) -> None:
        """Create image storage and initialize the checkerboard once.

        Args:
            default_color: Full-precision fallback used when there are no keys.
            time_range: Inclusive time bounds mapped to the gradient image.
            gradient_provider: Existing gradient storage, or None to create it.
            checker_provider: Existing checkerboard storage, or None to create it.
        """
        self.fallback_color = default_color
        self.time_range = time_range
        self.gradient_provider = gradient_provider if gradient_provider is not None else ui.ByteImageProvider()
        self.checker_provider = checker_provider if checker_provider is not None else ui.ByteImageProvider()
        checker = create_checkerboard(_CHECKER_IMAGE_WIDTH, _CHECKER_IMAGE_HEIGHT, cell_size=4)
        self.checker_provider.set_bytes_data(checker.ravel().tolist(), [_CHECKER_IMAGE_WIDTH, _CHECKER_IMAGE_HEIGHT])

    def build_checkerboard(self) -> ui.Frame:
        """Build a clipped checkerboard that scales uniformly with its own view."""
        frame = ui.Frame(horizontal_clipping=True, vertical_clipping=True)

        def build() -> None:
            """Cover the frame without stretching checker cells into rectangles."""
            # ImageWithProvider's aspect-crop policy distorts checker cells in omni.ui 3.1.3.
            scale = max(frame.computed_width / _CHECKER_IMAGE_WIDTH, frame.computed_height / _CHECKER_IMAGE_HEIGHT)
            ui.ImageWithProvider(
                self.checker_provider,
                width=ui.Pixel(_CHECKER_IMAGE_WIDTH * scale),
                height=ui.Pixel(_CHECKER_IMAGE_HEIGHT * scale),
                fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                name="ColorGradientBar",
                identifier="GradientCheckerboard",
            )

        frame.set_build_fn(build)
        frame.set_computed_content_size_changed_fn(frame.rebuild)
        return frame

    def render(self, keyframes: Sequence[Keyframe]) -> None:
        """Render sorted keys without retaining them or changing the fallback color."""
        minimum, maximum = self.time_range
        span = maximum - minimum or 1.0
        if keyframes:
            stops = [
                ((time - minimum) / span, tuple(int(channel * 255) for channel in color)) for time, color in keyframes
            ]
        else:
            color = tuple(int(channel * 255) for channel in self.fallback_color)
            stops = [(0.0, color), (1.0, color)]
        gradient = create_multi_stop_gradient(_GRADIENT_IMAGE_WIDTH, _GRADIENT_IMAGE_HEIGHT, stops)
        self.gradient_provider.set_bytes_data(
            gradient.ravel().tolist(), [_GRADIENT_IMAGE_WIDTH, _GRADIENT_IMAGE_HEIGHT]
        )


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
        model: Grouped-key payload storage model.
        group_id: Group id to edit in ``model``.
        preview: Shared images, fallback color, and time bounds.
        read_only: If ``True``, all mouse interactions and editing are disabled.
    """

    def __init__(
        self,
        model: GroupedKeysModel,
        group_id: str,
        preview: GradientPreview,
        *,
        read_only: bool = False,
        child_popup_dismissed_fn: Callable[[], None] | None = None,
    ) -> None:
        """Create a grouped-key-backed color gradient widget.

        Args:
            model: Grouped-key payload storage model.
            group_id: Group id to edit in ``model``.
            preview: Shared images, fallback color, and time bounds.
            read_only: Whether to disable editing interactions.
            child_popup_dismissed_fn: Optional handler called when a nested menu or picker is dismissed.
        """
        self._model: GroupedKeysModel | None = model
        self._preview: GradientPreview | None = preview
        self._group_id = group_id
        self._model_sub = self._model.subscribe(self._on_model_changed)
        self._time_min, self._time_max = preview.time_range

        self._keyframes: list[_KF] = []
        self._read_only: bool = read_only
        self._child_popup_dismissed_fn = child_popup_dismissed_fn
        self._is_editing_model = False
        self._set_keyframes(self._read_model_keyframes(), refresh=False)

        # Widget references
        self._color_widget: ui.ColorWidget | None = None
        self._presets_menu: ui.Menu | None = None

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
        self._color_picker_active = False
        self._picker_input_subscription: int | None = None
        self._destroyed = False

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

    def _update_gradient_image(self):
        """Refresh the shared image without retaining editing controls in the preview."""
        if self._preview is not None:
            self._preview.render(self.get_keyframes())

    # ------------------------------------------------------------------
    # Popup open / close
    # ------------------------------------------------------------------

    def build_editor(self) -> None:
        """Build Gradient editing content in the current UI container."""
        if self._destroyed:
            return
        self.set_keyframes(self._read_model_keyframes())
        content = ui.ZStack()
        if "Rectangle::ColorGradientBarOverlay" not in ui.Style.get_instance().default:
            content.set_style(get_color_gradient_style())
        with content:
            ui.Rectangle(style={"background_color": GRADIENT_BACKGROUND_COLOR})
            self._build_popup_content()

    def _build_popup_content(self) -> None:
        with ui.VStack(spacing=0):
            popup_container = ui.ZStack()
            popup_container.set_mouse_wheel_fn(lambda *_: None)
            with popup_container:
                with ui.HStack(spacing=0):
                    with ui.VStack(spacing=0):
                        ui.Spacer(height=ui.Pixel(GRADIENT_BAR_PADDING))
                        # Optional shared providers keep separate views synchronized without another model listener.
                        with ui.HStack(spacing=0, height=ui.Pixel(GRADIENT_BAR_HEIGHT)):
                            ui.Spacer(width=ui.Pixel(_HALF_MARKER))
                            with ui.ZStack(width=ui.Fraction(1)):
                                ui.Rectangle(
                                    style={
                                        "background_color": GRADIENT_BACKGROUND_COLOR,
                                        "border_radius": GRADIENT_BORDER_RADIUS,
                                    }
                                )
                                self._preview.build_checkerboard()
                                ui.ImageWithProvider(
                                    self._preview.gradient_provider,
                                    fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                                    name="ColorGradientBar",
                                )
                                self._popup_gradient_overlay = ui.Rectangle(
                                    name="ColorGradientBarOverlay",
                                    tooltip="Click to add keyframe",
                                    mouse_released_fn=self._on_popup_bar_released if not self._read_only else _NOOP,
                                )
                            ui.Spacer(width=ui.Pixel(_HALF_MARKER))
                        ui.Spacer(height=ui.Pixel(GRADIENT_BAR_PADDING))
                        # Marker row — fraction height fills remaining VStack space.
                        with ui.HStack(spacing=0, height=ui.Fraction(1)):
                            self._popup_markers_frame = ui.Frame(width=ui.Fraction(1))
                            self._popup_markers_frame.set_build_fn(self._build_popup_markers)
                            ui.Spacer(width=ui.Pixel(GRADIENT_MARKER_SIZE))
                        ui.Spacer(height=ui.Pixel(_POPUP_MARKER_BOTTOM_PAD))
                        # Edit row
                        with ui.HStack(height=ui.Pixel(_EDIT_ROW_HEIGHT), spacing=0):
                            ui.Spacer(width=ui.Pixel(_HALF_MARKER))
                            kf = self._find_kf(self._selected_uid) if self._selected_uid else None
                            initial = kf.color if kf else self._preview.fallback_color
                            self._color_widget = ui.ColorWidget(
                                *initial,
                                width=ui.Percent(25),
                                height=ui.Pixel(_EDIT_ROW_HEIGHT),
                                name="ColorsWidgetFieldRead",
                                enabled=not self._read_only,
                            )
                            if not self._read_only:
                                self._subscribe_color_widget()
                            ui.Spacer(width=ui.Pixel(_EDIT_GROUP_SPACING))
                            # Keep the swatch/picker alive when history rebuilds the selected-key controls.
                            self._popup_edit_frame = ui.Frame(width=ui.Fraction(1))
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
                        width=ui.Pixel(GRADIENT_MARKER_SIZE),
                        height=ui.Pixel(_POPUP_MARKER_HEIGHT),
                        tooltip=self._format_marker_tooltip(kf.time, kf.color),
                    ):
                        marker = ui.Image(
                            _gradient_kf_icon(),
                            width=ui.Pixel(GRADIENT_MARKER_SIZE),
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
        """Schedule keyframe-marker rebuilding while editing content is attached."""
        if self._popup_markers_frame:
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
        """Build the popup's controls for the selected keyframe."""
        self._subs.clear()
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

        # Layout groups: time | arrows + counter | delete + options
        with ui.HStack(height=h, spacing=0, style=row_style):
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
                self._subs.extend(
                    (
                        time_model.subscribe_begin_edit_fn(lambda *_: self._fire_drag_started()),
                        time_model.subscribe_value_changed_fn(partial(self._on_edit_time_changed, kf.uid)),
                        time_model.subscribe_end_edit_fn(lambda *_: self._fire_drag_ended()),
                    )
                )

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
                ui.Image(
                    "",
                    name="MenuBurger",
                    width=icon,
                    height=icon,
                    tooltip="Gradient presets and options",
                    mouse_released_fn=lambda *_: self._show_presets_menu(),
                )

            ui.Spacer(width=ui.Pixel(_HALF_MARKER))

    def _rebuild_edit_row(self):
        """Rebuild selected-key controls without replacing the native swatch."""
        if self._popup_edit_frame:
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
        """Observe color changes and the root model's native picker lifetime."""
        cw = self._color_widget
        for child in cw.model.get_item_children():
            sub_model = cw.model.get_item_value_model(child)
            self._color_subs.append(sub_model.subscribe_value_changed_fn(self._on_swatch_component_changed))
        self._color_subs.append(cw.model.subscribe_begin_edit_fn(lambda *_: self._on_color_picker_begin()))
        self._color_subs.append(cw.model.subscribe_end_edit_fn(lambda *_: self._on_color_picker_end()))

    def _on_color_picker_begin(self) -> None:
        """Observe scene-history shortcuts while the native picker is open."""
        if self._destroyed or self._color_picker_active:
            return
        self._color_picker_active = True
        self._picker_input_subscription = acquire_input_interface().subscribe_to_input_events(
            self._on_picker_input, order=-1
        )

    def _on_picker_input(self, event: InputEvent) -> bool:
        """Checkpoint picker edits before Kit executes its asynchronously queued history action."""
        if self._destroyed or not self._color_picker_active or event.deviceType != DeviceType.KEYBOARD:
            return True
        keyboard = event.event
        modifiers = (
            KEYBOARD_MODIFIER_FLAG_CONTROL
            | KEYBOARD_MODIFIER_FLAG_SHIFT
            | KEYBOARD_MODIFIER_FLAG_ALT
            | KEYBOARD_MODIFIER_FLAG_SUPER
        )
        if (
            keyboard.type == KeyboardEventType.KEY_PRESS
            and keyboard.input in (KeyboardInput.Z, KeyboardInput.Y)
            and keyboard.modifiers & modifiers == KEYBOARD_MODIFIER_FLAG_CONTROL
        ):
            self._fire_drag_ended()
        return True

    def _on_color_picker_end(self) -> None:
        """Finish the picker edit and report its dismissal, not component drag releases."""
        if not self._color_picker_active:
            return
        self._color_picker_active = False
        try:
            self._fire_drag_ended()
        finally:
            subscription, self._picker_input_subscription = self._picker_input_subscription, None
            if subscription is not None:
                acquire_input_interface().unsubscribe_to_input_events(subscription)
            if not self._destroyed and self._child_popup_dismissed_fn is not None:
                self._child_popup_dismissed_fn()

    def _on_swatch_component_changed(self, model):
        """Called on every R/G/B/A change from the swatch color picker."""
        if self._destroyed or self._ignore_swatch_change:
            return
        cw = self._color_widget
        children = cw.model.get_item_children()
        new_color: Color4 = tuple(cw.model.get_item_value_model(c).get_value_as_float() for c in children)

        kf = self._find_kf(self._selected_uid) if self._selected_uid else None
        if kf is None and self._keyframes:
            kf = self._keyframes[0]
        current_color = kf.color if kf else self._preview.fallback_color
        if new_color == current_color:
            return
        if self._color_picker_active:
            self._fire_drag_started()

        # If no keyframes exist, update the default color (Constant preset behavior)
        if not self._keyframes:
            self._preview.fallback_color = new_color
            self._update_gradient_image()
            self._fire_changed()
            return

        # Edit the selected keyframe
        kf.color = new_color
        self._update_gradient_image()
        self._fire_changed()

    def _update_swatch(self):
        """Sync the swatch to the selected (or first) keyframe color."""
        if not self._color_widget:
            return
        kf = self._find_kf(self._selected_uid) if self._selected_uid else None
        if kf is None and self._keyframes:
            kf = self._keyframes[0]
        color = kf.color if kf else self._preview.fallback_color
        children = self._color_widget.model.get_item_children()
        self._ignore_swatch_change = True
        try:
            for child, value in zip(children, color):
                self._color_widget.model.get_item_value_model(child).set_value(value)
        finally:
            self._ignore_swatch_change = False

    # ------------------------------------------------------------------
    # Bar click (release)
    # ------------------------------------------------------------------

    def _on_popup_bar_released(self, x, y, button, modifier):
        """Click-to-add handler for the popup gradient bar.

        Uses the editing bar's own overlay bounds to map clicks to keyframe times
        independently of the host size.
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
            self._preview.fallback_color = deleted_kf.color

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
        self._presets_menu.set_shown_changed_fn(self._on_presets_menu_shown_changed)

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
                ui.MenuItem(
                    preset_name, triggered_fn=partial(self._on_presets_action, partial(self._apply_preset, preset_name))
                )

            # Operations section
            _section_header("Operations")
            ui.MenuItem("Reverse", triggered_fn=partial(self._on_presets_action, self._reverse_gradient))
            ui.MenuItem("Distribute Evenly", triggered_fn=partial(self._on_presets_action, self._distribute_evenly))
            ui.MenuItem("Randomize Colors", triggered_fn=partial(self._on_presets_action, self._randomize_colors))
            ui.MenuItem("Clear All", triggered_fn=partial(self._on_presets_action, self._clear_all_keyframes))

        # Show the menu
        self._presets_menu.show()

    def _on_presets_action(self, action: Callable[[], None]) -> None:
        """Keep menu selection distinct from outside dismissal."""
        # The native menu hides before focus returns to the editor; selection must not dismiss it.
        self._presets_menu.set_shown_changed_fn(None)
        action()

    def _on_presets_menu_shown_changed(self, shown: bool) -> None:
        """Report menu dismissal without notifying during content destruction."""
        if not shown and not self._destroyed and self._child_popup_dismissed_fn is not None:
            self._child_popup_dismissed_fn()

    @property
    def child_popup_active(self) -> bool:
        """Whether a native picker or presets menu currently owns input."""
        return self._color_picker_active or (self._presets_menu is not None and self._presets_menu.shown)

    def _apply_preset(self, preset_name: str) -> None:
        """Apply a gradient preset."""
        if preset_name not in GRADIENT_PRESETS:
            return

        keyframes = GRADIENT_PRESETS[preset_name]
        self.set_keyframes(keyframes)
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
        """Refresh all UI components and commit the current payload."""
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
            return self._preview.fallback_color
        # Convert internal keyframes to the format expected by sample_gradient_at_time
        stops = [(kf.time, kf.color) for kf in self._keyframes]
        return sample_gradient_at_time(stops, time)

    def _fire_drag_started(self) -> None:
        """Notify the model that a continuous widget edit has started."""
        model = self._model
        if self._is_editing_model or model is None:
            return
        self._is_editing_model = True
        model.begin_edit(self._group_id)

    def _fire_drag_ended(self) -> None:
        """Notify the model that the current continuous widget edit has ended."""
        if not self._is_editing_model:
            return
        self._is_editing_model = False
        model = self._model
        if model is None:
            return
        model.end_edit(self._group_id)

    def _fire_changed(self) -> None:
        """Commit current keyframes as one grouped payload."""
        if self._model is not None:
            payload: GroupedKeysPayload = {
                "times": [kf.time for kf in self._keyframes],
                "values": [kf.color for kf in self._keyframes],
            }
            self._model.commit_payload(self._group_id, payload)

    def _read_model_keyframes(self) -> list[Keyframe]:
        """Read current keyframes from the grouped-key model.

        Returns:
            Keyframes converted from the current model payload.
        """
        return keyframes_from_payload(self._model.get_payload(self._group_id) if self._model is not None else None)

    def _on_model_changed(self, group_id: str) -> None:
        """Reload when the backing model reports an external change for this group.

        Args:
            group_id: Changed group id from the model.
        """
        if group_id != self._group_id or self._is_editing_model:
            return
        self.set_keyframes(self._read_model_keyframes())

    def _set_keyframes(self, keyframes: Sequence[Keyframe], refresh: bool) -> None:
        """Replace internal keyframes and optionally refresh dependent UI.

        Args:
            keyframes: Keyframes to store in the widget.
            refresh: Whether to rebuild gradient, swatch, marker, and edit-row UI.
        """
        self._keyframes = [_KF(time, color) for time, color in normalize_gradient_keyframes(keyframes)]
        self._selected_uid = self._keyframes[0].uid if self._keyframes else None
        if refresh:
            self._update_gradient_image()
            self._update_swatch()
            self._rebuild_markers()
            self._rebuild_edit_row()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_keyframes(self, keyframes: Sequence[Keyframe]) -> None:
        """Replace all keyframes locally and refresh the widget without committing.

        Args:
            keyframes: Keyframes to display.
        """
        self._set_keyframes(keyframes, refresh=True)

    def get_keyframes(self) -> list[Keyframe]:
        """Return the current keyframes as ``(time, color)`` tuples."""
        return [(kf.time, kf.color) for kf in self._keyframes]

    @property
    def read_only(self) -> bool:
        """Whether the widget is in read-only mode."""
        return self._read_only

    def destroy(self) -> None:
        """Finish gestures and release this opening's controls, preserving its model and preview."""
        if self._destroyed:
            return
        self._destroyed = True
        self._model_sub = None
        try:
            try:
                subscription, self._picker_input_subscription = self._picker_input_subscription, None
                if subscription is not None:
                    acquire_input_interface().unsubscribe_to_input_events(subscription)
            finally:
                self._fire_drag_ended()
        finally:
            try:
                self._color_picker_active = False
                self._color_subs.clear()
                self._subs.clear()
                for frame in (self._popup_markers_frame, self._popup_edit_frame):
                    if frame is not None:
                        frame.set_build_fn(None)
                if self._presets_menu is not None:
                    self._presets_menu.destroy()
            finally:
                self._presets_menu = None
                self._popup_markers_frame = None
                self._popup_edit_frame = None
                self._marker_widgets.clear()
                self._marker_placers.clear()
                self._popup_gradient_overlay = None
                self._color_widget = None
                self._child_popup_dismissed_fn = None
                self._keyframes.clear()
                self._model = None
                self._preview = None

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

__all__ = ("ColorGradientField", "GradientFieldEditor")

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import omni.ui as ui
from omni.flux.utils.widget import ColorGradientWidget, GroupedKeysModel
from omni.flux.utils.widget.color_gradient import (
    DEFAULT_GRADIENT_COLOR,
    GRADIENT_BACKGROUND_COLOR,
    GRADIENT_BAR_HEIGHT,
    GRADIENT_BAR_PADDING,
    GRADIENT_BORDER_RADIUS,
    GRADIENT_MARKER_SIZE,
    GradientPreview,
    keyframes_from_payload,
    normalize_gradient_keyframes,
)

from ..base import AbstractField
from ..field_popup_window import FieldPopupWindow

if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item as _PropertyWidgetItem

_FIELD_LEFT_PADDING = 8  # px gap between the field edge and the gradient bar
_EDITOR_MINIMUM_WIDTH = 500
_EDITOR_HEIGHT = 110
Color4 = tuple[float, float, float, float]


class GradientFieldEditor(FieldPopupWindow):
    """Own disposable Gradient controls independently of their inline launcher."""

    def __init__(
        self,
        *,
        model: GroupedKeysModel,
        group_id: str,
        preview: GradientPreview,
        property_name: str,
        context_name: str | None,
        pre_open_fn: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        """Construct a hidden editor sharing the model and preview with its launcher.

        Args:
            model: Borrowed grouped-key model retained through editor cleanup.
            group_id: Group edited by this opening.
            preview: Shared images, fallback color, and time bounds.
            property_name: Friendly property name shown in the native title.
            context_name: USD context whose selection changes dismiss the editor, or None.
            pre_open_fn: Optional preparation callback run before model-session activation.
        """
        self._model: GroupedKeysModel | None = model
        self._group_id = group_id
        self._preview: GradientPreview | None = preview
        self._content: ColorGradientWidget | None = None
        self._session_started = False
        super().__init__(
            title=f"{property_name} - Gradient Editor" if property_name else "Gradient Editor",
            context_name=context_name,
            pre_open_fn=pre_open_fn,
        )

    def _build_content(self) -> None:
        """Start this opening's session and create its editing controls."""
        model = self._model
        self._session_started = True
        model.begin_session()
        if self._closing:
            return
        self._content = ColorGradientWidget(
            model, self._group_id, self._preview, child_popup_dismissed_fn=self._on_child_popup_dismissed
        )
        self._content.build_editor()

    def _on_outside_click(self) -> None:
        """Let an open child handle its input before deciding whether to dismiss the editor."""
        if self._content is None or not self._content.child_popup_active:
            super()._on_outside_click()

    def _on_child_popup_dismissed(self) -> None:
        """Close after child dismissal unless the click returned to this editor."""
        if self.is_open and not self.focused:
            self.close()

    def _release_content(self) -> None:
        """Release controls and this opening's session, preserving borrowed data."""
        content, self._content = self._content, None
        model, self._model = self._model, None
        session_started, self._session_started = self._session_started, False
        self._preview = None
        try:
            if content is not None:
                content.destroy()
        finally:
            if session_started and model is not None:
                model.finish_session()


class ColorGradientField(AbstractField["_PropertyWidgetItem"]):
    """Display an inline Gradient preview that launches independent disposable editors."""

    HEIGHT = GRADIENT_BAR_HEIGHT

    def __init__(
        self,
        model: GroupedKeysModel,
        group_id: str,
        default_color: Color4 | None = None,
        read_only: bool = False,
        time_range: tuple[float, float] = (0.0, 1.0),
        title: str = "",
        *,
        context_name: str | None = None,
        identifier: str | None = None,
        pre_open_fn: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        """Create a field delegate for grouped-key color gradients.

        Args:
            model: Grouped-key model that stores the gradient payload.
            group_id: Group id to edit in ``model``.
            default_color: Optional solid color when no keyframes are present.
            read_only: Whether to disable edit interactions.
            time_range: Time bounds for keyframe placement.
            title: Optional popup title prefix.
            context_name: USD context whose selection changes dismiss the editor, or None for non-USD content.
            identifier: Optional native frame identifier for UI lookup.
            pre_open_fn: Optional preparation callback run before starting the model session.
        """
        super().__init__(identifier=identifier)
        resolved_default_color = default_color if default_color is not None else DEFAULT_GRADIENT_COLOR
        self._model: GroupedKeysModel | None = model
        self._group_id = group_id
        self._read_only = read_only
        self._title = title
        self._context_name = context_name
        self._pre_open_fn = pre_open_fn
        self._destroyed = False
        self._outer_container: ui.VStack | None = None
        self._preview: GradientPreview | None = GradientPreview(resolved_default_color, time_range)
        self._on_model_changed(group_id)
        self._model_subscription = model.subscribe(self._on_model_changed)

    def build_ui(self, item: _PropertyWidgetItem | None, **kwargs: Any) -> list[ui.Widget]:
        """Build the color-gradient widget for the value column.

        Args:
            item: Unused property tree item; the supplied model owns this field's data.
            **kwargs: Additional UI options forwarded by the delegate.

        Returns:
            Built UI widgets for this field.
        """
        widgets: list[ui.Widget] = []
        if self._destroyed:
            return widgets

        frame = ui.Frame(identifier=self.identifier or "")
        with frame:
            with ui.HStack(height=ui.Pixel(self.HEIGHT)):
                ui.Spacer(width=ui.Pixel(_FIELD_LEFT_PADDING))
                gradient_container = ui.VStack(spacing=0, **kwargs)
                self._outer_container = gradient_container
                with gradient_container:
                    ui.Spacer(height=ui.Pixel(GRADIENT_BAR_PADDING))
                    with ui.HStack(spacing=0):
                        with ui.ZStack(
                            width=ui.Fraction(1),
                            tooltip="Click to open the gradient editor"
                            if not self._read_only
                            else "The attribute is read-only",
                        ):
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
                            ui.Rectangle(
                                name="ColorGradientBarOverlay",
                                mouse_released_fn=self._on_inline_bar_released if not self._read_only else None,
                            )
                    ui.Spacer(height=ui.Pixel(GRADIENT_BAR_PADDING))
        widgets.append(frame)

        return widgets

    def destroy(self) -> None:
        """Disable this launcher and release its references without affecting an open editor."""
        if self._destroyed:
            return
        self._destroyed = True
        self._model_subscription = None
        self._outer_container = None
        self._model = None
        self._preview = None
        self._pre_open_fn = None

    def _on_model_changed(self, group_id: str) -> None:
        """Refresh the inline preview when its model group changes."""
        if self._destroyed or group_id != self._group_id:
            return
        self._preview.render(normalize_gradient_keyframes(keyframes_from_payload(self._model.get_payload(group_id))))

    def _on_inline_bar_released(self, _x: float, _y: float, button: int, _modifier: int) -> None:
        """Launch a fresh editor using the inline preview's current bounds."""
        if button != 0 or self._destroyed or self._read_only or self._outer_container is None:
            return
        width = self._outer_container.computed_width
        editor = GradientFieldEditor(
            model=self._model,
            group_id=self._group_id,
            preview=self._preview,
            property_name=self._title,
            context_name=self._context_name,
            pre_open_fn=self._pre_open_fn,
        )
        editor.open(
            preferred_size=(max(width + 2 * GRADIENT_MARKER_SIZE, _EDITOR_MINIMUM_WIDTH), _EDITOR_HEIGHT),
            anchor_rect=(
                self._outer_container.screen_position_x,
                self._outer_container.screen_position_y,
                width,
                self._outer_container.computed_height,
            ),
        )

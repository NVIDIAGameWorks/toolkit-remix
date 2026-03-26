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

__all__ = ("ColorGradientField",)

from collections.abc import Callable

import carb
import omni.ui as ui
from omni.flux.utils.widget.color_gradient import ColorGradientWidget

from ..base import AbstractField

_FIELD_LEFT_PADDING = 8  # px gap between the field edge and the gradient bar


class ColorGradientField(AbstractField):
    """Property-panel delegate that displays a color gradient editor.

    Receives keyframes and callbacks at construction time; all attribute
    reads/writes are handled by the caller via the provided callbacks.
    """

    def __init__(
        self,
        keyframes: list | None = None,
        on_gradient_changed_fn: Callable | None = None,
        get_keyframes_fn: Callable | None = None,  # () -> list, for external refresh
        default_color: tuple | None = None,
        read_only: bool = False,
        time_range: tuple = (0.0, 1.0),
        style_name: str = "ColorGradientField",
        title: str = "",
    ):
        super().__init__(style_name=style_name)
        self._keyframes = keyframes or []
        self._on_gradient_changed_fn = on_gradient_changed_fn
        self._get_keyframes_fn = get_keyframes_fn
        self._default_color = default_color
        self._read_only = read_only
        self._time_range = time_range
        self._title = title
        self._gradient_widget: ColorGradientWidget | None = None
        self._value_model_sub = None
        self._ignore_model_change: int = 0

    # ------------------------------------------------------------------
    # AbstractField interface
    # ------------------------------------------------------------------

    def build_ui(self, item, **kwargs) -> list[ui.Widget]:
        widgets: list[ui.Widget] = []
        gradient_kwargs = {}
        if self._default_color is not None:
            gradient_kwargs["default_color"] = self._default_color
        with ui.HStack(height=ui.Pixel(ColorGradientWidget.HEIGHT)) as container:
            ui.Spacer(width=ui.Pixel(_FIELD_LEFT_PADDING))
            self._gradient_widget = ColorGradientWidget(
                keyframes=self._keyframes,
                read_only=self._read_only,
                on_gradient_changed_fn=self._handle_widget_changed,
                time_range=self._time_range,
                title=self._title,
                **gradient_kwargs,
            )
            self._gradient_widget.subscribe_drag_started_fn(self._on_drag_started)
            self._gradient_widget.subscribe_drag_ended_fn(self._on_drag_ended)
        widgets.append(container)

        if self._get_keyframes_fn:
            value_model = item.value_models[0]
            self._value_model_sub = value_model.subscribe_value_changed_fn(self._on_model_changed)

        return widgets

    # ------------------------------------------------------------------
    # Gradient change handling
    # ------------------------------------------------------------------

    def _handle_widget_changed(self, times, values):
        """Wrapper that suppresses the external-change subscription while writing."""
        if self._on_gradient_changed_fn is None:
            return
        self._ignore_model_change += 1
        try:
            self._on_gradient_changed_fn(times, values)
        finally:
            self._ignore_model_change = max(0, self._ignore_model_change - 1)

    def _on_drag_started(self) -> None:
        """Suppress external model-change refreshes for the duration of a drag."""
        self._ignore_model_change += 1

    def _on_drag_ended(self) -> None:
        """Restore external model-change refreshes after a drag completes."""
        self._ignore_model_change = max(0, self._ignore_model_change - 1)

    # ------------------------------------------------------------------
    # External change handling
    # ------------------------------------------------------------------

    def _on_model_changed(self, _model):
        """Refresh the widget when the external model reports a change."""
        if self._ignore_model_change > 0 or not self._gradient_widget or not self._get_keyframes_fn:
            return
        try:
            keyframes = self._get_keyframes_fn()
            self._gradient_widget.set_keyframes(keyframes)
        except (AttributeError, RuntimeError) as e:
            carb.log_error(f"Failed to refresh gradient widget: {e}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def destroy(self):
        """Release subscriptions and child widget resources."""
        self._value_model_sub = None
        if self._gradient_widget is not None:
            self._gradient_widget.destroy()
            self._gradient_widget = None
        self._on_gradient_changed_fn = None
        self._get_keyframes_fn = None

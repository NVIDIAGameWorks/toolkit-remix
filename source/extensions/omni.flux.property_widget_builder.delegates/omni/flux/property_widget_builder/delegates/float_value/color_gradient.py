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

from typing import TYPE_CHECKING, Any

import omni.ui as ui
from omni.flux.utils.widget import ColorGradientWidget, GroupedKeysModel

from ..base import AbstractField

if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item as _PropertyWidgetItem

_FIELD_LEFT_PADDING = 8  # px gap between the field edge and the gradient bar
Color4 = tuple[float, float, float, float]


class ColorGradientField(AbstractField["_PropertyWidgetItem"]):
    """Property-panel delegate that displays a color gradient editor.

    Receives a grouped-key model; all persistence is handled by that model.
    """

    def __init__(
        self,
        model: GroupedKeysModel,
        group_id: str,
        default_color: Color4 | None = None,
        read_only: bool = False,
        time_range: tuple[float, float] = (0.0, 1.0),
        style_name: str = "ColorGradientField",
        title: str = "",
    ) -> None:
        """Create a field delegate for grouped-key color gradients.

        Args:
            model: Grouped-key model that stores the gradient payload.
            group_id: Group id to edit in ``model``.
            default_color: Optional solid color when no keyframes are present.
            read_only: Whether to disable edit interactions.
            time_range: Time bounds for keyframe placement.
            style_name: UI style name for the field.
            title: Optional popup title prefix.
        """
        super().__init__(style_name=style_name)
        self._model: GroupedKeysModel | None = model
        self._group_id = group_id
        self._default_color = default_color
        self._read_only = read_only
        self._time_range = time_range
        self._title = title
        self._gradient_widget: ColorGradientWidget | None = None

    def build_ui(self, item: _PropertyWidgetItem, **kwargs: Any) -> list[ui.Widget]:
        """Build the color-gradient widget for the value column.

        Args:
            item: Property tree item that owns this field.
            **kwargs: Additional UI options forwarded by the delegate.

        Returns:
            Built UI widgets for this field.
        """
        widgets: list[ui.Widget] = []
        if self._model is None:
            return widgets

        gradient_kwargs = {}
        if self._default_color is not None:
            gradient_kwargs["default_color"] = self._default_color
        with ui.HStack(height=ui.Pixel(ColorGradientWidget.HEIGHT)) as container:
            ui.Spacer(width=ui.Pixel(_FIELD_LEFT_PADDING))
            self._gradient_widget = ColorGradientWidget(
                model=self._model,
                group_id=self._group_id,
                read_only=self._read_only,
                time_range=self._time_range,
                title=self._title,
                **gradient_kwargs,
            )
        widgets.append(container)

        return widgets

    def destroy(self) -> None:
        """Release subscriptions and child widget resources."""
        if self._gradient_widget is not None:
            self._gradient_widget.destroy()
            self._gradient_widget = None
        self._model = None

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

from collections.abc import Callable
from typing import Any

from omni import ui
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

__all__ = ["NormalMapConventionSelector"]


class NormalMapConventionSelector:
    """Shared batch-level normal map convention control for model and material ingestion."""

    PRESERVE_IMPORTED_LABEL = "Preserve Imported"
    NORMAL_TYPES = (
        _TextureTypes.NORMAL_OGL,
        _TextureTypes.NORMAL_DX,
        _TextureTypes.NORMAL_OTH,
    )
    DEFAULT_TOOLTIP = (
        "Type convention for normal maps.\n\n"
        "The normal map convention to use for this ingestion batch.\n"
        "Generally, the application used to create normal maps will explain the convention used.\n"
        "If selected incorrectly, the normal map when applied in meshes will appear as \n"
        "indentations rather than bumps."
    )

    __DEFAULT_SPACER = ui.Pixel(8)
    __DEFAULT_UI_HEIGHT = ui.Pixel(24)

    def __init__(
        self,
        value: _TextureTypes | str | None = None,
        *,
        include_preserve_imported: bool = False,
        label_width: int | None = None,
        tooltip: str | None = None,
    ):
        """Create the selector with the requested convention selected."""
        if isinstance(value, str):
            value = _TextureTypes[value]

        self._options = (None, *self.NORMAL_TYPES) if include_preserve_imported else self.NORMAL_TYPES
        self._value = value if value is not None or include_preserve_imported else _TextureTypes.NORMAL_OGL
        self._changed = _Event()
        self._field_subscription = None
        self._info_icon = None

        self._frame = ui.Frame()
        with self._frame:
            with ui.HStack(
                height=self.__DEFAULT_UI_HEIGHT,
                spacing=self.__DEFAULT_SPACER,
            ):
                ui.Label(
                    "Normal Map Convention",
                    name="PropertiesWidgetLabel",
                    alignment=ui.Alignment.RIGHT_CENTER if label_width is not None else ui.Alignment.LEFT_CENTER,
                    width=ui.Pixel(label_width) if label_width is not None else 0,
                    identifier="normal_map_convention_label",
                )

                try:
                    selected_index = self._options.index(self._value)
                except ValueError:
                    selected_index = 0

                field = ui.ComboBox(
                    selected_index,
                    *[
                        normal_type.value if normal_type is not None else self.PRESERVE_IMPORTED_LABEL
                        for normal_type in self._options
                    ],
                    identifier="normals_type_combobox",
                )

                with ui.VStack(width=0):
                    ui.Spacer()
                    self._info_icon = _InfoIconWidget(message=tooltip or self.DEFAULT_TOOLTIP)
                    ui.Spacer()

        self._field_subscription = field.model.subscribe_item_changed_fn(self._on_changed)

    @property
    def value(self) -> _TextureTypes | None:
        """Return the selected normal map convention."""
        return self._value

    def subscribe_changed(self, callback: Callable[[_TextureTypes | None], Any]) -> _EventSubscription:
        """Subscribe to convention changes."""
        return _EventSubscription(self._changed, callback)

    def _on_changed(self, model: ui.AbstractItemModel, _):
        selected_index = model.get_item_value_model().get_value_as_int()
        self._value = self._options[selected_index]
        self._changed(self._value)

    def destroy(self):
        """Release UI subscriptions and owned widgets."""
        self._field_subscription = None
        if self._info_icon is not None:
            self._info_icon.destroy()
        self._info_icon = None
        self._frame = None

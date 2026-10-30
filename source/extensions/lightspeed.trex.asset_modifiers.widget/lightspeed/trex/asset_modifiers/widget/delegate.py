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

__all__ = ["ModifierDelegate"]

from omni import ui
from omni.flux.property_widget_builder.delegates import FloatDragFieldGroup, IntDragFieldGroup
from omni.flux.property_widget_builder.model.native import NativeDelegate
from omni.flux.property_widget_builder.widget import FieldBuilder, ItemGroup, claim_each

from .item import ModifierValueItem


class ModifierDelegate(NativeDelegate):
    """Use the ComfyUI workflow panel row height and indentation, and the declared numeric bounds."""

    DEFAULT_IMAGE_ICON_SIZE = ui.Pixel(26)
    _ROW_INDENT = ui.Pixel(32)

    def __init__(self):
        """Add the bounded numeric field builder."""
        super().__init__(
            field_builders=[
                FieldBuilder(
                    claim_func=claim_each(
                        lambda item: (
                            isinstance(item, ModifierValueItem)
                            and item.value_type in (int, float)
                            and (item.modifier_input.min_value is not None or item.modifier_input.max_value is not None)
                        )
                    ),
                    build_func=self._build_bounded_drag,
                    supports_field_cleanup=True,
                    builds_drag_field_group=True,
                )
            ],
            right_aligned_labels=False,
        )

    def build_branch(self, model, item, column_id, level, expanded):
        """Indent input rows like the workflow panel."""
        if column_id == 0 and isinstance(item, ModifierValueItem):
            with ui.HStack(width=self._ROW_INDENT, height=self.DEFAULT_IMAGE_ICON_SIZE):
                ui.Spacer()
            return
        super().build_branch(model, item, column_id, level, expanded)

    def _build_item_widgets(self, model, item, column_id, level, expanded):
        """Leave the value cell of group rows empty."""
        if column_id == 1 and isinstance(item, ItemGroup):
            return None
        return super()._build_item_widgets(model, item, column_id, level, expanded)

    @staticmethod
    def _build_bounded_drag(item: ModifierValueItem, **kwargs) -> list[ui.Widget]:
        """Build the shared numeric drag field with the declared bounds."""
        field_type = FloatDragFieldGroup if item.value_type is float else IntDragFieldGroup
        return field_type(
            min_value=item.modifier_input.min_value,
            max_value=item.modifier_input.max_value,
            identifier=f"AssetModifierInput_{item.modifier_input.name}",
        ).build_ui(item, **kwargs)

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

__all__ = ["ModifierValueItem"]

import enum
from functools import partial

from lightspeed.trex.asset_modifiers.core.settings import AssetModifierSettings
from lightspeed.trex.asset_modifiers.factory import AssetModifierBase, ModifierInput
from omni.flux.property_widget_builder.model.native import NativeChoiceModel, NativeItem
from omni.flux.property_widget_builder.widget import CallbackValueModel
from omni.flux.property_widget_builder.widget.tree.item_model import ItemGroupNameModel


class ModifierValueItem(NativeItem):
    """Show one modifier input with the native property editor for its type."""

    def __init__(self, modifier: type[AssetModifierBase], item: ModifierInput):
        """Create the name and value models of one input row."""
        super().__init__()
        self.modifier_input = item
        settings = AssetModifierSettings()
        value_model = CallbackValueModel(
            item.value_type,
            partial(settings.get_value, modifier, item),
            partial(settings.set_value, modifier, item),
        )
        self._name_models = [ItemGroupNameModel(item.label, tooltip=item.tooltip)]
        self._value_models = [
            NativeChoiceModel(value_model, tuple(item.value_type))
            if issubclass(item.value_type, enum.Enum)
            else value_model
        ]

    @property
    def value_type(self) -> type:
        """Return the Python type that selects the native editor."""
        return self.modifier_input.value_type

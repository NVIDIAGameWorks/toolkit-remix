"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.ui as ui
from omni.flux.property_widget_builder.delegates import ColorGradientField
from omni.flux.property_widget_builder.widget import ClaimResult, FieldBuilder, Item
from pxr import Sdf

from ..grouped_keys_primvar import PropertyGroupedKeysModel
from ..items import _BaseUSDAttributeItem
from ..logical_group_constants import GRADIENT_LOGICAL_GROUP_DEFINITION, GRADIENT_LOGICAL_SUFFIXES
from .base import _generate_identifier

__all__ = ("GRADIENT_FIELD_BUILDERS",)

_PRIMARY_SUFFIX = "values"

_COLOR_ARRAY_TYPES = {
    Sdf.ValueTypeNames.Color3fArray,
    Sdf.ValueTypeNames.Color3dArray,
    Sdf.ValueTypeNames.Color3hArray,
    Sdf.ValueTypeNames.Color4fArray,
    Sdf.ValueTypeNames.Color4dArray,
    Sdf.ValueTypeNames.Color4hArray,
}


def _is_color_array(item: _BaseUSDAttributeItem) -> bool:
    """Check if the item's USD attribute is a color array type."""
    try:
        type_name = Sdf.ValueTypeNames.Find(item.value_models[0].metadata.get(Sdf.PrimSpec.TypeNameKey, ""))
    except (IndexError, AttributeError):
        return False
    return type_name in _COLOR_ARRAY_TYPES


def _claim_gradients(items: list[Item]) -> ClaimResult:
    """Bucket items by base name; satisfy only when both suffixes present and values is a color array.

    Args:
        items: Property-panel items to scan for gradient suffix companions.

    Returns:
        Claim result containing the primary gradient rows and companion rows
        consumed by those primaries.
    """
    groups: dict[str, dict[str, Item]] = {}
    for item in items:
        if not isinstance(item, _BaseUSDAttributeItem):
            continue
        attr_paths = item.attribute_paths
        if not attr_paths:
            continue
        parts = attr_paths[0].name.rsplit(":", 1)
        if len(parts) != 2 or parts[1] not in GRADIENT_LOGICAL_SUFFIXES:
            continue
        if parts[1] == "values" and not _is_color_array(item):
            continue
        groups.setdefault(parts[0], {})[parts[1]] = item

    primary: list[Item] = []
    companions: list[Item] = []
    for collected in groups.values():
        if collected.keys() < GRADIENT_LOGICAL_SUFFIXES:
            continue
        logical_group_items = [collected[suffix] for suffix in sorted(GRADIENT_LOGICAL_SUFFIXES)]
        collected[_PRIMARY_SUFFIX].logical_group_items = logical_group_items
        collected[_PRIMARY_SUFFIX].logical_group_definition = GRADIENT_LOGICAL_GROUP_DEFINITION
        for suffix, item in collected.items():
            (primary if suffix == _PRIMARY_SUFFIX else companions).append(item)

    return ClaimResult(primary=primary, companions=companions)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _gradient_builder(item: Item) -> list[ui.Widget] | None:
    """Build USD-backed color gradient controls for the primary gradient item.

    Args:
        item: Primary gradient item claimed by ``_claim_gradients``.
    Returns:
        Gradient controls for the value column, or ``None`` when unavailable.
    """
    identifier = _generate_identifier(item)
    if not item.attribute_paths:
        return None

    model = PropertyGroupedKeysModel.from_item(item)
    display_name = item.name_models[0].get_value_as_string() if item.name_models else ""
    field = ColorGradientField(
        model=model,
        group_id=model.group_ids[0],
        context_name=item.context_name,
        pre_open_fn=item.pre_open_callback,
        title=display_name or model.group_ids[0],
        identifier=identifier,
    )
    return field.build_ui(item)


GRADIENT_FIELD_BUILDERS = [
    FieldBuilder(claim_func=_claim_gradients, build_func=_gradient_builder),
]

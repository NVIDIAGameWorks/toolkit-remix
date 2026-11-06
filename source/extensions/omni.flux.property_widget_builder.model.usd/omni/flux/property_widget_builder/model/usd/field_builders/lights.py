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

__all__ = ("LIGHT_FIELD_BUILDERS",)

import omni.ui as ui
from omni.flux.property_widget_builder.delegates.float_value.drag import FloatDragFieldGroup
from omni.flux.property_widget_builder.widget import FieldBuilder
from omni.flux.utils.common.lights import LightTypes, get_light_type
from omni.flux.utils.common.types import ScalarValue

from ..items import USDAttributeItem
from .base import USDBuilderList, _generate_identifier

_DEFAULT_LIGHT_FIELD_CONFIG = {
    "inputs:colorTemperature": {
        "min_value": 2500.0,
        "max_value": 8500.0,
    },
    "inputs:exposure": {
        "hard_min_value": 0.0,
        "max_value": 10.0,
    },
    "inputs:intensity": {
        "hard_min_value": 0.0,
        "max_value": 65000.0,
        "step": 0.5,
    },
    "inputs:radius": {
        "hard_min_value": 0.0,
        "max_value": 65000.0,
        "step": 0.1,
    },
    "inputs:shaping:cone:angle": {
        "hard_min_value": 0.0,
        "hard_max_value": 360.0,
    },
    "inputs:shaping:cone:softness": {
        "hard_min_value": 0.0,
        "max_value": 10.0,
    },
    "inputs:shaping:focus": {
        "hard_min_value": 0.0,
        "max_value": 10.0,
    },
    "inputs:volumetric_radiance_scale": {
        "hard_min_value": 0.0,
        "max_value": 10.0,
    },
}
_LIGHT_FIELD_OVERRIDES = {
    LightTypes.DistantLight: {
        "inputs:intensity": {"step": 0.1},
    },
}


def _get_light_field_config(item: USDAttributeItem) -> dict[str, ScalarValue]:
    """Resolve an independent field configuration for the selected light attributes."""
    attribute_name = item.attribute_paths[0].name
    config = _DEFAULT_LIGHT_FIELD_CONFIG[attribute_name].copy()
    if "step" not in config:
        return config

    metadata_step = item.get_step_value()
    if metadata_step is not None:
        config["step"] = metadata_step
        return config

    selected_steps = []
    for attribute in item.get_all_attributes():
        light_type = get_light_type(attribute.GetPrim())
        type_overrides = _LIGHT_FIELD_OVERRIDES.get(light_type, {})
        field_overrides = type_overrides.get(attribute_name, {})
        selected_steps.append(field_overrides.get("step", config["step"]))
    # Match the bounds adapter's coarsest-step policy for mixed selections.
    config["step"] = max(selected_steps, default=config["step"])
    return config


def _light_drag_builder(
    item: USDAttributeItem, *, register_cleanup=None, linked_edit_coordinator=None
) -> list[ui.Widget]:
    """Build an independent light field with metadata or light-type drag sensitivity."""
    config = _get_light_field_config(item)
    builder = FloatDragFieldGroup(**config, identifier=_generate_identifier(item))
    return builder(item, register_cleanup=register_cleanup, linked_edit_coordinator=linked_edit_coordinator)


LIGHT_FIELD_BUILDERS = USDBuilderList()


for _attribute_name in _DEFAULT_LIGHT_FIELD_CONFIG:
    LIGHT_FIELD_BUILDERS.append(
        FieldBuilder(
            claim_func=LIGHT_FIELD_BUILDERS.claim_by_name(_attribute_name),
            build_func=_light_drag_builder,
            supports_field_cleanup=True,
            builds_drag_field_group=True,
        )
    )
